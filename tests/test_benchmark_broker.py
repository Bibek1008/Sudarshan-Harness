"""Actual loopback transport with MOCKED provider; never a real Gemini call."""
import io
import json
import time
from urllib.error import URLError,HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from unittest.mock import patch
import unittest
from sudarshan import provider
from sudarshan.evaluation.broker import Broker


class BenchmarkBrokerTests(unittest.TestCase):
    def test_loopback_model_fixed_and_usage_preserved(self):
        reply={"text":"PRIVATE_RESPONSE","tool_calls":[],"usage_details":{"input":3}}
        with patch.object(provider,"complete",return_value=reply) as complete:
            with Broker("gemini-test",time.monotonic()+5,1) as endpoint:
                request=Request(endpoint["url"],data=json.dumps({"system":"PRIVATE_PROMPT","messages":[],"tools":[]}).encode(),headers={"Authorization":"Bearer "+endpoint["capability"]})
                with build_opener(ProxyHandler({})).open(request,timeout=3) as response: value=json.loads(response.read())
                self.assertEqual(value["usage_details"]["input"],3)
                with self.assertRaises(HTTPError): build_opener(ProxyHandler({})).open(request,timeout=3)
        self.assertEqual(complete.call_args.args[0],"gemini-test")
        self.assertEqual(complete.call_count,1)

    def test_bad_capability_never_calls_provider(self):
        with patch.object(provider,"complete",side_effect=AssertionError("no API")) as complete:
            with Broker("gemini-test",time.monotonic()+5,1) as endpoint:
                request=Request(endpoint["url"],data=b'{}',headers={"Authorization":"Bearer bad"})
                with self.assertRaises(HTTPError) as error: build_opener(ProxyHandler({})).open(request,timeout=3)
                self.assertEqual(error.exception.code,403)
        complete.assert_not_called()

    def test_provider_deadline_bounds_transport_and_backoff(self):
        scope=provider.REQUEST_DEADLINE.set(time.monotonic()+.25)
        try:
            with patch.object(provider,"api_key",return_value="synthetic"),patch.object(provider,"urlopen",side_effect=URLError("PRIVATE_SECRET")) as request,patch.object(provider.time,"sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError,"deadline"): provider._post("https://example.invalid",{})
            self.assertLessEqual(request.call_args.kwargs["timeout"],.25)
            sleep.assert_not_called()
        finally: provider.REQUEST_DEADLINE.reset(scope)

    def test_worker_broker_flow_with_mock_provider_and_no_key_access(self):
        from pathlib import Path
        import tempfile
        from sudarshan.evaluation.runner import run_suite
        from tests.evaluation_samples import replies
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch.object(provider,"complete",side_effect=replies("slug")) as complete,patch.object(provider,"api_key",side_effect=AssertionError("real keys forbidden")) as key:
                result=run_suite(directory,model="gemini-test",task_ids=["slug"],live=True,approve_workspace_edits=True)
            self.assertEqual(result["summary"]["passed"],1)
            self.assertEqual(complete.call_count,2)
            key.assert_not_called()
            for call in complete.call_args_list:
                self.assertNotIn("core/verifiers",json.dumps(call.args))

    def test_provider_infrastructure_failure_is_inconclusive_not_success(self):
        from pathlib import Path
        import tempfile
        from sudarshan.evaluation.runner import run_suite
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch.object(provider,"complete",side_effect=RuntimeError("PRIVATE_QUOTA")):
                result=run_suite(directory,model="gemini-test",task_ids=["slug"],live=True)
        self.assertEqual(result["trials"][0]["status"],"inconclusive")
        self.assertEqual(result["trials"][0]["error_category"],"provider_unavailable")
        self.assertNotIn("PRIVATE_QUOTA",json.dumps(result))

    def test_failed_request_retry_counts_survive_rpc_without_raw_errors(self):
        from pathlib import Path
        import tempfile
        from sudarshan import telemetry
        from sudarshan.evaluation.runner import run_suite
        def fail(*args):
            recorder=telemetry.ACTIVE.get()
            for _ in range(2): telemetry.emit("model_retry",request_id=recorder.request_id,status="started",error_category="model_error")
            raise RuntimeError("PRIVATE_PROVIDER_ERROR")
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch.object(provider,"complete",side_effect=fail):
                result=run_suite(directory,model="gemini-test",task_ids=["slug"],live=True)
        trial=result["trials"][0]
        self.assertEqual(trial["status"],"inconclusive")
        self.assertEqual(trial["metrics"]["retries"],2)
        self.assertIsNone(trial["metrics"]["tokens"]["input"])
        self.assertNotIn("PRIVATE_PROVIDER_ERROR",json.dumps(result))
