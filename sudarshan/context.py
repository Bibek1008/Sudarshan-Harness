"""Day 3: bounded transcript context through factual, coherent compaction.

This module keeps the loop provider-neutral: it estimates cheaply, summarizes
only overflow, and retains recent messages without starting on a tool result.
The summary call preserves decisions and unfinished work rather than prose.
"""

from typing import Any

from . import provider


CHARS_PER_TOKEN = 4
KEEP_RECENT = 6
COMPACTION_SYSTEM = (
    "You compress agent transcripts. Preserve: the original task, every file "
    "created or edited and its purpose, key decisions, unresolved errors, and "
    "what remains to be done. Be dense and factual."
)


def estimate_tokens(messages: list[dict[str, Any]]) -> float:
    """Estimate transcript tokens from message string lengths without an API call."""
    return sum(len(str(message)) for message in messages) / CHARS_PER_TOKEN


def compact(model: str, messages: list[dict[str, Any]], budget_tokens: int) -> list[dict[str, Any]]:
    """Summarize old transcript state when it exceeds the supplied token budget."""
    if estimate_tokens(messages) <= budget_tokens or len(messages) <= KEEP_RECENT + 1:
        return messages
    old, recent = messages[:-KEEP_RECENT], messages[-KEEP_RECENT:]
    # Preserve dropped results in the summary rather than leaving a tool result orphaned.
    while recent and recent[0]["role"] == "tool":
        old.append(recent.pop(0))
    transcript = "\n".join(_render(message) for message in old)
    response = provider.complete(
        model,
        COMPACTION_SYSTEM,
        [{"role": "user", "text": transcript}],
        [],
    )
    summary = {"role": "user", "text": f"[Conversation so far, compacted]\n{response['text']}"}
    return [summary] + recent


def _render(message: dict[str, Any]) -> str:
    """Render one neutral message as compact plain transcript text."""
    parts = [f"role={message['role']}"]
    if message.get("name"):
        parts.append(f"name={message['name']}")
    if message.get("text"):
        parts.append(f"text={message['text'][:1000]}")
    calls = message.get("tool_calls", [])
    if calls:
        parts.append("tool_calls=" + ", ".join(call["name"] for call in calls))
    return " | ".join(parts)
