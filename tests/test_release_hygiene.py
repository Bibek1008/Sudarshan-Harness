"""Final-release failure handling and narrowly scoped ignore rules."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from sudarshan import cli, provider
from tests.test_harness_security import WorkspaceCase


class ReleaseCLITests(WorkspaceCase):
    def test_negative_turn_limit_is_rejected_before_workspace_creation(self):
        with patch.object(cli, "Harness") as harness, redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as caught:
                cli.main(["--max-turns", "-1", "-p", "task"])
        self.assertEqual(caught.exception.code, 2)
        harness.assert_not_called()
        self.assertIn("zero or greater", error.getvalue())

    def test_zero_turn_limit_still_requests_final_report(self):
        with patch.object(cli, "Harness") as harness:
            cli.main(["--max-turns", "0", "-p", "task"])
        self.assertEqual(harness.call_args.kwargs["max_turns"], 0)
        harness.return_value.run.assert_called_once_with("task")

    def test_workspace_and_resume_failures_are_safe_and_actionable(self):
        for during in ("startup", "resume"):
            with self.subTest(during=during), patch.object(cli, "Harness") as harness, redirect_stderr(io.StringIO()) as error:
                if during == "startup":
                    harness.side_effect = PermissionError("PRIVATE_ERROR synthetic-value")
                else:
                    harness.return_value.resume.side_effect = FileNotFoundError("PRIVATE_ERROR synthetic-value")
                with self.assertRaises(SystemExit) as caught:
                    cli.main(["--resume", "missing.jsonl", "-p", "task"])
                self.assertEqual(caught.exception.code, 1)
                self.assertIn("--resume", error.getvalue())
                self.assertNotIn("PRIVATE_ERROR", error.getvalue())
                self.assertNotIn("Traceback", error.getvalue())

    def test_headless_expected_failure_does_not_echo_private_details(self):
        for failure in (RuntimeError, ValueError, PermissionError):
            with self.subTest(failure=failure), patch.object(cli, "Harness") as harness, redirect_stderr(io.StringIO()) as error:
                harness.return_value.run.side_effect = failure("api_key=synthetic-private-value")
                with self.assertRaises(SystemExit) as caught:
                    cli.main(["-p", "task"])
                self.assertEqual(caught.exception.code, 1)
                self.assertIn("--verbose", error.getvalue())
                self.assertNotIn("--resume", error.getvalue())
                self.assertNotIn("synthetic-private-value", error.getvalue())

    def test_interactive_expected_failure_allows_another_task(self):
        with patch.object(cli, "Harness") as harness, patch("builtins.input", side_effect=["first", "second", EOFError]), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            harness.return_value.run.side_effect = [RuntimeError("private"), "done"]
            cli.main([])
        self.assertEqual(harness.return_value.run.call_count, 2)

    def test_missing_first_run_key_fails_without_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(provider, "urlopen", side_effect=AssertionError("no network")) as network, redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as caught:
                cli.main(["-d", str(self.root), "-p", "Inspect this project", "--no-telemetry"])
        self.assertEqual(caught.exception.code, 1)
        network.assert_not_called()
        self.assertIn("SUDARSHAN_API_KEY", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())


class RepositoryIgnoreTests(unittest.TestCase):
    def ignored(self, paths):
        root = Path(__file__).resolve().parents[1]
        if not shutil.which("git") or not (root / ".git").exists():
            self.skipTest("Git checkout required to verify ignore rules")
        result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin", "-z"],
                                input=("\0".join(paths) + "\0").encode("utf-8"), cwd=root,
                                capture_output=True, timeout=10)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return set(result.stdout.decode("utf-8").split("\0")) - {""}

    def test_runtime_credentials_and_editor_files_are_ignored(self):
        paths = [".env", ".env.local", "credentials.json", "id_ed25519", "local.pem",
                 "sudarshan/__pycache__/cli.cpython-312.pyc", "module.pyo", ".venv/pyvenv.cfg",
                 ".sudarshan/sessions/private.jsonl", ".sudarshan/telemetry/events/private.jsonl",
                 ".sudarshan/benchmarks/runs/private.json", "ci-results/unittest.log",
                 "benchmark-exports/local.json", "benchmark-results/local.json", "validation.log",
                 ".vscode/settings.json", "Thumbs.db", "notes.md~"]
        self.assertEqual(self.ignored(paths), set(paths))

    def test_source_docs_fixtures_and_workflows_are_not_hidden(self):
        paths = ["sudarshan/cli.py", "tests/test_release_hygiene.py", "docs/GETTING_STARTED.md",
                 "docs/SECURITY.md", "RELEASE_NOTES.md", "FINAL_PROJECT_REPORT.md",
                 "PHASE6_MEMORY_REPORT.md", "benchmarks/core/tasks/config.json",
                 "benchmarks/custom/fixtures/sample.log", "docs/work/example.md",
                 ".github/workflows/cross-platform.yml"]
        self.assertEqual(self.ignored(paths), set())
