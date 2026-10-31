"""Independent artifact checks, separate from assistant claims.

HTML checks establish static prerequisites, never browser interaction success.
Generated Python tests execute with host permissions, not in a sandbox.
"""
import ast
import hashlib
from datetime import datetime, timezone
import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from sudarshan.environment import safe_shell_environment


class PageFacts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = {}
        self.visible = []
        self.suppressed = []

    def handle_starttag(self, tag, attrs):
        self.tags[tag] = self.tags.get(tag, 0) + 1
        values = dict(attrs)
        hidden = (tag in {'script', 'style', 'template', 'noscript'} or 'hidden' in values
                  or values.get('aria-hidden') == 'true'
                  or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', values.get('style', ''))))
        if tag not in {'meta', 'link', 'input', 'img', 'br', 'hr', 'source', 'area', 'embed', 'wbr'}:
            self.suppressed.append((tag, hidden or bool(self.suppressed and self.suppressed[-1][1])))

    def handle_endtag(self, tag):
        for index in range(len(self.suppressed) - 1, -1, -1):
            if self.suppressed[index][0] == tag:
                del self.suppressed[index:]
                break

    def handle_data(self, data):
        if not self.suppressed or not self.suppressed[-1][1]:
            self.visible.append(data)


def _read(root: Path, relative: str) -> str:
    target = (root / relative).resolve()
    target.relative_to(root)
    return target.read_text(encoding='utf-8')


def _run(root, args):
    return subprocess.run([sys.executable, *args], cwd=root, env=safe_shell_environment(),
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)


def _taskman(root, errors, details):
    source = _read(root, 'taskman.py')
    readme = _read(root, 'README.md')
    compile(source, 'taskman.py', 'exec')
    if len(source.strip()) < 150 or len(readme.split()) < 20:
        errors.append('Taskman source or README is not meaningful')
    test_files = sorted(root.glob('test*.py')) + sorted((root / 'tests').glob('test*.py'))
    count = 0
    for path in test_files:
        code = _read(root, str(path.relative_to(root)))
        tree = ast.parse(code)
        count += sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test')
                     for n in ast.walk(tree))
    details['test_methods'] = count
    if count < 10:
        errors.append('Taskman needs at least ten test methods')
        return
    test_path = 'tests' if (root / 'tests').is_dir() else '.'
    result = _run(root, ['-m', 'unittest', 'discover', '-s', test_path, '-v'])
    output = result.stdout + result.stderr
    details['tests'] = {'exit_code': result.returncode, 'output': output[-4000:]}
    ran = re.search(r'Ran (\d+) tests?', output)
    if result.returncode or not ran or int(ran[1]) < 10 or re.search(r'skipped=|expected failures=', output):
        errors.append('Taskman test execution must pass at least ten tests without skips')
    # Independent CLI lifecycle with a new store, not the model's claimed result.
    with tempfile.TemporaryDirectory(dir=root, prefix='verify-') as directory:
        store = str(Path(directory, 'tasks.json'))
        def command(*args):
            completed = _run(root, ['taskman.py', '--store', store, *args])
            if completed.returncode:
                raise ValueError('Taskman CLI command failed: ' + args[0])
            return completed.stdout
        command('add', 'Independent verification task')
        data = json.loads(Path(store).read_text(encoding='utf-8'))
        tasks = data.get('tasks') if isinstance(data, dict) else data
        if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], dict):
            raise ValueError('Taskman store must hold a tasks list with stable IDs')
        identifier = str(tasks[0]['id'])
        if 'Independent verification task' not in command('list'):
            errors.append('Taskman list did not show the persisted task')
        command('done', identifier)
        data = json.loads(Path(store).read_text(encoding='utf-8'))
        tasks = data.get('tasks') if isinstance(data, dict) else data
        if not tasks[0].get('done'):
            errors.append('Taskman done did not persist completion')
        command('stats')
        command('rm', identifier)
        data = json.loads(Path(store).read_text(encoding='utf-8'))
        if (data.get('tasks') if isinstance(data, dict) else data):
            errors.append('Taskman rm did not persist deletion')
    details['cli_lifecycle_executed'] = True


def artifact_digest(workdir):
    """Bind attestation to project files, excluding transient runtime state."""
    root = Path(workdir).resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if any(p in {'.sudarshan', '__pycache__', '.git'} for p in relative.parts):
            continue
        if path.is_file():
            path.resolve().relative_to(root)
            digest.update(str(relative).encode())
            digest.update(b'\x00' + path.read_bytes() + b'\x00')
    return digest.hexdigest()


def record_manual_verification(name, workdir, evidence_path, reviewer, checks):
    """Explicit human attestation: checks map requirement text to passed/evidence.

    Store outside the agent's project. This records a human claim, not a trusted
    signature; protect the evidence file using host permissions.
    """
    root, target = Path(workdir).resolve(), Path(evidence_path).resolve()
    if target.is_relative_to(root):
        raise ValueError('manual evidence must be outside the product workspace')
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError('a named reviewer is required')
    required = verify_product(name, root)['manual_required']
    if not required or not isinstance(checks, dict) or set(checks) - set(required):
        raise ValueError('checks must identify known manual requirements')
    evidence = {'product': name, 'reviewer': reviewer.strip(),
                'recorded_at': datetime.now(timezone.utc).isoformat(),
                'artifact_digest': artifact_digest(root), 'checks': checks}
    target.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    return evidence


def verify_product(name, workdir, manual_evidence=None):
    """Return static/executable evidence and explicit remaining manual checks."""
    root = Path(workdir).resolve()
    errors, details = [], {}
    manual = []
    try:
        if name == 'taskman':
            _taskman(root, errors, details)
            manual = ['Inspect meaningful assertions, temporary-store subprocess coverage and aligned output']
        elif name in {'artisan-coffee', 'viper'}:
            source = _read(root, 'index.html')
            page = PageFacts()
            page.feed(source)
            words = re.findall(r"\b[\w'-]+\b", ' '.join(page.visible))
            details.update(words=len(words), tags=page.tags)
            if len(source.strip()) < 500 or not page.tags.get('script') or not page.tags.get('button'):
                errors.append('Expected substantive self-contained HTML with scripts and controls')
            if re.search(r'lorem ipsum|TODO|coming soon', source, re.I):
                errors.append('Placeholder content remains')
            if name == 'artisan-coffee':
                for good, message in (
                    (page.tags.get('section', 0) >= 9, 'At least nine sections required'),
                    (len(words) > 1200, 'More than 1200 visible text words required'),
                    (page.tags.get('svg', 0) >= 4, 'At least four inline SVGs required'),
                    (bool(page.tags.get('main')), 'Semantic main element required'),
                    (all(term in source for term in ('localStorage', '@media', ':focus', '--')), 'Design/responsiveness/focus hooks missing'),
                ):
                    if not good:
                        errors.append(message)
                manual = ['Verify six priced origins, tiers, hero artifact and original SVGs',
                          'Exercise billing toggle, brew tabs, FAQ and persisted dark mode',
                          'Inspect visible copy, accessibility and layouts at 360/768/1280']
            else:
                if not page.tags.get('canvas'):
                    errors.append('Canvas element required')
                for term in ('requestAnimationFrame', 'localStorage', 'keydown'):
                    if term not in source:
                        errors.append('Missing gameplay hook: ' + term)
                manual = ['Play keyboard movement, food, score and speed-up every five foods',
                          'Exercise pause, restart, game over and persisted high score']
        else:
            errors.append('Unknown product')
    except (OSError, ValueError, SyntaxError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        errors.append(f'{type(error).__name__}: {error}')
    passed = False
    evidence_error = None
    if manual_evidence is not None:
        try:
            target = Path(manual_evidence).resolve()
            if target.is_relative_to(root):
                raise ValueError('manual evidence must be outside the product workspace')
            evidence = json.loads(target.read_text(encoding='utf-8'))
            checks = evidence.get('checks', {})
            passed = (evidence.get('product') == name and bool(evidence.get('reviewer', '').strip())
                      and bool(evidence.get('recorded_at'))
                      and evidence.get('artifact_digest') == artifact_digest(root)
                      and bool(manual) and all(
                          isinstance(checks.get(check), dict)
                          and checks[check].get('passed') is True
                          and isinstance(checks[check].get('evidence'), str)
                          and bool(checks[check]['evidence'].strip()) for check in manual))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            evidence_error = str(error)
    accepted = not errors and passed
    return {'automated_ok': not errors, 'accepted': accepted,
            'automated_passed': not errors, 'manual_pending': not passed,
            'manual_passed': passed, 'final_accepted': accepted,
            'manual_evidence_error': evidence_error,
            'errors': errors, 'details': details, 'manual_required': manual,
            'status': 'final_accepted' if accepted else 'manual_pending' if not errors else 'automated_failed'}
