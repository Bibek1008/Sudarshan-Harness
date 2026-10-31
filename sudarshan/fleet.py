"""Day 5: ordered concurrent execution of independent Harness jobs.

Every job owns its Harness; input ordering is preserved despite concurrency.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


def run_fleet(jobs: list[dict[str, str]], make_harness: Callable[[str], Any], max_workers: int = 4) -> list[dict[str, object]]:
    """Run jobs concurrently and return success or error reports in input order."""
    def run(job: dict[str, str]) -> dict[str, object]:
        try:
            return {"name": job["name"], "ok": True, "report": make_harness(job["workdir"]).run(job["task"])}
        except Exception as error:
            return {"name": job["name"], "ok": False, "report": f"{type(error).__name__}: {error}"}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(run, jobs))
