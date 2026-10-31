"""Day 5: verify live runner orchestration without claiming generated products."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from demos import product_fleet
from sudarshan import provider


class ProductPreparationTests(unittest.TestCase):
    """Exercise actual Harness sessions and tools with a deterministic model stub."""

    def test_two_phases_use_one_session_and_load_skill(self):
        """Each independent workdir records both phases and actual assistant events."""
        Path('work').mkdir(exist_ok=True)
        previous = Path.cwd()
        with tempfile.TemporaryDirectory(dir='work') as tmp:
            try:
                os.chdir(tmp)
                def complete(model, system, messages, tools):
                    if messages[-1]['role'] == 'tool':
                        return {'text': 'Orchestration fixture only; no product built.', 'tool_calls': []}
                    return {'text': '', 'tool_calls': [{'name': 'use_skill', 'args': {'name': 'design-engineering'}}]}
                # Stub artifact inspection only for this orchestration/session test.
                verified = {'automated_ok': True, 'accepted': False, 'errors': [],
                            'manual_required': ['Fixture only'], 'status': 'incomplete'}
                with patch.object(product_fleet, 'verify_product', return_value=verified), patch.object(product_fleet, 'api_key', return_value='fixture'), patch.object(provider, 'complete', side_effect=complete), contextlib.redirect_stdout(io.StringIO()):
                    product_fleet.main()
                data = json.loads(Path('projects/run-evidence.json').read_text())
                self.assertEqual([r['name'] for r in data['builds']], list(product_fleet.TASKS))
                for name, phases in data['evidence'].items():
                    self.assertEqual(phases['build']['session'], phases['review']['session'])
                    self.assertEqual(len(list(Path('projects', name, '.sudarshan/sessions').glob('*.jsonl'))), 1)
                    for phase in phases.values():
                        self.assertEqual(phase['turns'], 2)
                        self.assertTrue(phase['skill_loaded'])
                    messages = [json.loads(line) for line in Path(phases['review']['session']).read_text().splitlines()]
                    self.assertIn(product_fleet.REVIEW, [m.get('text') for m in messages])
                self.assertTrue(all(not result['ok'] for result in data['final']))
            finally:
                os.chdir(previous)

    def test_text_only_success_is_repaired_and_never_accepted(self):
        Path('work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='work') as tmp:
            with patch.object(provider, 'complete', return_value={'text': 'All done!', 'tool_calls': []}):
                data = product_fleet.run_products(Path(tmp) / 'projects')
            self.assertEqual([r['name'] for r in data['builds']], list(product_fleet.TASKS))
            self.assertTrue(all(not r['ok'] for r in data['builds']))
            self.assertTrue(all(r['status'] == 'blocked' for r in data['reviews']))
            self.assertEqual(len(data['phases']['build_repair']), 3)
            self.assertEqual(len(data['phases']['review_repair']), 3)
            self.assertTrue(all(r['status'] == 'incomplete' for r in data['final']))
            for phases in data['evidence'].values():
                self.assertEqual(len({p['session'] for p in phases.values()}), 1)

    def test_failed_build_and_review_are_repaired_in_original_sessions(self):
        Path('work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='work') as tmp:
            root = (Path(tmp) / 'projects').resolve()

            def complete(model, system, messages, tools):
                if messages[-1]['role'] == 'tool':
                    return {'text': 'Fixture phase finished', 'tool_calls': []}
                task = messages[-1]['text']
                # Every initial build lacks an artifact; repairs create it.
                calls = [{'name': 'use_skill', 'args': {'name': 'design-engineering'}}]
                if task.startswith('Repair'):
                    calls.append({'name': 'write_file', 'args': {'path': 'fixture-output.txt', 'content': 'ready'}})
                elif task == product_fleet.REVIEW and sum(m.get('text') == product_fleet.REVIEW for m in messages) == 1:
                    calls.append({'name': 'write_file', 'args': {'path': 'fixture-output.txt', 'content': 'broken'}})
                return {'text': '', 'tool_calls': calls}

            def verify(name, directory):
                marker = Path(directory) / 'fixture-output.txt'
                good = marker.is_file() and marker.read_text() == 'ready'
                return {'automated_ok': good, 'accepted': good,
                        'errors': [] if good else ['Fixture artifact missing'], 'manual_required': []}

            with patch.object(provider, 'complete', side_effect=complete), patch.object(product_fleet, 'verify_product', side_effect=verify):
                data = product_fleet.run_products(root)
            self.assertTrue(all(not r['ok'] for r in data['builds']))
            self.assertTrue(all(r['ok'] for r in data['phases']['build_repair']))
            self.assertTrue(all(not r['ok'] for r in data['reviews']))
            self.assertTrue(all(r['ok'] for r in data['phases']['review_repair']))
            self.assertTrue(all(r['ok'] for r in data['phases']['final_review']))
            self.assertTrue(all(r['ok'] for r in data['final']))
            for phases in data['evidence'].values():
                self.assertEqual(len({p['session'] for p in phases.values()}), 1)

    def test_missing_credentials_stop_before_workspace_creation(self):
        with patch.object(product_fleet, 'api_key', side_effect=RuntimeError('not configured')), patch.object(product_fleet, 'run_products') as run:
            with self.assertRaises(RuntimeError):
                product_fleet.main()
            run.assert_not_called()

    def test_artifact_gate_cannot_replace_required_skill_loading(self):
        Path('work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='work') as tmp:
            verified = {'automated_ok': True, 'accepted': True, 'errors': [], 'manual_required': []}
            with patch.object(provider, 'complete', return_value={'text': 'done', 'tool_calls': []}), patch.object(product_fleet, 'verify_product', return_value=verified):
                data = product_fleet.run_products(Path(tmp) / 'projects')
            self.assertTrue(all(not result['ok'] for result in data['builds']))
            self.assertTrue(all(not result['skill_loaded'] for result in data['builds']))
            self.assertTrue(all(result['status'] == 'blocked' for result in data['reviews']))
            self.assertTrue(all(not result['ok'] for result in data['final']))

    def test_existing_project_is_preserved(self):
        Path('work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='work') as tmp:
            root = Path(tmp)
            existing = root / 'artisan-coffee'
            existing.mkdir()
            marker = existing / 'user.txt'
            marker.write_text('preserve')
            with self.assertRaises(RuntimeError):
                product_fleet.run_products(root)
            self.assertEqual(marker.read_text(), 'preserve')
