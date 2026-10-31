"""Use the actual fleet approval factory, with no permissive policy replacement."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from demos.product_approval import product_harness
from sudarshan import Harness, provider


class ProductApprovalTests(unittest.TestCase):
    def setUp(self):
        parent = Path('work').resolve()
        parent.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.tmp.name)
        skill = self.root / 'skills/design-engineering/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\ndescription: Fixture\n---\nQuality fixture', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_calls(self, calls):
        harness = product_harness(self.root, persist=False)
        replies = [{'text': '', 'tool_calls': calls}, {'text': 'done', 'tool_calls': []}]
        with patch.object(provider, 'complete', side_effect=replies):
            harness.run('fixture')
        return harness

    def test_real_skill_write_edit_and_tests_work_with_filtered_credentials(self):
        code = '''import os, unittest
class Check(unittest.TestCase):
    def test_environment(self):
        for key in ('SUDARSHAN_API_KEY', 'ODYSSEUS_API_KEY', 'GEMINI_API_KEY', 'UNRELATED_TOKEN'):
            self.assertNotIn(key, os.environ)
'''
        calls = [
            {'name': 'use_skill', 'args': {'name': 'design-engineering'}},
            {'name': 'write_file', 'args': {'path': 'test_product.py', 'content': code}},
            {'name': 'write_file', 'args': {'path': 'note.txt', 'content': 'before'}},
            {'name': 'edit_file', 'args': {'path': 'note.txt', 'old': 'before', 'new': 'after'}},
            {'name': 'bash', 'args': {'command': 'python -m unittest discover -v'}},
        ]
        with patch.dict(os.environ, {key: 'fixture' for key in
                        ('SUDARSHAN_API_KEY', 'ODYSSEUS_API_KEY', 'GEMINI_API_KEY', 'UNRELATED_TOKEN')}):
            harness = self.run_calls(calls)
        results = [m['text'] for m in harness.messages if m['role'] == 'tool']
        self.assertIn('Quality fixture', results[0])
        self.assertEqual((self.root / 'note.txt').read_text(), 'after')
        self.assertIn('exit 0', results[-1])
        self.assertIn('Ran 1 test', results[-1])

    def test_escapes_unknown_skills_and_unrestricted_shell_are_refused(self):
        outside = self.root.parent / (self.root.name + '-outside.txt')
        calls = [
            {'name': 'write_file', 'args': {'path': '../' + outside.name, 'content': 'bad'}},
            {'name': 'write_file', 'args': {'path': str(outside), 'content': 'bad'}},
            {'name': 'edit_file', 'args': {'path': '../' + outside.name, 'old': 'x', 'new': 'y'}},
            {'name': 'use_skill', 'args': {'name': 'other'}},
            {'name': 'bash', 'args': {'command': 'python -c "print(1)"'}},
            {'name': 'bash', 'args': {'command': 'python -m unittest discover -v && echo unsafe'}},
            {'name': 'write_file', 'args': {'path': 'skills/design-engineering/SKILL.md', 'content': 'bad'}},
        ]
        harness = self.run_calls(calls)
        self.assertFalse(outside.exists())
        self.assertTrue(all(m['text'].startswith('BLOCKED:')
                            for m in harness.messages if m['role'] == 'tool'))
        with self.assertRaises(PermissionError):
            harness.tools['write_file'].run('../' + outside.name, 'bad')
        with self.assertRaises(PermissionError):
            harness.tools['read_file'].run('../' + outside.name)

    def test_dangerous_commands_keep_hard_deny_and_ordinary_harness_is_safe(self):
        harness = product_harness(self.root, persist=False)
        self.assertEqual(harness.policy.mode, 'safe')
        self.assertEqual(Harness(self.root, persist=False).policy.mode, 'safe')
        for command in ('rm -rf /tmp/..', 'find /var/.. -delete', 'sudo id'):
            self.assertIn('never allowed', harness._check_tool({'name': 'bash', 'args': {'command': command}}))
            self.assertIn('BLOCKED:', harness.tools['bash'].run(command))
