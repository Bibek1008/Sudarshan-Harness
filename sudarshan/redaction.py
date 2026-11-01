"""Best-effort redaction for diagnostic display, never secret discovery."""
import re
from typing import Any


_SECRET_NAME = re.compile(r"api[_-]?key|password|secret|token|authorization|credential", re.I)
_ASSIGNMENT = re.compile(
    r"(?i)([\w-]*(?:api[_-]?key|password|secret|token|authorization|credential)[\w-]*\s*[=:]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s;&]+)")
_BEARER = re.compile(r"(?i)(bearer\s+)[^\s,;]+")
_URL_KEY = re.compile(r"(?i)([?&]key=)[^&\s]+")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_NAME.search(str(key)) else redact(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = _BEARER.sub(lambda match: match[1] + "[REDACTED]", value)
        value = _ASSIGNMENT.sub(lambda match: match[1] + "[REDACTED]", value)
        return _URL_KEY.sub(lambda match: match[1] + "[REDACTED]", value)
    return value
