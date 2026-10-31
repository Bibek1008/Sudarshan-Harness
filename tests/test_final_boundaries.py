"""Regression tests for credential-safe failures and sandbox configuration."""
import io
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from sudarshan import provider
from sudarshan.execution.sandbox import SandboxedExecutionBackend


class FinalBoundaryTests(unittest.TestCase):
    def test_provider_errors_never_expose_credentials(self):
        secret = 'fixture-private-key'
        for error in (
            HTTPError('https://example.test/?key=' + secret, 400, secret, {}, io.BytesIO(secret.encode())),
            HTTPError('https://example.test', 503, secret, {}, io.BytesIO(secret.encode())),
            URLError('https://example.test/?key=' + secret),
        ):
            with self.subTest(error=type(error).__name__), patch.object(provider, 'urlopen', side_effect=error):
                try:
                    provider._post('https://example.test', {}, retries=1)
                except RuntimeError:
                    self.assertNotIn(secret, traceback.format_exc())
                else:
                    self.fail('provider must fail')

    def test_malformed_candidate_parts_raise_provider_error(self):
        for candidate in (None, 'bad', {'content': 'bad'}, {'content': {'parts': 'bad'}},
                          {'content': {'parts': [None, {'text': 123}, {'functionCall': {}}]}}):
            with self.subTest(candidate=candidate), patch.object(provider, 'api_key', return_value='fixture'), patch.object(provider, '_post', return_value={'candidates': [candidate]}):
                with self.assertRaisesRegex(RuntimeError, 'Gemini returned no usable candidate'):
                    provider.complete('model', 'system', [], [])

    def test_sandbox_rejects_root_and_option_images(self):
        Path('work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='work') as root:
            for options in ({'image': '--privileged'}, {'image': ''}, {'user': None},
                            {'user': '0:0'}, {'user': 'root'}, {'container_workdir': '/work,other'}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    SandboxedExecutionBackend(root, **options)
            SandboxedExecutionBackend(root)
