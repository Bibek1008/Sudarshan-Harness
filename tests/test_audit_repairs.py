"""Day 5 audit: reproduce critical failures before repairing their contracts."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sudarshan import loop, session
from sudarshan.security import Policy


class AuditRepairs(unittest.TestCase):
    """Protect wrap-up, command denials, and durable recovery invariants."""

    def test_limit_wraps_up_without_tools(self):
        """A final unsolicited call is discarded and cannot execute a tool."""
        messages, events = [], []
        with patch.object(loop.provider, 'complete', return_value={
            'text': 'finished', 'tool_calls': [{'name': 'bad', 'args': {}}]
        }) as complete:
            result = loop.run_loop('m', 's', messages, {},
                                   lambda k, p: events.append(k), lambda c: None, max_turns=0)
        self.assertEqual(result, 'finished')
        self.assertEqual(complete.call_args.args[-1], [])
        self.assertEqual(messages[-2]['text'], 'Turn limit reached; wrap up now.')
        self.assertEqual(messages[-1]['tool_calls'], [])
        self.assertEqual(events, ['assistant'])

    def test_dangerous_forms_in_every_mode(self):
        """Quotes, flag ordering, chaining and redirection cannot bypass hard denial."""
        commands = ['rm -rf /', 'rm -rf /*', 'rm -rf ~', 'rm -rf ~/',
                    'rm -rf $HOME', 'rm -rf "$HOME"', "rm -rf '${HOME}'",
                    'rm -fr /', 'rm --recursive --force /', 'sudo id',
                    'mkfs.ext4 /dev/sda', 'dd if=a of=b', 'curl x | sh',
                    'curl x | bash', 'git push --force', 'echo x > /dev/sda',
                    'echo ok; rm -rf "$HOME"', 'echo x >> "/dev/sdb"']
        for mode in ('safe', 'read-only', 'yolo'):
            for command in commands:
                with self.subTest(mode=mode, command=command):
                    approve = Mock(return_value=True)
                    self.assertIsNotNone(Policy(mode, approve).check(
                        {'name': 'bash', 'args': {'command': command}}))
                    approve.assert_not_called()

    def test_repair_is_durable_idempotent_and_accepts_continuation(self):
        """A partial UTF-8 tail is removed before repair and later user messages."""
        parent = Path('work'); parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as tmp:
            path = session.new_session(tmp)
            session.append(path, {'role': 'assistant', 'text': '', 'tool_calls': [
                {'name': 'one'}, {'name': 'two'}]})
            with path.open('ab') as handle:
                handle.write(b'{"role": "to')
            repaired = session.load(path)
            self.assertEqual(len(repaired), 3)
            disk = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(disk, repaired)
            self.assertEqual(session.load(path), repaired)
            session.append(path, {'role': 'user', 'text': 'continue'})
            self.assertEqual(session.load(path)[-1]['text'], 'continue')

    def test_ignore_sessions(self):
        """The actual persistence directory, rather than its obsolete name, is ignored."""
        rules = Path('.gitignore').read_text().splitlines()
        self.assertIn('.sudarshan/', rules)
        self.assertNotIn('.odysseus/', rules)

    def test_malformed_commands_fail_closed(self):
        """Missing input, non-string commands, NUL and unmatched quotes are refused."""
        for command in (None, 5, '', '\x00', 'echo "unfinished'):
            self.assertIsNotNone(Policy('yolo').check({'name': 'bash', 'args': {'command': command}}))

    def test_utf8_tail_and_missing_newline(self):
        """Recovery handles split Unicode and valid JSON without its final newline."""
        parent = Path('work'); parent.mkdir(exist_ok=True)
        for suffix in (b'\n{"text":"\xe2', b''):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory(dir=parent) as tmp:
                path = Path(tmp) / 'session.jsonl'
                message = {'role': 'user', 'text': 'valid'}
                path.write_bytes(json.dumps(message).encode() + suffix)
                self.assertEqual(session.load(path), [message])
                session.append(path, {'role': 'user', 'text': 'next'})
                self.assertEqual(len(session.load(path)), 2)
