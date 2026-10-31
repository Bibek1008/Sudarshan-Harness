"""Default approval behavior and explicit yolo opt-in."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sudarshan import cli, provider
from sudarshan.harness import Harness
from sudarshan.security import Policy


class PolicyDefaultTests(unittest.TestCase):
    def test_harness_defaults_refuse_unapproved_writes_and_children_inherit(self):
        parent = Path(__file__).resolve().parent.parent / 'work'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as root:
            harness = Harness(root, persist=False)
            self.assertEqual(harness.policy.mode, 'safe')
            self.assertIsNotNone(harness._check_tool({'name': 'write_file', 'args': {}}))
            self.assertIs(harness._make_child(1).policy, harness.policy)
            replies = [
                {'text': '', 'tool_calls': [{'name': 'write_file',
                 'args': {'path': 'blocked.txt', 'content': 'must not write'}}]},
                {'text': 'done', 'tool_calls': []},
            ]
            with patch.object(provider, 'complete', side_effect=replies):
                harness.run('attempt a write')
            self.assertFalse(Path(root, 'blocked.txt').exists())
            self.assertTrue(harness.messages[-2]['text'].startswith('BLOCKED:'))

    def test_headless_safe_refuses_write_on_eof(self):
        with patch.object(cli, 'Harness') as factory, patch('builtins.input', side_effect=EOFError), contextlib.redirect_stdout(io.StringIO()):
            cli.main(['-p', 'task'])
            policy = factory.call_args.kwargs['policy']
            self.assertEqual(policy.mode, 'safe')
            self.assertIsNotNone(policy.check({'name': 'write_file', 'args': {}}))

    def test_explicit_yolo_keeps_hard_denials(self):
        with patch.object(cli, 'Harness') as factory:
            cli.main(['-p', 'task', '--mode', 'yolo'])
        policy = factory.call_args.kwargs['policy']
        self.assertEqual(policy.mode, 'yolo')
        self.assertIsNone(policy.check({'name': 'write_file', 'args': {}}))
        self.assertIsNotNone(policy.check({'name': 'bash', 'args': {'command': 'rm / -rf'}}))

    def test_policy_defaults_to_safe_and_can_approve_explicitly(self):
        call = {'name': 'write_file', 'args': {}}
        self.assertIsNotNone(Policy().check(call))
        self.assertIsNone(Policy('safe', lambda *args: True).check(call))
