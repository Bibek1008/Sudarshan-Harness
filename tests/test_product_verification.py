"""Artifact acceptance does not depend on assistant text or self-reports."""
import tempfile
import unittest
from pathlib import Path

from demos.product_verify import PageFacts, verify_product, record_manual_verification


class ProductVerificationTests(unittest.TestCase):
    def setUp(self):
        parent = Path('work').resolve()
        parent.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_hidden_fixtures_exclude_copy_sections_and_svgs(self):
        fixtures = (
            ('class="zero"', '.zero { opacity: 0.0; }'),
            ('class="filtered"', '.filtered { filter: opacity(0); }'),
            ('class="reader"', '.reader { position:absolute;width:1px;height:1px;overflow:hidden; }'),
            ('class="gone"', '.gone { display: none; }'),
            ('class="concealed"', '.concealed { visibility: hidden; }'),
            ('class="visually-hidden"', '.visually-hidden { position:absolute;clip:rect(0,0,0,0); }'),
            ('aria-hidden="true"', ''), ('hidden', ''),
            ('style="display:none"', ''),
        )
        for attrs, css in fixtures:
            with self.subTest(attrs=attrs):
                source = f'<main><section>real words</section><svg>visible drawing</svg><div {attrs}>'
                source += '<section>' + 'concealed ' * 1300 + '</section><svg>hidden drawing</svg></div>'
                source += f'<script>{"scriptword " * 1300}</script><style>{css}</style></main>'
                facts = PageFacts()
                facts.feed(source)
                self.assertEqual(facts.tags['section'], 1)
                self.assertEqual(facts.tags['svg'], 1)
                self.assertEqual(' '.join(facts.visible), 'real words visible drawing')
                (self.root / 'index.html').write_text(source)
                result = verify_product('artisan-coffee', self.root)
                self.assertFalse(result['automated_ok'])
                self.assertLess(result['details']['words'], 10)
                self.assertEqual(result['details']['visibility_method'], 'conservative_static')

    def test_hidden_svg_and_section_elements_are_not_counted(self):
        facts = PageFacts()
        facts.feed('<section hidden>hidden</section><svg class="off">hidden</svg>'
                   '<section>visible</section><svg>drawing</svg><style>.off{display:none}</style>')
        self.assertEqual(facts.tags['section'], 1)
        self.assertEqual(facts.tags['svg'], 1)

    def test_external_stylesheet_requires_observed_visibility(self):
        self.test_viper_static_hooks_do_not_prove_browser_acceptance()
        path = self.root / 'index.html'
        path.write_text('<link rel="stylesheet" href="unknown.css">' + path.read_text())
        result = verify_product('viper', self.root)
        self.assertFalse(result['automated_ok'])
        self.assertIn('unknown.css', result['details']['external_stylesheets'])
        self.assertFalse(result['final_accepted'])

    def test_configured_browser_measurements_take_precedence(self):
        self.test_viper_static_hooks_do_not_prove_browser_acceptance()
        widths = []
        def probe(path, width):
            widths.append(width)
            return {'words': 0, 'sections': 0, 'svgs': 0}
        result = verify_product('artisan-coffee', self.root, browser_probe=probe)
        self.assertEqual(widths, [360, 768, 1280])
        self.assertEqual(result['details']['words'], 0)
        self.assertEqual(result['details']['visibility_method'], 'browser_computed')
        self.assertFalse(result['automated_ok'])
        self.assertFalse(result['final_accepted'])

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
        self.assertTrue(result['automated_passed'])
        self.assertTrue(result['manual_pending'])
        self.assertFalse(result['final_accepted'])

    def test_manual_evidence_completion_and_stale_artifacts(self):
        self.test_viper_static_hooks_do_not_prove_browser_acceptance()
        required = verify_product('viper', self.root)['manual_required']
        evidence = self.root.parent / (self.root.name + '-manual.json')
        try:
            record_manual_verification('viper', self.root, evidence, 'Fixture reviewer', {})
            self.assertFalse(verify_product('viper', self.root, evidence)['final_accepted'])
            checks = {check: {'passed': True, 'evidence': 'Fixture observation of this check'} for check in required}
            record_manual_verification('viper', self.root, evidence, 'Fixture reviewer', checks)
            result = verify_product('viper', self.root, evidence)
            self.assertTrue(result['manual_passed'])
            self.assertTrue(result['final_accepted'])
            self.assertFalse(result['manual_pending'])
            with (self.root / 'index.html').open('a') as handle:
                handle.write('changed')
            self.assertFalse(verify_product('viper', self.root, evidence)['manual_passed'])
        finally:
            evidence.unlink(missing_ok=True)

    def test_incomplete_or_project_local_attestation_is_not_acceptance(self):
        self.test_viper_static_hooks_do_not_prove_browser_acceptance()
        with self.assertRaises(ValueError):
            record_manual_verification('viper', self.root, self.root / 'evidence.json', 'Reviewer', {})
        required = verify_product('viper', self.root)['manual_required']
        evidence = self.root.parent / (self.root.name + '-manual.json')
        try:
            checks = {check: {'passed': True, 'evidence': ''} for check in required}
            record_manual_verification('viper', self.root, evidence, 'Reviewer', checks)
            self.assertFalse(verify_product('viper', self.root, evidence)['accepted'])
        finally:
            evidence.unlink(missing_ok=True)

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
