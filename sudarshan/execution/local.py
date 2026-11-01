"""Execution architecture: a path-confined local subprocess backend.

This module treats the workspace root as a capability boundary: every file
path resolves through one validator, including symlink targets.  Commands are
ordinary local subprocesses, not a sandbox, and receive a minimal environment
so common API-key variables are not exposed to child processes.
"""

import fnmatch
import os
import subprocess
import time
from pathlib import Path

from ..environment import safe_shell_environment
from .filesystem import WorkspaceFiles
from .process import run_owned

from .base import (
    ExecutionBackend,
    ExecutionError,
    ExecutionPermissionError,
    ExecutionResult,
    ExecutionTimeout,
)


IGNORED_DIRECTORIES = {".git", "node_modules", "__pycache__", ".venv"}
OUTPUT_LIMIT = 12000


class LocalExecutionBackend(ExecutionBackend):
    """Execute commands and files inside one resolved local workspace root."""

    name = "local"

    def __init__(self, workdir: str | Path) -> None:
        """Bind the backend to an existing local directory."""
        self.root = Path(workdir).expanduser().resolve()
        if not self.root.is_dir():
            raise ExecutionError(f"local workspace does not exist: {self.root}")
        self.files = WorkspaceFiles(self.root)

    def execute(self, command: str, timeout: float = 120) -> ExecutionResult:
        """Run ``command`` in the workspace and return captured process details."""
        started = time.perf_counter()
        try:
            completed = run_owned(command, shell=True, cwd=self.root, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise ExecutionTimeout(f"local command timed out after {timeout}s") from None
        except OSError as error:
            raise ExecutionError("could not start local command") from None
        elapsed = time.perf_counter() - started
        error = None if completed.returncode == 0 else f"command exited with {completed.returncode}"
        return ExecutionResult(
            _truncate(completed.stdout),
            _truncate(completed.stderr),
            completed.returncode,
            self.name,
            elapsed,
            error,
        )

    def read_file(self, path: str) -> ExecutionResult:
        """Read a UTF-8 text file after validating its resolved target path."""
        started = time.perf_counter()
        self._path(path)
        try:
            content = self.files.read_text(path)
        except PermissionError as error:
            raise ExecutionPermissionError("local file permission denied") from None
        except OSError as error:
            raise ExecutionError(f"could not read {path!r}") from None
        return self._result(content, "", 0, started)

    def write_file(self, path: str, content: str) -> ExecutionResult:
        """Write UTF-8 text after validating the target and its parent path."""
        started = time.perf_counter()
        self._path(path)
        try:
            self.files.write_text(path, content)
        except PermissionError as error:
            raise ExecutionPermissionError("local file permission denied") from None
        except OSError as error:
            raise ExecutionError(f"could not write {path!r}") from None
        return self._result(f"Wrote {len(content)} chars to {path}", "", 0, started)

    def list_files(self, pattern: str = "**/*") -> ExecutionResult:
        """List matching regular files without traversing ignored or escaped trees."""
        started = time.perf_counter()
        matches: list[str] = []
        for directory, names, files in os.walk(self.root, followlinks=False):
            names[:] = [name for name in names if name not in IGNORED_DIRECTORIES
                        and not Path(directory, name).is_symlink()
                        and not getattr(Path(directory, name), "is_junction", lambda: False)()]
            for name in files:
                candidate = Path(directory, name)
                relative = candidate.relative_to(self.root).as_posix()
                if not _matches(relative, name, pattern):
                    continue
                try:
                    self._path(relative)
                except ExecutionPermissionError:
                    continue
                matches.append(relative)
        return self._result("\n".join(sorted(matches)), "", 0, started)

    def _path(self, path: str) -> Path:
        """Resolve a supplied path and reject traversal and symlink escapes."""
        candidate = Path(path)
        target = (self.root / candidate).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as error:
            raise ExecutionPermissionError(
                f"{path!r} escapes the local working directory"
            ) from None
        return target

    def _result(self, stdout: str, stderr: str, code: int, started: float) -> ExecutionResult:
        """Build a successful local result with a consistent elapsed-time value."""
        return ExecutionResult(
            _truncate(stdout), _truncate(stderr), code, self.name,
            time.perf_counter() - started,
        )


def createLocalBashOperations(workdir: str | Path) -> LocalExecutionBackend:
    """Create local command operations rooted at ``workdir``."""
    return LocalExecutionBackend(workdir)


def createLocalReadOperations(workdir: str | Path) -> LocalExecutionBackend:
    """Create local file operations rooted at ``workdir``."""
    return LocalExecutionBackend(workdir)


def _matches(relative: str, name: str, pattern: str) -> bool:
    """Match a glob against both a workspace-relative path and its basename."""
    return pattern == "**/*" or fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern)


def _truncate(text: str) -> str:
    """Bound captured output while preserving both its beginning and its end."""
    if len(text) <= OUTPUT_LIMIT:
        return text
    half = OUTPUT_LIMIT // 2
    return text[:half] + "\n... output truncated ...\n" + text[-half:]


def _safe_environment() -> dict[str, str]:
    """Return only OS runtime variables needed by ordinary local commands."""
    return safe_shell_environment()
