"""Capability and failure classification, independent of an installed browser."""
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from demos import browser_probe
from tests import test_browser_probe as browser_tests


class BrowserCapabilityTests(unittest.TestCase):
    def test_missing_executable(self):
        with patch.object(browser_probe, 'browser_executable', return_value=None), patch.object(browser_probe.subprocess, 'run') as run:
            capability = browser_probe.browser_capability_preflight()
        self.assertFalse(capability.available)
        self.assertIn('no browser executable found', capability.reason)
        run.assert_not_called()

    def test_present_but_secure_launch_refused(self):
        reason = 'Running as root without a usable sandbox is not supported'
        with patch.object(browser_probe.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr=reason)) as run:
            capability = browser_probe.browser_capability_preflight('chromium')
        self.assertFalse(capability.available)
        self.assertIn(reason, capability.reason)
        self.assertIn('exit 1', capability.reason)
        self.assertNotIn('--no-sandbox', run.call_args.args[0])
        self.assertIn('--headless', run.call_args.args[0])
        self.assertIn('--dump-dom', run.call_args.args[0])

    def test_successful_secure_launch(self):
        response = '<pre id="sudarshan-probe-result">{"viewport":768,"words":2,"sections":0,"svgs":0,"checks":{}}</pre>'
        with patch.object(browser_probe.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=response, stderr='')) as run:
            capability = browser_probe.browser_capability_preflight('chromium')
        self.assertTrue(capability.available)
        self.assertEqual(capability.executable, 'chromium')
        self.assertNotIn('--no-sandbox', run.call_args.args[0])

    def test_os_errors_and_timeouts_have_exact_reasons(self):
        for error, reason in ((PermissionError('launch denied'), 'launch denied'),
                              (subprocess.TimeoutExpired('chromium', 40), 'timed out after 40 seconds')):
            with self.subTest(error=type(error).__name__), patch.object(browser_probe.subprocess, 'run', side_effect=error):
                capability = browser_probe.browser_capability_preflight('chromium')
            self.assertFalse(capability.available)
            self.assertIn(reason, capability.reason)

    def test_only_preflight_unavailability_skips_tests(self):
        class Fixture(browser_tests.BrowserProbeTests):
            def test_only(self):
                self.fail('must not run when runtime unavailable')
        reason = 'Secure runtime unavailable: fixture sandbox refusal'
        with patch('tests.test_browser_probe.browser_capability_preflight', return_value=browser_probe.BrowserCapability(False, 'chromium', reason)):
            result = unittest.TestResult()
            unittest.TestSuite([Fixture('test_only')]).run(result)
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.skipped[0][1], reason)
        self.assertFalse(result.failures or result.errors)

    def test_assertion_after_success_is_failure_not_skip(self):
        class Fixture(browser_tests.BrowserProbeTests):
            def test_only(self):
                self.assertTrue(False, 'actual browser assertion failed')
        with patch('tests.test_browser_probe.browser_capability_preflight', return_value=browser_probe.BrowserCapability(True, 'chromium', 'ready')):
            result = unittest.TestResult()
            unittest.TestSuite([Fixture('test_only')]).run(result)
        self.assertEqual(len(result.failures), 1)
        self.assertFalse(result.skipped)

    def test_product_failure_after_launch_is_error_not_skip(self):
        class Fixture(browser_tests.BrowserProbeTests):
            def test_only(self):
                raise ValueError('product failed to produce expected observations')
        with patch('tests.test_browser_probe.browser_capability_preflight', return_value=browser_probe.BrowserCapability(True, 'chromium', 'ready')):
            result = unittest.TestResult()
            unittest.TestSuite([Fixture('test_only')]).run(result)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(result.skipped)
