"""Run real validation commands, retaining exit codes, logs and skip reasons."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sudarshan.environment import safe_shell_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-only", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "ci-results"
    destination.mkdir(exist_ok=True)
    commands = [("compile", ["-m", "compileall", "-q", "sudarshan", "demos", "tests"]),
                ("unittest", ["-m", "unittest", "discover", "-v"]),
                ("help", ["-m", "sudarshan", "--help"])]
    if args.docker_only:
        commands = [("docker", ["-m", "unittest", "tests.test_live_docker", "-v"])]
    env = safe_shell_environment()
    env["PYTHONUTF8"] = "1"
    if os.environ.get("SUDARSHAN_DOCKER_INTEGRATION") == "1":
        env["SUDARSHAN_DOCKER_INTEGRATION"] = "1"
    results = []
    for name, arguments in commands:
        log = destination / (name + ".log")
        try:
            with log.open("w", encoding="utf-8") as output:
                completed = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env,
                                           stdout=output, stderr=subprocess.STDOUT, timeout=600)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code = 124
            with log.open("a", encoding="utf-8") as output:
                output.write("\nValidation command exceeded its 600 second limit.\n")
        text = log.read_text(encoding="utf-8", errors="replace")
        print(text, end="")
        results.append({"name": name, "command": [sys.executable, *arguments], "exit_code": code,
                        "skips": [line for line in text.splitlines() if "skipped" in line.lower()],
                        "log": log.name, "successful_test_records": len(re.findall(r"^.*\.\.\. ok$", text, re.M))})
    summary = {"platform": platform.platform(), "python": platform.python_version(),
               "commands": results, "docker_requested": args.docker_only}
    if args.docker_only:
        failed = any(item["exit_code"] for item in results)
        successes = sum(item["successful_test_records"] for item in results)
        summary["docker_status"] = "failed" if failed else "passed" if successes else "not_executed"
        print("Docker integration:", summary["docker_status"])
    (destination / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return int(any(result["exit_code"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
