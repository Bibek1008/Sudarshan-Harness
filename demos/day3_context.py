"""Day 3: a compacted tool loop with prompt memory and discoverable skills.

The demo wires compaction into the existing loop socket instead of modifying the
loop.  It builds a temporary workspace, injects durable prompt context, and
keeps all provider-facing state in the neutral Day 1 message format.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sudarshan.context import compact
from sudarshan.loop import run_loop
from sudarshan.memory import build_system_prompt
from sudarshan.provider import DEFAULT_MODEL
from sudarshan.security import Policy
from sudarshan.skills import catalog_prompt
from sudarshan.tools import core_tools


def print_event(kind: str, payload: dict[str, Any]) -> None:
    """Print the loop lifecycle without needing a special provider protocol."""
    if kind == "assistant":
        print(f"\nassistant: {payload['text']}")
    elif kind == "tool_start":
        print(f"tool start: {payload['name']}")
    else:
        print(f"tool end: {payload['name']}: {payload['text'][:120]}")


def main() -> None:
    """Run a memory-aware coding task with a 1500-token compaction budget."""
    scratch_parent = Path("work")
    scratch_parent.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="sudarshan-day3-", dir=scratch_parent) as scratch:
        available = {tool.name: tool for tool in core_tools(scratch)}
        system = build_system_prompt(scratch, catalog_prompt(scratch))
        task = "Create hello.py, run it, and report only the output you verified."
        result = run_loop(
            DEFAULT_MODEL,
            system,
            [{"role": "user", "text": task}],
            available,
            print_event,
            Policy("yolo").check,
            before_turn=lambda msgs: compact(DEFAULT_MODEL, msgs, 1500),
        )
        print(f"\nfinal: {result}")


if __name__ == "__main__":
    main()
