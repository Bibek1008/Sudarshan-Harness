"""Day 2: build a tiny program through the tool loop and a yolo policy.

The demo keeps generated files in a temporary workspace, makes every model
action visible, and demonstrates that policy plugs into the existing loop
without changing either the provider or its conversation protocol.
"""

from tempfile import TemporaryDirectory
from typing import Any

from sudarshan.loop import run_loop
from sudarshan.provider import DEFAULT_MODEL
from sudarshan.security import Policy
from sudarshan.tools import core_tools


TASK = """Create fib.py with an iterative fib(n), a main printing fib(30),
run it, and confirm that the output is 832040."""
SYSTEM = """You are a careful coding assistant. Use tools to inspect, create,
and run files. Report only facts you have verified from tool output."""


def print_event(kind: str, payload: dict[str, Any]) -> None:
    """Print concise lifecycle events emitted by the loop."""
    if kind == "assistant":
        print(f"\nassistant: {payload['text']}")
    elif kind == "tool_start":
        print(f"tool start: {payload['name']}({payload['args']})")
    else:
        print(f"tool end: {payload['name']}: {payload['text']}")


def main() -> None:
    """Run the Day 2 build task in an isolated scratch workspace."""
    with TemporaryDirectory(prefix="sudarshan-day2-") as scratch:
        available = {item.name: item for item in core_tools(scratch)}
        policy = Policy("yolo")
        result = run_loop(
            DEFAULT_MODEL,
            SYSTEM,
            [{"role": "user", "text": TASK}],
            available,
            print_event,
            policy.check,
        )
        print(f"\nfinal: {result}")


if __name__ == "__main__":
    main()
