"""Day 1: the deterministic model-and-tool execution loop.

The loop owns conversation state and tool ordering, while the provider and tool
implementations remain replaceable boundaries.  Events make execution visible;
guard checks happen before any tool can cause an external effect.
"""

from typing import Any, Callable

from . import provider


def run_loop(
    model: str,
    system: str,
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

    Raises:
        RuntimeError: If the model keeps asking for tools beyond ``max_turns``.
    """
    tool_specs = [tool.spec for tool in tools.values()]
    for _ in range(max_turns):
        if before_turn is not None:
            # Compaction updates the caller's list instead of severing its reference.
            messages[:] = before_turn(messages)
        reply = provider.complete(model, system, messages, tool_specs)
        assistant = {
            "role": "assistant",
            "text": reply["text"],
            "tool_calls": reply["tool_calls"],
        }
        messages.append(assistant)
        on_event("assistant", assistant)
        if not reply["tool_calls"]:
            return reply["text"]

        for call in reply["tool_calls"]:
            # Sequential execution preserves both model order and transcript order.
            on_event("tool_start", call)
            name = call["name"]
            reason = before_tool(call)
            if reason is not None:
                # A refusal is returned to the model as ordinary tool output.
                result = f"BLOCKED: {reason}"
            elif name not in tools:
                result = f"ERROR: unknown tool {name}"
            else:
                try:
                    result = str(tools[name].run(**call["args"]))
                except Exception as error:
                    result = f"ERROR: {type(error).__name__}: {error}"
            tool_message = {"role": "tool", "name": name, "text": result}
            messages.append(tool_message)
            on_event("tool_end", tool_message)
    raise RuntimeError(f"Loop exceeded maximum of {max_turns} turns")
