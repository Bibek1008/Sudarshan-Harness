"""Day 3: durable project memory injected directly into a system prompt.

Memory is a human-readable Markdown file under the working directory.  The
prompt builder resolves its location, preserves supplied facts verbatim, and
does not need an extra tool call for a fresh conversation to use them.
"""

import platform
from pathlib import Path


MEMORY_FILE = "SUDARSHAN.md"
BASE_SYSTEM_PROMPT = """You are Sudarshan, a small sharp coding agent working inside one directory with the tools provided.
Act, don't narrate.
Inspect before assuming.
Prefer edit_file for small changes.
Verify after building by running or re-reading.
Never repeat a failing call unchanged.
When complete, reply with a short summary and stop calling tools."""


def build_system_prompt(workdir: str | Path, extra: str = "") -> str:
    """Build the system prompt with resolved workspace, memory, and extra text.

    The memory section is prompt context, not a tool result, so a fresh agent
    can rely on it before it has made any filesystem call.
    """
    root = Path(workdir).resolve()
    sections = [BASE_SYSTEM_PROMPT, f"Platform: {platform.platform()}\nWorking directory: {root}"]
    memory = root / MEMORY_FILE
    if memory.is_file():
        sections.append(f"Project memory ({MEMORY_FILE}):\n{memory.read_text(encoding='utf-8')}")
    if extra:
        sections.append(extra)
    return "\n\n".join(sections)


def remember(workdir: str | Path, note: str) -> str:
    """Append one durable project fact and return a model-readable confirmation.

    Appending preserves earlier decisions in simple, reviewable Markdown.
    """
    memory = Path(workdir).resolve() / MEMORY_FILE
    with memory.open("a", encoding="utf-8") as handle:
        handle.write(f"- {note}\n")
    return f"Remembered in {MEMORY_FILE}"
