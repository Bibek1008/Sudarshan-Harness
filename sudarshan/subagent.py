"""Day 4: bounded delegation to isolated child harness conversations.

The parent supplies child construction, which keeps delegation independent of
provider details.  Depth is explicit and finite so a model cannot recursively
spend unbounded work on fresh contexts.
"""

from typing import Any, Callable

from .tools import Tool, tool


def subagent_tool(
    make_harness: Callable[[int], Any], depth: int = 0, max_depth: int = 2,
) -> Tool:
    """Build the bounded ``spawn_agent`` tool for a harness at ``depth``."""
    @tool(
        "Delegate a self-contained task to a fresh sub-agent with its own clean context. "
        "The child cannot see this conversation and returns its final report.",
        task="Self-contained task for the fresh sub-agent.",
    )
    def spawn_agent(task: str) -> str:
        """Run one isolated child task unless the configured depth limit is reached."""
        if depth >= max_depth:
            return "ERROR: sub-agent depth limit reached; do this task yourself"
        return make_harness(depth + 1).run(task)

    return spawn_agent
