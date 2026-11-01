"""Day 2: a small, explicit approval policy for harness tools.

Policy checks are deterministic and run before tool execution.  A short list
of destructive shell forms is never delegated, read tools remain frictionless,
and every other effect requires the mode's stated authority.
"""

import re
import shlex
import posixpath
from typing import Any, Callable


READ_TOOLS = {"read_file", "list_files", "grep"}
DENY_PATTERNS = (
    r"(?i)\b(?:remove-item|ri|del|erase|rmdir|rd|rm)\b[^\n]*(?:-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?(?=\s|:|$)|/s(?=\s|$))",
    r"(?i)\b(?:format|clear-disk|initialize-disk)\b",
    r"\brm\s+(?:--?[\w-]+\s+)+(?:/\*?|~/?|\$(?:HOME|\{HOME\})/?)(?=\s|[;&|]|$)",
    # Obvious root/home find deletion, including common traversal options.
    r"\bfind\s+(?:(?:-[HLP]|-O\d+)\s+)*(?:/\*?|~/?|\$(?:HOME|\{HOME\})(?:/[^\s;&|]*)?)(?=\s)[^;\n|&]*\s-delete\b",
    r"\bfind\s+(?:(?:-[HLP]|-O\d+)\s+)*(?:/\*?|~/?|\$(?:HOME|\{HOME\})(?:/[^\s;&|]*)?)(?=\s)[^;\n|&]*\s-exec(?:dir)?\s+(?:/\S*/)?rm\b",
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
    small set of permanently denied shell commands. Safe is the default.
    No policy mode is a sandbox: yolo only skips approval, and approved shell
    commands retain the OS account's filesystem, network and process access.
    Hard-deny inspection is incomplete; use OS isolation for untrusted code.
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
        if (not isinstance(call, dict) or not isinstance(call.get("name"), str)
                or not isinstance(call.get("args", {}), dict)):
            return "malformed tool call"
        name = _logical_tool_name(call["name"])
        if name == "bash":
            command = call.get("args", {}).get("command")
            if not isinstance(command, str) or not command.strip() or '\x00' in command:
                return "bash command cannot be evaluated safely"
            try:
                tokens = list(shlex.shlex(command, posix=True, punctuation_chars=';&|()'))
            except ValueError:
                return "bash command cannot be evaluated safely"
            # Normalize shell quoting for conservative inspection, never for execution.
            inspected = command.replace("'", "").replace('"', '').replace('\\\n', '')
            inspected = inspected.replace("^", "").replace("`", "")
            if (_dangerous_rm(tokens) or _dangerous_find(command)
                    or any(re.search(pattern, inspected) for pattern in DENY_PATTERNS)):
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
    """Keep read trust exact; shell suffixes only add restrictive inspection."""
    if name.endswith('_bash'):
        return 'bash'
    return name


def _dangerous_rm(tokens: list[str]) -> bool:
    """Deny broad deletion targets regardless of option position or spelling.

    This deliberately rejects root/home targets even without recursive flags.
    Token inspection is not a proof of arbitrary shell program safety.
    """
    active = False
    for token in tokens:
        if token and all(char in ';&|()' for char in token):
            active = False
        elif token.rsplit('/', 1)[-1] == 'rm':
            active = True
        elif active and not token.startswith('-'):
            if token.startswith(('~', '$HOME', '${HOME}')):
                return True
            if _root_equivalent(token):
                return True
    return False


def _root_equivalent(token: str) -> bool:
    """Lexically detect absolute root equivalents; do not resolve host paths."""
    return token.startswith('/') and (
        posixpath.normpath(token).strip('/') == ''
        or all(part in ('', '.', '..', '*') for part in token.split('/')))


def _dangerous_find(command: str) -> bool:
    """Inspect root-equivalent find operands without claiming full shell safety."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|()')
    lexer.whitespace_split = True
    segment: list[str] = []
    for token in list(lexer) + [';']:
        if token and all(char in ';&|()' for char in token):
            if any(part.rsplit('/', 1)[-1] == 'find' for part in segment):
                if any(_root_equivalent(part) for part in segment) and (
                        '-delete' in segment or any(part in ('-exec', '-execdir') for part in segment)
                        and any(part.rsplit('/', 1)[-1] == 'rm' for part in segment)):
                    return True
            segment = []
        else:
            segment.append(token)
    return False
