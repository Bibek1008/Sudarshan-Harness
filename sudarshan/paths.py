"""Shared boundary checks for workspace-owned metadata."""
from pathlib import Path
import os


def _resolved(path: Path) -> Path:
    value = str(path.resolve())
    # Windows may return extended-length spelling during concurrent creation.
    # Normalize spelling on both sides before comparing the same real paths.
    if os.name == "nt":
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
    return Path(value)


def workspace_path(workdir: str | Path, path: str | Path) -> Path:
    root = _resolved(Path(workdir))
    target = _resolved(root / path)
    try:
        target.relative_to(root)
    except ValueError:
        raise PermissionError("Metadata path escapes the working directory") from None
    return target
