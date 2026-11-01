"""Real disposable-worker lifecycle with scripted model replies only."""
import json
from pathlib import Path
from unittest.mock import patch
from sudarshan.evaluation.runner import run_suite, execute_trial, configuration
from sudarshan.evaluation.registry import load_suite
from sudarshan.evaluation.reporting import ResultStore
from sudarshan.execution.base import ExecutionTimeout, ExecutionError
from tests.evaluation_samples import replies
from tests.test_harness_security import WorkspaceCase


class BenchmarkRunnerTests(WorkspaceCase):
    def run_slug(self, **options):
        defaults=dict(model="test-model",task_ids=["slug"],mock_scripts={"slug":[replies("slug")]},approve_workspace_edits=True)
        defaults.update(options)
        return run_suite(self.root,**defaults)

    def test_mocked_end_to_end_all_ten_independent_verifiers(self):
        scripts={task.id:[replies(task.id)] for task in load_suite()["tasks"]}
        with patch("sudarshan.provider.complete",side_effect=AssertionError("parent must not contact model")):
            result=run_suite(self.root,model="test-model",mock_scripts=scripts,approve_workspace_edits=True)
        self.assertEqual(result["summary"]["passed"],10,[(t["task_id"],t["status"],t["verification"]) for t in result["trials"]])
        self.assertEqual(result["summary"]["task_success_rate"],1)
        self.assertEqual(result["mode"],"mock")
        stored=ResultStore(self.root).load(result["run_id"])
        self.assertEqual(stored,result)
        self.assertNotIn("PRIVATE_CLAIM_OF_SUCCESS",json.dumps(result))

    def test_claim_without_artifacts_does_not_pass(self):
        result=self.run_slug(mock_scripts={"slug":[[{"text":"I passed everything", "tool_calls":[]}]]})
        self.assertEqual(result["summary"]["passed"],0)
        self.assertEqual(result["trials"][0]["status"],"invalid_output")
        self.assertNotIn("I passed everything",json.dumps(result))

    def test_safe_mode_denies_edits_without_explicit_approval(self):
        result=self.run_slug(approve_workspace_edits=False)
        self.assertNotEqual(result["trials"][0]["status"],"passed")
        self.assertEqual(result["trials"][0]["metrics"]["denied_tools"],1)
        self.assertEqual(result["configuration"]["approval_policy"],"safe-deny-effects")

    def test_repeated_trials_are_clean_and_ids_unique(self):
        scripts={"slug":[replies("slug"),[{"text":"done", "tool_calls":[]}]]}
        result=self.run_slug(runs=2,mock_scripts=scripts)
        self.assertEqual([t["status"] for t in result["trials"]],["passed","invalid_output"])
        self.assertEqual(len({t["trial_id"] for t in result["trials"]}),2)
        self.assertEqual(result["summary"]["task_success_rate"],.5)
        self.assertFalse(list((self.root/".sudarshan/benchmarks").glob("scratch-*")))

    def test_actual_telemetry_from_mock_responses(self):
        result=self.run_slug()
        metrics=result["trials"][0]["metrics"]
        self.assertEqual(metrics["model_requests"],2)
        self.assertEqual(metrics["tokens"]["input"],200)
        self.assertEqual(metrics["tokens"]["total"],250)
        self.assertEqual(result["summary"]["telemetry_coverage"]["complete_trials"],1)
        self.assertIsNone(metrics["estimated_cost"])

    def test_missing_usage_remains_unavailable(self):
        result=self.run_slug(mock_scripts={"slug":[replies("slug",usage=False)]})
        self.assertIsNone(result["summary"]["measured_tokens"]["input"])
        self.assertEqual(result["summary"]["telemetry_coverage"]["complete_trials"],0)

    def test_timeout_and_interruption_statuses_not_success(self):
        for error,status in ((ExecutionTimeout("PRIVATE_SECRET"),"timeout"),(KeyboardInterrupt(),"interrupted"),(ExecutionError("PRIVATE_SECRET"),"inconclusive")):
            with self.subTest(status=status),patch("sudarshan.evaluation.runner.run_owned",side_effect=error):
                result=self.run_slug()
            self.assertEqual(result["trials"][0]["status"],status)
            self.assertNotIn("PRIVATE_SECRET",json.dumps(result))

    def test_run_budget_guard_and_explicit_execution_mode(self):
        for runs in (0,21,True):
            with self.assertRaises(ValueError): self.run_slug(runs=runs)
        with self.assertRaises(ValueError): run_suite(self.root)
        with self.assertRaises(ValueError): run_suite(self.root,live=True,mock_scripts={})

    def test_configured_estimate_retains_provenance(self):
        from sudarshan.telemetry import Store
        store=Store(self.root)
        fixture={"input_per_million":"2","output_per_million":"4","currency":"USD","source":"synthetic-not-real-pricing","effective_date":"2026-01-01","thought_policy":"additional_output"}
        with store.locked(): store.atomic_json("pricing.json",{"test-model":fixture})
        result=self.run_slug()
        cost=result["trials"][0]["metrics"]["estimated_cost"]
        self.assertEqual(cost["estimated"],"0.0006")
        self.assertEqual(cost["source"],"synthetic-not-real-pricing")
        self.assertNotEqual(result["configuration"]["pricing_config_id"],"unavailable")

    def test_missing_telemetry_remains_none(self):
        import subprocess
        payload=json.dumps({"schema_version":1,"execution_status":"failed","metrics":None})
        with patch("sudarshan.evaluation.runner.run_owned",return_value=subprocess.CompletedProcess([],0,payload,"")):
            result=self.run_slug()
        self.assertIsNone(result["trials"][0]["metrics"])
        self.assertIsNone(result["summary"]["measured_tokens"]["input"])

    def test_generated_candidate_does_not_inherit_synthetic_api_key(self):
        source="import os\ndef slugify(text):\n    assert os.environ.get('SUDARSHAN_API_KEY') is None\n    return '-'.join(text.lower().split())\n"
        values=replies("slug")
        values[0]["tool_calls"][0]["args"]["content"]=source
        with patch.dict("os.environ",{"SUDARSHAN_API_KEY":"PRIVATE_ENV_SENTINEL"}):
            result=self.run_slug(mock_scripts={"slug":[values]})
        self.assertEqual(result["summary"]["passed"],1)
        self.assertNotIn("PRIVATE_ENV_SENTINEL",json.dumps(result))

    def test_unparseable_worker_output_is_not_stored_or_passed(self):
        import subprocess
        with patch("sudarshan.evaluation.runner.run_owned",return_value=subprocess.CompletedProcess([],0,"PRIVATE_RAW_OUTPUT","PRIVATE_RAW_ERROR")):
            result=self.run_slug()
        self.assertEqual(result["trials"][0]["status"],"inconclusive")
        self.assertNotIn("PRIVATE_RAW",json.dumps(result))
