"""Execution tests: registry, policy normalization, adapter, and loop behavior."""

import unittest
from unittest.mock import patch

import sudarshan.loop as loop
from sudarshan.execution.base import (
    BackendUnavailable,
    ExecutionBackend,
    ExecutionRegistry,
    ExecutionResult,
    backend_tools,
)
from sudarshan.security import Policy


class RecordingBackend(ExecutionBackend):
    """A deterministic backend used to verify adapter and loop boundaries."""

    name = "recording"

    def __init__(self, fail: bool = False) -> None:
        """Create a backend that optionally reports a runtime availability error."""
        self.fail = fail
        self.calls: list[tuple[str, object]] = []

    def execute(self, command: str, timeout: float = 120) -> ExecutionResult:
        """Record a command or raise the configured availability error."""
        if self.fail:
            raise BackendUnavailable("recording backend is unavailable")
        self.calls.append((command, timeout))
        return ExecutionResult("ran\n", "", 0, self.name, 0.01)

    def read_file(self, path: str) -> ExecutionResult:
        """Return a deterministic read result for adapter coverage."""
        self.calls.append(("read", path))
        return ExecutionResult("content", "", 0, self.name, 0.01)

    def write_file(self, path: str, content: str) -> ExecutionResult:
        """Return a deterministic write result for adapter coverage."""
        self.calls.append(("write", path))
        return ExecutionResult("written", "", 0, self.name, 0.01)

    def list_files(self, pattern: str = "**/*") -> ExecutionResult:
        """Return a deterministic list result for adapter coverage."""
        self.calls.append(("list", pattern))
        return ExecutionResult("file.txt", "", 0, self.name, 0.01)


class ExecutionIntegrationTests(unittest.TestCase):
    """Verify execution selection and policy remain independent from the provider."""

    def test_registry_selects_explicit_and_default_backends(self) -> None:
        """Registry selection is explicit and has no dependency on model modules."""
        first = RecordingBackend()
        second = RecordingBackend()
        registry = ExecutionRegistry()
        registry.register("first", first)
        registry.register("second", second, default=True)
        self.assertIs(registry.get(), second)
        self.assertIs(registry.get("first"), first)
        with self.assertRaises(ValueError):
            registry.register("first", RecordingBackend())

    def test_prefixed_backend_tools_preserve_hard_denials(self) -> None:
        """A yolo policy cannot use a prefixed backend name to bypass bash denial."""
        backend = RecordingBackend()
        policy = Policy("yolo")
        tools = {tool.name: tool for tool in backend_tools(backend, "sandbox", policy)}
        output = tools["sandbox_bash"].run("rm -rf ~")
        self.assertTrue(output.startswith("BLOCKED: dangerous bash command"))
        self.assertEqual(backend.calls, [])

    def test_read_only_and_safe_policy_apply_to_prefixed_tools(self) -> None:
        """Backend selection cannot weaken read-only or approval requirements."""
        backend = RecordingBackend()
        read_only = {tool.name: tool for tool in backend_tools(backend, "local", Policy("read-only"))}
        self.assertTrue(read_only["local_write_file"].run("x", "y").startswith("BLOCKED:"))
        safe = {tool.name: tool for tool in backend_tools(backend, "remote", Policy("safe"))}
        self.assertTrue(safe["remote_bash"].run("echo ok").startswith("BLOCKED:"))

    def test_loop_blocks_prefixed_hard_deny_before_backend_execution(self) -> None:
        """The existing before-tool socket recognizes execution adapter names."""
        backend = RecordingBackend()
        tools = {tool.name: tool for tool in backend_tools(backend, "local")}
        replies = iter([
            {"text": "", "tool_calls": [{"name": "local_bash", "args": {"command": "rm -rf ~"}, "signature": None}]},
            {"text": "refused", "tool_calls": []},
        ])
        messages: list[dict[str, object]] = []
        with patch.object(loop.provider, "complete", side_effect=lambda *args: next(replies)):
            answer = loop.run_loop("test", "test", messages, tools, lambda *args: None, Policy("yolo").check)
        self.assertEqual(answer, "refused")
        self.assertTrue(str(messages[-2]["text"]).startswith("BLOCKED:"))
        self.assertEqual(backend.calls, [])

    def test_backend_error_is_returned_as_tool_text(self) -> None:
        """Adapter errors survive a loop turn instead of terminating the transcript."""
        backend = RecordingBackend(fail=True)
        tools = {tool.name: tool for tool in backend_tools(backend, "sandbox")}
        replies = iter([
            {"text": "", "tool_calls": [{"name": "sandbox_bash", "args": {"command": "echo ok"}, "signature": None}]},
            {"text": "unavailable", "tool_calls": []},
        ])
        messages: list[dict[str, object]] = []
        with patch.object(loop.provider, "complete", side_effect=lambda *args: next(replies)):
            loop.run_loop("test", "test", messages, tools, lambda *args: None, Policy("yolo").check)
        self.assertIn("ERROR: BackendUnavailable", str(messages[-2]["text"]))


if __name__ == "__main__":
    unittest.main()
