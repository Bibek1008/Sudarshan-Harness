import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
from unittest.mock import Mock, patch

from sudarshan.execution.base import (BackendUnavailable, ExecutionError, ExecutionTimeout,
    ExecutionPermissionError, ExecutionRegistry, ExecutionResult, backend_tools)
from sudarshan.execution.local import LocalExecutionBackend
from sudarshan.execution.remote import RemoteExecutionBackend, REMOTE_FILE_HELPER
from sudarshan.execution.sandbox import SandboxedExecutionBackend
from sudarshan.security import Policy
from tests.test_harness_security import WorkspaceCase


class TestExecution(WorkspaceCase):
    def test_local_unicode_roundtrip_and_listing(self):
        backend = LocalExecutionBackend(self.root)
        backend.write_file("nested/café.txt", "नमस्ते café")
        self.assertEqual(backend.read_file("nested/café.txt").stdout, "नमस्ते café")
        self.assertIn("nested/café.txt", backend.list_files("*.txt").stdout)
        with self.assertRaises(ExecutionError):
            backend.read_file("missing.txt")

    def test_local_path_restrictions(self):
        backend = LocalExecutionBackend(self.root)
        for path in ("../outside.txt", str(self.base / "outside.txt")):
            with self.assertRaises(ExecutionPermissionError):
                backend.write_file(path, "x")
            with self.assertRaises(ExecutionPermissionError):
                backend.read_file(path)
        self.assertFalse((self.base / "outside.txt").exists())

    def test_local_symlink_boundary(self):
        outside = self.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        self.symlink(self.root / "link.txt", outside)
        backend = LocalExecutionBackend(self.root)
        with self.assertRaises(ExecutionPermissionError):
            backend.read_file("link.txt")
        self.assertNotIn("link.txt", backend.list_files().stdout)

    def test_actual_local_process_and_nonzero_exit(self):
        backend = LocalExecutionBackend(self.root)
        quote_command = subprocess.list2cmdline if os.name == "nt" else shlex.join
        command = quote_command([sys.executable, "-c", "print('local-ok')"])
        result = backend.execute(command)
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertIn("local-ok", result.stdout)
        result = backend.execute(quote_command([sys.executable, "-c", "raise SystemExit(7)"]))
        self.assertEqual(result.exit_code, 7)
        self.assertIn("7", result.error)

    def test_actual_powershell(self):
        executable = shutil.which("powershell") or shutil.which("pwsh")
        if not executable:
            self.skipTest("PowerShell executable not installed")
        quote_command = subprocess.list2cmdline if os.name == "nt" else shlex.join
        command = quote_command([executable, "-NoProfile", "-NonInteractive", "-Command", "Write-Output 'powershell-ok'"])
        result = LocalExecutionBackend(self.root).execute(command)
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertIn("powershell-ok", result.stdout)

    def test_local_timeouts_and_subprocess_errors(self):
        backend = LocalExecutionBackend(self.root)
        with patch("sudarshan.execution.local.run_owned", side_effect=subprocess.TimeoutExpired("test", 1)):
            with self.assertRaises(ExecutionTimeout):
                backend.execute("test", 1)
        with patch("sudarshan.execution.local.run_owned", side_effect=OSError("failed")):
            with self.assertRaises(ExecutionError):
                backend.execute("test")

    def test_local_permission_error(self):
        backend = LocalExecutionBackend(self.root)
        with patch("sudarshan.execution.local.WorkspaceFiles.write_text", side_effect=PermissionError("denied")):
            with self.assertRaises(ExecutionPermissionError):
                backend.write_file("file.txt", "x")

    def test_local_environment_is_filtered(self):
        code = "import os; print(os.environ.get('SUDARSHAN_API_KEY', 'absent')); print(os.environ.get('PYTHONPATH', 'absent'))"
        quote_command = subprocess.list2cmdline if os.name == "nt" else shlex.join
        with patch.dict(os.environ, {"SUDARSHAN_API_KEY": "synthetic-secret", "PYTHONPATH": "injection"}):
            result = LocalExecutionBackend(self.root).execute(quote_command([sys.executable, "-I", "-S", "-c", code]))
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["absent", "absent"])

    def test_docker_hardening_and_success(self):
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value="docker-test"), patch(
                "sudarshan.execution.sandbox.run_owned", return_value=subprocess.CompletedProcess([], 0, "ok", "")) as run:
            result = SandboxedExecutionBackend(self.root).execute("echo ok")
        self.assertEqual(result.stdout, "ok")
        arguments = run.call_args.args[0]
        for flag in ("--rm", "--read-only", "--cap-drop", "--security-opt", "--user"):
            self.assertIn(flag, arguments)
        self.assertEqual(arguments[arguments.index("--network") + 1], "none")
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_docker_timeout_cleanup(self):
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value="docker-test"), patch(
                "sudarshan.execution.sandbox.run_owned", side_effect=[ExecutionTimeout("test timed out"), subprocess.CompletedProcess([], 0, "", "")]) as run:
            with self.assertRaisesRegex(ExecutionTimeout, "container removed"):
                SandboxedExecutionBackend(self.root).execute("test", 1)
        original = run.call_args_list[0].args[0]
        name = original[original.index("--name") + 1]
        self.assertEqual(run.call_args_list[1].args[0], ["docker-test", "rm", "-f", name])

    def test_docker_cleanup_failure_is_explicit(self):
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value="docker-test"), patch(
                "sudarshan.execution.sandbox.run_owned", side_effect=[ExecutionTimeout("test timed out"), subprocess.CompletedProcess([], 1, "", "denied")]):
            with self.assertRaisesRegex(ExecutionTimeout, "cleanup unconfirmed"):
                SandboxedExecutionBackend(self.root).execute("test", 1)

    def test_docker_unavailable_and_failed_process(self):
        backend = SandboxedExecutionBackend(self.root)
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value=None):
            with self.assertRaises(BackendUnavailable):
                backend.execute("test")
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value="docker-test"), patch(
                "sudarshan.execution.sandbox.run_owned", side_effect=OSError("failed")):
            with self.assertRaises(ExecutionError):
                backend.execute("test")
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value="docker-test"), patch(
                "sudarshan.execution.sandbox.run_owned", return_value=subprocess.CompletedProcess([], 125, "", "failed")):
            self.assertEqual(backend.execute("test").exit_code, 125)

    def test_docker_path_and_option_restrictions(self):
        backend = SandboxedExecutionBackend(self.root)
        with self.assertRaises(ExecutionPermissionError):
            backend.read_file("../outside")
        for options in ({"user": "root"}, {"user": None}, {"image": "--privileged"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                SandboxedExecutionBackend(self.root, **options)

    def test_ssh_options_and_quoted_injection(self):
        backend = RemoteExecutionBackend("example.invalid", workdir="/workspace with spaces")
        with patch("sudarshan.execution.remote.trusted_executable", return_value="ssh-test"), patch(
                "sudarshan.execution.remote.run_owned", return_value=subprocess.CompletedProcess([], 0, "ok", "")) as run:
            backend.write_file("file'; echo injected; '.txt", "text $(echo injected)")
        arguments = run.call_args.args[0]
        self.assertIn("StrictHostKeyChecking=yes", arguments)
        self.assertIn("BatchMode=yes", arguments)
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        import shlex
        parts = shlex.split(arguments[-1])
        self.assertEqual(parts[-2:], ["file'; echo injected; '.txt", "text $(echo injected)"])

    def test_ssh_errors_timeouts_and_missing_executable(self):
        backend = RemoteExecutionBackend("example.invalid")
        with patch("sudarshan.execution.remote.trusted_executable", return_value=None):
            with self.assertRaises(BackendUnavailable):
                backend.execute("test")
        for effect, expected in ((OSError("failed"), BackendUnavailable), (subprocess.TimeoutExpired("test", 1), ExecutionTimeout)):
            with patch("sudarshan.execution.remote.trusted_executable", return_value="ssh-test"), patch(
                    "sudarshan.execution.remote.run_owned", side_effect=effect):
                with self.assertRaises(expected):
                    backend.execute("test", 1)
        with patch("sudarshan.execution.remote.trusted_executable", return_value="ssh-test"), patch(
                "sudarshan.execution.remote.run_owned", return_value=subprocess.CompletedProcess([], 255, "", "denied")):
            self.assertIn("host-key", backend.execute("test").error)

    def test_ssh_connection_argument_injection(self):
        for host in ("-oProxyCommand=evil", "host;echo", "host\nother", "host with space"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                RemoteExecutionBackend(host)
        with self.assertRaises(ValueError):
            RemoteExecutionBackend("example.invalid", port=0)

    def test_remote_helper_path_restrictions_without_network(self):
        args = [sys.executable, "-c", REMOTE_FILE_HELPER, str(self.root), "write", "../escape.txt", "blocked"]
        result = subprocess.run(args, cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes", result.stderr)
        self.assertFalse((self.base / "escape.txt").exists())

    def test_registry_and_backend_policy_adapter(self):
        registry = ExecutionRegistry()
        with self.assertRaises(BackendUnavailable):
            registry.get()
        backend = Mock()
        registry.register("local", backend)
        self.assertIs(registry.get(), backend)
        with self.assertRaises(ValueError):
            registry.register("local", backend)
        tools = {tool.name: tool for tool in backend_tools(backend, "local", Policy("read-only"))}
        self.assertIn("BLOCKED", tools["local_write_file"].run("x", "y"))
        backend.write_file.assert_not_called()
        backend.read_file.return_value = ExecutionResult("ok", "", 0, "local", 0)
        self.assertIn("ok", tools["local_read_file"].run("x"))
        with self.assertRaises(ValueError):
            backend_tools(backend, "bad-prefix")

    def test_backend_startup_exceptions_do_not_leak_secrets(self):
        cases = [(LocalExecutionBackend(self.root), "sudarshan.execution.local", ExecutionError),
                 (RemoteExecutionBackend("example.invalid"), "sudarshan.execution.remote", BackendUnavailable),
                 (SandboxedExecutionBackend(self.root), "sudarshan.execution.sandbox", ExecutionError)]
        for backend, module, expected in cases:
            with self.subTest(backend=backend.name), patch(module + ".run_owned", side_effect=OSError("synthetic-secret")):
                if backend.name == "local":
                    with self.assertRaises(expected) as caught:
                        backend.execute("test")
                else:
                    with patch(module + ".trusted_executable", return_value="mock-executable"):
                        with self.assertRaises(expected) as caught:
                            backend.execute("test")
                self.assertNotIn("synthetic-secret", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    def test_backend_file_permission_error_does_not_leak(self):
        backend = LocalExecutionBackend(self.root)
        with patch("sudarshan.execution.local.WorkspaceFiles.read_text", side_effect=PermissionError("synthetic-secret")):
            with self.assertRaises(ExecutionPermissionError) as caught:
                backend.read_file("file.txt")
        self.assertNotIn("synthetic-secret", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
