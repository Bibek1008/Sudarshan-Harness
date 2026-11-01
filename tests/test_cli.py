from contextlib import redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from taskman.cli import CLI
from taskman.storage import StorageError


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.json"
        self.cli = CLI(str(self.path))

    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.cli.run(args)
        self.assertNotIn("Traceback", err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def test_all_five_commands(self):
        code, output, error = self.run_cli(["add", "Task one", "several", "description", "words"])
        self.assertEqual((code, error), (0, ""))
        first = self.cli.storage.load()[0]
        self.assertIn(first.id, output)
        self.assertEqual(first.description, "several description words")
        self.assertEqual(self.run_cli(["add", "Task two", "quoted description words"])[0], 0)
        second = self.cli.storage.load()[1]
        code, output, _ = self.run_cli(["list"])
        self.assertEqual(code, 0)
        self.assertIn(first.title, output)
        self.assertIn(second.title, output)
        self.assertEqual(self.run_cli(["complete", first.id])[0], 0)
        code, output, _ = self.run_cli(["show", first.id])
        self.assertEqual(code, 0)
        for value in (first.id, first.title, first.description, first.created_at, "Completed"):
            self.assertIn(value, output)
        self.assertEqual(self.run_cli(["delete", second.id])[0], 0)
        self.assertEqual([task.id for task in CLI(str(self.path)).storage.load()], [first.id])
        self.assertTrue(self.cli.storage.load()[0].completed)

    def test_empty_titles(self):
        for title in ("", " ", "\t\n"):
            with self.subTest(title=title):
                code, _, error = self.run_cli(["add", title])
                self.assertEqual(code, 1)
                self.assertIn("Title", error)
                self.assertFalse(self.path.exists())

    def test_nonexistent_ids(self):
        self.run_cli(["add", "Keep"])
        original = self.path.read_bytes()
        for command in ("show", "complete", "delete"):
            with self.subTest(command=command):
                code, _, error = self.run_cli([command, "missing"])
                self.assertEqual(code, 1)
                self.assertIn("not found", error)
                self.assertEqual(self.path.read_bytes(), original)

    def test_missing_arguments_and_unknown_commands(self):
        for args in ([], ["add"], ["show"], ["complete"], ["delete"], ["unknown"], ["list", "extra"]):
            with self.subTest(args=args):
                code, _, error = self.run_cli(args)
                self.assertEqual(code, 2)
                self.assertIn("usage:", error)

    def test_help(self):
        for args in (["--help"], ["add", "--help"], ["show", "--help"]):
            with self.subTest(args=args):
                code, output, error = self.run_cli(args)
                self.assertEqual((code, error), (0, ""))
                self.assertIn("usage:", output)
        self.assertFalse(self.path.exists())

    def test_missing_storage_list(self):
        code, output, error = self.run_cli(["list"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("No tasks", output)

    def test_corrupt_storage_all_commands_preserve_file(self):
        for content in ("not json", "{}", '[{"bad": true}]'):
            for args in (["add", "Task"], ["list"], ["show", "id"], ["complete", "id"], ["delete", "id"]):
                with self.subTest(content=content, args=args):
                    self.path.write_text(content, encoding="utf-8")
                    code, _, error = self.run_cli(args)
                    self.assertEqual(code, 1)
                    self.assertIn("preserved", error)
                    self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_save_failure_no_traceback(self):
        with patch.object(self.cli.storage, "save", side_effect=StorageError("disk full")):
            code, _, error = self.run_cli(["add", "Task"])
        self.assertEqual(code, 1)
        self.assertIn("disk full", error)

    def test_fresh_process_persistence_and_exit_codes(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        def invoke(*args):
            return subprocess.run([sys.executable, "-m", "taskman", *args],
                                  cwd=self.temp.name, env=env, capture_output=True, text=True)
        added = invoke("add", "Persisted", "description with spaces")
        self.assertEqual(added.returncode, 0, added.stderr)
        shown = invoke("list")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Persisted", shown.stdout)
        for args, expected in ((["show", "missing"], 1), (["add"], 2), (["--help"], 0)):
            result = invoke(*args)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
