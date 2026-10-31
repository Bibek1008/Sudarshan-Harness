"""Day 5: explicit SSH argument boundaries and Docker timeout cleanup."""

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from demos import day1_dice
from sudarshan.execution.remote import RemoteExecutionBackend
from sudarshan.execution.sandbox import SandboxedExecutionBackend
from sudarshan.execution.base import ExecutionTimeout


class BackendHardeningTests(unittest.TestCase):
    """Mock external runtimes; verify exact argv and no host fallback."""

    def test_ssh_rejects_option_injection(self):
        """Host, user and executable cannot smuggle SSH options or shell tokens."""
        for value in ('-oProxyCommand=evil', 'a;evil', 'a\nb', 'a$(evil)'):
            with self.assertRaises(ValueError):
                RemoteExecutionBackend(value)
            with self.assertRaises(ValueError):
                RemoteExecutionBackend('host', username=value)

    def test_docker_timeout_removes_exact_container(self):
        """A timed-out Docker client triggers bounded removal of its named container."""
        with patch('sudarshan.execution.sandbox.shutil.which', return_value='docker'), patch('sudarshan.execution.sandbox.subprocess.run', side_effect=[subprocess.TimeoutExpired('docker', 1), SimpleNamespace(returncode=0)]) as run:
            with self.assertRaisesRegex(ExecutionTimeout, 'container removed'):
                SandboxedExecutionBackend('.').execute('sleep 99', timeout=1)
        argv = run.call_args_list[0].args[0]
        name = argv[argv.index('--name') + 1]
        self.assertEqual(run.call_args_list[1].args[0], ['docker', 'rm', '-f', name])

    def test_dice_demo(self):
        """The restored demo computes real rolls and passes the exact task to the loop."""
        with patch.object(day1_dice.random, 'randint', side_effect=[3, 4, 5]):
            self.assertIn('total: 12', day1_dice.roll_dice('3'))
        with patch.object(day1_dice, 'run_loop') as loop:
            day1_dice.main()
        args = loop.call_args.args
        self.assertEqual(args[2][0]['text'], 'Roll 3 dice and tell me whether the total beats 10')
        self.assertIsNone(args[5]({}))
