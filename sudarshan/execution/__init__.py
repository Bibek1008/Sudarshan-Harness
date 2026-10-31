"""Execution architecture: provider-independent command and file backends.

Backends share a structured result contract so the agent loop can remain
unaware of whether a tool ran locally, through SSH, or in a container.
"""

from .base import (
    BackendUnavailable,
    ExecutionBackend,
    ExecutionError,
    ExecutionPermissionError,
    ExecutionRegistry,
    ExecutionResult,
    ExecutionTimeout,
    backend_tools,
)

__all__ = [
    "BackendUnavailable",
    "ExecutionBackend",
    "ExecutionError",
    "ExecutionPermissionError",
    "ExecutionRegistry",
    "ExecutionResult",
    "ExecutionTimeout",
    "backend_tools",
]
