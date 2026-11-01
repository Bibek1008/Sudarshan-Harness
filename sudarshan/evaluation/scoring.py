"""Task-weighted metrics with explicit denominators and unavailable values."""
from collections import Counter
from decimal import Decimal
from statistics import mean, median, pstdev
from ..telemetry import COUNTS


def summarize(trials, planned_trials=None):
    count = len(trials)
    statuses = Counter(trial["status"] for trial in trials)
    successes = [t for t in trials if t["status"] == "passed"]
    first = [t for t in trials if t["trial_number"] == 1]
    metrics = [t.get("metrics") for t in trials]
    known = [m for m in metrics if m is not None]
    tokens = {key: sum(m["tokens"][key] for m in known if m["tokens"].get(key) is not None) if any(m["tokens"].get(key) is not None for m in known) else None for key in COUNTS}
    cost_entries = [m.get("estimated_cost") if m else None for m in metrics]
    currencies = {c["currency"] for c in cost_entries if c}
    total_cost = None
    if count and all(cost_entries) and len(currencies) == 1:
        total_cost = {"estimated": str(sum((Decimal(c["estimated"]) for c in cost_entries), Decimal(0))), "currency": next(iter(currencies)), "billing": "estimate_not_provider_bill"}
    def average(field):
        return mean(m[field] for m in known) if count and len(known) == count and all(not m.get("partial", True) for m in known) else None
    verification_rates = [sum(c["passed"] for c in t["verification"]["checks"]) / len(t["verification"]["checks"]) if t.get("verification") else 0 for t in trials]
    durations = [t["duration_ms"] for t in trials]
    checks = [c for trial in trials if trial.get("verification") and trial["verification"].get("executed") for c in trial["verification"]["checks"]]
    validation = [c for trial in trials if trial["category"] == "validation" and trial.get("verification") and trial["verification"].get("executed") for c in trial["verification"]["checks"]]
    error_ids = {"empty", "invalid", "range", "types", "regression", "errors_empty"}
    errors = [c for c in checks if c["id"] in error_ids]
    regressions = [c for trial in trials if trial["category"] == "regression" and trial.get("verification") and trial["verification"].get("executed") for c in trial["verification"]["checks"]]
    def rate(values): return sum(c["passed"] for c in values)/len(values) if values else None
    artifacts = [trial["verification"]["artifacts_present"]/trial["verification"]["artifacts_required"] if trial.get("verification") else 0 for trial in trials]
    return {"attempted_trials": count, "planned_trials": planned_trials, "run_complete": count == planned_trials if planned_trials is not None else None, "statuses": dict(statuses), "passed": len(successes),
            "task_success_rate": len(successes)/count if count else None,
            "verification_pass_rate": mean(verification_rates) if count else None,
            "verification_denominator": "equal_weight_per_attempted_trial;unverified=0",
            "quality_diagnostics": {"independent_check_pass_rate": rate(checks), "executed_check_records": len(checks),
                "artifact_completion_rate": mean(artifacts) if artifacts else None,
                "input_validation_check_pass_rate": rate(validation), "error_handling_check_pass_rate": rate(errors),
                "regression_failed_checks": sum(not c["passed"] for c in regressions) if regressions else None,
                "note": "criterion counts are diagnostics; they do not weight task success"},
            "first_attempt_success_rate": sum(t["status"] == "passed" for t in first)/len(first) if first else None,
            "first_attempt_denominator": len(first), "average_turns": average("turns"),
            "median_duration_ms": median(durations) if durations else None,
            "duration_stddev_ms": pstdev(durations) if durations else None,
            "average_success_duration_ms": mean(t["duration_ms"] for t in successes) if successes else None,
            "measured_tokens": tokens,
            "telemetry_coverage": {"measured_trials": len(known), "attempted_trials": count,
                "tokens": {key: {"measured_requests": sum(m["token_coverage"][key]["measured_requests"] for m in known),
                                 "successful_requests_with_telemetry": sum(m["token_coverage"][key]["successful_requests"] for m in known)} for key in COUNTS},
                "complete_trials": sum(m is not None and not m.get("partial", True) and m["model_requests"] > 0 and m["token_coverage"]["input"]["successful_requests"] == m["model_requests"] and all(m["token_coverage"][k]["measured_requests"] == m["token_coverage"][k]["successful_requests"] for k in COUNTS) for m in metrics)},
            "estimated_total_cost": total_cost,
            "estimated_cost_per_success_including_failed_attempts": {**total_cost, "estimated": str(Decimal(total_cost["estimated"])/len(successes))} if total_cost and successes else None,
            "metric_averages": {key: average(key) for key in ("model_requests", "tool_calls", "successful_tools", "failed_tools", "denied_tools", "retries", "timeouts")},
            "categories": {category: summarize_category([t for t in trials if t["category"] == category]) for category in sorted({t["category"] for t in trials})}}


def summarize_category(trials):
    return {"attempted_trials": len(trials), "passed": sum(t["status"] == "passed" for t in trials),
            "success_rate": sum(t["status"] == "passed" for t in trials)/len(trials)}
