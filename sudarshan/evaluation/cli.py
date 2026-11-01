"""Explicit live opt-in; read-only commands never invoke a provider."""
import argparse
import json
import sys
from .registry import load_suite, suites
from .runner import dry_run, run_suite
from .reporting import ResultStore, render
from .comparison import compare


def main(argv):
    parser = argparse.ArgumentParser(prog="sudarshan benchmark", description="Controlled benchmark tasks; local workspaces are not an OS sandbox.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show"); show.add_argument("suite")
    run = commands.add_parser("run"); run.add_argument("suite")
    modes = run.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--live", action="store_true")
    run.add_argument("--model")
    run.add_argument("--runs", type=int, default=1)
    run.add_argument("--approve-workspace-edits", action="store_true", help="Explicit safe-mode approval for confined write/edit tools only; shell remains denied")
    run.add_argument("--task", action="append")
    run.add_argument("-d", "--workdir", default=".")
    run.add_argument("--retention", type=int, default=100)
    for command in ("report", "export"):
        sub = commands.add_parser(command); sub.add_argument("run_id"); sub.add_argument("-d", "--workdir", default=".")
        sub.add_argument("--json", action="store_true", dest="json_output")
    comp = commands.add_parser("compare"); comp.add_argument("first"); comp.add_argument("second"); comp.add_argument("-d", "--workdir", default=".")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            print("\n".join(suites())); return
        if args.command == "show":
            suite = load_suite(args.suite)
            print(json.dumps({"suite": suite["name"], "version": suite["version"], "fingerprint": suite["fingerprint"], "tasks": [t.public_metadata() for t in suite["tasks"]]}, indent=2)); return
        if args.command == "run":
            if args.live and not args.model: parser.error("--live requires an explicit --model")
            model = args.model or "gemini-3.1-flash-lite"
            plan = dry_run(args.suite, model, args.runs, args.approve_workspace_edits, args.task)
            if args.dry_run:
                print(json.dumps(plan, indent=2)); return
            # Validate all controls before producing any model request.
            if not 1 <= args.retention <= 1000: parser.error("retention must be 1 through 1000")
            from .runner import configuration
            suite = load_suite(args.suite)
            config = configuration(suite, model, args.runs, args.approve_workspace_edits, args.task)
            print("WARNING: live benchmarking makes paid or quota-consuming Gemini requests.")
            print("Model:", model, "repetitions:", args.runs, "policy:", config["approval_policy"])
            print("Per-task execution limits:", json.dumps(config["limits"]))
            print("Shell effects are denied. Controlled tasks only; temporary directories are not OS isolation.", flush=True)
            result = run_suite(args.workdir, args.suite, model=model, runs=args.runs, live=True,
                               approve_workspace_edits=args.approve_workspace_edits, task_ids=args.task, retention=args.retention)
            print("Run ID:", result["run_id"]); print(render(result)); return
        store = ResultStore(args.workdir)
        if args.command == "compare":
            print(json.dumps(compare(store.load(args.first), store.load(args.second)), indent=2)); return
        run = store.load(args.run_id)
        print(json.dumps(run, indent=2) if args.command == "export" or args.json_output else render(run))
    except (OSError, ValueError, TypeError, KeyError):
        print("Error: invalid benchmark configuration, unavailable result, or failed validation. No raw output is disclosed.", file=sys.stderr)
        raise SystemExit(1) from None
