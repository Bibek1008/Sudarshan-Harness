"""Allowlisted CLI diagnostics: never render exception text, source or locals.

Redacting arbitrary exception strings cannot guarantee that an unlabelled secret
or a dotenv file dump is removed. Instead report known failure codes/details and
structural traceback locations. This module never reads credentials or files.
"""
from contextvars import ContextVar
from pathlib import Path
import re
import sys
from typing import Callable
from urllib.error import HTTPError, URLError

from .execution.base import BackendUnavailable, ExecutionError, ExecutionPermissionError, ExecutionTimeout


TOOL_ERROR_HANDLER: ContextVar[Callable[[Exception], None] | None] = ContextVar(
    "sudarshan_tool_error_handler", default=None
)
_PACKAGE = Path(__file__).parent
_SAFE_TYPES = {
    ValueError, TypeError, KeyError, IndexError, AttributeError, AssertionError,
    RuntimeError, OSError, FileNotFoundError, PermissionError, IsADirectoryError,
    NotADirectoryError, UnicodeDecodeError, UnicodeEncodeError, TimeoutError, ConnectionError,
    ConnectionRefusedError, ConnectionResetError, HTTPError, URLError,
    BackendUnavailable, ExecutionError, ExecutionPermissionError, ExecutionTimeout,
}


def _chain(error: BaseException):
    seen = set()
    while error is not None and id(error) not in seen and len(seen) < 8:
        seen.add(id(error))
        yield error
        error = error.__cause__ or error.__context__


def describe(error: Exception, stage: str = "task") -> tuple[str, str]:
    """Classify known failures without echoing a URL, header, body or argument."""
    errors = list(_chain(error))
    if stage == "startup":
        return "workspace", "Cannot open the workspace or session. Check -d, --resume and file permissions."
    if stage == "telemetry":
        return "telemetry", "Telemetry could not be read or configured. Check UUID, permissions and configuration."
    if stage == "tool":
        if isinstance(error, ExecutionTimeout):
            return "tool", "Tool execution timed out; inspect project files before retrying."
        return "tool", "Tool execution failed; inspect the requested operation and project files."
    if isinstance(error, UnicodeEncodeError):
        return "terminal", "Terminal encoding cannot display output. Use a UTF-8 terminal or PYTHONUTF8=1."
    for item in errors:
        message = item.args[0] if item.args and isinstance(item.args[0], str) else ""
        # Full matches are essential: provider messages are bounded protocol
        # strings, not arbitrary exception text to copy into a diagnostic.
        code = item.code if isinstance(item, HTTPError) else None
        match = re.fullmatch(r"Gemini HTTP ([1-5]\d\d)|Gemini request failed after \d+ attempts: HTTP ([1-5]\d\d)", message)
        if match:
            code = int(match[1] or match[2])
        if type(code) is int:
            if code in {401, 403}:
                return "authentication", f"Gemini HTTP {code}: authentication or access denied. Check key permissions and project access."
            if code == 404:
                return "model", "Gemini HTTP 404: model or endpoint unavailable. Check -m and account access."
            if code == 429:
                return "quota", "Gemini HTTP 429: quota or rate limit reached. Check quota and retry later."
            if code >= 500:
                return "network", f"Gemini HTTP {code}: provider service failure. Retry later."
            return "provider", "Gemini rejected the request. Check model compatibility and request configuration."
        if message.startswith("Set SUDARSHAN_API_KEY (or legacy ODYSSEUS_API_KEY / GEMINI_API_KEY)"):
            return "authentication", "No API key configured. Set SUDARSHAN_API_KEY or check the selected project's configuration."
        if message == "Invalid Gemini model name":
            return "model", "Invalid Gemini model identifier. Check -m."
        if re.fullmatch(r"(?:Unclosed quote|Unexpected text) in project \.env on line \d+", message):
            return "configuration", "Project key configuration has invalid quoting or trailing text. Review it locally; contents are withheld."
        if isinstance(item, (URLError, TimeoutError, ConnectionError)) or re.fullmatch(
            r"Gemini request failed after \d+ attempts: network or timeout error|Gemini request deadline exceeded", message
        ):
            return "network", "Network connection, TLS, DNS or request timeout failed. Check connectivity and retry."
        if message in {"Model returned a malformed response", "Model returned a malformed tool call",
                       "Model returned an empty response", "Gemini returned malformed JSON",
                       "Gemini returned an invalid response object"}:
            return "provider", message + "."
        if message.startswith("Gemini returned no usable candidate:"):
            return "provider", "Gemini returned no usable candidate; the response may have been blocked or empty."
    if isinstance(error, ExecutionError):
        return "tool", "Execution backend failed. Check the operation and runtime availability."
    if isinstance(error, OSError):
        return "workspace", "File or workspace operation failed. Check paths and permissions."
    return "internal", "Task failed with an unexpected internal error."


def report(error: Exception, *, verbose: bool = False, stage: str = "task") -> None:
    """Print safe details and, optionally, a traceback without source or values."""
    category, detail = describe(error, stage)
    print(f"Error [{category}]: {detail}", file=sys.stderr)
    if not verbose:
        print("Use --verbose for sanitized diagnostics.", file=sys.stderr)
        return
    kind = type(error).__name__ if type(error) in _SAFE_TYPES else "Exception (custom type withheld)"
    print(f"Exception type: {kind}", file=sys.stderr)
    print("Sanitized traceback (most recent call last; source, locals and exception text withheld):", file=sys.stderr)
    tb = error.__traceback__
    count = 0
    while tb is not None and count < 40:
        frame = tb.tb_frame
        # Only package-owned locations are displayed. External/plugin filenames
        # can themselves contain secrets, so do not render arbitrary paths.
        filename = Path(frame.f_code.co_filename)
        try:
            relative = filename.relative_to(_PACKAGE).as_posix()
        except ValueError:
            relative = "<external frame>"
        if relative != "<external frame>" and not re.fullmatch(r"[a-zA-Z0-9_/]+\.py", relative):
            relative = "<external frame>"
        print(f"  {relative}, line {tb.tb_lineno}", file=sys.stderr)
        tb = tb.tb_next
        count += 1
    if tb is not None:
        print("  [remaining frames omitted]", file=sys.stderr)


def report_tool_error(error: Exception) -> None:
    """Optional scoped CLI hook; raw exceptions never enter event/telemetry data."""
    handler = TOOL_ERROR_HANDLER.get()
    if handler is not None:
        try:
            handler(error)
        except Exception:
            pass  # A diagnostic sink failure must not change tool semantics.
