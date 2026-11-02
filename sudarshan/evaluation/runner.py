"""Disposable, bounded agent trials; independent verification determines success."""
from contextlib import nullcontext
from datetime import datetime, timezone
import platform
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from .broker import Broker
from .metrics import clean, price
from .registry import load_suite, linked
from .reporting import ResultStore
from .scoring import summarize
from .verifier import verify
from ..execution.base import ExecutionError, ExecutionTimeout
from ..execution.filesystem import WorkspaceFiles
from ..environment import safe_shell_environment
from ..execution.process import run_owned, trusted_executable
from ..telemetry import Store, label

BOOTSTRAP = "import sys,runpy; root,config=sys.argv[1:3]; sys.path.insert(0,root); sys.argv=['worker',config]; runpy.run_module('sudarshan.evaluation.worker',run_name='__main__')"


def stamp(): return datetime.now(timezone.utc).isoformat()


def commit_sha():
    try:
        root = Path(__file__).resolve().parents[2]
        executable = trusted_executable("git", root)
        if not executable: return "unavailable"
        value = subprocess.check_output([executable, "rev-parse", "HEAD"], cwd=root, env=safe_shell_environment(), text=True, timeout=5, stderr=subprocess.DEVNULL).strip()
        return value if len(value) in {40,64} and all(c in "0123456789abcdef" for c in value) else "unavailable"
    except (OSError, subprocess.SubprocessError): return "unavailable"


def engine_fingerprint():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if path.is_symlink(): raise ValueError("linked engine source")
        path.resolve().relative_to(root.resolve())
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0" + path.read_text(encoding="utf-8").replace("\r\n", "\n").encode())
    return digest.hexdigest()


def configuration(suite, model, runs, approved, task_ids=None):
    if type(runs) is not int or not 1 <= runs <= 20: raise ValueError("runs must be 1 through 20")
    if label(model) != model or not model.startswith(("gemini-", "test-")): raise ValueError("invalid model identifier")
    tasks = [t for t in suite["tasks"] if task_ids is None or t.id in task_ids]
    if not tasks or task_ids is not None and set(task_ids) != {t.id for t in tasks}: raise ValueError("unknown task selection")
    return {"suite": suite["name"], "suite_version": suite["version"], "fingerprint": suite["fingerprint"],
            "task_versions": {t.id: t.version for t in tasks}, "runs": runs, "model": model,
            "provider_config": "gemini-rest-v1", "limits": {t.id: {"seconds": t.seconds, "turns": t.turns, "verifier_seconds": 15} for t in tasks},
            "approval_policy": "safe-workspace-edits" if approved else "safe-deny-effects",
            "prompt_config": "core-instructions-v1", "commit_sha": commit_sha(), "engine_fingerprint": engine_fingerprint(),
            "platform": platform.system()+"-"+platform.machine(), "python_version": platform.python_version(),
            "fixture_isolation": "local-owned-process-not-sandbox", "pricing_config_id": "unavailable"}


def dry_run(name="core", model="gemini-3.1-flash-lite", runs=1, approve_workspace_edits=False, task_ids=None):
    suite = load_suite(name)
    return {"mode": "dry_run", "configuration": configuration(suite, model, runs, approve_workspace_edits, task_ids),
            "tasks": [t.public_metadata() for t in suite["tasks"] if task_ids is None or t.id in task_ids], "model_requests_made": 0}


def prepare(task, suite, workspace):
    fixture = suite["root"] / "fixtures" / task.fixture
    if linked(fixture): raise ValueError("fixture link rejected")
    destination = WorkspaceFiles(workspace)
    from .models import safe_relative
    for relative, content in suite["fixtures"][task.id].items():
        safe_relative(relative)
        if len(content.encode()) > 65536: raise ValueError("fixture exceeds bound")
        destination.write_text(relative, content)


def execute_trial(task, suite, config, trial_number, scratch, *, live=False, mock_replies=None, prices=None):
    begin, started = time.perf_counter(), stamp()
    trial = {"trial_id": str(uuid.uuid4()), "task_id": task.id, "category": task.category,
             "task_version": task.version, "trial_number": trial_number, "status": "inconclusive",
             "execution_status": "not_started", "error_category": None, "started_at": started,
             "completed_at": started, "duration_ms": 0, "verification": None, "metrics": None}
    with tempfile.TemporaryDirectory(dir=scratch, prefix="trial-") as directory:
        control = Path(directory)
        workspace = control / "workspace"; workspace.mkdir(mode=0o700)
        try:
            if engine_fingerprint() != config["engine_fingerprint"]: raise ValueError("engine changed during evaluation")
            prepare(task, suite, workspace)
            verifier_script = control / "trusted-checks.py"
            verifier_script.write_text(suite["verifier_source"], encoding="utf-8")
            worker_config = {"mode": "live" if live else "mock", "model": config["model"], "workspace": str(workspace),
                             "instructions": task.instructions, "seconds": task.seconds, "turns": task.turns,
                             "approve_workspace_edits": config["approval_policy"] == "safe-workspace-edits"}
            if not live: worker_config["mock_replies"] = mock_replies or []
            broker = Broker(config["model"], time.monotonic()+task.seconds, task.turns*2) if live else nullcontext(None)
            with broker as endpoint:
                if endpoint: worker_config["broker"] = endpoint
                path = control / "worker.json"
                encoded = json.dumps(worker_config)
                if len(encoded.encode()) > 1048576: raise ValueError("worker configuration exceeds bound")
                path.write_text(encoded, encoding="utf-8"); path.chmod(0o600)
                result = run_owned([sys.executable, "-I", "-S", "-X", "utf8", "-c", BOOTSTRAP,
                                    str(Path(__file__).resolve().parents[2]), str(path)], cwd=workspace, timeout=task.seconds)
            try:
                data = json.loads(result.stdout)
                if set(data) != {"schema_version", "execution_status", "metrics"} or data["schema_version"] != 1 or data["execution_status"] not in {"completed", "failed", "interrupted", "unavailable"}:
                    raise ValueError("invalid worker protocol")
            except (TypeError, ValueError, AttributeError):
                trial.update(status="inconclusive", execution_status="failed", error_category="worker_protocol")
            else:
                trial["execution_status"] = data["execution_status"]
                trial["metrics"] = price(clean(data["metrics"]), config["model"], prices or {})
                verification = verify(task, workspace, verifier_script, control)
                trial["verification"] = verification
                if result.returncode:
                    trial.update(status="inconclusive", execution_status="failed", error_category="worker_process")
                elif data["execution_status"] == "unavailable":
                    trial.update(status="inconclusive", execution_status="failed", error_category="provider_unavailable")
                elif data["execution_status"] != "completed":
                    trial["status"] = "interrupted" if data["execution_status"] == "interrupted" else "failed"
                    trial["error_category"] = "agent_execution"
                else:
                    trial["status"] = verification["status"]
                    trial["error_category"] = verification["error_category"]
        except ExecutionTimeout:
            trial.update(status="timeout", execution_status="timeout", error_category="agent_deadline")
        except KeyboardInterrupt:
            trial.update(status="interrupted", execution_status="interrupted", error_category="interrupted")
        except (ExecutionError, OSError, ValueError):
            trial.update(status="inconclusive", error_category="infrastructure")
    trial["duration_ms"] = (time.perf_counter()-begin)*1000
    trial["completed_at"] = stamp()
    return trial


def run_suite(workdir, name="core", *, model="gemini-3.1-flash-lite", runs=1, live=False,
              mock_scripts=None, approve_workspace_edits=False, task_ids=None, retention=100):
    if type(live) is not bool or type(approve_workspace_edits) is not bool: raise ValueError("explicit boolean controls required")
    if live and mock_scripts is not None: raise ValueError("live and mock modes cannot be mixed")
    if not live and mock_scripts is None: raise ValueError("execution requires explicit live or test-only mock scripts; use dry_run")
    suite = load_suite(name)
    config = configuration(suite, model, runs, approve_workspace_edits, task_ids)
    if not live: config["provider_config"] = "mock-scripted-v1"
    store = ResultStore(workdir, retention)
    try: prices = Store(workdir).read_json("pricing.json", {})
    except (OSError, ValueError): prices = {}
    if isinstance(prices, dict) and isinstance(prices.get(model), dict):
        fields = {"input_per_million", "output_per_million", "cached_per_million", "currency", "source", "effective_date", "thought_policy"}
        selected = {key:value for key,value in prices[model].items() if key in fields}
        config["pricing_config_id"] = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    begin = stamp()
    trials = []
    with store.locked(): pass
    with tempfile.TemporaryDirectory(dir=store.root, prefix="scratch-") as scratch:
        stop = False
        for repetition in range(1, runs+1):
            for task in suite["tasks"]:
                if task.id not in config["task_versions"]: continue
                scripts = (mock_scripts or {}).get(task.id, [])
                replies = scripts[repetition-1] if repetition <= len(scripts) else []
                trial = execute_trial(task, suite, config, repetition, scratch, live=live, mock_replies=replies, prices=prices)
                trials.append(trial)
                if trial["status"] == "interrupted": stop = True; break
            if stop: break
    run = {"schema_version": 1, "run_id": str(uuid.uuid4()), "mode": "live" if live else "mock",
           "configuration": config, "started_at": begin, "completed_at": stamp(), "trials": trials, "summary": summarize(trials, len(config["task_versions"])*runs)}
    store.save(run)
    return run
