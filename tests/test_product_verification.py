"""Artifact acceptance does not depend on assistant text or self-reports."""
import tempfile
import unittest
from pathlib import Path

from demos.product_verify import verify_product


class ProductVerificationTests(unittest.TestCase):
    def setUp(self):
        parent = Path('work').resolve()
        parent.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_expected_files_are_mandatory_for_every_product(self):
        for name in ('artisan-coffee', 'taskman', 'viper'):
            result = verify_product(name, self.root)
            self.assertFalse(result['automated_ok'])
            self.assertFalse(result['accepted'])

    def test_viper_static_hooks_do_not_prove_browser_acceptance(self):
        source = '<main><canvas></canvas><button>Pause</button><p>' + 'Game instructions ' * 50
        source += '</p><script>requestAnimationFrame; localStorage; keydown;</script></main>'
        (self.root / 'index.html').write_text(source)
        result = verify_product('viper', self.root)
        self.assertTrue(result['automated_ok'])
        self.assertFalse(result['accepted'])
        self.assertTrue(result['manual_required'])

    def test_hidden_copy_and_scripts_do_not_satisfy_coffee_word_quota(self):
        source = '<main><section>Real copy</section>' + '<section></section>' * 8
        source += '<svg></svg>' * 4 + '<button>FAQ</button><p hidden>' + 'filler ' * 1300
        source += '</p><script>localStorage; ' + 'invisible ' * 1300
        source += '</script><style>@media { --color:red; :focus {} }</style></main>'
        (self.root / 'index.html').write_text(source)
        result = verify_product('artisan-coffee', self.root)
        self.assertFalse(result['automated_ok'])
        self.assertLess(result['details']['words'], 10)

    def test_taskman_needs_actual_discoverable_tests(self):
        (self.root / 'taskman.py').write_text('import argparse\n' + '# implementation fixture\n' * 15)
        (self.root / 'README.md').write_text('Usage instructions ' * 20)
        (self.root / 'test_empty.py').write_text('import unittest\n')
        result = verify_product('taskman', self.root)
        self.assertFalse(result['automated_ok'])
        self.assertIn('Taskman needs at least ten test methods', result['errors'])

    def test_taskman_executes_tests_and_independent_cli_lifecycle(self):
        # A tiny fixture CLI is not a delivered Taskman product. Manual review
        # remains mandatory even when these executable prerequisites pass.
        source = '''import argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--store', required=True)
p.add_argument('command', choices=['add', 'list', 'done', 'rm', 'stats'])
p.add_argument('value', nargs='?')
a = p.parse_args()
path = Path(a.store)
tasks = json.loads(path.read_text()) if path.exists() else []
if a.command == 'add':
    tasks.append({'id': 1, 'title': a.value, 'done': False})
elif a.command == 'done':
    tasks[0]['done'] = True
elif a.command == 'rm':
    tasks = []
elif a.command == 'list':
    print(tasks[0]['title'] if tasks else '')
else:
    print(len(tasks))
path.write_text(json.dumps(tasks))
'''
        (self.root / 'taskman.py').write_text(source)
        (self.root / 'README.md').write_text('Fixture usage documentation ' * 15)
        tests = 'import unittest\nclass Checks(unittest.TestCase):\n'
        tests += ''.join(f'    def test_{i}(self):\n        self.assertEqual({i}, {i})\n' for i in range(10))
        (self.root / 'test_fixture.py').write_text(tests)
        result = verify_product('taskman', self.root)
        self.assertTrue(result['automated_ok'], result['errors'])
        self.assertTrue(result['details']['cli_lifecycle_executed'])
        self.assertEqual(result['details']['test_methods'], 10)
        self.assertFalse(result['accepted'])

    def test_test_shaped_functions_do_not_satisfy_executed_count(self):
        (self.root / 'taskman.py').write_text('import argparse\n' + '# fixture\n' * 30)
        (self.root / 'README.md').write_text('Usage instructions ' * 20)
        source = ''.join(f'def test_{i}():\n    assert True\n' for i in range(10))
        (self.root / 'test_fixture.py').write_text(source)
        result = verify_product('taskman', self.root)
        self.assertFalse(result['automated_ok'])
        self.assertTrue(any('test execution' in error for error in result['errors']))
