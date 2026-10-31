"""Execution tests: local command, boundary, output, and file behavior."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sudarshan.execution.base import ExecutionPermissionError, ExecutionTimeout
from sudarshan.execution.local import LocalExecutionBackend


class LocalExecutionBackendTests(unittest.TestCase):
    """Prove that local operations remain inside their configured workspace."""

    def setUp(self) -> None:
        """Create a fresh workspace and backend for each local test."""
        scratch_parent = Path(__file__).resolve().parent.parent / "work"
        scratch_parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch_parent)
        self.root = Path(self.temporary.name)
        self.backend = LocalExecutionBackend(self.root)

    def tearDown(self) -> None:
        """Release the temporary workspace after each local test."""
        self.temporary.cleanup()

    def test_successful_and_failed_commands_return_structured_results(self) -> None:
        """Command exit status and captured output remain visible to callers."""
        success = self.backend.execute('echo hello')
        failure = self.backend.execute('python -c "import sys; sys.exit(7)"')
        self.assertEqual(success.exit_code, 0)
        self.assertIn("hello", success.stdout)
        self.assertEqual(failure.exit_code, 7)
        self.assertEqual(failure.execution_backend, "local")
        self.assertEqual(failure.error, "command exited with 7")

    def test_timeout_raises_distinct_exception(self) -> None:
        """A command deadline cannot be confused with a normal command failure."""
        command = f'"{sys.executable}" -c "import time; time.sleep(2)"'
        with self.assertRaises(ExecutionTimeout):
            self.backend.execute(command, timeout=0.01)

    def test_file_operations_and_traversal_protection(self) -> None:
        """Read/write succeed inside the root and reject relative traversal."""
        written = self.backend.write_file("nested/note.txt", "hello")
        read = self.backend.read_file("nested/note.txt")
        listed = self.backend.list_files("*.txt")
        self.assertEqual(written.exit_code, 0)
        self.assertEqual(read.stdout, "hello")
        self.assertIn("nested/note.txt", listed.stdout)
        with self.assertRaises(ExecutionPermissionError):
            self.backend.read_file("../outside.txt")

    def test_symlink_escape_is_rejected(self) -> None:
        """A path that looks local but resolves outside the root is never read."""
        outside = Path(self.temporary.name).parent / "sudarshan-outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "escape.txt"
        try:
            os.symlink(outside, link)
        except OSError as error:
            self.skipTest(f"symlink creation is unavailable: {error}")
        with self.assertRaises(ExecutionPermissionError):
            self.backend.read_file("escape.txt")

    def test_output_is_bounded(self) -> None:
        """Very large process output keeps useful context without growing forever."""
        command = f'"{sys.executable}" -c "print(\'x\' * 13000)"'
        result = self.backend.execute(command)
        self.assertIn("... output truncated ...", result.stdout)
        self.assertLess(len(result.stdout), 13050)


if __name__ == "__main__":
    unittest.main()
