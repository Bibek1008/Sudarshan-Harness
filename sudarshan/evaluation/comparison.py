"""Compare matching configurations without asserting statistical significance."""
from statistics import mean, pstdev

FIELDS = ("suite", "suite_version", "fingerprint", "task_versions", "runs", "limits", "approval_policy", "provider_config", "prompt_config", "commit_sha", "engine_fingerprint", "platform", "python_version")


def compare(first, second):
    differences = [key for key in FIELDS if first["configuration"].get(key) != second["configuration"].get(key)]
    if not first["summary"].get("run_complete") or not second["summary"].get("run_complete"): differences.append("incomplete_run")
    if first.get("mode") != second.get("mode"): differences.append("mode")
    return {"schema_version": 1, "run_ids": [first["run_id"], second["run_id"]],
            "comparable": not differences, "configuration_differences": differences,
            "success_rate_delta": second["summary"]["task_success_rate"] - first["summary"]["task_success_rate"] if not differences and first["summary"]["task_success_rate"] is not None and second["summary"]["task_success_rate"] is not None else None,
            "trial_variability": [variability(first), variability(second)],
            "pricing_configuration_differs": first["configuration"].get("pricing_config_id") != second["configuration"].get("pricing_config_id"),
            "cost_savings_claim": None, "statistical_significance": "not_established"}


def variability(run):
    numbers = sorted({t["trial_number"] for t in run["trials"]})
    rates = [sum(t["status"] == "passed" for t in run["trials"] if t["trial_number"] == n)/sum(t["trial_number"] == n for t in run["trials"]) for n in numbers]
    return {"per_repetition_success_rates": rates, "population_stddev": pstdev(rates) if rates else None}
