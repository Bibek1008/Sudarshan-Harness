"""Day 2: a small, explicit approval policy for harness tools.

Policy checks are deterministic and run before tool execution.  A short list
of destructive shell forms is never delegated, read tools remain frictionless,
and every other effect requires the mode's stated authority.
"""

import re
from typing import Any, Callable


READ_TOOLS = {"read_file", "list_files", "grep"}
DENY_PATTERNS = (
    r"\brm\s+(?:-[^\s]*[rf][^\s]*\s+)+(?:/|~(?:/)?|\$HOME(?:/)?)(?:\s|$)",
    r"\bsudo\b",
    r"\bmkfs(?:\.\w+)?\b|\bdd\s+[^\n]*\bif=",
    r"\bcurl\b[^|]*\|\s*(?:sh|bash)\b",
    r"\bgit\s+push\b[^\n]*\s--force(?:\S*)",
    r"(?:>|>>)\s*/dev/sd[a-z]",
)


class Policy:
    """Decide whether a neutral tool call may execute in a named safety mode.

    ``read-only`` permits only the named read tools.  ``safe`` asks its
    approver before every effect, and ``yolo`` permits effects but never the
    small set of permanently denied shell commands.
    """

    def __init__(
        self,
        mode: str = "safe",
        approver: Callable[[dict[str, Any], str], bool] | None = None,
    ) -> None:
        """Create a policy; absent approvers conservatively decline requests.

        Raises:
            ValueError: If ``mode`` is not one of the three supported modes.
        """
        if mode not in {"read-only", "safe", "yolo"}:
            raise ValueError("mode must be 'read-only', 'safe', or 'yolo'")
        self.mode = mode
        self.approver = approver or (lambda call, reason: False)

    def check(self, call: dict[str, Any]) -> str | None:
        """Allow a call with ``None`` or return the reason it must be blocked.

        Permanent bash denials deliberately precede the mode decision, so
        neither automatic approval nor ``yolo`` can bypass them.  Execution
        adapters may prefix a backend name, but retain the same logical policy.
        """
        name = _logical_tool_name(call["name"])
        command = str(call.get("args", {}).get("command", ""))
        if name == "bash" and any(re.search(pattern, command) for pattern in DENY_PATTERNS):
            return "dangerous bash command is never allowed"
        if name in READ_TOOLS or self.mode == "yolo":
            return None
        if self.mode == "read-only":
            return "read-only mode allows only read tools"
        reason = f"{name} may modify files or run commands"
        if self.approver(call, reason):
            return None
        return "approval was declined"


def _logical_tool_name(name: str) -> str:
    """Normalize registered backend tool names without changing Policy's API."""
    actions = READ_TOOLS | {"bash", "write_file"}
    for action in actions:
        if name == action or name.endswith(f"_{action}"):
            return action
    return name
