"""Day 4: compose tools, policy, context, memory, sessions, and subagents.

Harness is the orchestration boundary for the first four days.  It preserves
the neutral loop protocol, records messages append-only, and gives children a
shared workspace but no resumable session state.
"""

import os
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from . import context, loop, memory, provider, session, skills, telemetry as diagnostics
from .security import Policy
from .paths import workspace_path
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
        telemetry: bool | None = None,
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
        self.telemetry = persist if telemetry is None else telemetry
        self.last_telemetry_session = None
        self.telemetry_storage_failed = False
        self._depth = _depth
        self.enable_subagents = enable_subagents
        self._extra_tools = list(extra_tools.values()) if isinstance(extra_tools, dict) else list(extra_tools or [])
        self.messages: list[dict[str, Any]] = []
        self._original_task = ""
        self.session_path = workspace_path(self.workdir, session_path) if session_path else None
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
        self._prompt_extra = "\n\n".join(part for part in (skills.catalog_prompt(self.workdir), system_extra) if part)
        self.system = self._system_prompt("")

    def _system_prompt(self, task: str) -> str:
        """Refresh bounded project facts; unreadable memory never stops a session."""
        allowance = min(memory.MEMORY_TOKENS, max(0, self.budget_tokens // 8))
        workspace_path(self.workdir, memory.MEMORY_FILE)
        try:
            return memory.build_system_prompt(self.workdir, self._prompt_extra,
                                              task=task, memory_tokens=allowance)
        except (OSError, ValueError):
            return memory.build_system_prompt(self.workdir, self._prompt_extra,
                                              memory_tokens=0) + "\n\nProject memory unavailable; inspect or repair SUDARSHAN.md. Original file preserved."

    def resume(self, path: str | Path | None = None) -> bool:
        """Load a selected or newest session and repair interrupted tool-call pairs."""
        target = workspace_path(self.workdir, path) if path is not None else session.latest(self.workdir)
        if target is None:
            return False
        self.messages = session.load(target)
        self._original_task = next((message["text"] for message in self.messages
                                    if message["role"] == "user"), "")
        self.session_path = target
        return True

    def run(self, task: str) -> str:
        """Execute with project-local credential lookup and metadata-only telemetry."""
        env_file_token = provider.PROJECT_ENV_FILE.set(self.workdir / ".env")
        try:
            recorder = None
            if self.telemetry:
                try:
                    store = diagnostics.Store(self.workdir)
                    if store.enabled(): recorder = diagnostics.Recorder(store, self.model)
                except (OSError, ValueError):
                    self.telemetry_storage_failed = True
            token = diagnostics.ACTIVE.set(recorder)
            if recorder:
                self.last_telemetry_session = recorder.session_id
                recorder.emit("session_started", status="started")
            try:
                answer = self._run(task)
                if recorder: recorder.emit("session_completed", duration_ms=(time.perf_counter()-recorder.started)*1000)
                return answer
            except BaseException as error:
                if recorder:
                    interrupted = isinstance(error, (KeyboardInterrupt, SystemExit))
                    recorder.emit("session_interrupted" if interrupted else "session_completed", status="interrupted" if interrupted else "failed", error_category="interrupted" if interrupted else "session_error", duration_ms=(time.perf_counter()-recorder.started)*1000)
                raise
            finally:
                if recorder:
                    recorder.finish()
                    self.telemetry_storage_failed = recorder.storage_failed
                diagnostics.ACTIVE.reset(token)
        finally:
            provider.PROJECT_ENV_FILE.reset(env_file_token)

    def _run(self, task: str) -> str:
        """Record one task, run the loop, and persist each event-produced message."""
        self.system = self._system_prompt(task)
        if not self._original_task:
            self._original_task = task
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
            self.system = self._system_prompt(task)
            # Estimates guide compaction; only telemetry reports measured usage.
            transcript_budget = max(1, self.budget_tokens - context.estimate_text_tokens(self.system))
            compacted = context.compact(self.model, messages, transcript_budget,
                                        original_task=self._original_task)
            # A summary replaces prior records; never index past the compacted transcript.
            recorded = min(recorded, len(compacted))
            return compacted

        def current_system() -> str:
            """Also refresh for the tool-free wrap-up after the turn limit."""
            self.system = self._system_prompt(task)
            return self.system

        result = loop.run_loop(
            self.model, current_system, self.messages, self.tools, record_event,
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
        @tool("Save or explicitly update a durable project fact. Never save secrets or personal data.",
              note="Single-line fact; empty only to delete the exact replaces fact.",
              section="Optional section: " + ", ".join(memory.SECTIONS),
              replaces="Exact existing bullet text to replace or remove; never inferred.",
              verified="Optional YYYY-MM-DD date supported by evidence; otherwise leave empty.")
        def remember(note: str, section: str = "", replaces: str = "", verified: str = "") -> str:
            """Use the normal tool policy approval boundary for every memory mutation."""
            return memory.remember(self.workdir, note, section, replaces, verified)

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
            enable_subagents=self.enable_subagents, persist=False, _depth=depth, telemetry=self.telemetry,
        )
