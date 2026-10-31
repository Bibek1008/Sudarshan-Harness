"""Day 2 audit: real filesystem tools and loop failure isolation."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sudarshan import loop
from sudarshan.tools import core_tools


class LoopToolsTests(unittest.TestCase):
    """Check actual tool effects and transcript ordering across error paths."""

    def test_multiple_tool_results_and_errors(self):
        """Missing, denied and failing tools each get an ordered result."""
        run = Mock(side_effect=ValueError('bad argument'))
        tools = {'fail': SimpleNamespace(spec={'schema': {}}, run=run)}
        calls = [{'name': name, 'args': {}} for name in ['missing', 'blocked', 'fail']]
        replies = [{'text': '', 'tool_calls': calls}, {'text': 'done', 'tool_calls': []}]
        messages, events = [], []
        with patch.object(loop.provider, 'complete', side_effect=replies):
            answer = loop.run_loop('m', 's', messages, tools, lambda k, p: events.append(k),
                                   lambda c: 'no' if c['name'] == 'blocked' else None)
        self.assertEqual(answer, 'done')
        self.assertEqual([m['text'] for m in messages if m['role'] == 'tool'],
                         ['ERROR: unknown tool missing', 'BLOCKED: no', 'ERROR: ValueError: bad argument'])
        self.assertEqual(events.count('tool_end'), 3)

    def test_before_turn_preserves_list_identity(self):
        """The caller observes compaction and the final response on the same list."""
        messages = [{'role': 'user', 'text': 'old'}]
        with patch.object(loop.provider, 'complete', return_value={'text': 'ok', 'tool_calls': []}):
            loop.run_loop('m', 's', messages, {}, lambda *a: None, lambda c: None,
                          before_turn=lambda msgs: [{'role': 'user', 'text': 'summary'}])
        self.assertEqual(messages[0]['text'], 'summary')
        self.assertEqual(messages[-1]['text'], 'ok')

    def test_file_tools_and_edit_uniqueness(self):
        """Reads, edits, grep and listing agree on the actual written file."""
        parent = Path('work'); parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as tmp:
            tools = {t.name: t.run for t in core_tools(tmp)}
            tools['write_file']('nested/a.txt', 'ping\nping\nunique\n')
            self.assertIn('1\tping', tools['read_file']('nested/a.txt'))
            self.assertIn('appears 2 times', tools['edit_file']('nested/a.txt', 'ping', 'pong'))
            self.assertIn('not found', tools['edit_file']('nested/a.txt', 'absent', 'pong'))
            self.assertEqual(tools['edit_file']('nested/a.txt', 'unique', 'changed'), 'Edited nested/a.txt')
            self.assertIn('nested/a.txt:3: changed', tools['grep']('changed'))
            self.assertEqual(tools['list_files']('*.txt'), 'nested/a.txt')
            with self.assertRaises(PermissionError):
                tools['read_file']('../../outside')
            with patch('sudarshan.tools.subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 1)):
                self.assertEqual(tools['bash']('test', '1'), 'ERROR: timed out after 1s')
            with patch('sudarshan.tools.subprocess.run', return_value=SimpleNamespace(stdout='a'*13000, stderr='', returncode=0)):
                output = tools['bash']('test')
            self.assertIn('truncated', output)
            self.assertTrue(output.startswith('a'*6000) and output.endswith('a'*6000))
