"""Day 1 audit: provider serialization, credentials, parsing, and HTTP retries."""

import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from sudarshan import provider


class ProviderTests(unittest.TestCase):
    """Verify vendor boundary behavior without credentials or network access."""

    def setUp(self):
        key = patch.object(provider, "api_key", return_value="synthetic-test-key")
        # Only transport tests need a synthetic key; key selection has its own test.
        if self._testMethodName != "test_keys":
            key.start()
            self.addCleanup(key.stop)

    def test_keys(self):
        """Harness-specific key wins; fallback and missing-key error remain stable."""
        with patch.dict('os.environ', {'ODYSSEUS_API_KEY': 'one', 'GEMINI_API_KEY': 'two'}, clear=True):
            self.assertEqual(provider.api_key(), 'one')
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'two'}, clear=True):
            self.assertEqual(provider.api_key(), 'two')
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(RuntimeError):
            provider.api_key()

    def test_serialization_and_response(self):
        """Thought signatures round trip while thought text stays out of user output."""
        call = {'name': 'read', 'args': {'path': 'x'}, 'signature': 'signature'}
        messages = [{'role': 'assistant', 'text': '', 'tool_calls': [call]},
                    {'role': 'tool', 'name': 'read', 'text': 'contents'}]
        response = {'candidates': [{'content': {'parts': [
            {'text': 'private', 'thought': True}, {'text': 'answer'},
            {'functionCall': {'name': 'read', 'args': {'path': 'x'}}, 'thoughtSignature': 'signature'}]}}],
            'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 20}}
        with patch.object(provider, 'api_key', return_value='fake'), patch.object(provider, '_post', return_value=response) as post:
            result = provider.complete('model', 'system', messages, [{'schema': {'name': 'read'}}])
        body = post.call_args.args[1]
        self.assertEqual(body['contents'][0]['parts'][0]['thoughtSignature'], 'signature')
        self.assertEqual(body['contents'][1]['parts'][0]['functionResponse']['response']['result'], 'contents')
        self.assertEqual(body['tools'][0]['functionDeclarations'], [{'name': 'read'}])
        self.assertEqual(body['systemInstruction']['parts'][0]['text'], 'system')
        self.assertEqual(result, {'text': 'answer', 'tool_calls': [call], 'usage': {'input': 10, 'output': 20}})

    def test_retryable_errors(self):
        """Transient HTTP and network errors follow the specified backoff."""
        errors = [HTTPError('https://example.test', code, 'error', {}, io.BytesIO(b'busy'))
                  for code in (429, 500, 502, 503)] + [URLError('offline'), TimeoutError()]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch.object(provider, 'urlopen', side_effect=[error, io.BytesIO(b'{}')]) as request, patch.object(provider.time, 'sleep') as sleep:
                self.assertEqual(provider._post('https://example.test', {}), {})
                sleep.assert_called_once_with(2)
                self.assertEqual(request.call_args.kwargs['timeout'], 600)

    def test_permanent_http_error(self):
        """Permanent failures expose status without response bodies or retries."""
        error = HTTPError('https://example.test', 400, 'bad', {}, io.BytesIO(b'x' * 500))
        with patch.object(provider, 'urlopen', side_effect=error), patch.object(provider.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 400') as raised:
                provider._post('https://example.test', {})
        self.assertLessEqual(len(str(raised.exception)), 410)
        sleep.assert_not_called()
