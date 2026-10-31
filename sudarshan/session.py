"""Day 4: append-only JSONL sessions with torn-write and call-pair repair.

Sessions favor recoverability over clever storage: each message is independently
durable, a malformed tail stops loading safely, and unfinished tool calls gain
explicit interruption results so the next model turn sees a valid transcript.
"""

import json
import os
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
    stamp = int(time.time())
    collision = 0
    while True:
        suffix = f'-{collision}' if collision else ''
        target = directory / f"{stamp}-{slug}{suffix}.jsonl"
        try:
            # Exclusive creation reserves the path, including across processes.
            with target.open('x', encoding='utf-8'):
                pass
            return target
        except FileExistsError:
            collision += 1


def append(path: str | Path, message: dict[str, Any]) -> None:
    """Append one neutral message as a single UTF-8 JSONL record."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load(path: str | Path) -> list[dict[str, Any]]:
    """Truncate torn bytes and durably append missing tool results, idempotently.

    Each session has one writer; callers must not resume a live writer's log.
    """
    messages: list[dict[str, Any]] = []
    with Path(path).open('r+b') as handle:
        valid_end = 0
        last_line = b''
        while line := handle.readline():
            try:
                message = json.loads(line.decode('utf-8'))
                if not isinstance(message, dict) or 'role' not in message:
                    raise ValueError('not a message')
                messages.append(message)
            except (ValueError, UnicodeDecodeError):
                # A partial UTF-8 codepoint is also a torn tail; retain valid bytes.
                handle.seek(valid_end)
                handle.truncate()
                break
            valid_end = handle.tell()
            last_line = line
        if last_line and not last_line.endswith(b'\n'):
            handle.seek(valid_end)
            handle.write(b'\n')
        handle.flush()
        os.fsync(handle.fileno())
    original_count = len(messages)
    _repair(messages)
    for message in messages[original_count:]:
        append(path, message)
    return messages


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
