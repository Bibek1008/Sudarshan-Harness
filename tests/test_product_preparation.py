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
                with patch.object(product_fleet, 'api_key', return_value='fixture'), patch.object(provider, 'complete', side_effect=complete), contextlib.redirect_stdout(io.StringIO()):
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
            finally:
                os.chdir(previous)
