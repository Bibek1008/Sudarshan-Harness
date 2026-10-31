"""Day 5: argparse front door for interactive and headless Harness sessions.

The CLI keeps approvals explicit and forwards all agent behavior to Harness.
"""

import argparse
from typing import Any, Sequence

from .harness import Harness
from .security import Policy


def _event(kind: str, payload: dict[str, Any]) -> None:
    """Render assistant text and concise tool lifecycle events."""
    if kind == "assistant" and payload["text"]:
        print(payload["text"])
    elif kind == "tool_start":
        print(f"→ {payload['name']}({str(payload['args'])[:140]})")
    elif kind == "tool_end":
        first = payload["text"].splitlines()[0] if payload["text"] else "(no output)"
        print(f"  \x1b[2m{first}\x1b[0m")


def _approver(call: dict[str, Any], reason: str) -> bool:
    """Ask for explicit approval, refusing unless the user says yes."""
    print(f"{reason}: {call['name']}({call.get('args', {})})")
    try:
        return input("approve ...? [y/N] ").strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def main(argv: Sequence[str] | None = None) -> None:
    """Run a headless task or an interactive, resumable prompt loop."""
    parser = argparse.ArgumentParser(description="Sudarshan, the small sharp coding agent.")
    parser.add_argument("-p", "--prompt")
    parser.add_argument("-d", "--workdir", default=".")
    parser.add_argument("-m", "--model")
    parser.add_argument("--mode", choices=("safe", "yolo", "read-only"), default="safe",
                        help="approval policy (default: safe); yolo skips approval and is not a sandbox")
    parser.add_argument("--resume", nargs="?", const="")
    parser.add_argument("--max-turns", type=int, default=120)
    args = parser.parse_args(argv)
    mode = args.mode
    harness = Harness(args.workdir, model=args.model, policy=Policy(mode, _approver if mode == "safe" else None), on_event=_event, max_turns=args.max_turns)
    if args.resume is not None and not harness.resume(args.resume or None):
        print("No session available to resume.")
    if args.prompt is not None:
        try:
            harness.run(args.prompt)
        except KeyboardInterrupt:
            print("\nInterrupted; the session log is safe and --resume continues it.")
            raise SystemExit(130)
        return
    print(f"Sudarshan · model={harness.model} · mode={mode} · workdir={harness.workdir}")
    while True:
        try:
            task = input("sudarshan> ").strip()
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print("\nInterrupted; the session log is safe and --resume continues it.")
            continue
        if task:
            try:
                harness.run(task)
            except KeyboardInterrupt:
                print("\nInterrupted; the session log is safe and --resume continues it.")
