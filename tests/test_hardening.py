"""Day 5 hardening: permission, provider and session edge-case regressions."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sudarshan import provider, session
from sudarshan.security import Policy
from sudarshan import Harness, Tool


class HardeningTests(unittest.TestCase):
    """Reproduce independent review findings with isolated inputs."""

    def test_explicit_read_permissions(self):
        """Only core read names bypass policy; suffixes never confer authority."""
        for name in ('read_file', 'list_files', 'grep'):
            self.assertIsNone(Policy('read-only').check({'name': name}))
        for name in ('dangerous_read_file', 'custom_read_file', 'local_read_file', 'unknown'):
            self.assertIsNotNone(Policy('read-only').check({'name': name}))
            approve = Mock(return_value=False)
            self.assertIsNotNone(Policy('safe', approve).check({'name': name}))
            approve.assert_called_once()
            self.assertIsNone(Policy('yolo').check({'name': name}))

    def test_custom_core_name_override_is_restricted(self):
        """Registry-provided overrides cannot impersonate a built-in reader."""
        harness = Harness('.', persist=False, policy=Policy('read-only'),
                          extra_tools=[Tool('read_file', {}, lambda: 'effect')])
        self.assertIsNotNone(harness._check_tool({'name': 'read_file'}))

    def test_rm_argument_permutations(self):
        """Root and home targets are denied independent of flag position."""
        commands = ['rm / -rf', 'rm -rf "$HOME/.."', 'rm -rf ${HOME}/../',
                    'rm -rf / -rf', 'rm -r -f /', 'rm -rf -- /',
                    'rm --force --recursive ~/', 'echo ok && rm / -rf']
        for mode in ('safe', 'read-only', 'yolo'):
            for command in commands:
                with self.subTest(mode=mode, command=command):
                    approve = Mock(return_value=True)
                    self.assertIsNotNone(Policy(mode, approve).check({'name': 'bash', 'args': {'command': command}}))
                    approve.assert_not_called()
        self.assertIsNone(Policy('yolo').check({'name': 'bash', 'args': {'command': 'rm -rf ./scratch'}}))

    def test_key_precedence(self):
        """Primary, legacy and generic names respect explicit precedence."""
        cases = [({'SUDARSHAN_API_KEY': 'primary'}, 'primary'),
                 ({'SUDARSHAN_API_KEY': 'primary', 'ODYSSEUS_API_KEY': 'legacy', 'GEMINI_API_KEY': 'generic'}, 'primary'),
                 ({'ODYSSEUS_API_KEY': 'legacy'}, 'legacy'),
                 ({'GEMINI_API_KEY': 'generic'}, 'generic'),
                 ({'SUDARSHAN_API_KEY': '', 'GEMINI_API_KEY': 'generic'}, 'generic')]
        for environment, expected in cases:
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(provider.api_key(), expected)
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, 'SUDARSHAN_API_KEY'):
            provider.api_key()

    def test_empty_provider_responses(self):
        """Missing or unusable candidates give a clear error instead of empty success."""
        for response in ({}, {'candidates': []}, {'candidates': [{}]},
                         {'candidates': [{'content': {}}]},
                         {'candidates': [{'content': {'parts': []}}]}):
            with self.subTest(response=response), patch.object(provider, 'api_key', return_value='secret'), patch.object(provider, '_post', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'Gemini'):
                    provider.complete('m', 's', [], [])

    def test_missing_usage_defaults(self):
        """Valid content still defaults missing usage metadata to zero."""
        with patch.object(provider, 'api_key', return_value='secret'), patch.object(provider, '_post', return_value={'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}):
            self.assertEqual(provider.complete('m', 's', [], [])['usage'], {'input': 0, 'output': 0})

    def test_session_collisions(self):
        """Frozen time cannot overwrite an existing session with the same label."""
        Path('work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='work') as root, patch.object(session.time, 'time', return_value=123):
            paths = []
            for index in range(4):
                path = session.new_session(root, 'same label')
                session.append(path, {'role': 'user', 'text': str(index)})
                os.utime(path, (index + 1, index + 1))
                paths.append(path)
            self.assertEqual(len(set(paths)), 4)
            for index, path in enumerate(paths):
                self.assertEqual(session.load(path)[0]['text'], str(index))
            self.assertEqual(session.latest(root), paths[-1])
