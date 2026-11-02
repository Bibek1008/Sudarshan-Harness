"""Day 1: the deterministic model-and-tool execution loop.

The loop owns conversation state and tool ordering, while the provider and tool
implementations remain replaceable boundaries.  Events make execution visible;
guard checks happen before any tool can cause an external effect.
"""

from typing import Any, Callable

import time
import uuid
from . import provider, telemetry, error_reporting


def run_loop(
    model: str,
    system: str | Callable[[], str],
    messages: list[dict[str, Any]],
    tools: dict[str, Any],
    on_event: Callable[[str, dict[str, Any]], None],
    before_tool: Callable[[dict[str, Any]], str | None],
    max_turns: int = 80,
    before_turn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> str:
    """Run model turns until a text-only reply, executing requested tools in order.

    ``messages`` is both the input transcript and the durable record of this
    execution.  The optional ``before_turn`` hook may compact that transcript
    without replacing its list identity.  Event callbacks observe an assistant
    reply and every requested tool, including calls denied by ``before_tool``.

    After the turn budget, request exactly one tool-free final report.
    """
    if max_turns < 0:
        raise ValueError("max_turns must not be negative")
    tool_specs = [tool.spec for tool in tools.values()]
    for turn in range(1, max_turns + 1):
        recorder = telemetry.ACTIVE.get()
        if recorder: recorder.turn = turn
        if before_turn is not None:
            # Compaction updates the caller's list instead of severing its reference.
            messages[:] = before_turn(messages)
        reply = telemetry.request(model, lambda: _validated_reply(provider.complete(model, system() if callable(system) else system, messages, tool_specs)))
        assistant = {
            "role": "assistant",
            "text": reply["text"],
            "tool_calls": reply["tool_calls"],
        }
        messages.append(assistant)
        on_event("assistant", assistant)
        if not reply["tool_calls"]:
            telemetry.emit("turn_completed")
            return reply["text"]

        for call in reply["tool_calls"]:
            # Sequential execution preserves both model order and transcript order.
            on_event("tool_start", call)
            name = call["name"]
            call_id = str(uuid.uuid4())
            if recorder: recorder.call_id = call_id
            started = time.perf_counter()
            backend = telemetry.label(getattr(tools.get(name), "execution_backend", None) or "in_process")
            trace = {"call_id": call_id, "tool": telemetry.label(name), "backend": backend}
            telemetry.emit("tool_call_started", status="started", **trace)
            reason = before_tool(call)
            failed, timed_out = False, False
            if reason is not None:
                # A refusal is returned to the model as ordinary tool output.
                result = f"BLOCKED: {reason}"
                telemetry.emit("tool_approval_denied", status="denied", approval="denied", error_category="denied", duration_ms=(time.perf_counter()-started)*1000, **trace)
            elif name not in tools:
                result = f"ERROR: unknown tool {name}"
                failed = True
            else:
                try:
                    result = str(tools[name].run(**call["args"]))
                except Exception as error:
                    error_reporting.report_tool_error(error)
                    result = f"ERROR: {type(error).__name__}: tool execution failed"
                    failed = True
                    from .execution.base import ExecutionTimeout
                    timed_out = isinstance(error, ExecutionTimeout)
                except BaseException:
                    telemetry.emit("tool_call_failed", status="interrupted", error_category="interrupted", duration_ms=(time.perf_counter()-started)*1000, **trace)
                    raise
            if reason is None:
                denied_result = result.startswith("BLOCKED:")
                failed = failed or result.startswith("ERROR:") or "\nERROR:" in result
                timed_out = timed_out or (failed and any(word in result.lower() for word in ("timed out", "timeout", "executiontimeout")))
                if denied_result:
                    telemetry.emit("tool_approval_denied", status="denied", approval="denied", error_category="denied", duration_ms=(time.perf_counter()-started)*1000, **trace)
                else:
                    telemetry.emit("tool_call_failed" if failed else "tool_call_completed", status="failed" if failed else "success", duration_ms=(time.perf_counter()-started)*1000, **({"error_category": "timeout" if timed_out else "tool_error"} if failed else {}), **trace)
                if timed_out: telemetry.emit("execution_timeout", status="failed", error_category="timeout", **trace)
            tool_message = {"role": "tool", "name": name, "text": result}
            messages.append(tool_message)
            on_event("tool_end", tool_message)
            if recorder: recorder.call_id = None
        telemetry.emit("turn_completed")
    recorder = telemetry.ACTIVE.get()
    if recorder: recorder.turn = max_turns + 1
    messages.append({"role": "user", "text": "Turn limit reached; wrap up now."})
    reply = telemetry.request(model, lambda: _validated_reply(provider.complete(model, system() if callable(system) else system, messages, [])))
    # Even a noncompliant provider cannot execute or leave unpaired final calls.
    assistant = {"role": "assistant", "text": reply["text"], "tool_calls": []}
    messages.append(assistant)
    on_event("assistant", assistant)
    telemetry.emit("turn_completed")
    return reply["text"]


def _validated_reply(reply: Any) -> dict[str, Any]:
    """Reject malformed model output before executing any requested effects."""
    if (not isinstance(reply, dict) or not isinstance(reply.get("text"), str)
            or not isinstance(reply.get("tool_calls"), list)):
        raise RuntimeError("Model returned a malformed response")
    for call in reply["tool_calls"]:
        if (not isinstance(call, dict) or not isinstance(call.get("name"), str)
                or not call["name"].strip() or not isinstance(call.get("args"), dict)):
            raise RuntimeError("Model returned a malformed tool call")
    if not reply["text"].strip() and not reply["tool_calls"]:
        raise RuntimeError("Model returned an empty response")
    return reply
