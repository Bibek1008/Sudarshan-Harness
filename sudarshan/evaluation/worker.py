"""Trusted worker entrypoint. No API key, hidden tests or personal files supplied."""
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import URLError

class ProviderUnavailable(RuntimeError):
    pass
from ..harness import Harness
from ..security import Policy
from .. import provider, telemetry


def execute(config):
    deadline = time.monotonic() + config["seconds"]
    replies = iter(config.get("mock_replies", []))
    def complete(model, system, messages, tools):
        if config["mode"] == "mock":
            try: return next(replies)
            except StopIteration: raise RuntimeError("mock response budget exhausted") from None
        wire = json.dumps({"system": system, "messages": messages, "tools": tools}).encode()
        endpoint = config["broker"]
        request = Request(endpoint["url"], data=wire, headers={"Content-Type": "application/json", "Authorization": "Bearer " + endpoint["capability"]})
        try:
            with build_opener(ProxyHandler({})).open(request, timeout=max(.1, deadline-time.monotonic())) as response:
                data = json.loads(response.read(2097153))
        except (URLError, TimeoutError, ValueError):
            raise ProviderUnavailable("provider unavailable") from None
        if not isinstance(data, dict): raise ProviderUnavailable("broker protocol unavailable")
        retries = data.pop("_broker_retries", 0)
        if type(retries) is not int or not 0 <= retries <= 100: raise ProviderUnavailable("broker retry metadata unavailable")
        recorder = telemetry.ACTIVE.get()
        if recorder:
            for _ in range(retries):
                telemetry.emit("model_retry", request_id=recorder.request_id, status="started", error_category="model_error")
        if data.get("_broker_failure") is True: raise ProviderUnavailable("provider unavailable")
        return data
    provider.complete = complete
    approved = config["approve_workspace_edits"]
    def approver(call, reason):
        return approved and call.get("name") in {"write_file", "edit_file"}
    harness = Harness(config["workspace"], model=config["model"], policy=Policy("safe", approver),
                      max_turns=max(0, config["turns"]-1), budget_tokens=16000,
                      persist=False, telemetry=True, enable_subagents=False)
    status = "completed"
    try: harness.run(config["instructions"])
    except ProviderUnavailable: status = "unavailable"
    except KeyboardInterrupt: status = "interrupted"
    except Exception: status = "failed"
    summaries = telemetry.Store(config["workspace"]).stats()["sessions"]
    metrics = summaries[0] if len(summaries) == 1 and not harness.telemetry_storage_failed else None
    return {"schema_version": 1, "execution_status": status, "metrics": metrics}


if __name__ == "__main__":
    # Module invoked through an isolated -I -S bootstrap, never PYTHONPATH.
    try:
        config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = execute(config)
        print(json.dumps(result))
    except BaseException:
        print(json.dumps({"schema_version": 1, "execution_status": "failed", "metrics": None}))
        raise SystemExit(1)
