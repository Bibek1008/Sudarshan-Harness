"""Candidate artifacts must satisfy independent behavior, never self-reports."""
import subprocess
from unittest.mock import patch
from sudarshan.evaluation.registry import load_suite
from sudarshan.evaluation.runner import prepare
from sudarshan.evaluation.verifier import verify
from sudarshan.execution.base import ExecutionTimeout
from tests.test_harness_security import WorkspaceCase


class BenchmarkVerifierTests(WorkspaceCase):
    def setUp(self):
        super().setUp(); self.suite=load_suite(); self.task=self.suite["tasks"][0]
        prepare(self.task,self.suite,self.root)

    def run_verifier(self): return verify(self.task,self.root,self.suite["root"]/"verifiers/checks.py",self.base)

    def test_bad_behavior_fails(self):
        (self.root/"solution.py").write_text("def slugify(text): return 'I passed'",encoding="utf-8")
        self.assertEqual(self.run_verifier()["status"],"failed")

    def test_partial_behavior_is_not_success(self):
        (self.root/"solution.py").write_text("def slugify(text): return text.lower().replace(' ','-')",encoding="utf-8")
        result=self.run_verifier()
        self.assertEqual(result["status"],"partial")
        self.assertEqual(sum(c["passed"] for c in result["checks"]),1)

    def test_syntax_and_missing_artifact_invalid(self):
        self.assertEqual(self.run_verifier()["status"],"invalid_output")
        (self.root/"solution.py").write_text("def broken(",encoding="utf-8")
        self.assertEqual(self.run_verifier()["status"],"invalid_output")

    def test_verifier_protocol_failure_never_success(self):
        (self.root/"solution.py").write_text("def slugify(text): return text",encoding="utf-8")
        with patch("sudarshan.evaluation.verifier.run_owned",return_value=subprocess.CompletedProcess([],0,'PRIVATE_OUTPUT', 'PRIVATE_ERROR')):
            self.assertEqual(self.run_verifier()["status"],"verifier_error")

    def test_verifier_timeout_is_distinct(self):
        (self.root/"solution.py").write_text("def slugify(text): return text",encoding="utf-8")
        with patch("sudarshan.evaluation.verifier.run_owned",side_effect=ExecutionTimeout("PRIVATE_SECRET")):
            result=self.run_verifier()
        self.assertEqual(result["status"],"timeout")
        self.assertEqual(result["error_category"],"verifier_timeout")
        self.assertNotIn("PRIVATE_SECRET",str(result))

    def test_artifact_link_permission_failure_invalid(self):
        with patch("sudarshan.evaluation.verifier.WorkspaceFiles.read_text",side_effect=PermissionError("private")):
            self.assertEqual(self.run_verifier()["status"],"invalid_output")
