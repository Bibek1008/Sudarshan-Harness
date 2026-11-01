"""Validation must return failure, preserve diagnostics and not inherit secrets."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace
import subprocess
from scripts import ci_validate


class ValidationTests(unittest.TestCase):
    def test_failed_tests_fail_runner_and_retain_diagnostics(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            codes = iter([0, 7, 0])
            def run(arguments, **kwargs):
                self.assertNotIn("SUDARSHAN_API_KEY", kwargs["env"])
                code = next(codes)
                kwargs["stdout"].write("test_example ... FAIL\n" if code else "completed\n")
                return subprocess.CompletedProcess(arguments, code)
            with patch.object(ci_validate, "ROOT", Path(directory)), patch.object(ci_validate, "subprocess", SimpleNamespace(run=run, STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired)), patch("sys.argv", ["ci_validate.py"]), redirect_stdout(io.StringIO()), patch.dict("os.environ", {"SUDARSHAN_API_KEY": "synthetic-secret"}):
                self.assertEqual(ci_validate.main(), 1)
            results = json.loads((Path(directory) / "ci-results/summary.json").read_text())
            self.assertEqual([entry["exit_code"] for entry in results["commands"]], [0, 7, 0])
            self.assertIn("FAIL", (Path(directory) / "ci-results/unittest.log").read_text())

    def test_timeout_is_failure_and_diagnostic(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch.object(ci_validate, "ROOT", Path(directory)), patch.object(ci_validate, "subprocess", SimpleNamespace(run=Mock(side_effect=subprocess.TimeoutExpired("validation", 600)), STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired)), patch("sys.argv", ["ci_validate.py", "--docker-only"]), redirect_stdout(io.StringIO()):
                self.assertEqual(ci_validate.main(), 1)
            results = json.loads((Path(directory) / "ci-results/summary.json").read_text())
            self.assertEqual(results["commands"][0]["exit_code"], 124)
