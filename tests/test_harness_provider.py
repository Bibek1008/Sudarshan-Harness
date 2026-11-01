import io
import json
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from sudarshan import provider


class TestProvider(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"SUDARSHAN_API_KEY": "synthetic-secret"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        # Fail closed: no test can reach the real network.
        self.network = patch.object(provider, "urlopen")
        self.open = self.network.start()
        self.addCleanup(self.network.stop)
        self.sleep_patch = patch.object(provider.time, "sleep")
        self.sleep = self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def response(self, data):
        context = MagicMock()
        context.__enter__.return_value.read.return_value = data
        return context

    def test_success_and_key_not_in_url(self):
        self.open.return_value = self.response(json.dumps({
            "candidates": [{"content": {"parts": [
                {"text": "hidden", "thought": True}, {"text": "hello"},
                {"functionCall": {"name": "read_file", "args": {"path": "x"}}, "thoughtSignature": "signature"}]}}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4}
        }).encode())
        result = provider.complete("test-model", "system", [{"role": "user", "text": "hi"}], [])
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["usage"], {"input": 3, "output": 4})
        self.assertEqual(result["tool_calls"][0]["signature"], "signature")
        request = self.open.call_args.args[0]
        self.assertNotIn("synthetic-secret", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "synthetic-secret")
        self.assertEqual(self.open.call_args.kwargs["timeout"], 600)

    def test_permanent_http_errors_redacted(self):
        for status in (400, 401, 403):
            with self.subTest(status=status):
                error = HTTPError("https://invalid/?key=synthetic-secret", status,
                                  "synthetic-secret", {}, io.BytesIO(b"synthetic-secret"))
                self.open.side_effect = error
                self.open.reset_mock()
                with self.assertRaisesRegex(RuntimeError, f"Gemini HTTP {status}") as caught:
                    provider._post("https://invalid", {})
                self.assertNotIn("synthetic-secret", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertEqual(self.open.call_count, 1)
                self.assertTrue(error.fp.closed)
        self.sleep.assert_not_called()

    def test_transient_http_retry_backoff(self):
        for status in (429, 500):
            with self.subTest(status=status):
                self.open.side_effect = [HTTPError("https://invalid", status, "secret", {}, io.BytesIO()),
                                         self.response(b'{"ok": true}')]
                self.sleep.reset_mock()
                self.assertEqual(provider._post("https://invalid", {}), {"ok": True})
                self.sleep.assert_called_once_with(2)

    def test_retry_exhaustion(self):
        self.open.side_effect = URLError("synthetic-secret")
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts") as caught:
            provider._post("https://invalid", {}, retries=3)
        self.assertNotIn("synthetic-secret", str(caught.exception))
        self.assertEqual(self.open.call_count, 3)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [2, 4])

    def test_timeout_retry(self):
        self.open.side_effect = [TimeoutError("synthetic-secret"), self.response(b'{}')]
        self.assertEqual(provider._post("https://invalid", {}), {})
        self.sleep.assert_called_once_with(2)

    def test_malformed_json_and_wrong_root(self):
        for data in (b"synthetic-secret", b"", b"\xff", b"[]", b"null"):
            with self.subTest(data=data):
                self.open.return_value = self.response(data)
                with self.assertRaises(RuntimeError) as caught:
                    provider._post("https://invalid", {})
                self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_missing_empty_and_malformed_candidates(self):
        values = [{}, {"candidates": []}, {"candidates": "bad"}, {"candidates": [None]},
                  {"promptFeedback": ["bad"]}, {"promptFeedback": {"blockReason": []}},
                  {"candidates": [{"content": {"parts": [None, {"text": " "},
                    {"functionCall": {"name": "x", "args": []}}]}}]}]
        for value in values:
            with self.subTest(value=value), patch.object(provider, "_post", return_value=value):
                with self.assertRaisesRegex(RuntimeError, "no usable candidate"):
                    provider.complete("test", "", [], [])

    def test_feedback_and_usage_shape(self):
        with patch.object(provider, "_post", return_value={"promptFeedback": {"blockReason": "SAFETY"}}):
            with self.assertRaisesRegex(RuntimeError, "SAFETY"):
                provider.complete("test", "", [], [])
        with patch.object(provider, "_post", return_value={"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": [1]}):
            self.assertEqual(provider.complete("test", "", [], [])["usage"], {"input": 0, "output": 0})

    def test_api_key_precedence_and_missing(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "gemini", "ODYSSEUS_API_KEY": "legacy"}, clear=True):
            self.assertEqual(provider.api_key(), "legacy")
            with patch.dict("os.environ", {"SUDARSHAN_API_KEY": "preferred"}):
                self.assertEqual(provider.api_key(), "preferred")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Set SUDARSHAN_API_KEY"):
                provider.api_key()

    def test_invalid_model_and_retry_count(self):
        for model in ("../other", "model?key=bad", "", "bad/name"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                provider.complete(model, "", [], [])
        with self.assertRaises(ValueError):
            provider._post("https://invalid", {}, retries=0)
        self.open.assert_not_called()

    def test_wire_conversion_preserves_signatures(self):
        messages = [{"role": "user", "text": "start"},
                    {"role": "assistant", "text": "", "tool_calls": [{"name": "x", "args": {}, "signature": "sig"}]},
                    {"role": "tool", "name": "x", "text": "done"}]
        wire = provider._to_wire(messages)
        self.assertEqual(wire[1]["parts"][0]["thoughtSignature"], "sig")
        self.assertEqual(wire[2]["parts"][0]["functionResponse"]["response"], {"result": "done"})
        with self.assertRaises(ValueError):
            provider._to_wire([{"role": "invalid"}])

    def test_complete_rejects_non_object_provider_response(self):
        with patch.object(provider, "_post", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "invalid response object"):
                provider.complete("test", "", [], [])
