import ctypes
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from unittest.mock import patch, Mock

from sudarshan.execution.base import ExecutionError, ExecutionTimeout, ExecutionPermissionError
from sudarshan.execution.filesystem import WorkspaceFiles, FILE_LIMIT
from sudarshan.execution.local import LocalExecutionBackend
from sudarshan.execution.process import run_owned, validate_timeout
from sudarshan.execution import process
from sudarshan.tools import core_tools
from tests.test_harness_security import WorkspaceCase


class TestOwnedProcesses(WorkspaceCase):
    def worker(self, finish=False):
        path = self.root / "worker.py"
        path.write_text("""import os, subprocess, sys, time
from pathlib import Path
pids = Path('pids.txt')
with pids.open('a') as handle:
    handle.write(str(os.getpid()) + '\\n')
depth = int(sys.argv[1])
if depth:
    subprocess.Popen([sys.executable, '-I', '-S', __file__, str(depth-1)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
if sys.argv[1] == '2' and FINISH:
    deadline = time.monotonic() + 3
    while len(pids.read_text().splitlines()) < 3 and time.monotonic() < deadline:
        time.sleep(.01)
else:
    time.sleep(20)
""".replace("FINISH", repr(finish)), encoding="utf-8")
        return [sys.executable, "-I", "-S", str(path), "2"]

    def assert_workers_stopped(self):
        pids = [int(value) for value in (self.root / "pids.txt").read_text().splitlines()]
        self.assertEqual(len(pids), 3)
        for pid in pids:
            if os.name == "nt":
                from ctypes import wintypes as w
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
                kernel.OpenProcess.restype = w.HANDLE
                kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
                kernel.CloseHandle.argtypes = [w.HANDLE]
                handle = kernel.OpenProcess(0x100000, False, pid)
                if handle:
                    try:
                        self.assertEqual(kernel.WaitForSingleObject(handle, 2000), 0, f"test-owned process {pid} survived")
                    finally:
                        kernel.CloseHandle(handle)
                else:
                    self.assertEqual(ctypes.get_last_error(), 87)  # PID no longer exists
            else:
                deadline = time.monotonic() + 2
                while True:
                    status = Path(f"/proc/{pid}/stat")
                    try:
                        if status.exists() and status.read_text().split()[2] == "Z":
                            break  # dead orphan pending the OS reaper
                        os.kill(pid, 0)
                    except (ProcessLookupError, FileNotFoundError):
                        break
                    if time.monotonic() >= deadline:
                        self.fail(f"test-owned process {pid} survived")
                    time.sleep(.01)

    def test_timeout_kills_nested_process_tree(self):
        with self.assertRaises(ExecutionTimeout):
            run_owned(self.worker(), cwd=self.root, timeout=1.5)
        self.assert_workers_stopped()

    def test_success_also_cleans_background_children(self):
        result = run_owned(self.worker(finish=True), cwd=self.root, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_workers_stopped()

    def test_interrupt_cleans_tree(self):
        command = self.worker()
        original_sleep = time.sleep
        def interrupt(_):
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                path = self.root / "pids.txt"
                if path.exists() and len(path.read_text().splitlines()) == 3:
                    raise KeyboardInterrupt
                original_sleep(.01)
            self.fail("test workers did not start")
        with patch.object(process.time, "sleep", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_owned(command, cwd=self.root, timeout=5)
        self.assert_workers_stopped()

    def test_output_exhaustion_is_bounded(self):
        code = "import os; [os.write(1, b'x'*4096) for _ in range(400)]"
        with self.assertRaisesRegex(ExecutionError, "output budget"):
            run_owned([sys.executable, "-I", "-S", "-c", code], cwd=self.root, timeout=5)

    def test_capture_is_bounded_and_redacted(self):
        code = "print('api_key=synthetic-secret'); print('x'*20000); print('password=synthetic-password')"
        result = run_owned([sys.executable, "-I", "-S", "-c", code], cwd=self.root)
        self.assertNotIn("synthetic-secret", result.stdout)
        self.assertNotIn("synthetic-password", result.stdout)
        self.assertIn("truncated", result.stdout)
        self.assertLess(len(result.stdout), 12200)

    def test_actual_environment_excludes_synthetic_secrets(self):
        code = "import os; print({k:v for k,v in os.environ.items() if k.startswith('PHASE2_')})"
        with patch.dict(os.environ, {"PHASE2_UNKNOWN_KEY": "synthetic", "PHASE2_PASSWORD": "synthetic"}):
            result = run_owned([sys.executable, "-I", "-S", "-c", code], cwd=self.root)
        self.assertEqual(result.stdout.strip(), "{}")

    def test_timeout_validation_and_empty_commands_before_spawn(self):
        for value in (None, "bad", "nan", "inf", 0, -1, 3601):
            with self.subTest(value=value), patch.object(process.subprocess, "Popen") as popen:
                with self.assertRaises(ValueError):
                    run_owned("echo test", shell=True, timeout=value)
                popen.assert_not_called()
        for command in ("", " ", "x\x00y", None):
            with self.subTest(command=command), self.assertRaises(ValueError):
                run_owned(command, shell=True)

    def test_windows_job_assignment_failure_never_releases_gate(self):
        if os.name != "nt":
            self.skipTest("Windows Job Object ownership test")
        marker = self.root / "must-not-exist.txt"
        with patch.object(process.WindowsJob, "assign", side_effect=ExecutionError("assignment failed")):
            with self.assertRaisesRegex(ExecutionError, "assignment failed"):
                run_owned([sys.executable, "-I", "-S", "-c", f"open({str(marker)!r}, 'w').write('bad')"], cwd=self.root)
        self.assertFalse(marker.exists())

    def test_core_shell_uses_owned_runner_and_reports_nonzero(self):
        tools = {tool.name: tool for tool in core_tools(self.root)}
        with patch("sudarshan.tools.run_owned", side_effect=ExecutionTimeout("test timeout")):
            self.assertIn("timeout", tools["bash"].run("echo test"))
        with patch("sudarshan.tools.run_owned", return_value=subprocess.CompletedProcess([], 7, "failure output", "")):
            self.assertIn("exited with 7", tools["bash"].run("echo test"))

    def test_working_directory_is_start_location_not_shell_confinement(self):
        # Demonstrate the limitation only against a sibling disposable directory.
        sibling = self.base / "sibling"
        sibling.mkdir()
        quote = subprocess.list2cmdline if os.name == "nt" else shlex.join
        code = f"import os; os.chdir({str(sibling)!r}); print(os.getcwd())"
        result = LocalExecutionBackend(self.root).execute(quote([sys.executable, "-I", "-S", "-c", code]))
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), sibling)

    def test_windows_owner_crash_closes_job_and_kills_descendants(self):
        if os.name != "nt":
            self.skipTest("Windows Job Object owner-death guarantee")
        import json
        from sudarshan.environment import safe_shell_environment
        command = self.worker()
        source_root = str(Path(__file__).resolve().parents[1])
        code = """import os, sys, time, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from sudarshan.execution import process
original_sleep = time.sleep
def crash_when_ready(_):
    path = Path('pids.txt')
    if path.exists() and len(path.read_text().splitlines()) == 3:
        os._exit(7)
    original_sleep(.01)
process.time.sleep = crash_when_ready
process.run_owned(json.loads(sys.argv[2]), cwd=Path.cwd(), timeout=5)
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-c", code, source_root, json.dumps(command)],
                                cwd=self.root, env=safe_shell_environment(), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assert_workers_stopped()

    def test_cleanup_exception_does_not_echo_command_secrets(self):
        if os.name != "nt":
            self.skipTest("Windows mocked process-handle cleanup")
        import io
        fake = Mock()
        fake.stdin = io.BytesIO()
        fake.stdout = io.BytesIO()
        fake.stderr = io.BytesIO()
        fake.poll.return_value = 0
        fake.wait.side_effect = subprocess.TimeoutExpired("synthetic-secret", 5)
        with patch.object(process, "WindowsJob"), patch.object(process.subprocess, "Popen", return_value=fake):
            with self.assertRaisesRegex(ExecutionError, "cleanup unconfirmed") as caught:
                run_owned("echo harmless", shell=True, cwd=self.root)
        self.assertNotIn("synthetic-secret", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_reader_failure_has_no_background_traceback(self):
        if os.name != "nt":
            self.skipTest("Windows mocked process-handle capture")
        import io
        fake = Mock()
        fake.stdin = io.BytesIO()
        fake.stdout.read.side_effect = OSError("synthetic-secret")
        fake.stderr = io.BytesIO()
        fake.poll.return_value = 0
        with patch.object(process, "WindowsJob"), patch.object(process.subprocess, "Popen", return_value=fake), patch("threading.excepthook") as hook:
            with self.assertRaisesRegex(ExecutionError, "capture failed"):
                run_owned("echo harmless", shell=True, cwd=self.root)
        hook.assert_not_called()


class TestHandleFilesystem(WorkspaceCase):
    def test_absolute_traversal_drive_and_stream_paths(self):
        files = WorkspaceFiles(self.root)
        for path in ("../escape.txt", str(self.base / "escape.txt"), "C:relative.txt", "C:\\outside.txt", "\\\\server\\share\\file"):
            with self.subTest(path=path), self.assertRaises(ExecutionPermissionError):
                files.write_text(path, "blocked")
        if os.name == "nt":
            for path in ("file.txt:stream", "NUL", "folder./file.txt", "file.txt "):
                with self.subTest(path=path), self.assertRaises(ExecutionPermissionError):
                    files.write_text(path, "blocked")
        self.assertFalse((self.base / "escape.txt").exists())

    def test_hardlink_alias_cannot_modify_sibling(self):
        outside = self.base / "outside.txt"
        outside.write_text("original", encoding="utf-8")
        try:
            os.link(outside, self.root / "alias.txt")
        except OSError as error:
            self.skipTest(f"hard links unavailable: {type(error).__name__}, winerror={getattr(error, 'winerror', None)}")
        files = WorkspaceFiles(self.root)
        with self.assertRaises(ExecutionPermissionError):
            files.write_text("alias.txt", "changed")
        with self.assertRaises(ExecutionPermissionError):
            files.read_text("alias.txt")
        self.assertEqual(outside.read_text(encoding="utf-8"), "original")

    def test_edit_holds_same_handle_and_preserves_sibling(self):
        files = WorkspaceFiles(self.root)
        files.write_text("file.txt", "original")
        with files.open("file.txt", "r+") as handle:
            if os.name == "nt":
                with self.assertRaises(PermissionError):
                    (self.root / "file.txt").rename(self.root / "moved.txt")
            handle.seek(0)
            handle.write("updated!")
            handle.truncate()
        self.assertEqual(files.read_text("file.txt"), "updated!")

    def test_root_replacement_is_rejected(self):
        files = WorkspaceFiles(self.root)
        moved = self.base / "old-workspace"
        self.root.rename(moved)
        self.root.mkdir()
        with self.assertRaises(ExecutionPermissionError):
            files.write_text("new.txt", "blocked")
        self.assertFalse((self.root / "new.txt").exists())
        self.assertFalse((moved / "new.txt").exists())

    def test_file_size_limits_before_write(self):
        files = WorkspaceFiles(self.root)
        files.write_text("file.txt", "keep")
        with self.assertRaises(ValueError):
            files.write_text("file.txt", "x" * (FILE_LIMIT + 1))
        self.assertEqual(files.read_text("file.txt"), "keep")

    def test_windows_junction_escape(self):
        if os.name != "nt":
            self.skipTest("Windows junction test")
        target = self.base / "outside"
        target.mkdir()
        junction = self.root / "junction"
        result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, text=True)
        if result.returncode:
            self.skipTest("Windows junction creation unavailable: " + (result.stderr or result.stdout).strip())
        if hasattr(junction, "is_junction"):
            self.assertTrue(junction.is_junction())
        with self.assertRaises(ExecutionPermissionError):
            WorkspaceFiles(self.root).write_text("junction/blocked.txt", "blocked")
        self.assertEqual(list(target.iterdir()), [])
        self.assertNotIn("junction", LocalExecutionBackend(self.root).list_files().stdout)

    def test_parent_pinned_against_rename(self):
        if os.name != "nt":
            self.skipTest("Windows directory sharing-lock test")
        files = WorkspaceFiles(self.root)
        files.write_text("nested/file.txt", "original")
        with files.open("nested/file.txt", "r+"):
            with self.assertRaises(PermissionError):
                (self.root / "nested").rename(self.root / "renamed")
        self.assertEqual(files.read_text("nested/file.txt"), "original")

    def test_posix_symlink_swap_rejected_without_truncation(self):
        if os.name == "nt":
            self.skipTest("POSIX O_NOFOLLOW descriptor test; Windows uses reparse handles")
        target = self.base / "outside.txt"
        target.write_text("original", encoding="utf-8")
        (self.root / "link.txt").symlink_to(target)
        with self.assertRaises(ExecutionPermissionError):
            WorkspaceFiles(self.root).write_text("link.txt", "blocked")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_windows_reparse_and_link_metadata_rejected_before_truncation(self):
        if os.name != "nt":
            self.skipTest("Windows handle metadata regression")
        from ctypes import wintypes as w
        files = WorkspaceFiles(self.root)
        files.write_text("file.txt", "original")
        original_loader = ctypes.WinDLL
        for kind in ("reparse", "hardlink"):
            with self.subTest(kind=kind):
                kernel = original_loader("kernel32", use_last_error=True)
                inspect = kernel.GetFileInformationByHandle
                inspect.argtypes = [w.HANDLE, ctypes.c_void_p]
                inspect.restype = w.BOOL
                def metadata(handle, info):
                    result = inspect(handle, info)
                    if not info._obj.attributes & 0x10:
                        if kind == "reparse":
                            info._obj.attributes |= 0x400
                        else:
                            info._obj.links = 2
                    return result
                proxy = Mock(wraps=kernel)
                proxy.GetFileInformationByHandle = Mock(side_effect=metadata)
                with patch.object(ctypes, "WinDLL", return_value=proxy):
                    with self.assertRaises(ExecutionPermissionError):
                        files.write_text("file.txt", "blocked")
                self.assertEqual(files.read_text("file.txt"), "original")


class TestBackendHardening(WorkspaceCase):
    def test_docker_interrupt_cleanup_is_exact_and_not_host_deletion(self):
        from sudarshan.execution.sandbox import SandboxedExecutionBackend
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value="mock-docker"), patch(
                "sudarshan.execution.sandbox.run_owned", side_effect=[KeyboardInterrupt(), subprocess.CompletedProcess([], 0, "", "")]) as run:
            with self.assertRaises(KeyboardInterrupt):
                SandboxedExecutionBackend(self.root).execute("echo harmless")
        args = run.call_args_list[0].args[0]
        name = args[args.index("--name") + 1]
        self.assertEqual(run.call_args_list[1].args[0], ["mock-docker", "rm", "-f", name])
        self.assertIn("--pids-limit", args)
        self.assertIn("--init", args)

    def test_ssh_timeout_explicitly_does_not_promise_remote_cleanup(self):
        from sudarshan.execution.remote import RemoteExecutionBackend
        with patch("sudarshan.execution.remote.trusted_executable", return_value="mock-ssh"), patch(
                "sudarshan.execution.remote.run_owned", side_effect=ExecutionTimeout("synthetic-secret")):
            with self.assertRaisesRegex(ExecutionTimeout, "remote termination unconfirmed") as caught:
                RemoteExecutionBackend("example.invalid").execute("echo harmless")
        self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_remote_shell_uses_empty_environment_and_no_login_startup(self):
        from sudarshan.execution.remote import RemoteExecutionBackend
        backend = RemoteExecutionBackend("example.invalid")
        with patch.object(backend, "_ssh", return_value=None) as ssh:
            backend.execute("echo harmless")
        command = ssh.call_args.args[0]
        self.assertIn("/usr/bin/env -i PATH=/usr/bin:/bin /bin/sh -c", command)
        self.assertNotIn("sh -lc", command)

    def test_remote_file_helper_local_roundtrip_without_ssh(self):
        from sudarshan.execution.remote import REMOTE_FILE_HELPER
        for action, content in (("write", "Unicode café नमस्ते"), ("read", None)):
            args = [sys.executable, "-I", "-S", "-X", "utf8", "-c", REMOTE_FILE_HELPER, str(self.root), action, "nested/café.txt"]
            if content is not None:
                args.append(content)
            result = run_owned(args, cwd=self.root)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Unicode café नमस्ते")

    def test_adapter_exception_and_result_diagnostics_are_redacted(self):
        from sudarshan.execution.base import backend_tools, ExecutionResult
        backend = Mock()
        backend.execute.side_effect = ExecutionError("synthetic-secret")
        tools = {tool.name: tool for tool in backend_tools(backend, "owned")}
        self.assertNotIn("synthetic-secret", tools["owned_bash"].run("echo harmless"))
        result = ExecutionResult("api_key=synthetic-key", "", 1, "mock", 0, "password=synthetic-password")
        self.assertNotIn("synthetic-key", result.text())
        self.assertNotIn("synthetic-password", result.text())

    def test_abbreviated_and_obfuscated_windows_deletion_is_denied(self):
        from sudarshan.security import Policy
        # Inspection only. These strings are never passed to a process.
        for command in ("Remove-Item target -r", "ri target -rec", "ReMoVe-ItEm target -RECURSE:$true", "Re`move-Item target -Recurse", "r^d /s target", "rm target -Recurse"):
            with self.subTest(command=command):
                self.assertIsNotNone(Policy("yolo").check({"name": "bash", "args": {"command": command}}))

    def test_untrusted_comspec_cannot_select_command_interpreter(self):
        if os.name != "nt":
            self.skipTest("Windows command interpreter selection")
        from sudarshan.execution.process import _environment
        with patch.dict(os.environ, {"COMSPEC": str(self.root / "untrusted.exe")}):
            env = _environment()
            result = run_owned("echo trusted-shell", shell=True, cwd=self.root)
        self.assertNotEqual(env["COMSPEC"], str(self.root / "untrusted.exe"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("trusted-shell", result.stdout)

    def test_posix_session_leader_is_used(self):
        if os.name == "nt":
            self.skipTest("POSIX process groups unavailable on Windows")
        result = run_owned([sys.executable, "-I", "-S", "-c", "import os; print(os.getpid()==os.getsid(0))"], cwd=self.root)
        self.assertEqual(result.stdout.strip(), "True")

    def test_generated_product_tests_have_owned_timeout_cleanup(self):
        from demos.product_approval import product_harness
        harness = product_harness(self.root, persist=False)
        with patch("demos.product_approval.run_owned", side_effect=ExecutionTimeout("timed out")), patch(
                "demos.product_approval.subprocess.run", side_effect=AssertionError("unmanaged execution")):
            output = harness.tools["bash"].run("python -m unittest discover -v")
        self.assertIn("product tests timed out", output)

    def test_artifact_test_runner_uses_owned_execution(self):
        from demos.product_verify import _run
        with patch("demos.product_verify.run_owned", side_effect=ExecutionTimeout("timed out")), patch(
                "demos.product_verify.subprocess.run", side_effect=AssertionError("unmanaged execution")):
            with self.assertRaises(ExecutionTimeout):
                _run(self.root, ["-m", "unittest", "discover", "-v"])

    def test_failed_docker_client_also_checks_container_cleanup(self):
        from sudarshan.execution.sandbox import SandboxedExecutionBackend
        with patch("sudarshan.execution.sandbox.trusted_executable", return_value="mock-docker"), patch(
                "sudarshan.execution.sandbox.run_owned", side_effect=[subprocess.CompletedProcess([], 125, "", "client failed"),
                                                                        subprocess.CompletedProcess([], 1, "", "cleanup failed")]) as run:
            result = SandboxedExecutionBackend(self.root).execute("echo harmless")
        self.assertEqual(result.exit_code, 125)
        self.assertIn("cleanup unconfirmed", result.error)
        self.assertEqual(run.call_count, 2)

    def test_backend_client_resolution_excludes_workspace_and_relative_path(self):
        from sudarshan.execution.process import trusted_executable
        search = self.base / "trusted-bin"
        search.mkdir()
        suffix = ".exe" if os.name == "nt" else ""
        name = "phase2-client" + suffix
        local = self.root / name
        trusted = search / name
        local.write_bytes(b"not executed")
        trusted.write_bytes(b"not executed")
        if os.name != "nt":
            local.chmod(0o700)
            trusted.chmod(0o700)
        with patch.object(process.os, "get_exec_path", return_value=[str(self.root), ".", "", str(search)]):
            self.assertEqual(trusted_executable(name, self.root), str(trusted))
        self.assertIsNone(trusted_executable(str(local), self.root))

    def test_windows_batch_client_is_not_silently_executed_via_shell(self):
        if os.name != "nt":
            self.skipTest("Windows batch-file implicit shell behavior")
        from sudarshan.execution.process import trusted_executable
        script = self.base / "client.cmd"
        script.write_text("@echo harmless", encoding="utf-8")
        self.assertIsNone(trusted_executable(str(script), self.root))
