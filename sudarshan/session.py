"""Day 4: append-only JSONL sessions with torn-write and call-pair repair.

Sessions favor recoverability over clever storage: each message is independently
durable, a malformed tail stops loading safely, and unfinished tool calls gain
explicit interruption results so the next model turn sees a valid transcript.
"""

import json
import re
import time
from pathlib import Path
from typing import Any


SESSION_DIR = ".sudarshan/sessions"


def new_session(workdir: str | Path, label: str = "session") -> Path:
    """Create the session directory and return a timestamped, slugged JSONL path."""
    directory = Path(workdir).resolve() / SESSION_DIR
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "session"
    return directory / f"{int(time.time())}-{slug}.jsonl"


def append(path: str | Path, message: dict[str, Any]) -> None:
    """Append one neutral message as a single UTF-8 JSONL record."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message, ensure_ascii=False) + "\n")


def load(path: str | Path) -> list[dict[str, Any]]:
    """Load complete JSONL records, ignoring a torn tail and repairing call pairs."""
    messages: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                break
    return _repair(messages)


def latest(workdir: str | Path) -> Path | None:
    """Return the most recently modified session file, or ``None`` when absent."""
    directory = Path(workdir).resolve() / SESSION_DIR
    sessions = list(directory.glob("*.jsonl")) if directory.is_dir() else []
    return max(sessions, key=lambda path: path.stat().st_mtime) if sessions else None


def _repair(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append interruption responses for calls after the final assistant message."""
    assistant_index = next((index for index in range(len(messages) - 1, -1, -1)
                            if messages[index].get("role") == "assistant"), None)
    if assistant_index is None:
        return messages
    calls = messages[assistant_index].get("tool_calls", [])
    completed = sum(message.get("role") == "tool" for message in messages[assistant_index + 1:])
    # Tool-call order is the pairing constraint; only its unpaired suffix is synthetic.
    for call in calls[completed:]:
        messages.append({
            "role": "tool",
            "name": call["name"],
            "text": "Interrupted before this ran (process restarted).",
        })
    return messages
