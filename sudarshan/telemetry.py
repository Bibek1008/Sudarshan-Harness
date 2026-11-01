"""Versioned metadata-only diagnostics. No transcripts, arguments or outputs."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from .paths import workspace_path

ACTIVE = ContextVar("sudarshan_telemetry", default=None)
KINDS = frozenset("session_started session_completed session_interrupted model_request_started model_request_completed model_request_failed model_retry tool_call_started tool_call_completed tool_call_failed tool_approval_requested tool_approval_granted tool_approval_denied context_compacted turn_completed execution_timeout".split())
COUNTS = ("input", "output", "total", "thought", "cached")
ERRORS = {"model_error", "tool_error", "timeout", "interrupted", "denied", "storage_error", "session_error"}
FIELDS = {"schema_version", "event_id", "session_id", "timestamp", "event_type", "turn", "model", "duration_ms", "status", "error_category", "request_id", "call_id", "tool", "backend", "approval", "usage", "cost"}


def label(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value) else "unknown"


def identifier(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("invalid telemetry identifier")
    return value


def usage_metadata(metadata):
    """Only nonnegative integral provider counts are actual measurements."""
    names = dict(zip(COUNTS, ("promptTokenCount", "candidatesTokenCount", "totalTokenCount", "thoughtsTokenCount", "cachedContentTokenCount")))
    data = metadata if isinstance(metadata, dict) else {}
    result = {key: data.get(name) if type(data.get(name)) is int and 0 <= data[name] <= 10**15 else None for key, name in names.items()}
    result["available"] = any(result[key] is not None for key in COUNTS)
    return result


def estimate_cost(usage, model, prices):
    """Explicit per-million-token prices only; never fetch or infer pricing."""
    try:
        config = prices[model]
        if not isinstance(config, dict) or config.get("thought_policy") not in {"additional_output", "included_in_output"}:
            return None
        source, effective, currency = config["source"], config["effective_date"], config["currency"]
        if not isinstance(source, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", source):
            return None
        date.fromisoformat(effective)
        if not re.fullmatch(r"[A-Z]{3}", currency):
            return None
        rates = {}
        for key in ("input", "output", "cached"):
            value = config.get(key + "_per_million")
            if value is None and key == "cached":
                continue
            if isinstance(value, bool):
                return None
            rates[key] = Decimal(str(value))
            if not rates[key].is_finite() or not 0 <= rates[key] <= 10**9:
                return None
        if usage.get("input") is None or usage.get("output") is None:
            return None
        # Unknown cache/thought counts must not silently be assumed zero.
        if usage.get("cached") is None or usage.get("thought") is None:
            return None
        if usage["cached"] > usage["input"]:
            return None
        if usage["cached"] and "cached" not in rates:
            return None
        amount = ((usage["input"] - usage["cached"]) * rates["input"] +
                  usage["cached"] * rates.get("cached", Decimal(0)) +
                  (usage["output"] + (usage["thought"] if config["thought_policy"] == "additional_output" else 0)) * rates["output"]) / Decimal(1000000)
        return {"estimated": str(amount), "currency": currency, "source": source,
                "effective_date": effective, "billing": "estimate_not_provider_bill"}
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        return None


def valid_event(event):
    try:
        if not isinstance(event, dict) or set(event) - FIELDS or type(event["schema_version"]) is not int or event["schema_version"] != 1 or event["event_type"] not in KINDS:
            return False
        identifier(event["event_id"]); identifier(event["session_id"])
        if event["event_type"].startswith("model_") and "request_id" not in event:
            return False
        if event["event_type"].startswith("tool_call_") or event["event_type"] == "execution_timeout":
            if not {"call_id", "tool", "backend"} <= set(event): return False
        stamp = datetime.fromisoformat(event["timestamp"])
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            return False
        if type(event["turn"]) is not int or event["turn"] < 0:
            return False
        for name in ("model", "tool", "backend"):
            if name in event and label(event[name]) != event[name]:
                return False
        for name in ("request_id", "call_id"):
            if name in event:
                identifier(event[name])
        if event.get("status") not in {"started", "success", "failed", "denied", "interrupted"}:
            return False
        if "duration_ms" in event and (type(event["duration_ms"]) not in {float, int} or not 0 <= event["duration_ms"] <= 10**12):
            return False
        if "approval" in event and event["approval"] not in {"requested", "granted", "denied", "not_required"}:
            return False
        if "error_category" in event and event["error_category"] not in ERRORS:
            return False
        if "usage" in event:
            usage = event["usage"]
            if not isinstance(usage, dict) or set(usage) != set(COUNTS) | {"available"} or type(usage["available"]) is not bool:
                return False
            if any(usage[key] is not None and (type(usage[key]) is not int or not 0 <= usage[key] <= 10**15) for key in COUNTS):
                return False
            if usage["available"] != any(usage[key] is not None for key in COUNTS): return False
        if "cost" in event and event["cost"] is not None:
            cost = event["cost"]
            if not isinstance(cost, dict) or set(cost) != {"estimated", "currency", "source", "effective_date", "billing"}:
                return False
            if cost["billing"] != "estimate_not_provider_bill" or not re.fullmatch(r"[A-Z]{3}", cost["currency"]) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", cost["source"]):
                return False
            date.fromisoformat(cost["effective_date"])
            if not isinstance(cost["estimated"], str) or len(cost["estimated"]) > 100: return False
            amount = Decimal(cost["estimated"])
            if not amount.is_finite() or not 0 <= amount <= 10**30:
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation):
        return False


class Store:
    """Cross-process lock, per-session rotation and bounded session retention."""
    def __init__(self, workdir, max_bytes=None, segments=None, sessions=None):
        self.workdir = Path(workdir).resolve()
        self.root = self.workdir / ".sudarshan/telemetry"
        config = self.read_json("settings.json", {})
        if not isinstance(config, dict): raise ValueError("invalid telemetry configuration")
        max_bytes = config.get("max_bytes", 1048576) if max_bytes is None else max_bytes
        segments = config.get("segments", 4) if segments is None else segments
        sessions = config.get("sessions", 100) if sessions is None else sessions
        if (any(type(value) is not int for value in (max_bytes, segments, sessions)) or
                not 4096 <= max_bytes <= 16777216 or not 1 <= segments <= 16 or not 1 <= sessions <= 10000):
            raise ValueError("invalid telemetry retention bounds")
        self.max_bytes, self.segments, self.sessions = max_bytes, segments, sessions

    def path(self, relative):
        target = (self.root / relative).absolute()
        workspace_path(self.workdir, target).relative_to(self.root)
        target.relative_to(self.root)
        # Reject existing links/reparse metadata rather than opening other files.
        for item in (target, *target.parents):
            if item == self.workdir:
                break
            if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
                raise PermissionError("telemetry links are not permitted")
            if item.exists() and item.is_file() and item.stat().st_nlink != 1:
                raise PermissionError("telemetry hard links are not permitted")
        return target

    def read_json(self, relative, default):
        try:
            target = self.path(relative)
            if target.stat().st_size > 65536: raise ValueError("telemetry configuration exceeds size bound")
            with target.open(encoding="utf-8") as handle:
                return json.loads(handle.read(65537))
        except FileNotFoundError:
            return default
        except (ValueError, UnicodeError):
            raise ValueError("invalid telemetry configuration; file preserved") from None

    def enabled(self):
        settings = self.read_json("settings.json", {})
        if not isinstance(settings, dict) or type(settings.get("enabled", True)) is not bool:
            raise ValueError("invalid telemetry configuration; file preserved")
        return settings.get("enabled", True)

    @contextmanager
    def locked(self):
        for attempt in range(4):
            try:
                self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                break
            except PermissionError as error:
                if os.name != "nt" or getattr(error, "winerror", None) != 5 or attempt == 3: raise
                time.sleep(.01 * (attempt + 1))
        target = self.path(".lock")
        fd = os.open(target, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        held = False
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            end = time.monotonic() + 10
            while True:
                try:
                    os.lseek(fd, 0, 0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held = True
                    break
                except (BlockingIOError, PermissionError, OSError):
                    if time.monotonic() >= end:
                        raise OSError("telemetry lock timeout") from None
                    time.sleep(.01)
            yield
        finally:
            if held:
                os.lseek(fd, 0, 0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def atomic_json(self, relative, value):
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".telemetry-", delete=False, mode="w", encoding="utf-8") as handle:
                temporary = Path(handle.name)
                json.dump(value, handle, allow_nan=False)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def configure(self, enabled):
        if type(enabled) is not bool: raise ValueError("enabled must be a boolean")
        with self.locked():
            config = self.read_json("settings.json", {})
            if not isinstance(config, dict): raise ValueError("invalid telemetry configuration")
            self.atomic_json("settings.json", {**config, "enabled": enabled})

    def append(self, event):
        if not valid_event(event):
            raise ValueError("invalid telemetry event")
        session = identifier(event["session_id"])
        encoded = (json.dumps(event, allow_nan=False) + "\n").encode("utf-8")
        if len(encoded) > 4096:
            raise ValueError("telemetry event exceeds record bound")
        with self.locked():
            directory = self.path("events")
            directory.mkdir(exist_ok=True, mode=0o700)
            target = self.path(f"events/{session}.jsonl")
            if target.exists() and target.stat().st_size + len(encoded) + 1 > self.max_bytes:
                last = self.path(f"events/{session}" + (f".{self.segments-1}" if self.segments > 1 else "") + ".jsonl")
                if last.exists(): last.unlink()
                for index in range(self.segments-2, -1, -1):
                    old = self.path(f"events/{session}" + (f".{index}" if index else "") + ".jsonl")
                    new = self.path(f"events/{session}.{index+1}.jsonl")
                    if old.exists(): os.replace(old, new)
            fd = os.open(target, os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "ab") as handle:
                # A torn tail remains recoverable, never concatenate a new record.
                if target.stat().st_size:
                    with target.open("rb") as previous:
                        previous.seek(-1, 2)
                        if previous.read(1) != b"\n": handle.write(b"\n")
                handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
            heads = sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            ids = []
            for item in heads:
                name = item.name.split(".")[0]
                try: identifier(name)
                except ValueError: continue
                if name not in ids: ids.append(name)
            for expired in ids[self.sessions:]:
                for item in directory.glob(expired + "*.jsonl"):
                    self.path(item).unlink()
                summary = self.path(f"summaries/{expired}.json")
                if summary.exists(): summary.unlink()

    def read(self, session):
        session = identifier(session)
        events, corrupt = [], 0
        for index in reversed(range(self.segments)):
            path = self.path(f"events/{session}" + (f".{index}" if index else "") + ".jsonl")
            if not path.exists(): continue
            with path.open("rb") as handle:
                while line := handle.readline(4097):
                    if len(line) > 4096:
                        while line and not line.endswith(b"\n"):
                            line = handle.readline(4097)
                        corrupt += 1; continue
                    try: value = json.loads(line)
                    except (ValueError, UnicodeError): corrupt += 1; continue
                    if valid_event(value) and value["session_id"] == session: events.append(value)
                    else: corrupt += 1
        return events, corrupt

    def stats(self, session=None, last=None):
        if last is not None and last < 1: raise ValueError("last must be positive")
        if session is not None: identifier(session)
        if not self.path("events").exists():
            return {"sessions": [], "aggregate": aggregate([])}
        result = []
        with self.locked():
            if session is not None: ids = [session]
            else:
                paths = sorted(self.path("events").glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                ids = []
                for path in paths:
                    name = path.name.split(".")[0]
                    try: identifier(name)
                    except ValueError: continue
                    if name not in ids: ids.append(name)
            if last is not None: ids = ids[:last]
            for value in ids:
                events, corrupt = self.read(value)
                if events: result.append(summarize(events, corrupt))
        return {"sessions": result, "aggregate": aggregate(result)}


def summarize(events, corrupt=0):
    unique = list({event["event_id"]: event for event in events}.values())
    start = next((event for event in unique if event["event_type"] == "session_started"), None)
    end = next((event for event in reversed(unique) if event["event_type"] in {"session_completed", "session_interrupted"}), None)
    requests = {event["request_id"]: event for event in unique if event["event_type"] == "model_request_completed" and "request_id" in event}
    tokens, coverage = {}, {}
    for key in COUNTS:
        values = [event.get("usage", {}).get(key) for event in requests.values()]
        measured = [value for value in values if value is not None]
        tokens[key] = sum(measured) if measured else None
        coverage[key] = {"measured_requests": len(measured), "successful_requests": len(values)}
    costs = [event.get("cost") for event in requests.values()]
    currencies = {value["currency"] for value in costs if value}
    cost = None
    if costs and all(costs) and len(currencies) == 1:
        cost = {"estimated": str(sum((Decimal(value["estimated"]) for value in costs), Decimal(0))), "currency": next(iter(currencies)), "billing": "estimate_not_provider_bill"}
    count = lambda kind: sum(event["event_type"] == kind for event in unique)
    partial = start is None or corrupt > 0
    return {"session_id": unique[0]["session_id"], "model": unique[0].get("model", "unknown"),
            "status": end["status"] if end else "incomplete_or_interrupted", "duration_ms": end.get("duration_ms") if end and "duration_ms" in end else max(0, (datetime.fromisoformat(unique[-1]["timestamp"]) - datetime.fromisoformat(start["timestamp"])).total_seconds()*1000) if start else None,
            "turns": count("turn_completed"), "model_requests": len({event["request_id"] for event in unique if event["event_type"] == "model_request_started"}),
            "retries": count("model_retry"), "tokens": tokens, "token_coverage": coverage,
            "estimated_cost": cost if not partial else None, "tool_calls": count("tool_call_started"),
            "successful_tools": count("tool_call_completed"), "failed_tools": count("tool_call_failed"),
            "denied_tools": count("tool_approval_denied"), "timeouts": count("execution_timeout"),
            "partial": partial, "corrupt_records": corrupt, "usage_scope": "successful_reported_requests_only"}


def aggregate(sessions):
    totals = {key: sum(item[key] for item in sessions) for key in ("turns", "model_requests", "retries", "tool_calls", "successful_tools", "failed_tools", "denied_tools", "timeouts")}
    totals["tokens"] = {key: sum(item["tokens"][key] for item in sessions if item["tokens"][key] is not None) if any(item["tokens"][key] is not None for item in sessions) else None for key in COUNTS}
    costs = [item["estimated_cost"] for item in sessions]
    currencies = {cost["currency"] for cost in costs if cost}
    totals["estimated_cost"] = {"estimated": str(sum((Decimal(c["estimated"]) for c in costs), Decimal(0))), "currency": next(iter(currencies)), "billing": "estimate_not_provider_bill"} if costs and all(costs) and len(currencies) == 1 else None
    totals["sessions"] = len(sessions)
    totals["partial"] = any(item["partial"] for item in sessions)
    return totals


class Recorder:
    def __init__(self, store, model):
        self.store, self.model = store, label(model)
        self.session_id = str(uuid.uuid4())
        self.turn, self.request_id, self.call_id = 0, None, None
        self.started = time.perf_counter()
        self.storage_failed = False
        self.pricing_unavailable = False
        try:
            self.prices = store.read_json("pricing.json", {})
            if not isinstance(self.prices, dict): raise ValueError("invalid pricing configuration")
        except (OSError, ValueError):
            self.prices = {}
            self.pricing_unavailable = True

    def emit(self, kind, **metadata):
        event = {"schema_version": 1, "event_id": str(uuid.uuid4()), "session_id": self.session_id,
                 "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": kind,
                 "turn": self.turn, "model": self.model, "status": "success"}
        if kind.startswith("tool_approval_") and self.call_id:
            event["call_id"] = self.call_id
        event.update(metadata)
        if not valid_event(event): raise ValueError("invalid telemetry metadata")
        try: self.store.append(event)
        except (OSError, ValueError): self.storage_failed = True
        return event

    def finish(self):
        try:
            report = self.store.stats(self.session_id)["sessions"]
            if report:
                with self.store.locked(): self.store.atomic_json(f"summaries/{self.session_id}.json", report[0])
        except (OSError, ValueError): self.storage_failed = True


def emit(kind, **metadata):
    recorder = ACTIVE.get()
    if recorder: return recorder.emit(kind, **metadata)


def request(model, operation):
    recorder = ACTIVE.get()
    if not recorder: return operation()
    previous = recorder.request_id
    request_id = str(uuid.uuid4())
    recorder.request_id = request_id
    started = time.perf_counter()
    emit("model_request_started", request_id=request_id, status="started")
    try:
        reply = operation()
        if not isinstance(reply, dict) or not isinstance(reply.get("text"), str) or not isinstance(reply.get("tool_calls"), list):
            raise RuntimeError("Model returned a malformed response")
        usage = reply.get("usage_details") if isinstance(reply, dict) else None
        if not isinstance(usage, dict): usage = {}
        usage = {key: usage.get(key) if type(usage.get(key)) is int and 0 <= usage[key] <= 10**15 else None for key in COUNTS}
        usage["available"] = any(value is not None for value in usage.values())
        emit("model_request_completed", request_id=request_id, duration_ms=(time.perf_counter()-started)*1000,
             usage=usage, cost=estimate_cost(usage, model, recorder.prices))
        return reply
    except BaseException as error:
        emit("model_request_failed", request_id=request_id, status="failed", error_category="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "model_error", duration_ms=(time.perf_counter()-started)*1000)
        raise
    finally: recorder.request_id = previous
