"""Day 5: argparse front door for interactive and headless Harness sessions.

The CLI keeps approvals explicit and forwards all agent behavior to Harness.
"""

import argparse
import json
from pathlib import Path
import re
import sys
from .telemetry import Store
from typing import Any, Sequence

from .harness import Harness
from .security import Policy
from .redaction import redact
from . import error_reporting


_SHELL_COMMAND = re.compile(
    r"(?i)^(?:(?:Get|Set|New|Remove|Invoke|Start|Stop|Write|Read|Test|Import|Export|Select|Format)-[a-z][\w-]*"
    r"|(?:sudarshan|powershell|pwsh|cmd|bash)(?:\.exe)?)(?:\s|$)"
    r"|^python(?:3(?:\.\d+)?)?(?:\.exe)?\s+-m\s+sudarshan(?:\s|$)"
)


def _interrupted(harness: Harness) -> None:
    """Mention resume only when a nonempty durable transcript actually exists."""
    print("\nInterrupted.")
    path = getattr(harness, "session_path", None)
    if getattr(harness, "persist", False) is True and isinstance(path, (str, Path)):
        try:
            if Path(path).is_file() and Path(path).stat().st_size:
                print("A session was saved. Inspect project files before continuing with --resume.")
        except OSError:
            pass


def _event(kind: str, payload: dict[str, Any]) -> None:
    """Render assistant text and concise tool lifecycle events."""
    if kind == "tool_end":
        # Error strings are untrusted and can contain unlabelled secrets.
        # Never render them, even before the normal best-effort redactor.
        if payload["text"].startswith("BLOCKED:"):
            print("  Policy denied the tool call; no fallback command was executed.")
            return
        if payload["text"].startswith("ERROR:"):
            print("  Tool execution failed; inspect the requested operation. Use --verbose for handled exception diagnostics.")
            return
    payload = redact(payload)
    if kind == "assistant" and payload["text"]:
        print(payload["text"])
    elif kind == "tool_start":
        print(f"→ {payload['name']}({str(payload['args'])[:140]})")
    elif kind == "tool_end":
        text = payload["text"]
        first = text.splitlines()[0] if text else "(no output)"
        print(f"  \x1b[2m{first}\x1b[0m")


def _approver(call: dict[str, Any], reason: str) -> bool:
    """Ask for explicit approval, refusing unless the user says yes."""
    displayed = redact(call)
    print(f"{reason}: {displayed['name']}({displayed.get('args', {})})")
    try:
        return input("approve ...? [y/N] ").strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def main(argv: Sequence[str] | None = None) -> None:
    """Run a headless task or an interactive, resumable prompt loop."""
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    if actual_argv and actual_argv[0] == "benchmark":
        from .evaluation.cli import main as benchmark_main
        return benchmark_main(actual_argv[1:])
    parser = argparse.ArgumentParser(description="Sudarshan, the small sharp coding agent.", epilog="Benchmark commands: python -m sudarshan benchmark --help")
    parser.add_argument("-p", "--prompt", help="Run one task and exit (may make Gemini requests)")
    parser.add_argument("-d", "--workdir", default=".", help="Project root for files, memory and sessions (default: current directory)")
    parser.add_argument("-m", "--model", help="Gemini model identifier; otherwise ODYSSEUS_MODEL or the provider default")
    parser.add_argument("--mode", choices=("safe", "yolo", "read-only"), default="safe",
                        help="approval policy (default: safe); yolo skips approval and is not a sandbox")
    parser.add_argument("--resume", nargs="?", const="", help="Resume the latest transcript, or a path inside the project")
    parser.add_argument("--max-turns", type=int, default=120, help="Maximum tool-capable turns before a final report (default: 120; minimum: 0)")
    parser.add_argument("--no-telemetry", action="store_true", help="Disable metadata telemetry for this invocation")
    parser.add_argument("--verbose", action="store_true", help="Show sanitized exception types, failure details and traceback locations; never raw values")
    parser.add_argument("diagnostic", nargs="?", choices=("stats", "trace", "telemetry"))
    parser.add_argument("--session", help="Opaque telemetry session UUID")
    parser.add_argument("--last", type=int, help="Most recent N telemetry sessions")
    parser.add_argument("--json", action="store_true", dest="json_output")
    toggles = parser.add_mutually_exclusive_group()
    toggles.add_argument("--disable", action="store_true")
    toggles.add_argument("--enable", action="store_true")
    args = parser.parse_args(actual_argv)
    if args.max_turns < 0:
        parser.error("--max-turns must be zero or greater")
    if args.last is not None and args.last < 1: parser.error("--last must be positive")
    if args.diagnostic:
        if args.prompt is not None or args.resume is not None:
            parser.error("diagnostics cannot be combined with an agent prompt or resume")
        try:
            store = Store(args.workdir)
            if args.diagnostic == "telemetry":
                if not (args.disable or args.enable): parser.error("telemetry requires --enable or --disable")
                store.configure(args.enable)
                print("Telemetry enabled." if args.enable else "Telemetry disabled.")
                return
            if args.disable or args.enable: parser.error("enable/disable requires telemetry")
            if args.diagnostic == "trace":
                if not args.session: parser.error("trace requires --session")
                with store.locked():
                    events, corrupt = store.read(args.session)
                result = {"events": events, "corrupt_records": corrupt}
            else:
                result = store.stats(args.session, args.last)
            if args.json_output: print(json.dumps(result, indent=2))
            elif args.diagnostic == "trace":
                for event in result["events"]:
                    print(f"{event['timestamp']} turn={event['turn']} {event['event_type']} {event['status']}")
                if not result["events"]: print("No telemetry found.")
                if corrupt: print(f"Skipped {corrupt} invalid telemetry records.")
            else:
                if not result["sessions"]: print("No telemetry found.")
                for item in result["sessions"]:
                    print(f"{item['session_id']} model={item['model']} status={item['status']} turns={item['turns']} requests={item['model_requests']} retries={item['retries']} duration_ms={item['duration_ms']}")
                    print("  actual measured tokens:", json.dumps(item['tokens']), "estimated cost:", json.dumps(item['estimated_cost']))
                print("Aggregate:", json.dumps(result["aggregate"]))
            return
        except Exception as error:
            error_reporting.report(error, verbose=args.verbose, stage="telemetry")
            raise SystemExit(1) from None
    if args.disable or args.enable or args.session or args.last is not None or args.json_output:
        parser.error("diagnostic options require stats, trace or telemetry")
    mode = args.mode
    try:
        harness = Harness(
            args.workdir, **({"telemetry": False} if args.no_telemetry else {}),
            model=args.model, policy=Policy(mode, _approver if mode == "safe" else None),
            on_event=_event, max_turns=args.max_turns,
        )
        if args.resume is not None and not harness.resume(args.resume or None):
            print("No session available to resume.")
    except Exception as error:
        error_reporting.report(error, verbose=args.verbose, stage="startup")
        raise SystemExit(1) from None

    def run_task(task: str) -> None:
        """Give expected failures safe guidance; keep interactive sessions usable."""
        handler = (lambda error: error_reporting.report(error, verbose=True, stage="tool")) if args.verbose else None
        token = error_reporting.TOOL_ERROR_HANDLER.set(handler)
        try:
            harness.run(task)
        except KeyboardInterrupt:
            _interrupted(harness)
            if args.prompt is not None:
                raise SystemExit(130) from None
        except Exception as error:
            error_reporting.report(error, verbose=args.verbose)
            if args.prompt is not None:
                raise SystemExit(1) from None
        finally:
            error_reporting.TOOL_ERROR_HANDLER.reset(token)

    if args.prompt is not None:
        run_task(args.prompt)
        return
    print(f"Sudarshan · model={harness.model} · mode={mode} · workdir={harness.workdir}")
    print("sudarshan> accepts natural-language tasks for the agent, not terminal commands.")
    print("Run PowerShell commands in PowerShell, not at sudarshan>. Exit this session before launching Sudarshan again.")
    print("Exit with exit, quit, :q, or Ctrl+Z then Enter on Windows (Ctrl+D on POSIX).")
    while True:
        try:
            task = input("sudarshan> ").strip()
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print("\nInput interrupted. Type exit to return to your terminal.")
            continue
        except Exception as error:
            error_reporting.report(error, verbose=args.verbose)
            raise SystemExit(1) from None
        if task.casefold() in {"exit", "quit", ":q", "\x1a"}:
            return
        if _SHELL_COMMAND.match(task):
            print("That looks like a shell command. Type exit, then run it in PowerShell or your terminal.")
            print("Here, describe a task in natural language, such as: List the project directories.")
            continue
        if task:
            run_task(task)
