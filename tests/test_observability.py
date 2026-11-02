from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import Mock, patch, MagicMock
from urllib.error import HTTPError

from sudarshan import telemetry as t, provider, session
from sudarshan.cli import main
from sudarshan.harness import Harness
from sudarshan.security import Policy
from sudarshan.tools import Tool
from sudarshan.execution.base import ExecutionTimeout
from sudarshan.environment import safe_shell_environment
from tests.test_harness_security import WorkspaceCase

META = {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 125,
        "thoughtsTokenCount": 5, "cachedContentTokenCount": 40}
PRICE = {"input_per_million": "2", "output_per_million": "4", "cached_per_million": ".5",
         "currency": "USD", "source": "test-fixture-not-real-pricing", "effective_date": "2026-01-01", "thought_policy": "additional_output"}


def answer(text="done", calls=None, usage=True):
    value = {"text": text, "tool_calls": calls or []}
    if usage: value["usage_details"] = t.usage_metadata(META)
    return value


class ObservabilityTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.store = t.Store(self.root)

    def run_session(self, replies, policy=None, tools=None, **options):
        harness = Harness(self.root, model="test-model", persist=False, telemetry=True,
                          policy=policy, extra_tools=tools, enable_subagents=False, **options)
        with patch.object(provider, "complete", side_effect=replies):
            harness.run("prompt synthetic-secret PRIVATE_PROMPT")
        return harness, self.store.stats(harness.last_telemetry_session)["sessions"][0]

    def events(self, harness):
        return self.store.read(harness.last_telemetry_session)[0]

    def test_schema_utc_ids_and_no_payload_fields(self):
        harness, summary = self.run_session([answer()])
        for event in self.events(harness):
            self.assertTrue(t.valid_event(event))
            self.assertEqual(datetime.fromisoformat(event["timestamp"]).utcoffset(), timedelta(0))
            self.assertEqual(str(uuid.UUID(event["event_id"])), event["event_id"])
            self.assertLessEqual(set(event), t.FIELDS)
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["turns"], 1)
        self.assertGreaterEqual(summary["duration_ms"], 0)

    def test_schema_rejects_unknown_fields_and_bad_types(self):
        recorder = t.Recorder(self.store, "test-model")
        event = recorder.emit("session_started", status="started")
        for update in ({"prompt": "secret"}, {"schema_version": 2}, {"schema_version": True}, {"turn": -1}, {"status": "raw secret"}, {"timestamp": "2026-01-01T00:00:00"}, {"event_id": "../x"}, {"duration_ms": float("nan")}):
            self.assertFalse(t.valid_event({**event, **update}))
        with self.assertRaises(ValueError): recorder.emit("turn_completed", arguments="secret")

    def test_real_usage_fields(self):
        usage = t.usage_metadata(META)
        self.assertEqual([usage[k] for k in t.COUNTS], [100, 20, 125, 5, 40])
        self.assertTrue(usage["available"])

    def test_missing_and_malformed_usage(self):
        for value in (None, [], "bad", {}, {"promptTokenCount": True, "candidatesTokenCount": -1, "totalTokenCount": "125"}):
            usage = t.usage_metadata(value)
            self.assertFalse(usage["available"])
            self.assertTrue(all(usage[key] is None for key in t.COUNTS))
        self.assertEqual(t.usage_metadata({"promptTokenCount": 0})["input"], 0)

    def test_partial_usage_never_estimates_total(self):
        usage = t.usage_metadata({"promptTokenCount": 8, "candidatesTokenCount": 3})
        self.assertIsNone(usage["total"])
        self.assertIsNone(t.estimate_cost(usage, "test-model", {"test-model": PRICE}))

    def test_configured_cost_decimal_and_provenance(self):
        cost = t.estimate_cost(t.usage_metadata(META), "test-model", {"test-model": PRICE})
        self.assertEqual(cost["estimated"], "0.00024")
        self.assertEqual(cost["source"], PRICE["source"])
        self.assertEqual(cost["billing"], "estimate_not_provider_bill")

    def test_missing_and_invalid_pricing_is_unavailable(self):
        usage = t.usage_metadata(META)
        for prices in ({}, {"other": PRICE}, {"test-model": {**PRICE, "output_per_million": "NaN"}}, {"test-model": {**PRICE, "effective_date": "bad"}}, {"test-model": {**PRICE, "thought_policy": "guess"}}):
            self.assertIsNone(t.estimate_cost(usage, "test-model", prices))

    def test_cached_tokens_not_double_charged_and_thought_policy(self):
        cost = t.estimate_cost(t.usage_metadata(META), "m", {"m": {**PRICE, "thought_policy": "included_in_output"}})
        self.assertEqual(cost["estimated"], "0.00022")
        self.assertIsNone(t.estimate_cost({**t.usage_metadata(META), "cached": 101}, "m", {"m": PRICE}))

    def test_multi_request_session_and_cumulative_cost(self):
        with self.store.locked(): self.store.atomic_json("pricing.json", {"test-model": PRICE})
        tool = Tool("check", {"schema": {"name": "check"}}, lambda: "private output")
        harness, summary = self.run_session([answer("", [{"name": "check", "args": {}}]), answer()], Policy("yolo"), [tool])
        self.assertEqual(summary["model_requests"], 2)
        self.assertEqual(summary["tokens"]["input"], 200)
        self.assertEqual(summary["estimated_cost"]["estimated"], "0.00048")
        self.run_session([answer()])
        self.assertEqual(self.store.stats()["aggregate"]["tokens"]["input"], 300)
        self.assertEqual(self.store.stats()["aggregate"]["estimated_cost"]["estimated"], "0.00072")

    def test_usage_deduplicates_events_and_request_ids(self):
        harness, _ = self.run_session([answer()])
        events = self.events(harness)
        request = next(e for e in events if e["event_type"] == "model_request_completed")
        self.store.append(request)
        self.store.append({**request, "event_id": str(uuid.uuid4())})
        summary = self.store.stats(harness.last_telemetry_session)["sessions"][0]
        self.assertEqual(summary["tokens"]["input"], 100)

    def test_retry_records_no_failed_attempt_token_charge(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"candidates": [{"content": {"parts": [{"text": "done"}]}}], "usageMetadata": META}).encode()
        error = HTTPError("https://example.invalid", 429, "synthetic-secret", {}, io.BytesIO())
        harness = Harness(self.root, model="test-model", persist=False, telemetry=True)
        with patch.object(provider, "urlopen", side_effect=[error, response]), patch.object(provider, "api_key", return_value="fake"), patch.object(provider.time, "sleep"):
            harness.run("PRIVATE_PROMPT")
        summary = self.store.stats(harness.last_telemetry_session)["sessions"][0]
        self.assertEqual(summary["model_requests"], 1)
        self.assertEqual(summary["retries"], 1)
        self.assertEqual(summary["tokens"]["input"], 100)
        self.assertNotIn("synthetic-secret", json.dumps(self.events(harness)))

    def test_failed_model_request_sanitized(self):
        harness = Harness(self.root, persist=False, telemetry=True)
        with patch.object(provider, "complete", side_effect=RuntimeError("api_key=synthetic-secret")):
            with self.assertRaises(RuntimeError): harness.run("PRIVATE_PROMPT")
        events = self.events(harness)
        self.assertIn("model_request_failed", [e["event_type"] for e in events])
        summary = self.store.stats(harness.last_telemetry_session)["sessions"][0]
        self.assertEqual(summary["status"], "failed")
        self.assertIsNone(summary["tokens"]["input"])
        self.assertNotIn("synthetic-secret", json.dumps(events))

    def test_approved_multi_tool_lifecycle(self):
        first = Tool("first", {"schema": {"name": "first"}}, lambda: "PRIVATE_OUTPUT")
        second = Tool("second", {"schema": {"name": "second"}}, lambda: "done")
        harness, summary = self.run_session([answer("", [{"name": "first", "args": {}}, {"name": "second", "args": {}}]), answer()], Policy("safe", lambda *args: True), [first, second])
        kinds = [event["event_type"] for event in self.events(harness)]
        self.assertEqual(kinds.count("tool_approval_requested"), 2)
        self.assertEqual(kinds.count("tool_approval_granted"), 2)
        self.assertEqual(summary["successful_tools"], 2)
        approvals = [e for e in self.events(harness) if e["event_type"] == "tool_approval_granted"]
        self.assertTrue(all("call_id" in event for event in approvals))

    def test_denial_distinct_from_failure(self):
        tool = Tool("check", {"schema": {"name": "check"}}, Mock())
        harness, summary = self.run_session([answer("", [{"name": "check", "args": {}}]), answer()], Policy("read-only"), [tool])
        self.assertEqual(summary["denied_tools"], 1)
        self.assertEqual(summary["failed_tools"], 0)
        tool.run.assert_not_called()

    def test_timeout_and_failed_tool(self):
        tool = Tool("check", {"schema": {"name": "check"}}, Mock(side_effect=ExecutionTimeout("PRIVATE_OUTPUT")))
        harness, summary = self.run_session([answer("", [{"name": "check", "args": {}}]), answer()], Policy("yolo"), [tool])
        self.assertEqual(summary["failed_tools"], 1)
        self.assertEqual(summary["timeouts"], 1)
        self.assertNotIn("PRIVATE_OUTPUT", json.dumps(self.events(harness)))

    def test_interrupted_session_and_active_context_reset(self):
        harness = Harness(self.root, telemetry=True, persist=False)
        with patch.object(provider, "complete", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): harness.run("PRIVATE_PROMPT")
        self.assertIsNone(t.ACTIVE.get())
        self.assertEqual(self.store.stats()["sessions"][0]["status"], "interrupted")

    def test_crash_without_terminal_event_is_incomplete(self):
        recorder = t.Recorder(self.store, "m")
        recorder.emit("session_started", status="started")
        self.assertEqual(self.store.stats()["sessions"][0]["status"], "incomplete_or_interrupted")

    def test_privacy_storage_and_trace(self):
        tool = Tool("echo", {"schema": {"name": "echo"}}, lambda **args: "PRIVATE_OUTPUT synthetic-secret")
        harness, _ = self.run_session([answer("PRIVATE_RESPONSE", [{"name": "echo", "args": {"content": "PRIVATE_ARGUMENT", "signature": "PRIVATE_SIGNATURE"}}]), answer()], Policy("yolo"), [tool])
        for file in self.store.root.rglob("*"):
            if file.is_file():
                contents = file.read_text(encoding="utf-8")
                for private in ("PRIVATE_PROMPT", "PRIVATE_OUTPUT", "PRIVATE_RESPONSE", "PRIVATE_ARGUMENT", "PRIVATE_SIGNATURE", "synthetic-secret"):
                    self.assertNotIn(private, contents)

    def test_telemetry_disabled_has_no_event_files(self):
        self.store.configure(False)
        harness = Harness(self.root, telemetry=True, persist=False)
        with patch.object(provider, "complete", return_value=answer()): harness.run("private")
        self.assertFalse((self.store.root / "events").exists())
        self.assertIsNone(harness.last_telemetry_session)

    def test_explicit_opt_out_has_no_telemetry_directory(self):
        harness = Harness(self.root, telemetry=False, persist=False)
        with patch.object(provider, "complete", return_value=answer()): harness.run("private")
        self.assertFalse(self.store.root.exists())

    def test_concurrent_threads(self):
        recorder = t.Recorder(self.store, "m")
        recorder.emit("session_started", status="started")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: recorder.emit("turn_completed"), range(80)))
        self.assertEqual(self.store.stats()["sessions"][0]["turns"], 80)

    def test_concurrent_processes(self):
        recorder = t.Recorder(self.store, "m")
        recorder.emit("session_started", status="started")
        source = str(Path(__file__).resolve().parents[1])
        code = "import sys; sys.path.insert(0,sys.argv[1]); from sudarshan.telemetry import Store,Recorder; r=Recorder(Store(sys.argv[2]),'m'); r.session_id=sys.argv[3]; [r.emit('turn_completed') for _ in range(12)]"
        def child(_):
            result = subprocess.run([sys.executable, "-I", "-S", "-c", code, source, str(self.root), recorder.session_id], env=safe_shell_environment(), cwd=self.root, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
        with ThreadPoolExecutor(max_workers=3) as pool: list(pool.map(child, range(3)))
        self.assertEqual(self.store.stats()["sessions"][0]["turns"], 36)

    def test_corrupt_jsonl_skipped_and_preserved(self):
        harness, _ = self.run_session([answer()])
        target = self.store.path(f"events/{harness.last_telemetry_session}.jsonl")
        with target.open("ab") as handle: handle.write(b'not JSON\n\xff\n')
        original = target.read_bytes()
        summary = self.store.stats()["sessions"][0]
        self.assertEqual(summary["corrupt_records"], 2)
        self.assertTrue(summary["partial"])
        self.assertEqual(target.read_bytes(), original)

    def test_torn_tail_append_remains_readable(self):
        recorder = t.Recorder(self.store, "m")
        recorder.emit("session_started", status="started")
        target = self.store.path(f"events/{recorder.session_id}.jsonl")
        with target.open("ab") as handle: handle.write(b'{torn')
        recorder.emit("turn_completed")
        summary = self.store.stats()["sessions"][0]
        self.assertEqual(summary["turns"], 1)
        self.assertEqual(summary["corrupt_records"], 1)

    def test_rotation_bounded_and_partial_marked(self):
        store = t.Store(self.root, max_bytes=4096, segments=2)
        recorder = t.Recorder(store, "m")
        recorder.emit("session_started", status="started")
        for _ in range(50): recorder.emit("turn_completed")
        files = list((store.root / "events").glob("*.jsonl"))
        self.assertLessEqual(len(files), 2)
        self.assertTrue(all(path.stat().st_size <= 4096 for path in files))
        self.assertTrue(store.stats()["sessions"][0]["partial"])

    def test_single_segment_rotation(self):
        store = t.Store(self.root, max_bytes=4096, segments=1)
        recorder = t.Recorder(store, "m")
        for _ in range(30): recorder.emit("turn_completed")
        self.assertEqual(len(list((store.root / "events").glob("*.jsonl"))), 1)
        self.assertLessEqual(next((store.root / "events").glob("*.jsonl")).stat().st_size, 4096)

    def test_session_retention(self):
        store = t.Store(self.root, sessions=2)
        for _ in range(4): t.Recorder(store, "m").emit("session_started", status="started")
        self.assertEqual(len(store.stats()["sessions"]), 2)

    def test_atomic_failure_preserves_settings_and_cleans_temporary(self):
        self.store.configure(True)
        before = self.store.path("settings.json").read_bytes()
        with patch.object(t.os, "replace", side_effect=OSError("synthetic-secret")):
            with self.assertRaises(OSError): self.store.configure(False)
        self.assertEqual(self.store.path("settings.json").read_bytes(), before)
        self.assertFalse(list(self.store.root.glob(".telemetry-*")))

    def test_storage_failure_does_not_break_agent(self):
        with patch.object(t.Store, "append", side_effect=OSError("synthetic-secret")):
            harness, _ = self.run_session_no_stats()
        self.assertTrue(harness.telemetry_storage_failed)

    def run_session_no_stats(self):
        harness = Harness(self.root, persist=False, telemetry=True)
        with patch.object(provider, "complete", return_value=answer()): result = harness.run("private")
        return harness, result

    def test_cli_stats_trace_json_and_toggles(self):
        harness, _ = self.run_session([answer()])
        for command in (["stats", "--json"], ["stats", "--last", "1", "--json"], ["trace", "--session", harness.last_telemetry_session, "--json"]):
            output = io.StringIO()
            with redirect_stdout(output): main([*command, "-d", str(self.root)])
            self.assertIsInstance(json.loads(output.getvalue()), dict)
        with redirect_stdout(io.StringIO()): main(["telemetry", "--disable", "-d", str(self.root)])
        self.assertFalse(self.store.enabled())
        with redirect_stdout(io.StringIO()): main(["telemetry", "--enable", "-d", str(self.root)])
        self.assertTrue(self.store.enabled())

    def test_cli_empty_and_invalid_identifier_errors(self):
        output = io.StringIO()
        with redirect_stdout(output): main(["stats", "-d", str(self.root)])
        self.assertIn("No telemetry", output.getvalue())
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["trace", "--session", "../private", "-d", str(self.root)])
        self.assertEqual(caught.exception.code, 1)

    def test_existing_session_format_unchanged(self):
        harness = Harness(self.root, telemetry=True)
        with patch.object(provider, "complete", return_value=answer()): harness.run("private")
        restored = session.load(harness.session_path)
        self.assertEqual([m["role"] for m in restored], ["user", "assistant"])
        self.assertFalse(any("event_type" in m for m in restored))

    def test_restrictive_permissions_where_supported(self):
        if os.name == "nt": self.skipTest("Windows uses inherited ACLs, not POSIX mode bits")
        harness, _ = self.run_session([answer()])
        self.assertEqual(self.store.path(f"events/{harness.last_telemetry_session}.jsonl").stat().st_mode & 0o777, 0o600)

    def test_compaction_request_accounted_separately(self):
        harness = Harness(self.root, persist=False, telemetry=True, budget_tokens=1)
        harness.messages = [{"role": "user", "text": "PRIVATE_CONTEXT" * 50} for _ in range(9)]
        with patch.object(provider, "complete", side_effect=[answer("PRIVATE_SUMMARY"), answer()]):
            harness.run("PRIVATE_PROMPT")
        events = self.events(harness)
        self.assertIn("context_compacted", [e["event_type"] for e in events])
        summary = self.store.stats()["sessions"][0]
        self.assertEqual(summary["model_requests"], 2)
        self.assertEqual(summary["tokens"]["input"], 200)
        self.assertNotIn("PRIVATE_CONTEXT", json.dumps(events))

    def test_trace_rejects_injected_payload_record(self):
        harness, _ = self.run_session([answer()])
        event = {**self.events(harness)[0], "prompt": "PRIVATE_INJECTED"}
        with self.store.path(f"events/{harness.last_telemetry_session}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        output = io.StringIO()
        with redirect_stdout(output): main(["trace", "--session", harness.last_telemetry_session, "--json", "-d", str(self.root)])
        self.assertNotIn("PRIVATE_INJECTED", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["corrupt_records"], 1)

    def test_config_corruption_preserved_and_errors_sanitized(self):
        self.store.configure(True)
        path = self.store.path("settings.json")
        path.write_text("{PRIVATE_CONFIG", encoding="utf-8")
        with redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
            main(["stats", "--session", "invalid", "-d", str(self.root)])
        self.assertNotIn("PRIVATE_CONFIG", error.getvalue())
        with self.assertRaises(ValueError): self.store.enabled()
        self.assertEqual(path.read_text(encoding="utf-8"), "{PRIVATE_CONFIG")

    def test_stale_summary_does_not_override_event_truth(self):
        harness, _ = self.run_session([answer()])
        with self.store.locked():
            self.store.atomic_json(f"summaries/{harness.last_telemetry_session}.json", {"status": "PRIVATE_FAKE"})
        self.assertEqual(self.store.stats()["sessions"][0]["status"], "success")

    def test_malformed_usage_details_in_model_double_is_unavailable(self):
        harness, summary = self.run_session([{**answer(), "usage_details": {"input": "PRIVATE_USAGE", "output": True}}])
        self.assertIsNone(summary["tokens"]["input"])
        self.assertNotIn("PRIVATE_USAGE", json.dumps(self.events(harness)))

    def test_cli_no_telemetry_flag_preserves_headless_behavior(self):
        with patch("sudarshan.cli.Harness") as harness:
            main(["--no-telemetry", "-p", "PRIVATE_PROMPT", "-d", str(self.root)])
        self.assertFalse(harness.call_args.kwargs["telemetry"])
        harness.return_value.run.assert_called_once_with("PRIVATE_PROMPT")

    def test_retention_settings_survive_enable_disable(self):
        with self.store.locked(): self.store.atomic_json("settings.json", {"enabled": True, "max_bytes": 4096, "segments": 2, "sessions": 3})
        configured = t.Store(self.root)
        self.assertEqual((configured.max_bytes, configured.segments, configured.sessions), (4096, 2, 3))
        configured.configure(False)
        self.assertEqual(t.Store(self.root).segments, 2)
        self.assertFalse(t.Store(self.root).enabled())
        with self.assertRaises(ValueError): configured.configure("false")

    def test_invalid_retention_bounds_rejected(self):
        for config in ({"max_bytes": 1}, {"segments": 0}, {"sessions": True}):
            with self.store.locked(): self.store.atomic_json("settings.json", config)
            with self.assertRaises(ValueError): t.Store(self.root)

    def test_invalid_pricing_file_does_not_disable_other_metrics(self):
        with self.store.locked(): self.store.atomic_json("pricing.json", {})
        self.store.path("pricing.json").write_text("PRIVATE_BAD_JSON", encoding="utf-8")
        harness, summary = self.run_session([answer()])
        self.assertEqual(summary["tokens"]["input"], 100)
        self.assertIsNone(summary["estimated_cost"])
        self.assertNotIn("PRIVATE_BAD_JSON", json.dumps(self.events(harness)))

    def test_cumulative_cost_does_not_mix_currencies(self):
        for currency in ("USD", "EUR"):
            with self.store.locked(): self.store.atomic_json("pricing.json", {"test-model": {**PRICE, "currency": currency}})
            self.run_session([answer()])
        self.assertIsNone(self.store.stats()["aggregate"]["estimated_cost"])

    def test_backend_trace_uses_adapter_identity_not_prefix_guess(self):
        from sudarshan.execution.base import backend_tools, ExecutionResult
        backend = Mock()
        backend.name = "ssh"
        backend.read_file.return_value = ExecutionResult("PRIVATE_FILE", "", 0, "ssh", 0)
        tools = backend_tools(backend, "different_prefix")
        harness, _ = self.run_session([answer("", [{"name": "different_prefix_read_file", "args": {"path": "PRIVATE_PATH"}}]), answer()], Policy("yolo"), tools)
        trace = next(event for event in self.events(harness) if event["event_type"] == "tool_call_completed")
        self.assertEqual(trace["backend"], "ssh")
        self.assertNotIn("PRIVATE_FILE", json.dumps(self.events(harness)))
