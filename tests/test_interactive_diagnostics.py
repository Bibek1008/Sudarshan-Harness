"""CLI-only usability and secret-safe diagnostics; no live provider requests."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from sudarshan import cli, error_reporting, provider
from sudarshan.environment import safe_shell_environment
from sudarshan.execution.base import ExecutionTimeout
from sudarshan.harness import Harness
from sudarshan.security import Policy
from sudarshan.tools import tool
from tests.test_harness_security import WorkspaceCase


class InteractiveDiagnosticsTests(WorkspaceCase):
    def test_exit_commands_are_local_case_insensitive_and_whitespace_tolerant(self):
        for text in ("exit", "quit", ":q", " EXIT ", " QuIt ", " :Q ", "\x1a"):
            with self.subTest(text=text), patch.object(cli, "Harness") as harness, patch(
                "builtins.input", return_value=text
            ), redirect_stdout(io.StringIO()) as output:
                cli.main(["--mode", "read-only"])
                harness.return_value.run.assert_not_called()
                self.assertIn("natural-language tasks", output.getvalue())
                self.assertIn("PowerShell", output.getvalue())
                self.assertIn("before launching Sudarshan again", output.getvalue())
                self.assertIn("Ctrl+Z then Enter", output.getvalue())

    def test_eof_and_empty_input_never_send_a_request(self):
        with patch.object(cli, "Harness") as harness, patch("builtins.input", side_effect=["", "  ", EOFError]), redirect_stdout(io.StringIO()):
            cli.main([])
        harness.return_value.run.assert_not_called()

    def test_shell_commands_and_nested_launcher_get_local_guidance(self):
        commands = ['Get-ChildItem "C:\\project"', 'Get-Content .env',
                    'sudarshan -d "C:\\project"', 'python -m sudarshan', 'pwsh.exe -Command dir',
                    'cmd /c dir', 'bash -c ls']
        with patch.object(cli, "Harness") as harness, patch("builtins.input", side_effect=commands + ["exit"]), redirect_stdout(io.StringIO()) as output:
            cli.main(["--mode", "read-only"])
        harness.return_value.run.assert_not_called()
        self.assertEqual(output.getvalue().count("That looks like a shell command"), len(commands))
        self.assertNotIn("Get-Content .env", output.getvalue())

    def test_natural_tasks_and_headless_exit_text_keep_existing_meaning(self):
        with patch.object(cli, "Harness") as harness, patch("builtins.input", side_effect=["Explain how Get-ChildItem works", "exit"]), redirect_stdout(io.StringIO()):
            cli.main([])
        harness.return_value.run.assert_called_once_with("Explain how Get-ChildItem works")
        with patch.object(cli, "Harness") as harness, redirect_stdout(io.StringIO()):
            cli.main(["-p", "exit"])
        harness.return_value.run.assert_called_once_with("exit")

    def test_real_stdin_eof_and_windows_control_z_exit_without_requests(self):
        code = (
            "import sys; from sudarshan import provider; from sudarshan.cli import main; "
            "provider.complete=lambda *args: sys.exit(77); "
            "main(['-d',sys.argv[1],'--mode','read-only'])"
        )
        inputs = [b""] + ([b"\x1a\r\n"] if os.name == "nt" else [])
        for content in inputs:
            with self.subTest(content=content):
                result = subprocess.run([sys.executable, "-c", code, str(self.root)],
                                        input=content, cwd=Path(__file__).resolve().parents[1],
                                        env=safe_shell_environment(), capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                self.assertNotIn(b"Error", result.stderr)
        self.assertFalse((self.root / ".sudarshan").exists())

    def test_default_is_short_and_unexpected_errors_do_not_escape_unsanitized(self):
        for failure in (RuntimeError, TypeError, KeyError, AssertionError):
            with self.subTest(failure=failure), patch.object(cli, "Harness") as harness, redirect_stderr(io.StringIO()) as output:
                harness.return_value.run.side_effect = failure("UNLABELLED_PRIVATE_VALUE")
                with self.assertRaises(SystemExit) as caught:
                    cli.main(["-p", "task"])
                self.assertEqual(caught.exception.code, 1)
                self.assertIn("Error [internal]", output.getvalue())
                self.assertIn("--verbose", output.getvalue())
                self.assertNotIn("UNLABELLED_PRIVATE_VALUE", output.getvalue())
                self.assertNotIn("traceback", output.getvalue())
                self.assertNotIn("--resume", output.getvalue())

    def test_classification_uses_known_details_without_raw_values(self):
        cases = [
            (RuntimeError("Gemini HTTP 401"), "authentication"),
            (RuntimeError("Gemini HTTP 403"), "authentication"),
            (RuntimeError("Gemini HTTP 404"), "model"),
            (ValueError("Invalid Gemini model name"), "model"),
            (RuntimeError("Gemini HTTP 429"), "quota"),
            (RuntimeError("Gemini request failed after 5 attempts: HTTP 503"), "network"),
            (RuntimeError("Gemini request failed after 5 attempts: network or timeout error"), "network"),
            (URLError("private network details"), "network"),
            (ValueError("Unclosed quote in project .env on line 3"), "configuration"),
            (RuntimeError("Model returned a malformed tool call"), "provider"),
            (PermissionError("private path"), "workspace"),
            (ExecutionTimeout("private output"), "tool"),
        ]
        for error, category in cases:
            with self.subTest(category=category), redirect_stderr(io.StringIO()) as output:
                error_reporting.report(error, verbose=True)
                self.assertIn(f"Error [{category}]", output.getvalue())
                self.assertNotIn("private", output.getvalue())

    def test_verbose_omits_secrets_source_locals_chain_headers_and_response_body(self):
        secrets = ["UNLABELLED_PRIVATE_VALUE", "synthetic-api-value", "synthetic-password",
                   "synthetic-bearer", "PRIVATE_ENV_CONTENTS", "PRIVATE_SOURCE_LINE"]
        body = io.BytesIO(b"PRIVATE_ENV_CONTENTS")
        source = "raise RuntimeError('PRIVATE_SOURCE_LINE')"
        try:
            try:
                raise HTTPError("https://example.invalid/?key=synthetic-api-value", 403,
                                "Authorization: Bearer synthetic-bearer", {"x-goog-api-key": "synthetic-api-value"}, body)
            except HTTPError as cause:
                try:
                    exec(compile(source, "PRIVATE_ENV_CONTENTS.py", "exec"))
                except RuntimeError as error:
                    error.args = ("UNLABELLED_PRIVATE_VALUE password=synthetic-password",)
                    raise error from cause
        except RuntimeError as error:
            with redirect_stderr(io.StringIO()) as output:
                error_reporting.report(error, verbose=True)
        text = output.getvalue()
        self.assertIn("authentication", text)
        self.assertIn("Exception type: RuntimeError", text)
        self.assertIn("Sanitized traceback", text)
        self.assertIn("<external frame>", text)
        for secret in secrets:
            self.assertNotIn(secret, text)
        self.assertEqual(body.tell(), 0)  # The diagnostic never reads HTTP bodies.
        body.close()

    def test_verbose_reports_package_locations_and_catches_startup_errors(self):
        with patch.object(provider, "complete", side_effect=TypeError("PRIVATE_DETAIL")), redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit):
                cli.main(["-d", str(self.root), "-p", "task", "--verbose", "--no-telemetry"])
        self.assertIn("cli.py, line", output.getvalue())
        self.assertIn("harness.py, line", output.getvalue())
        self.assertIn("Exception type: TypeError", output.getvalue())
        self.assertNotIn("PRIVATE_DETAIL", output.getvalue())
        self.assertIsNone(error_reporting.TOOL_ERROR_HANDLER.get())
        with patch.object(cli, "Harness", side_effect=ValueError("PRIVATE_DETAIL")), redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit):
                cli.main(["--verbose", "-p", "task"])
        self.assertIn("Exception type: ValueError", output.getvalue())
        self.assertNotIn("PRIVATE_DETAIL", output.getvalue())

    def test_tool_exception_has_scoped_verbose_traceback_and_safe_event_output(self):
        @tool("Fail safely.")
        def fail():
            raise ValueError("UNLABELLED_PRIVATE_VALUE")

        real = Harness(self.root, extra_tools=[fail], policy=Policy("yolo"),
                       enable_subagents=False, persist=False, on_event=cli._event)
        replies = [{"text": "", "tool_calls": [{"name": "fail", "args": {}}]},
                   {"text": "done", "tool_calls": []}]
        with patch.object(cli, "Harness", return_value=real), patch.object(provider, "complete", side_effect=replies), redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as error:
            cli.main(["-p", "task", "--verbose"])
        self.assertIn("Tool execution failed", output.getvalue())
        self.assertIn("Error [tool]", error.getvalue())
        self.assertIn("Exception type: ValueError", error.getvalue())
        self.assertIn("loop.py, line", error.getvalue())
        self.assertNotIn("UNLABELLED_PRIVATE_VALUE", output.getvalue() + error.getvalue())
        self.assertIsNone(error_reporting.TOOL_ERROR_HANDLER.get())

    def test_read_only_still_denies_shell_and_never_calls_process_backend(self):
        replies = [{"text": "", "tool_calls": [{"name": "bash", "args": {"command": "Get-ChildItem"}}]},
                   {"text": "done", "tool_calls": []}]
        with patch.object(provider, "complete", side_effect=replies), patch("sudarshan.tools.run_owned") as process, redirect_stdout(io.StringIO()) as output:
            cli.main(["-d", str(self.root), "--mode", "read-only", "-p", "List project files"])
        process.assert_not_called()
        self.assertIn("Policy denied", output.getvalue())

    def test_event_errors_and_custom_type_names_cannot_carry_secrets(self):
        with redirect_stdout(io.StringIO()) as output:
            for text in ("ERROR: PRIVATE_ENV_CONTENTS", "BLOCKED: UNLABELLED_PRIVATE_VALUE"):
                cli._event("tool_end", {"name": "fail", "text": text})
        self.assertNotIn("PRIVATE_ENV_CONTENTS", output.getvalue())
        self.assertNotIn("UNLABELLED_PRIVATE_VALUE", output.getvalue())
        error = type("PRIVATE_TYPE_NAME", (Exception,), {})("PRIVATE_ERROR")
        with redirect_stderr(io.StringIO()) as output:
            error_reporting.report(error, verbose=True)
        self.assertNotIn("PRIVATE_TYPE_NAME", output.getvalue())
        self.assertNotIn("PRIVATE_ERROR", output.getvalue())

    def test_resume_hint_requires_nonempty_persisted_session(self):
        harness = Harness(self.root, persist=False)
        with redirect_stdout(io.StringIO()) as output:
            cli._interrupted(harness)
        self.assertNotIn("--resume", output.getvalue())
        harness.persist = True
        harness.session_path = self.root / "saved.jsonl"
        harness.session_path.write_text('{"role":"user","text":"task"}\n', encoding="utf-8")
        with redirect_stdout(io.StringIO()) as output:
            cli._interrupted(harness)
        self.assertIn("--resume", output.getvalue())

    def test_interactive_error_continues_and_handler_is_reset(self):
        with patch.object(cli, "Harness") as harness, patch("builtins.input", side_effect=["first", "second", "exit"]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as output:
            harness.return_value.run.side_effect = [TypeError("PRIVATE_VALUE"), "done"]
            cli.main(["--verbose"])
        self.assertEqual(harness.return_value.run.call_count, 2)
        self.assertNotIn("PRIVATE_VALUE", output.getvalue())
        self.assertIsNone(error_reporting.TOOL_ERROR_HANDLER.get())

    def test_input_failure_is_sanitized_without_a_retry_loop(self):
        with patch.object(cli, "Harness"), patch("builtins.input", side_effect=OSError("PRIVATE_INPUT_VALUE")), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as caught:
                cli.main(["--verbose"])
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("Exception type: OSError", output.getvalue())
        self.assertNotIn("PRIVATE_INPUT_VALUE", output.getvalue())

    def test_diagnostic_hook_failure_does_not_change_tool_error_handling(self):
        token = error_reporting.TOOL_ERROR_HANDLER.set(lambda error: (_ for _ in ()).throw(OSError("sink failed")))
        try:
            error_reporting.report_tool_error(ValueError("private"))
        finally:
            error_reporting.TOOL_ERROR_HANDLER.reset(token)
