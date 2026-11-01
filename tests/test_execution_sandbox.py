"""Execution tests: Docker availability, hardening flags, and result handling."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sudarshan.execution.base import BackendUnavailable, ExecutionPermissionError, ExecutionTimeout
from sudarshan.execution.sandbox import SandboxedExecutionBackend


class SandboxedExecutionBackendTests(unittest.TestCase):
    """Verify Docker command construction without requiring Docker itself."""

    def setUp(self) -> None:
        """Create a writable test workspace within the repository sandbox."""
        parent = Path(__file__).resolve().parent.parent / "work"
        parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.backend = SandboxedExecutionBackend(
            self.temporary.name, image="python:3.12-alpine", memory="256m", cpus="0.5",
        )

    def tearDown(self) -> None:
        """Remove the scratch workspace after each mocked Docker test."""
        self.temporary.cleanup()

    def test_unavailable_docker_never_falls_back_to_local(self) -> None:
        """Missing Docker is a clear availability error, not host command execution."""
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value=None):
            with self.assertRaises(BackendUnavailable):
                self.backend.execute("echo should-not-run")

    @patch("sudarshan.execution.sandbox.run_owned")
    @patch("sudarshan.execution.sandbox.trusted_executable", return_value="docker")
    def test_hardened_docker_command_and_resource_limits(self, _which, run) -> None:
        """Network, privilege, root filesystem, and resource settings are explicit."""
        run.return_value = subprocess.CompletedProcess([], 0, "hello\n", "")
        result = self.backend.execute("python -c 'print(\"hello\")'")
        command = run.call_args.args[0]
        rendered = " ".join(command)
        mount = command[command.index("--mount") + 1]
        self.assertEqual(mount, f"type=bind,src={self.backend.root},dst=/workspace")
        self.assertTrue(all("=" in field for field in mount.split(",")))
        self.assertEqual(result.execution_backend, "sandbox")
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("ALL", command)
        self.assertIn("--read-only", command)
        self.assertIn("--memory", command)
        self.assertIn("256m", command)
        self.assertIn("--cpus", command)
        self.assertIn("0.5", command)
        self.assertIn("--user", command)
        self.assertNotIn("--privileged", command)
        self.assertNotIn("docker.sock", rendered)

    @patch("sudarshan.execution.sandbox.run_owned")
    @patch("sudarshan.execution.sandbox.trusted_executable", return_value="docker")
    def test_timeout_and_container_failure_remain_distinct(self, _which, run) -> None:
        """Timeouts raise while ordinary nonzero container exits return details."""
        run.side_effect = [ExecutionTimeout("timeout"), subprocess.CompletedProcess([], 0, "", "")]
        with self.assertRaises(ExecutionTimeout):
            self.backend.execute("sleep 5", timeout=0.01)
        run.side_effect = None
        run.return_value = subprocess.CompletedProcess([], 3, "", "bad command")
        result = self.backend.execute("false")
        self.assertEqual(result.exit_code, 3)
        self.assertIn("container exited with 3", result.error)
        self.assertIn("cleanup unconfirmed", result.error)
        self.assertIn("bad command", result.stderr)

    def test_file_path_traversal_is_rejected_before_docker(self) -> None:
        """Container mounting does not make host workspace escape acceptable."""
        with self.assertRaises(ExecutionPermissionError):
            self.backend.read_file("../../outside.txt")


if __name__ == "__main__":
    unittest.main()
