"""Execution architecture: Docker-backed, deliberately constrained commands.

Docker adds an isolation boundary but is not a complete security guarantee:
kernel vulnerabilities, daemon policy, and writable bind mounts still matter.
This backend never falls back to host execution; without Docker it raises a
clear availability error instead of misrepresenting local subprocesses as safe.
"""

import fnmatch
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath

from .base import (
    BackendUnavailable,
    ExecutionBackend,
    ExecutionError,
    ExecutionPermissionError,
    ExecutionResult,
    ExecutionTimeout,
)


class SandboxedExecutionBackend(ExecutionBackend):
    """Run Docker commands with an isolated root and one writable workspace mount."""

    name = "sandbox"

    def __init__(
        self,
        workdir: str | Path,
        image: str = "python:3.12-slim",
        container_workdir: str = "/workspace",
        memory: str = "512m",
        cpus: str = "1.0",
        user: str | None = "1000:1000",
        docker_executable: str = "docker",
    ) -> None:
        """Configure a non-privileged, network-disabled Docker execution boundary."""
        self.root = Path(workdir).expanduser().resolve()
        if not self.root.is_dir():
            raise ExecutionError(f"sandbox workspace does not exist: {self.root}")
        if not container_workdir.startswith("/") or "\x00" in container_workdir:
            raise ValueError("container workdir must be an absolute, non-NUL path")
        self.image = image
        self.container_workdir = container_workdir.rstrip("/") or "/"
        self.memory = memory
        self.cpus = cpus
        self.user = user
        self.docker_executable = docker_executable

    def execute(self, command: str, timeout: float = 120) -> ExecutionResult:
        """Run a command inside Docker; Docker absence never executes it locally."""
        return self._docker(command, timeout)

    def read_file(self, path: str) -> ExecutionResult:
        """Read a workspace-relative file from inside the selected container image."""
        relative = self._relative(path)
        return self.execute(f"cat -- {shlex.quote(relative)}")

    def write_file(self, path: str, content: str) -> ExecutionResult:
        """Write a validated workspace-relative file through the container mount."""
        relative = self._relative(path)
        parent = str(PurePosixPath(relative).parent)
        command = (
            f"mkdir -p -- {shlex.quote(parent)} && "
            f"printf %s {shlex.quote(content)} > {shlex.quote(relative)} && "
            f"printf %s {shlex.quote(f'Wrote {len(content)} chars to {path}')}"
        )
        return self.execute(command)

    def list_files(self, pattern: str = "**/*") -> ExecutionResult:
        """List container-visible workspace files, filtering their relative paths locally."""
        result = self.execute("find . -type f -print")
        if result.exit_code != 0:
            return result
        paths = [line.removeprefix("./") for line in result.stdout.splitlines()]
        matches = [path for path in paths if _matches(path, pattern)]
        return ExecutionResult(
            "\n".join(sorted(matches)), result.stderr, result.exit_code,
            result.execution_backend, result.execution_time, result.error,
        )

    def _docker(self, command: str, timeout: float) -> ExecutionResult:
        """Invoke Docker with fixed hardening flags and captured process results."""
        executable = shutil.which(self.docker_executable)
        if executable is None:
            raise BackendUnavailable(f"Docker executable {self.docker_executable!r} is unavailable")
        mount = f"type=bind,src={self.root},dst={self.container_workdir},rw"
        container_name = 'sudarshan-' + uuid.uuid4().hex
        arguments = [
            executable, "run", "--rm",
            "--name", container_name,
            "--network", "none",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--memory", self.memory,
            "--cpus", self.cpus,
            "--mount", mount,
            "--workdir", self.container_workdir,
        ]
        if self.user:
            arguments.extend(["--user", self.user])
        arguments.extend([self.image, "sh", "-lc", command])
        started = time.perf_counter()
        try:
            completed = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            # Killing the Docker client does not stop its container. Remove our exact name.
            try:
                cleanup = subprocess.run([executable, 'rm', '-f', container_name],
                                         capture_output=True, text=True, timeout=15)
                if cleanup.returncode and 'No such container' not in cleanup.stderr:
                    raise ExecutionError(f'container cleanup failed: {container_name}')
            except (OSError, subprocess.TimeoutExpired, ExecutionError):
                raise ExecutionTimeout(f'sandbox timed out after {timeout}s; cleanup unconfirmed for {container_name}') from error
            raise ExecutionTimeout(f"sandbox command timed out after {timeout}s; container removed") from error
        except OSError as error:
            raise BackendUnavailable(f"could not run Docker: {error}") from error
        elapsed = time.perf_counter() - started
        error = None if completed.returncode == 0 else f"container exited with {completed.returncode}"
        return ExecutionResult(completed.stdout, completed.stderr, completed.returncode, self.name, elapsed, error)

    def _relative(self, path: str) -> str:
        """Resolve one host mount path and reject traversal or symlink escapes."""
        target = (self.root / Path(path)).resolve()
        try:
            return target.relative_to(self.root).as_posix()
        except ValueError as error:
            raise ExecutionPermissionError(
                f"{path!r} escapes the sandbox working directory"
            ) from error


def createSandboxedBashOps(workdir: str | Path, **options: object) -> SandboxedExecutionBackend:
    """Create Docker-backed sandbox operations; options map to the backend constructor."""
    return SandboxedExecutionBackend(workdir, **options)


def _matches(path: str, pattern: str) -> bool:
    """Match a list result against either a relative path or its basename."""
    return pattern == "**/*" or fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern)
