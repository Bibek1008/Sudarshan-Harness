"""Day 4 tests: isolated child construction and bounded recursive delegation."""

import unittest

from sudarshan.subagent import subagent_tool


class Child:
    """A tiny child harness substitute that records its self-contained task."""

    def __init__(self, depth: int) -> None:
        """Record the depth requested by the parent tool."""
        self.depth = depth

    def run(self, task: str) -> str:
        """Return a deterministic report without accessing parent context."""
        return f"child depth {self.depth}: {task}"


class SubagentTests(unittest.TestCase):
    """Verify delegation increments depth and stops at its hard limit."""

    def test_child_is_fresh_and_receives_task(self) -> None:
        """The factory receives depth plus one and the child report is returned."""
        requested: list[int] = []
        tool = subagent_tool(lambda depth: requested.append(depth) or Child(depth))
        self.assertEqual(tool.name, "spawn_agent")
        self.assertEqual(tool.run("write utils.py"), "child depth 1: write utils.py")
        self.assertEqual(requested, [1])

    def test_depth_limit_returns_model_readable_error(self) -> None:
        """At the limit no child harness is constructed."""
        tool = subagent_tool(lambda depth: Child(depth), depth=2, max_depth=2)
        self.assertEqual(tool.run("delegate"), "ERROR: sub-agent depth limit reached; do this task yourself")


if __name__ == "__main__":
    unittest.main()
