"""Day 4: compose tools, policy, context, memory, sessions, and subagents.

Harness is the orchestration boundary for the first four days.  It preserves
the neutral loop protocol, records messages append-only, and gives children a
shared workspace but no resumable session state.
"""

import os
from pathlib import Path
from typing import Any, Callable, Iterable

from . import context, loop, memory, provider, session, skills
from .security import Policy
from .subagent import subagent_tool
from .tools import Tool, core_tools, tool


class Harness:
    """A durable coding-agent composition rooted at one real working directory."""

    def __init__(
        self,
        workdir: str | Path = ".",
        model: str | None = None,
        policy: Policy | None = None,
        extra_tools: Iterable[Tool] | dict[str, Tool] | None = None,
        system_extra: str = "",
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        budget_tokens: int = 600_000,
        max_turns: int = 120,
        session_path: str | Path | None = None,
        enable_subagents: bool = True,
        persist: bool = True,
        _depth: int = 0,
    ) -> None:
        """Compose a harness while leaving provider and loop protocols unchanged."""
        self.workdir = Path(workdir).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.model = model or os.environ.get("ODYSSEUS_MODEL") or provider.DEFAULT_MODEL
        self.policy = policy if policy is not None else Policy("safe")
        self.system_extra = system_extra
        self.on_event = on_event or (lambda kind, payload: None)
        self.budget_tokens = budget_tokens
        self.max_turns = max_turns
        self.persist = persist
        self._depth = _depth
        self.enable_subagents = enable_subagents
        self._extra_tools = list(extra_tools.values()) if isinstance(extra_tools, dict) else list(extra_tools or [])
        self.messages: list[dict[str, Any]] = []
        self.session_path = Path(session_path) if session_path else None
        self.tools = {item.name: item for item in core_tools(self.workdir)}
        remember_tool = self._remember_tool()
        self.tools[remember_tool.name] = remember_tool
        if skills.catalog(self.workdir):
            skill_tool = self._skill_tool()
            self.tools[skill_tool.name] = skill_tool
        if enable_subagents:
            agent_tool = subagent_tool(self._make_child, depth=_depth)
            self.tools[agent_tool.name] = agent_tool
        self.tools.update({item.name: item for item in self._extra_tools})
        extra = "\n\n".join(part for part in (skills.catalog_prompt(self.workdir), system_extra) if part)
        self.system = memory.build_system_prompt(self.workdir, extra)

    def resume(self, path: str | Path | None = None) -> bool:
        """Load a selected or newest session and repair interrupted tool-call pairs."""
        target = Path(path) if path is not None else session.latest(self.workdir)
        if target is None:
            return False
        self.messages = session.load(target)
        self.session_path = target
        return True

    def run(self, task: str) -> str:
        """Record one task, run the loop, and persist each event-produced message."""
        if self.persist and self.session_path is None:
            self.session_path = session.new_session(self.workdir, task[:32])
        self.messages.append({"role": "user", "text": task})
        recorded = self._record_from(0 if len(self.messages) == 1 else len(self.messages) - 1)

        def record_event(kind: str, payload: dict[str, Any]) -> None:
            """Persist new loop messages before forwarding the caller's event callback."""
            nonlocal recorded
            recorded = self._record_from(min(recorded, len(self.messages)))
            self.on_event(kind, payload)

        def before_turn(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Compact in place while keeping the persisted-message cursor valid."""
            nonlocal recorded
            compacted = context.compact(self.model, messages, self.budget_tokens)
            # A summary replaces prior records; never index past the compacted transcript.
            recorded = min(recorded, len(compacted))
            return compacted

        result = loop.run_loop(
            self.model, self.system, self.messages, self.tools, record_event,
            self._check_tool, max_turns=self.max_turns, before_turn=before_turn,
        )
        self._record_from(min(recorded, len(self.messages)))
        return result

    def _check_tool(self, call: dict[str, Any]) -> str | None:
        """Restrict custom overrides even when they reuse a trusted core name."""
        if any(item.name == call['name'] for item in self._extra_tools):
            call = dict(call, name='custom_' + call['name'])
        return self.policy.check(call)

    def _record_from(self, index: int) -> int:
        """Append all messages at and after ``index`` when this harness persists."""
        if self.persist and self.session_path is not None:
            for message in self.messages[index:]:
                session.append(self.session_path, message)
        return len(self.messages)

    def _remember_tool(self) -> Tool:
        """Build the workspace-bound durable-memory tool."""
        @tool("Remember a durable project fact.", note="Fact to append to project memory.")
        def remember(note: str) -> str:
            """Append one project fact to this harness workspace's memory file."""
            return memory.remember(self.workdir, note)

        return remember

    def _skill_tool(self) -> Tool:
        """Build the workspace-bound skill document loader."""
        @tool("Load a named workspace skill document.", name="Skill name to load.")
        def use_skill(name: str) -> str:
            """Return a full skill document or an error listing available names."""
            return skills.read_skill(self.workdir, name)

        return use_skill

    def _make_child(self, depth: int) -> "Harness":
        """Create an ephemeral child with shared workspace and policy but no session log."""
        return Harness(
            self.workdir, model=self.model, policy=self.policy, extra_tools=self._extra_tools,
            system_extra=self.system_extra, on_event=self.on_event,
            budget_tokens=self.budget_tokens, max_turns=self.max_turns,
            enable_subagents=self.enable_subagents, persist=False, _depth=depth,
        )
