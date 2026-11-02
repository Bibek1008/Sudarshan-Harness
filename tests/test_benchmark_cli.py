"""CLI must never initiate a paid model run implicitly."""
from contextlib import redirect_stdout,redirect_stderr
import io
import json
from unittest.mock import patch
from sudarshan.cli import main
from sudarshan.evaluation.reporting import ResultStore
from tests.benchmark_examples import example
from tests.test_harness_security import WorkspaceCase


class BenchmarkCLITests(WorkspaceCase):
    def test_list_show_and_selected_dry_run_no_requests(self):
        with patch("sudarshan.provider.complete",side_effect=AssertionError("no API")):
            for args in (["list"],["show","core"],["run","core","--dry-run","--task","slug"]):
                output=io.StringIO()
                with redirect_stdout(output): main(["benchmark",*args])
                self.assertTrue(output.getvalue())
                if "--dry-run" in args:
                    self.assertEqual(len(json.loads(output.getvalue())["tasks"]),1)
        self.assertFalse((self.root/".sudarshan").exists())

    def test_no_mode_and_no_explicit_live_model_are_errors(self):
        for args in (["run","core"],["run","core","--live"],["run","core","--live","--dry-run"]):
            with self.subTest(args=args),patch("sudarshan.evaluation.cli.run_suite") as run,redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:
                main(["benchmark",*args])
            self.assertEqual(caught.exception.code,2)
            run.assert_not_called()

    def test_live_warning_and_approval_policy_are_explicit(self):
        output=io.StringIO()
        with patch("sudarshan.evaluation.cli.run_suite",return_value=example()) as run,redirect_stdout(output):
            main(["benchmark","run","core","--live","--model","gemini-test","-d",str(self.root)])
        self.assertIn("paid or quota-consuming",output.getvalue())
        self.assertTrue(run.call_args.kwargs["live"])
        self.assertFalse(run.call_args.kwargs["approve_workspace_edits"])

    def test_report_export_and_compare_are_provider_free(self):
        first,second=example(),example("failed")
        store=ResultStore(self.root); store.save(first);store.save(second)
        with patch("sudarshan.provider.complete",side_effect=AssertionError("no API")):
            for args in (["report",first["run_id"]],["export",first["run_id"],"--json"],["compare",first["run_id"],second["run_id"]]):
                output=io.StringIO()
                with redirect_stdout(output): main(["benchmark",*args,"-d",str(self.root)])
                self.assertTrue(output.getvalue())
                if args[0] != "report": self.assertIsInstance(json.loads(output.getvalue()),dict)

    def test_bad_result_errors_do_not_echo_input_or_contents(self):
        output=io.StringIO()
        with redirect_stderr(output),self.assertRaises(SystemExit): main(["benchmark","report","../.env","-d",str(self.root)])
        self.assertNotIn("../.env",output.getvalue())
        self.assertNotIn("Traceback",output.getvalue())
