"""Execution architecture: SSH operations with remote workspace validation.

SSH is invoked as an argument list with strict host-key verification and no
password handling.  File operations run a small quoted Python helper remotely,
where paths are resolved against the remote root rather than trusted locally.
"""

import inspect
from .filesystem import WorkspaceFiles, parts_for, FILE_LIMIT

import shlex
import re
import subprocess
import time
from .process import run_owned, validate_timeout, trusted_executable
from pathlib import Path

from .base import BackendUnavailable, ExecutionBackend, ExecutionError, ExecutionResult, ExecutionTimeout


# Send the same audited file primitive rather than maintaining a weaker copy.
REMOTE_FILE_HELPER = "\n".join([
    "import os, sys, stat, fnmatch",
    "from pathlib import Path, PureWindowsPath",
    "from contextlib import contextmanager",
    "ExecutionPermissionError = PermissionError",
    f"FILE_LIMIT = {FILE_LIMIT}",
    inspect.getsource(parts_for),
    inspect.getsource(WorkspaceFiles),
    r'''
root = Path(sys.argv[1]).resolve()
files = WorkspaceFiles(root)
action = sys.argv[2]
path = sys.argv[3] if len(sys.argv) > 3 else ""
if action == "read":
    print(files.read_text(path), end="")
elif action == "write":
    files.write_text(path, sys.argv[4])
    print("File written")
elif action == "list":
    matches = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = [name for name in names if name not in {".git", "node_modules", "__pycache__", ".venv"}
                    and not Path(directory, name).is_symlink()
                    and not getattr(Path(directory, name), "is_junction", lambda: False)()]
        for name in filenames:
            relative = Path(directory, name).relative_to(root).as_posix()
            if path == "**/*" or fnmatch.fnmatch(relative, path) or fnmatch.fnmatch(name, path):
                try:
                    with files.open(relative):
                        pass
                except (OSError, PermissionError):
                    continue
                matches.append(relative)
    print("\n".join(sorted(matches)))
else:
    raise ValueError("unknown remote file action")
'''.strip(),
])



class RemoteExecutionBackend(ExecutionBackend):
    """Run commands and file helpers on an SSH host with a remote workspace."""

    name = "ssh"

    def __init__(
        self,
        host: str,
        username: str | None = None,
        port: int = 22,
        identity_file: str | Path | None = None,
        workdir: str = ".",
        ssh_executable: str = "ssh",
        remote_python: str = "python3",
    ) -> None:
        """Configure key or agent authenticated SSH operations for one host."""
        self.host = _connection_value(host, "host")
        self.username = _connection_value(username, "username") if username else None
        if not 1 <= int(port) <= 65535:
            raise ValueError("SSH port must be between 1 and 65535")
        self.port = int(port)
        self.identity_file = str(identity_file) if identity_file is not None else None
        self.workdir = workdir
        self.ssh_executable = ssh_executable
        self.remote_python = _connection_value(remote_python, "remote Python executable")

    def execute(self, command: str, timeout: float = 120) -> ExecutionResult:
        """Execute a policy-approved command after safely changing to remote root."""
        remote = f"cd -- {shlex.quote(self.workdir)} && exec /usr/bin/env -i PATH=/usr/bin:/bin /bin/sh -c {shlex.quote(command)}"
        return self._ssh(remote, timeout)

    def read_file(self, path: str) -> ExecutionResult:
        """Read a remotely validated workspace-relative text file."""
        return self._file_operation("read", path)

    def write_file(self, path: str, content: str) -> ExecutionResult:
        """Write a remotely validated workspace-relative text file."""
        return self._file_operation("write", path, content)

    def list_files(self, pattern: str = "**/*") -> ExecutionResult:
        """List remotely validated workspace files matching a glob."""
        return self._file_operation("list", pattern)

    def _file_operation(self, action: str, path: str, content: str | None = None) -> ExecutionResult:
        """Run the remote validator helper with every dynamic argument quoted."""
        arguments = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", self.remote_python, "-c", REMOTE_FILE_HELPER, self.workdir, action, path]
        if content is not None:
            arguments.append(content)
        remote = " ".join(shlex.quote(argument) for argument in arguments)
        return self._ssh(remote, 120)

    def _ssh(self, remote_command: str, timeout: float) -> ExecutionResult:
        """Invoke system SSH without disabling any host-key protections."""
        timeout = validate_timeout(timeout)
        executable = trusted_executable(self.ssh_executable, Path.cwd())
        if executable is None:
            raise BackendUnavailable(f"SSH executable {self.ssh_executable!r} is unavailable")
        target = f"{self.username}@{self.host}" if self.username else self.host
        command = [
            executable,
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-p", str(self.port),
        ]
        if self.identity_file:
            command.extend(["-i", self.identity_file])
        command.extend([target, remote_command])
        started = time.perf_counter()
        try:
            completed = run_owned(command, timeout=timeout)
        except (subprocess.TimeoutExpired, ExecutionTimeout) as error:
            raise ExecutionTimeout(f"SSH operation timed out after {timeout}s; remote termination unconfirmed") from None
        except (OSError, ExecutionError) as error:
            raise BackendUnavailable("could not run SSH") from None
        elapsed = time.perf_counter() - started
        error = None if completed.returncode == 0 else _ssh_error(completed.returncode)
        return ExecutionResult(completed.stdout, completed.stderr, completed.returncode, self.name, elapsed, error)


def createRemoteBashOps(host: str, **options: object) -> RemoteExecutionBackend:
    """Create SSH command operations; options map to ``RemoteExecutionBackend``."""
    return RemoteExecutionBackend(host, **options)


def createRemoteReadOps(host: str, **options: object) -> RemoteExecutionBackend:
    """Create SSH file operations; options map to ``RemoteExecutionBackend``."""
    return RemoteExecutionBackend(host, **options)


def _connection_value(value: str, label: str) -> str:
    """Reject control characters and whitespace in SSH connection components."""
    if (not value or value.startswith('-')
            or not re.fullmatch(r'[A-Za-z0-9_./:@%\[\]-]+', value)):
        raise ValueError(f"SSH {label} must be a non-empty single token")
    return value


def _ssh_error(returncode: int) -> str:
    """Describe SSH failures without hiding authentication or host-key problems."""
    if returncode == 255:
        return "SSH authentication, connection, or host-key verification failed"
    return f"SSH command exited with {returncode}"
