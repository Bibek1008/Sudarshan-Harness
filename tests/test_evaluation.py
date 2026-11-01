"""Definition validation and privacy boundaries; no external model requests."""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch
from sudarshan.evaluation.registry import load_suite, TaskRegistry
from sudarshan.evaluation.runner import prepare, dry_run
from tests.test_harness_security import WorkspaceCase


class EvaluationDefinitionTests(WorkspaceCase):
    def test_core_ten_versioned_unique_categories(self):
        suite=load_suite()
        self.assertEqual(len(suite["tasks"]),10)
        self.assertEqual(len({t.category for t in suite["tasks"]}),10)
        self.assertEqual(suite["fingerprint"],load_suite()["fingerprint"])
        self.assertTrue(all(t.version == "1.0.0" and t.criteria for t in suite["tasks"]))

    def test_registration_and_duplicate_id(self):
        registry=TaskRegistry(); task=load_suite()["tasks"][0]
        registry.register(task)
        with self.assertRaises(ValueError): registry.register(task)

    def test_schema_rejects_bad_budgets_paths_and_fields(self):
        task=load_suite()["tasks"][0]
        for changes in ({"seconds":0},{"turns":True},{"deliverables":("../escape.py",)},{"deliverables":(".env",)},{"id":"../secret"},{"criteria":"abc"},{"criteria":("bad", "bad")}):
            with self.subTest(changes=changes),self.assertRaises(ValueError): replace(task,**changes).validate()

    def test_only_fixture_is_copied_and_hidden_verifiers_not_exposed(self):
        suite=load_suite(); task=suite["tasks"][0]
        prepare(task,suite,self.root)
        self.assertEqual({p.name for p in self.root.iterdir()},{"README.md"})
        self.assertFalse((self.root/"checks.py").exists())
        self.assertFalse((self.root/".git").exists())

    def test_fixture_reparse_rejected(self):
        suite=load_suite(); task=suite["tasks"][0]
        with patch.object(Path,"is_symlink",return_value=True):
            with self.assertRaises(ValueError): prepare(task,suite,self.root)

    def test_dry_run_has_no_provider_or_worker_execution(self):
        with patch("sudarshan.provider.complete",side_effect=AssertionError("no network")),patch("sudarshan.evaluation.runner.run_owned") as worker:
            plan=dry_run()
        self.assertEqual(plan["model_requests_made"],0)
        self.assertEqual(len(plan["tasks"]),10)
        worker.assert_not_called()

    def test_fixture_and_verifier_snapshots_stable_after_source_edit(self):
        from dataclasses import asdict
        import json
        from sudarshan.evaluation import registry
        parent=self.base/"assets";root=parent/"core"
        (root/"tasks").mkdir(parents=True)
        (root/"fixtures/slug").mkdir(parents=True)
        (root/"verifiers").mkdir()
        task=load_suite()["tasks"][0]
        (root/"suite.json").write_text(json.dumps({"name":"core","version":"1.0.0","tasks":["slug"]}))
        (root/"tasks/slug.json").write_text(json.dumps(asdict(task)))
        fixture=root/"fixtures/slug/README.md";fixture.write_text("original fixture")
        verifier=root/"verifiers/checks.py";verifier.write_text("# original hidden verifier")
        with patch.object(registry,"BENCHMARKS",parent): suite=load_suite()
        fixture.write_text("changed fixture");verifier.write_text("# changed")
        prepare(task,suite,self.root)
        self.assertEqual((self.root/"README.md").read_text(),"original fixture")
        self.assertEqual(suite["verifier_source"],"# original hidden verifier")
