"""Project Phase 4 metadata into a small, content-free evaluation schema."""
from .. import telemetry as t

FIELDS = ("turns", "model_requests", "tool_calls", "successful_tools", "failed_tools", "denied_tools", "retries", "timeouts")


def clean(summary):
    try:
        if not isinstance(summary, dict): return None
        result = {key: summary[key] for key in FIELDS}
        if any(type(value) is not int or not 0 <= value <= 100000 for value in result.values()): return None
        tokens = {key: summary["tokens"][key] for key in t.COUNTS}
        if any(value is not None and (type(value) is not int or not 0 <= value <= 10**15) for value in tokens.values()): return None
        coverage = {key: {field: summary["token_coverage"][key][field] for field in ("measured_requests", "successful_requests")} for key in t.COUNTS}
        if any(type(value) is not int or not 0 <= value <= result["model_requests"] for row in coverage.values() for value in row.values()): return None
        if any(row["measured_requests"] > row["successful_requests"] for row in coverage.values()): return None
        partial = summary.get("partial", True) or summary.get("status", "success") != "success"
        if type(partial) is not bool: return None
        return {**result, "tokens": tokens, "token_coverage": coverage, "partial": partial, "estimated_cost": None}
    except (KeyError, TypeError): return None


def price(metrics, model, prices):
    if metrics is None: return None
    required = ("input", "output", "thought", "cached")
    complete = not metrics["partial"] and metrics["model_requests"] > 0 and all(metrics["token_coverage"][key]["measured_requests"] == metrics["model_requests"] for key in required)
    if complete:
        usage = {**metrics["tokens"], "available": True}
        metrics["estimated_cost"] = t.estimate_cost(usage, model, prices)
    return metrics
