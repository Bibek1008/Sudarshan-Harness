"""Bounded, atomic, metadata-only reports and safe result loading."""
import json
from pathlib import Path
import re
from ..telemetry import Store, identifier
from .models import STATUSES


class ResultStore(Store):
    def __init__(self, workdir, retention=100):
        if type(retention) is not int or not 1 <= retention <= 1000: raise ValueError("invalid retention")
        self.workdir = Path(workdir).resolve()
        self.root = self.workdir / ".sudarshan/benchmarks"
        self.retention = retention

    def save(self, run):
        validate(run)
        encoded = json.dumps(run, allow_nan=False)
        if len(encoded.encode()) > 2097152: raise ValueError("benchmark result exceeds bound")
        with self.locked():
            path = self.path(f"runs/{identifier(run['run_id'])}.json")
            if path.exists(): raise FileExistsError("benchmark run already exists")
            self.atomic_json(path, run)
            self.atomic_json(f"reports/{run['run_id']}.json", {"schema_version": 1, "run_id": run["run_id"], "summary": run["summary"]})
            paths = sorted(self.path("runs").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in paths[self.retention:]:
                identifier(old.stem)
                self.path(old).unlink()
                report = self.path(f"reports/{old.stem}.json")
                if report.exists(): report.unlink()

    def load(self, run_id):
        path = self.path(f"runs/{identifier(run_id)}.json")
        if path.stat().st_size > 2097152: raise ValueError("oversized benchmark result")
        try:
            def unique(pairs):
                result = {}
                for key,item in pairs:
                    if key in result: raise ValueError("duplicate JSON field")
                    result[key] = item
                return result
            value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        except (ValueError, UnicodeError): raise ValueError("corrupt benchmark result; preserved") from None
        validate(value)
        if value["run_id"] != run_id: raise ValueError("benchmark run identity mismatch")
        return value


def validate(run):
    from datetime import datetime
    from .metrics import clean
    from .scoring import summarize
    from .. import telemetry
    def reject(): raise ValueError("invalid benchmark result metadata")
    def label(value):
        if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", value): reject()
    def timestamp(value):
        try: stamp = datetime.fromisoformat(value)
        except (TypeError, ValueError): reject()
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0: reject()
    if not isinstance(run, dict) or set(run) != {"schema_version", "run_id", "mode", "configuration", "started_at", "completed_at", "trials", "summary"} or type(run["schema_version"]) is not int or run["schema_version"] != 1: reject()
    identifier(run["run_id"])
    timestamp(run["started_at"]); timestamp(run["completed_at"])
    if run["mode"] not in {"mock", "live"} or not isinstance(run["trials"], list) or len(run["trials"]) > 200: reject()
    config = run["configuration"]
    keys = {"suite", "suite_version", "fingerprint", "task_versions", "runs", "model", "provider_config", "limits", "approval_policy", "prompt_config", "commit_sha", "fixture_isolation", "pricing_config_id", "engine_fingerprint", "platform", "python_version"}
    if not isinstance(config, dict) or set(config) != keys: reject()
    for key in ("suite", "suite_version", "model", "provider_config", "approval_policy", "prompt_config", "fixture_isolation", "platform", "python_version"): label(config[key])
    if config["approval_policy"] not in {"safe-deny-effects", "safe-workspace-edits"}: reject()
    if type(config["runs"]) is not int or not 1 <= config["runs"] <= 20: reject()
    if any(not re.fullmatch(r"[a-f0-9]{64}", config[key]) for key in ("fingerprint", "engine_fingerprint")): reject()
    for key in ("commit_sha", "pricing_config_id"):
        if config[key] != "unavailable" and not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", config[key]): reject()
    if not isinstance(config["task_versions"], dict) or not 1 <= len(config["task_versions"]) <= 10: reject()
    if not isinstance(config["limits"], dict) or set(config["limits"]) != set(config["task_versions"]): reject()
    for task,version in config["task_versions"].items():
        label(task); label(version)
        limits = config["limits"][task]
        if set(limits) != {"seconds", "turns", "verifier_seconds"}: reject()
        if type(limits["seconds"]) is not int or not 1 <= limits["seconds"] <= 300: reject()
        if type(limits["turns"]) is not int or not 1 <= limits["turns"] <= 40 or limits["verifier_seconds"] != 15: reject()
    ids, repetitions = set(), set()
    categories = {None, "agent_execution", "agent_deadline", "interrupted", "infrastructure", "worker_protocol", "verifier_protocol", "verifier_process", "verifier_timeout", "worker_process", "provider_unavailable"}
    for trial in run["trials"]:
        fields = {"trial_id", "task_id", "category", "task_version", "trial_number", "status", "execution_status", "error_category", "duration_ms", "started_at", "completed_at", "verification", "metrics"}
        if not isinstance(trial, dict) or set(trial) != fields or trial["status"] not in STATUSES: reject()
        identifier(trial["trial_id"])
        if trial["trial_id"] in ids: reject()
        ids.add(trial["trial_id"])
        if type(trial["trial_number"]) is not int or not 1 <= trial["trial_number"] <= config["runs"]: reject()
        pair = (trial["task_id"], trial["trial_number"])
        if pair in repetitions: reject()
        repetitions.add(pair)
        for key in ("task_id", "category", "task_version"): label(trial[key])
        if config["task_versions"].get(trial["task_id"]) != trial["task_version"]: reject()
        if type(trial["duration_ms"]) not in {int,float} or not 0 <= trial["duration_ms"] <= 10**9: reject()
        timestamp(trial["started_at"]); timestamp(trial["completed_at"])
        if trial["execution_status"] not in {"not_started", "completed", "failed", "interrupted", "timeout"} or trial["error_category"] not in categories: reject()
        verification = trial["verification"]
        if verification is not None:
            if not isinstance(verification, dict) or set(verification) != {"status", "error_category", "artifacts_present", "artifacts_required", "checks", "executed"} or verification["status"] not in STATUSES or verification["error_category"] not in categories: reject()
            if type(verification["artifacts_present"]) is not int or type(verification["artifacts_required"]) is not int or not 0 <= verification["artifacts_present"] <= verification["artifacts_required"] <= 16: reject()
            if type(verification["executed"]) is not bool: reject()
            checks = verification["checks"]
            if not isinstance(checks, list) or not 1 <= len(checks) <= 32: reject()
            for check in checks:
                if not isinstance(check, dict) or set(check) != {"id", "passed"} or type(check["passed"]) is not bool: reject()
                label(check["id"])
            if len({check["id"] for check in checks}) != len(checks): reject()
            if not verification["executed"] and any(c["passed"] for c in checks): reject()
            if verification["status"] == "passed" and (not verification["executed"] or not all(c["passed"] for c in checks) or verification["artifacts_present"] != verification["artifacts_required"]): reject()
        if trial["status"] == "passed" and (trial["execution_status"] != "completed" or verification is None or verification["status"] != "passed"): reject()
        metrics = trial["metrics"]
        if metrics is not None:
            safe = clean(metrics)
            if safe is None or {k:v for k,v in metrics.items() if k != "estimated_cost"} != {k:v for k,v in safe.items() if k != "estimated_cost"}: reject()
            cost = metrics.get("estimated_cost")
            if cost is not None:
                event = {"schema_version":1,"event_id":trial["trial_id"],"session_id":run["run_id"],"timestamp":trial["started_at"],"event_type":"turn_completed","turn":0,"status":"success","cost":cost}
                if not telemetry.valid_event(event): reject()
    if run["summary"] != summarize(run["trials"], len(config["task_versions"])*config["runs"]): reject()


def render(run):
    summary = run["summary"]
    lines = ["SUDARSHAN BENCHMARK REPORT", f"Suite: {run['configuration']['suite']}  Model: {run['configuration']['model']}  Mode: {run['mode']}",
             f"Attempted/planned trials: {summary['attempted_trials']}/{summary['planned_trials']}  Task success rate: {summary['task_success_rate']}",
             f"Verification pass rate (task-weighted): {summary['verification_pass_rate']}",
             f"First-attempt success rate: {summary['first_attempt_success_rate']}",
             f"Average turns: {summary['average_turns']}  Median duration ms: {summary['median_duration_ms']}",
             "Measured tokens: " + json.dumps(summary["measured_tokens"]),
             "Estimated cost (not billing): " + json.dumps(summary["estimated_total_cost"]),
             "Category breakdown: " + json.dumps(summary["categories"]),
             "Quality diagnostics: " + json.dumps(summary["quality_diagnostics"]),
             "Cost provenance: " + json.dumps([{"source":t["metrics"]["estimated_cost"]["source"], "effective_date":t["metrics"]["estimated_cost"]["effective_date"]} for t in run["trials"] if t.get("metrics") and t["metrics"].get("estimated_cost")])]
    for trial in run["trials"]:
        if trial["status"] != "passed": lines.append(f"{trial['task_id']} repetition={trial['trial_number']} status={trial['status']} execution={trial['execution_status']}")
    return "\n".join(lines)
