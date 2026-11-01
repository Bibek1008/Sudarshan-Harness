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
from .process import run_owned, validate_timeout, trusted_executable
from .filesystem import parts_for
from ..redaction import redact
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
        if not image or image.startswith('-') or any(c.isspace() for c in image):
            raise ValueError("container image must be a non-option image name")
        if not user or user.split(':', 1)[0] in {'0', 'root'}:
            raise ValueError("sandbox requires an explicit non-root user")
        if ',' in str(self.root) or ',' in container_workdir:
            raise ValueError("workspace mount paths cannot contain commas")
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
        timeout = validate_timeout(timeout)
        executable = trusted_executable(self.docker_executable, self.root)
        if executable is None:
            raise BackendUnavailable(f"Docker executable {self.docker_executable!r} is unavailable")
        mount = f"type=bind,src={self.root},dst={self.container_workdir},rw"
        container_name = 'sudarshan-' + uuid.uuid4().hex
        arguments = [
            executable, "run", "--rm",
            "--name", container_name,
            "--network", "none",
            "--pids-limit", "64",
            "--init",
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
        arguments.extend([self.image, "sh", "-c", command])
        started = time.perf_counter()
        try:
            completed = run_owned(arguments, timeout=timeout)
        except BaseException as error:
            # A client timeout/interruption does not stop a daemon-owned container.
            try:
                cleanup = run_owned([executable, "rm", "-f", container_name], timeout=15)
                cleaned = not cleanup.returncode or "No such container" in cleanup.stderr
            except BaseException:
                cleaned = False
            if not cleaned and isinstance(error, ExecutionTimeout):
                raise ExecutionTimeout(f"sandbox timed out after {timeout}s; cleanup unconfirmed for {container_name}") from None
            if not cleaned:
                raise ExecutionError(f"sandbox cleanup unconfirmed for {container_name}") from None
            if isinstance(error, ExecutionTimeout):
                raise ExecutionTimeout(f"sandbox command timed out after {timeout}s; container removed") from None
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise BackendUnavailable("could not run Docker; container cleanup attempted") from None
        elapsed = time.perf_counter() - started
        error = None if completed.returncode == 0 else f"container exited with {completed.returncode}"
        if completed.returncode:
            try:
                cleanup = run_owned([executable, "rm", "-f", container_name], timeout=15)
                cleaned = not cleanup.returncode or "No such container" in cleanup.stderr
            except Exception:
                cleaned = False
            error += "; cleanup confirmed" if cleaned else "; cleanup unconfirmed"
        return ExecutionResult(completed.stdout, completed.stderr, completed.returncode, self.name, elapsed, error)

    def _relative(self, path: str) -> str:
        """Resolve one host mount path and reject traversal or symlink escapes."""
        parts_for(path)
        target = (self.root / Path(path)).resolve()
        try:
            return target.relative_to(self.root).as_posix()
        except ValueError as error:
            raise ExecutionPermissionError(
                f"{path!r} escapes the sandbox working directory"
            ) from None


def createSandboxedBashOps(workdir: str | Path, **options: object) -> SandboxedExecutionBackend:
    """Create Docker-backed sandbox operations; options map to the backend constructor."""
    return SandboxedExecutionBackend(workdir, **options)


def _matches(path: str, pattern: str) -> bool:
    """Match a list result against either a relative path or its basename."""
    return pattern == "**/*" or fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern)
