"""Snapshot declared artifacts, then execute an independent bounded verifier."""
import ast
import json
from pathlib import Path
import sys
import tempfile
from ..execution.filesystem import WorkspaceFiles
from ..execution.process import run_owned
from ..execution.base import ExecutionError, ExecutionTimeout


def verify(task, workspace, verifier_script, scratch):
    present, contents = [], {}
    files = WorkspaceFiles(workspace)
    try:
        for relative in task.deliverables:
            try: text = files.read_text(relative)
            except FileNotFoundError: continue
            if len(text.encode("utf-8")) > 65536: return outcome("invalid_output", task, present)
            if relative.endswith(".py"): ast.parse(text)
            present.append(relative); contents[relative] = text
    except (SyntaxError, ValueError, OSError, ExecutionError):
        return outcome("invalid_output", task, present)
    if len(present) != len(task.deliverables):
        return outcome("partial" if present else "invalid_output", task, present)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="verify-") as directory:
        root = Path(directory)
        for relative, text in contents.items():
            target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        try:
            result = run_owned([sys.executable, "-I", "-S", "-X", "utf8", str(verifier_script), task.id, str(root)], cwd=root, timeout=15)
        except ExecutionTimeout: return outcome("timeout", task, present, "verifier_timeout")
        except ExecutionError: return outcome("verifier_error", task, present, "verifier_process")
        try:
            if result.returncode: raise ValueError("verifier exited")
            data = json.loads(result.stdout)
            if data.get("candidate_error") is True: return outcome("invalid_output", task, present)
            if data.get("infrastructure_error") is True: return outcome("verifier_error", task, present)
            if set(data) != {"schema_version", "checks"} or data["schema_version"] != 1: raise ValueError("invalid protocol")
            checks = data["checks"]
            if (not isinstance(checks, list) or len(checks) != len(task.criteria) or
                {item["id"] for item in checks} != set(task.criteria) or
                any(set(item) != {"id", "passed"} or type(item["passed"]) is not bool for item in checks)):
                raise ValueError("invalid verifier checks")
        except (ValueError, TypeError, KeyError, AttributeError):
            return outcome("verifier_error", task, present, "verifier_protocol")
        passed = sum(check["passed"] for check in checks)
        return {**outcome("passed" if passed == len(checks) else "partial" if passed else "failed", task, present), "checks": checks, "executed": True}


def outcome(status, task, present, category=None):
    return {"status": status, "error_category": category, "executed": False, "artifacts_present": len(present),
            "artifacts_required": len(task.deliverables), "checks": [{"id": c, "passed": False} for c in task.criteria]}
