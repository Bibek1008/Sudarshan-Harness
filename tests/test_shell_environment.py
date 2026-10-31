"""Exercise credential inheritance through real shell and descendant processes."""
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sudarshan.environment import safe_shell_environment
from sudarshan.execution.local import LocalExecutionBackend
from sudarshan.tools import core_tools


class ShellEnvironmentTests(unittest.TestCase):
    def test_allowlist_excludes_unknown_credentials_and_startup_hooks(self):
        environment = {'PATH': 'executables', 'SystemRoot': 'runtime',
                       'UNRELATED_SECRET': 'fixture', 'BASH_ENV': 'startup',
                       'PYTHONPATH': 'injection', 'SSH_AUTH_SOCK': 'socket'}
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(safe_shell_environment(),
                             {k: v for k, v in os.environ.items()
                              if k.upper() in {'PATH', 'SYSTEMROOT'}})
            self.assertEqual(os.environ['UNRELATED_SECRET'], 'fixture')

    def test_real_shell_and_descendants_do_not_inherit_credentials(self):
        keys = ('SUDARSHAN_API_KEY', 'ODYSSEUS_API_KEY', 'GEMINI_API_KEY',
                'AWS_SECRET_ACCESS_KEY', 'GITHUB_TOKEN', 'DATABASE_PASSWORD',
                'UNRELATED_CUSTOM_CREDENTIAL')
        fixtures = {key: 'fixture-secret-' + key for key in keys}
        parent = Path(__file__).resolve().parent.parent / 'work'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as root:
            probe = Path(root, 'probe.py')
            probe.write_text(
                'import json, os, subprocess, sys\n'
                'keys = ' + repr(keys) + '\n'
                'if len(sys.argv) == 1:\n'
                '    print(json.dumps({k: os.environ.get(k) for k in keys}))\n'
                'else:\n'
                '    subprocess.run([sys.executable, __file__], check=True)\n',
                encoding='utf-8')
            runners = {'core': {t.name: t.run for t in core_tools(root)}['bash'],
                       'local': lambda cmd: LocalExecutionBackend(root).execute(cmd).stdout}
            with patch.dict(os.environ, fixtures):
                for backend, run in runners.items():
                    for nested in (False, True):
                        args = [sys.executable, str(probe.resolve())] + (['nested'] if nested else [])
                        command = subprocess.list2cmdline(args) if os.name == 'nt' else shlex.join(args)
                        with self.subTest(backend=backend, nested=nested):
                            output = run(command)
                            self.assertEqual(json.loads(output), dict.fromkeys(keys))
                            self.assertFalse(any(value in output for value in fixtures.values()))
                self.assertEqual(os.environ['SUDARSHAN_API_KEY'], fixtures['SUDARSHAN_API_KEY'])
