"""Execution tests: SSH availability, strict options, results, and timeouts."""

import subprocess
import unittest
from unittest.mock import patch

from sudarshan.execution.base import BackendUnavailable, ExecutionTimeout
from sudarshan.execution.remote import REMOTE_FILE_HELPER, RemoteExecutionBackend


class RemoteExecutionBackendTests(unittest.TestCase):
    """Exercise SSH command construction without needing a remote server."""

    def setUp(self) -> None:
        """Create a representative key-authenticated remote backend."""
        self.backend = RemoteExecutionBackend(
            "build.example", username="agent", port=2202,
            identity_file="C:/keys/build", workdir="/srv/project",
        )

    def test_unavailable_ssh_raises_clear_exception(self) -> None:
        """An absent system SSH runtime is reported rather than emulated locally."""
        with patch("sudarshan.execution.remote.shutil.which", return_value=None):
            with self.assertRaises(BackendUnavailable):
                self.backend.execute("echo hello")

    @patch("sudarshan.execution.remote.subprocess.run")
    @patch("sudarshan.execution.remote.shutil.which", return_value="ssh")
    def test_command_uses_strict_host_key_options(self, _which, run) -> None:
        """SSH uses an argument list and never elects to accept an unknown host key."""
        run.return_value = subprocess.CompletedProcess([], 0, "hello\n", "")
        result = self.backend.execute("printf hello")
        command = run.call_args.args[0]
        self.assertEqual(result.stdout, "hello\n")
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("BatchMode=yes", command)
        self.assertIn("agent@build.example", command)
        self.assertNotIn("StrictHostKeyChecking=no", command)

    @patch("sudarshan.execution.remote.subprocess.run")
    @patch("sudarshan.execution.remote.shutil.which", return_value="ssh")
    def test_authentication_failure_is_structured(self, _which, run) -> None:
        """SSH's authentication-style exit code remains clear to the caller."""
        run.return_value = subprocess.CompletedProcess([], 255, "", "Permission denied")
        result = self.backend.execute("id")
        self.assertEqual(result.exit_code, 255)
        self.assertIn("authentication", result.error or "")
        self.assertIn("Permission denied", result.stderr)

    @patch("sudarshan.execution.remote.subprocess.run")
    @patch("sudarshan.execution.remote.shutil.which", return_value="ssh")
    def test_timeout_raises_distinct_exception(self, _which, run) -> None:
        """SSH timeouts are not converted into an ambiguous failed result."""
        run.side_effect = subprocess.TimeoutExpired(["ssh"], 0.01)
        with self.assertRaises(ExecutionTimeout):
            self.backend.execute("sleep 5", timeout=0.01)

    @patch("sudarshan.execution.remote.subprocess.run")
    @patch("sudarshan.execution.remote.shutil.which", return_value="ssh")
    def test_file_helper_validates_remote_paths_and_quotes_arguments(self, _which, run) -> None:
        """Remote file paths are passed as helper data, never concatenated shell code."""
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.backend.read_file("../../etc/passwd; touch owned")
        remote_command = run.call_args.args[0][-1]
        self.assertIn(REMOTE_FILE_HELPER, remote_command)
        self.assertIn("resolve()", REMOTE_FILE_HELPER)
        self.assertIn("relative_to(root)", REMOTE_FILE_HELPER)
        self.assertIn("'../../etc/passwd; touch owned'", remote_command)


if __name__ == "__main__":
    unittest.main()
