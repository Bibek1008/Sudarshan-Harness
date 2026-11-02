"""Load immutable task manifests and fingerprint all reproducibility inputs."""
import hashlib
import json
import re
from pathlib import Path
from .models import Task, safe_relative

def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


BENCHMARKS = Path(__file__).resolve().parents[2] / "benchmarks"


def load_suite(name="core"):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_-]{1,60}", name): raise ValueError("invalid suite name")
    if not (BENCHMARKS / name / "suite.json").is_file(): raise ValueError("unknown benchmark suite")
    root = BENCHMARKS / name
    tasks, snapshots = [], {}
    digest = hashlib.sha256()
    def add(path):
        path.resolve().relative_to(BENCHMARKS.resolve())
        if linked(path) or path.stat().st_size > 131072: raise ValueError("invalid benchmark source")
        content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        digest.update(path.relative_to(BENCHMARKS).as_posix().encode())
        digest.update(b"\0" + content.encode("utf-8"))
        return content
    data = json.loads(add(root / "suite.json"))
    if (not isinstance(data, dict) or set(data) != {"name", "version", "tasks"} or data["name"] != name or
        not isinstance(data["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", data["version"]) or
        not isinstance(data["tasks"], list) or not 1 <= len(data["tasks"]) <= 10):
        raise ValueError("invalid suite manifest")
    for task_id in data["tasks"]:
        if not isinstance(task_id, str) or not task_id.replace("-", "").isalnum(): raise ValueError("invalid task id")
        config = json.loads(add(root / "tasks" / (task_id + ".json")))
        if not isinstance(config.get("deliverables"), list) or not isinstance(config.get("criteria"), list): raise ValueError("invalid task lists")
        config["deliverables"] = tuple(config["deliverables"])
        config["criteria"] = tuple(config["criteria"])
        task = Task(**config).validate()
        if task.id != task_id: raise ValueError("mismatched benchmark definition")
        fixture = root / "fixtures" / task.fixture
        if not fixture.is_dir() or linked(fixture): raise ValueError("missing or linked fixture")
        snapshots[task.id] = {}
        for file in sorted(fixture.rglob("*")):
            relative_path = file.relative_to(fixture)
            # Importing bundled Python fixtures may create bytecode caches in
            # site-packages. They are runtime artifacts, not benchmark inputs.
            if "__pycache__" in relative_path.parts or file.suffix in {".pyc", ".pyo"}:
                continue
            if linked(file): raise ValueError("fixture links not permitted")
            if file.is_file():
                relative = safe_relative(file.relative_to(fixture).as_posix())
                content = add(file)
                if len(content.encode()) > 65536: raise ValueError("oversized fixture")
                snapshots[task.id][relative] = content
        tasks.append(task)
    verifier_source = add(root / "verifiers" / "checks.py")
    if len({task.id for task in tasks}) != len(tasks): raise ValueError("duplicate task ids")
    return {"name": name, "version": data["version"], "fingerprint": digest.hexdigest(), "root": root,
            "tasks": tasks, "fixtures": snapshots, "verifier_source": verifier_source}



class TaskRegistry:
    def __init__(self): self.tasks = {}

    def register(self, task):
        task.validate()
        if task.id in self.tasks: raise ValueError("duplicate task id")
        self.tasks[task.id] = task


def suites():
    return sorted(path.parent.name for path in BENCHMARKS.glob("*/suite.json") if re.fullmatch(r"[a-z0-9_-]{1,60}", path.parent.name))
