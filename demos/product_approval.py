"""Explicit product-workspace approvals; this is not an OS sandbox.

Only core file edits, the required skill and fixed unittest commands are
automatically approved. Test programs still run with the host account's rights.
Use an OS sandbox when generated code itself is untrusted.
"""
import math
import shlex
import subprocess
import sys
from pathlib import Path

from sudarshan import Harness
from sudarshan.execution.process import run_owned
from sudarshan.execution.base import ExecutionTimeout
from sudarshan.security import Policy


TEST_COMMANDS = {
    'python -m unittest discover',
    'python -m unittest discover -v',
    'python -m unittest discover -s tests -v',
}


def workspace_path(root: Path, path: str) -> Path:
    """Resolve a file tool operand, rejecting escapes and reserved state."""
    if not isinstance(path, str) or not path or '\x00' in path:
        raise ValueError('a nonempty project-relative path is required')
    relative = Path(path)
    if relative.is_absolute():
        raise ValueError('absolute paths are not approved')
    target = (root / relative).resolve()
    parts = target.relative_to(root).parts
    if not parts or parts[0].lower() in {'.git', '.sudarshan', 'skills'}:
        raise ValueError('reserved project state cannot be edited')
    return target


def product_harness(workdir, **options) -> Harness:
    """Compose the existing Harness with a narrow safe-mode approver."""
    root = Path(workdir).resolve()

    def approve(call, reason):
        name, args = call.get('name'), call.get('args', {})
        if name == 'use_skill':
            skill = root / 'skills' / 'design-engineering' / 'SKILL.md'
            try:
                skill.resolve().relative_to(root)
            except ValueError:
                return False
            return args.get('name') == 'design-engineering' and skill.is_file()
        if name in {'write_file', 'edit_file'}:
            try:
                workspace_path(root, args.get('path'))
                return True
            except (ValueError, OSError):
                return False
        return name == 'bash' and args.get('command') in TEST_COMMANDS

    harness = Harness(root, policy=Policy('safe', approve), enable_subagents=False, **options)

    def run_tests(command: str, timeout: str = '120') -> str:
        # Recheck at the callable boundary and never evaluate a shell program.
        reason = harness.policy.check({'name': 'bash', 'args': {'command': command}})
        if reason:
            return 'BLOCKED: ' + reason
        seconds = float(timeout)
        if not math.isfinite(seconds) or not 0 < seconds <= 120:
            raise ValueError('test timeout must be between 0 and 120 seconds')
        try:
            result = run_owned([sys.executable, *shlex.split(command)[1:]],
                               cwd=root, timeout=seconds)
        except ExecutionTimeout:
            return 'ERROR: product tests timed out'
        return f'exit {result.returncode}\n' + (result.stdout + result.stderr)[-12000:]

    harness.tools['bash'].run = run_tests
    return harness
