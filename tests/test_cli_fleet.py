"""Day 5 audit: terminal defaults and real concurrent fleet ordering."""

import contextlib
import io
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sudarshan import cli, run_fleet


class FrontDoorTests(unittest.TestCase):
    """Exercise user-facing control flow without a live provider."""

    def test_headless_empty_prompt_is_headless(self):
        """An explicitly provided empty task still selects headless defaults."""
        with patch.object(cli, 'Harness') as factory:
            cli.main(['-p', '', '--resume', 'saved.jsonl'])
        self.assertEqual(factory.call_args.kwargs['policy'].mode, 'yolo')
        factory.return_value.run.assert_called_once_with('')
        factory.return_value.resume.assert_called_once_with('saved.jsonl')

    def test_interactive_defaults_and_eof(self):
        """Interactive construction uses safe mode and exits at EOF."""
        with patch.object(cli, 'Harness') as factory, patch('builtins.input', side_effect=EOFError), contextlib.redirect_stdout(io.StringIO()):
            cli.main([])
        self.assertEqual(factory.call_args.kwargs['policy'].mode, 'safe')

    def test_read_only_override_and_interrupt(self):
        """Headless interruption returns 130 and actionable resume guidance."""
        with patch.object(cli, 'Harness') as factory, contextlib.redirect_stdout(io.StringIO()) as output:
            factory.return_value.run.side_effect = KeyboardInterrupt
            with self.assertRaises(SystemExit) as error:
                cli.main(['-p', 'task', '--mode', 'read-only'])
        self.assertEqual(error.exception.code, 130)
        self.assertEqual(factory.call_args.kwargs['policy'].mode, 'read-only')
        self.assertIn('--resume', output.getvalue())

    def test_approval_refuses_by_default(self):
        """Blank, negative, and interrupted replies cannot approve an effect."""
        for reply, expected in [('', False), ('n', False), ('yes', True), ('y', True)]:
            with patch('builtins.input', return_value=reply), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli._approver({'name': 'bash'}, 'execute'), expected)

    def test_final_text_printed_once(self):
        """Harness events own final answer printing."""
        def create(*args, **kwargs):
            def run(task):
                kwargs['on_event']('assistant', {'text': 'unique answer'})
                return 'unique answer'
            return SimpleNamespace(run=run)
        with patch.object(cli, 'Harness', side_effect=create), contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main(['-p', 'task'])
        self.assertEqual(output.getvalue().count('unique answer'), 1)

    def test_fleet_concurrency_failure_and_order(self):
        """A barrier requires simultaneous workers; the slow first job still leads."""
        barrier = threading.Barrier(3)
        last_done = threading.Event()
        seen = []
        def factory(workdir):
            seen.append(workdir)
            def run(task):
                barrier.wait(timeout=5)
                if task == 'a':
                    self.assertTrue(last_done.wait(5))
                elif task == 'b':
                    raise ValueError('expected failure')
                else:
                    last_done.set()
                return task
            return SimpleNamespace(run=run)
        jobs = [{'name': name, 'workdir': name, 'task': name} for name in 'abc']
        results = run_fleet(jobs, factory, max_workers=3)
        self.assertEqual([item['name'] for item in results], list('abc'))
        self.assertEqual(results[1], {'name': 'b', 'ok': False, 'report': 'ValueError: expected failure'})
        self.assertEqual(sorted(seen), list('abc'))
        self.assertTrue(results[0]['ok'] and results[2]['ok'])
