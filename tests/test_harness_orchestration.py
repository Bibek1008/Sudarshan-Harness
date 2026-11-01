from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
from pathlib import Path
import threading
from unittest.mock import Mock, patch

from sudarshan import context, session
from sudarshan.cli import _event, _approver, main
from sudarshan.fleet import run_fleet
from sudarshan.harness import Harness
from sudarshan.paths import workspace_path
from sudarshan.redaction import redact
from sudarshan.security import Policy
from sudarshan.subagent import subagent_tool
from tests.test_harness_security import WorkspaceCase
from demos import product_fleet, product_verify
from demos.product_approval import product_harness


class TestOrchestration(WorkspaceCase):
    def test_harness_persists_and_resumes(self):
        harness = Harness(self.root, enable_subagents=False)
        with patch("sudarshan.provider.complete", return_value={"text": "done", "tool_calls": []}):
            self.assertEqual(harness.run("task"), "done")
        restored = Harness(self.root)
        self.assertTrue(restored.resume())
        self.assertEqual(restored.messages, harness.messages)

    def test_harness_policy_blocks_unauthorized_modification(self):
        responses = [{"text": "", "tool_calls": [{"name": "write_file", "args": {"path": "blocked.txt", "content": "x"}}]},
                     {"text": "done", "tool_calls": []}]
        harness = Harness(self.root, policy=Policy("read-only"), persist=False)
        with patch("sudarshan.provider.complete", side_effect=responses):
            harness.run("task")
        self.assertFalse((self.root / "blocked.txt").exists())
        self.assertIn("BLOCKED", harness.messages[2]["text"])

    def test_subagent_depth_and_failure(self):
        factory = Mock()
        tool = subagent_tool(factory, depth=2)
        self.assertIn("depth limit", tool.run("task"))
        factory.assert_not_called()
        factory.return_value.run.return_value = "child report"
        self.assertEqual(subagent_tool(factory).run("task"), "child report")
        factory.assert_called_once_with(1)
        factory.return_value.run.side_effect = RuntimeError("child failure")
        with self.assertRaises(RuntimeError):
            subagent_tool(factory).run("task")

    def test_children_share_policy_but_not_transcript_or_persistence(self):
        parent = Harness(self.root)
        parent.messages.append({"role": "user", "text": "private parent conversation"})
        child = parent._make_child(1)
        self.assertIs(child.policy, parent.policy)
        self.assertEqual(child.messages, [])
        self.assertFalse(child.persist)
        self.assertEqual(child._depth, 1)

    def test_fleet_concurrency_order_and_failed_job(self):
        barrier = threading.Barrier(3)
        def factory(directory):
            child = Mock()
            def run(task):
                barrier.wait(timeout=5)
                if task == "fail":
                    raise RuntimeError("synthetic-secret")
                return task
            child.run.side_effect = run
            return child
        jobs = [{"name": str(index), "workdir": str(self.root), "task": task}
                for index, task in enumerate(("first", "fail", "last"))]
        results = run_fleet(jobs, factory, max_workers=3)
        self.assertEqual([result["name"] for result in results], ["0", "1", "2"])
        self.assertEqual([result["ok"] for result in results], [True, False, True])
        self.assertEqual(results[2]["report"], "last")
        self.assertNotIn("synthetic-secret", str(results))

    def test_malformed_fleet_job_returns_failure(self):
        results = run_fleet([{}], Mock())
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["name"], "<unnamed>")

    def test_context_compaction_preserves_tool_pairing(self):
        messages = [{"role": "user", "text": "old" * 100} for _ in range(4)]
        messages += [{"role": "assistant", "text": "", "tool_calls": [{"name": "x", "args": {}}]},
                     {"role": "tool", "name": "x", "text": "result"}]
        messages += [{"role": "user", "text": "recent"} for _ in range(5)]
        with patch("sudarshan.provider.complete", return_value={"text": "summary", "tool_calls": []}) as complete:
            compacted = context.compact("test", messages, 1)
        self.assertIn("summary", compacted[0]["text"])
        self.assertNotEqual(compacted[1]["role"], "tool")
        self.assertIn("result", complete.call_args.args[2][0]["text"])
        self.assertIs(context.compact("test", messages, 100000), messages)

    def test_console_redaction_and_approval(self):
        payload = {"name": "bash", "args": {"api_key": "synthetic-a", "command": "API_KEY=synthetic-b echo ok"}}
        output = io.StringIO()
        with redirect_stdout(output), patch("builtins.input", return_value="no"):
            _event("tool_start", payload)
            _event("assistant", {"text": "Authorization: Bearer synthetic-c"})
            self.assertFalse(_approver(payload, "approval"))
        for secret in ("synthetic-a", "synthetic-b", "synthetic-c"):
            self.assertNotIn(secret, output.getvalue())
        self.assertEqual(payload["args"]["api_key"], "synthetic-a")
        self.assertNotIn("synthetic-d", redact("https://invalid/?key=synthetic-d&x=1"))

    def test_cli_help_does_not_construct_harness(self):
        with patch("sudarshan.cli.Harness") as harness, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as exit:
                main(["--help"])
        self.assertEqual(exit.exception.code, 0)
        harness.assert_not_called()

    def test_metadata_boundary_with_mocked_symlink_resolution(self):
        root = self.root.resolve()
        outside = self.base / "outside"
        with patch.object(Path, "resolve", side_effect=[root, outside]):
            with self.assertRaises(PermissionError):
                workspace_path(root, "metadata")

    def test_latest_rejects_mocked_session_symlink(self):
        path = session.new_session(self.root)
        from sudarshan import paths
        original = paths._resolved
        def resolve(candidate):
            return self.base / "outside.jsonl" if candidate == path else original(candidate)
        with patch.object(paths, "_resolved", side_effect=resolve):
            with self.assertRaises(PermissionError):
                session.latest(self.root)

    def test_product_approvals_reject_command_injection(self):
        harness = product_harness(self.root, persist=False)
        self.assertIn("BLOCKED", harness.tools["bash"].run("python -m unittest discover -v; echo injected"))
        self.assertIsNotNone(harness.policy.check({"name": "write_file", "args": {"path": "../outside"}}))
        self.assertIsNotNone(harness.policy.check({"name": "write_file", "args": {"path": ".sudarshan/state"}}))
        self.assertIsNone(harness.policy.check({"name": "write_file", "args": {"path": "project.txt"}}))
        for timeout in ("nan", "inf", "0", "121"):
            with self.assertRaises(ValueError):
                harness.tools["bash"].run("python -m unittest discover -v", timeout)

    def test_artifact_verifier_rejects_missing_and_placeholder(self):
        result = product_verify.verify_product("viper", self.root)
        self.assertFalse(result["automated_ok"])
        self.assertFalse(result["accepted"])
        (self.root / "index.html").write_text("<html>TODO</html>", encoding="utf-8")
        result = product_verify.verify_product("viper", self.root)
        self.assertFalse(result["automated_ok"])
        self.assertTrue(any("Placeholder" in error for error in result["errors"]))

    def test_artifact_digest_changes_with_content(self):
        artifact = self.root / "artifact.txt"
        artifact.write_text("first", encoding="utf-8")
        before = product_verify.artifact_digest(self.root)
        artifact.write_text("second", encoding="utf-8")
        self.assertNotEqual(product_verify.artifact_digest(self.root), before)
        hidden = self.root / ".sudarshan"
        hidden.mkdir()
        before = product_verify.artifact_digest(self.root)
        (hidden / "transient.json").write_text("{}", encoding="utf-8")
        self.assertEqual(product_verify.artifact_digest(self.root), before)

    def test_hidden_content_is_not_counted(self):
        page = product_verify.PageFacts()
        page.feed('<style>.hidden{display:none}</style><main>Visible<button>Go</button><div class="hidden">Secret filler</div></main>')
        self.assertIn("Visible", " ".join(page.visible))
        self.assertNotIn("Secret filler", " ".join(page.visible))

    def test_fleet_repair_limits_when_all_artifacts_fail(self):
        def fake_fleet(jobs, factory, max_workers):
            return [{"name": job["name"], "ok": False, "report": "failed"} for job in jobs]
        failed = {"automated_ok": False, "accepted": False, "errors": ["bad artifact"]}
        with patch.object(product_fleet, "run_fleet", side_effect=fake_fleet) as fleet, patch.object(
                product_fleet, "verify_product", return_value=failed):
            report = product_fleet.run_products(self.root / "products")
        self.assertEqual(set(report["phases"]), {"build", "build_repair", "review", "review_repair", "final_review"})
        self.assertEqual(fleet.call_count, 5)
        self.assertEqual(len(fleet.call_args_list[4].args[0]), 0)
        self.assertEqual(len(fleet.call_args_list[2].args[0]), 0)
        self.assertTrue(all(not result["ok"] for result in report["final"]))
        self.assertIn("Incomplete", report["acceptance"])

    def test_fleet_success_requires_skill_and_manual_acceptance(self):
        def fake_harness(workdir, **options):
            child = Mock()
            options["on_event"]("tool_end", {"name": "use_skill", "text": product_fleet.QUALITY})
            child.resume.return_value = True
            child.run.return_value = "done"
            return child
        def fake_fleet(jobs, factory, max_workers):
            return [{"name": job["name"], "ok": True, "report": factory(job["workdir"]).run(job["task"])} for job in jobs]
        verified = {"automated_ok": True, "accepted": False, "manual_pending": True}
        with patch.object(product_fleet, "run_fleet", side_effect=fake_fleet), patch.object(
                product_fleet, "product_harness", side_effect=fake_harness), patch.object(
                product_fleet, "verify_product", return_value=verified):
            report = product_fleet.run_products(self.root / "products")
        self.assertEqual(set(report["phases"]), {"build", "review"})
        self.assertTrue(all(result["review_ok"] for result in report["final"]))
        self.assertTrue(all(not result["final_accepted"] for result in report["final"]))
