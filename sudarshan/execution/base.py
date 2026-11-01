"""Execution architecture: shared results, errors, registry, and tool adapter.

The execution boundary is deliberately independent of models and transcripts.
Backends return the same immutable-shaped result, while this module translates
them into the existing Day 2 ``Tool`` interface without bypassing policy.
"""

from ..redaction import redact

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


class ExecutionError(RuntimeError):
    """Base error for a failed execution operation."""


class ExecutionTimeout(ExecutionError):
    """Raised when a backend cannot finish an operation before its deadline."""


class ExecutionPermissionError(ExecutionError):
    """Raised when an operation would escape a backend's permitted workspace."""


class BackendUnavailable(ExecutionError):
    """Raised when a required execution runtime is not installed or reachable."""


@dataclass(frozen=True)
class ExecutionResult:
    """The backend-neutral record returned by every execution operation.

    ``error`` describes an operation failure without discarding captured output;
    timeout and permission failures use the explicit exceptions above instead.
    ``execution_time`` is measured in seconds by the executing backend.
    """

    stdout: str
    stderr: str
    exit_code: int
    execution_backend: str
    execution_time: float
    error: str | None = None

    def text(self) -> str:
        """Render a readable, transcript-safe representation of this result."""
        output = self.stdout + self.stderr
        if not output:
            output = f"(exit {self.exit_code}, no output)"
        if self.error:
            output = f"{output}\nERROR: {self.error}".strip()
        return redact(f"[{self.execution_backend}, {self.execution_time:.3f}s]\n{output}")


class ExecutionBackend(ABC):
    """Common interface implemented by local, remote, and sandbox backends."""

    name: str

    @abstractmethod
    def execute(self, command: str, timeout: float = 120) -> ExecutionResult:
        """Execute a shell command within this backend's configured workspace."""

    @abstractmethod
    def read_file(self, path: str) -> ExecutionResult:
        """Read a workspace-relative text file."""

    @abstractmethod
    def write_file(self, path: str, content: str) -> ExecutionResult:
        """Write a workspace-relative text file, creating parent directories."""

    @abstractmethod
    def list_files(self, pattern: str = "**/*") -> ExecutionResult:
        """List workspace-relative files matching a glob pattern."""


class ExecutionRegistry:
    """An explicit registry for application-selected execution backends."""

    def __init__(self, default: str | None = None) -> None:
        """Create an empty registry, optionally naming its eventual default."""
        self._backends: dict[str, ExecutionBackend] = {}
        self._default = default

    def register(self, name: str, backend: ExecutionBackend, default: bool = False) -> None:
        """Register ``backend`` under a unique explicit selection name."""
        if not name:
            raise ValueError("backend name must not be empty")
        if name in self._backends:
            raise ValueError(f"backend {name!r} is already registered")
        self._backends[name] = backend
        if default or self._default is None:
            self._default = name

    def get(self, name: str | None = None) -> ExecutionBackend:
        """Return a selected backend, using the configured default when omitted."""
        selected = name or self._default
        if selected is None:
            raise BackendUnavailable("no execution backend has been registered")
        try:
            return self._backends[selected]
        except KeyError as error:
            raise BackendUnavailable(f"execution backend {selected!r} is not registered") from error

    @property
    def default(self) -> str | None:
        """Return the default backend name, if one has been selected."""
        return self._default


def backend_tools(
    backend: ExecutionBackend,
    prefix: str,
    policy: Any | None = None,
) -> list[Any]:
    """Expose a backend through Day 2 ``Tool`` objects.

    Policy checks use canonical operation names before the backend runs.  This
    prevents a prefixed tool such as ``sandbox_bash`` from weakening the hard
    denial rules intended for the original ``bash`` tool.
    """
    from ..tools import Tool

    if not prefix or not prefix.replace("_", "").isalnum():
        raise ValueError("tool prefix must contain only letters, digits, and underscores")

    def invoke(action: str, operation: Callable[..., ExecutionResult], *args: Any) -> str:
        call = {"name": action, "args": _arguments(action, args)}
        if policy is not None:
            reason = policy.check(call)
            if reason is not None:
                return f"BLOCKED: {reason}"
        try:
            return operation(*args).text()
        except ExecutionError as error:
            return f"ERROR: {type(error).__name__}: execution backend failed"

    def make(name: str, description: str, properties: dict[str, str], run: Callable[..., str]) -> Any:
        schema = {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {key: {"type": "string", "description": value}
                               for key, value in properties.items()},
                "required": [key for key in properties if key not in {"timeout", "pattern"}],
            },
        }
        return Tool(name=name, spec={"schema": schema}, run=run, execution_backend=backend.name)

    def bash(command: str, timeout: str = "120") -> str:
        """Run a backend command after its canonical policy check."""
        return invoke("bash", backend.execute, command, float(timeout))

    def read_file(path: str) -> str:
        """Read a backend file after its canonical policy check."""
        return invoke("read_file", backend.read_file, path)

    def write_file(path: str, content: str) -> str:
        """Write a backend file after its canonical policy check."""
        return invoke("write_file", backend.write_file, path, content)

    def list_files(pattern: str = "**/*") -> str:
        """List backend files after its canonical policy check."""
        return invoke("list_files", backend.list_files, pattern)

    return [
        make(f"{prefix}_bash", "Run a command in the selected execution backend.",
             {"command": "Shell command to run.", "timeout": "Timeout in seconds."}, bash),
        make(f"{prefix}_read_file", "Read a file in the selected execution backend.",
             {"path": "Workspace-relative file path."}, read_file),
        make(f"{prefix}_write_file", "Write a file in the selected execution backend.",
             {"path": "Workspace-relative file path.", "content": "Complete file contents."}, write_file),
        make(f"{prefix}_list_files", "List files in the selected execution backend.",
             {"pattern": "Glob for paths or basenames."}, list_files),
    ]


def _arguments(action: str, values: tuple[Any, ...]) -> dict[str, Any]:
    """Map adapter positional values back into the canonical policy call shape."""
    names = {
        "bash": ("command", "timeout"),
        "read_file": ("path",),
        "write_file": ("path", "content"),
        "list_files": ("pattern",),
    }[action]
    return dict(zip(names, values))
