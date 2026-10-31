"""Day 3 tests: token estimates, summary calls, and coherent kept turns."""

import unittest
from unittest.mock import patch

from sudarshan.context import COMPACTION_SYSTEM, compact, estimate_tokens


class ContextTests(unittest.TestCase):
    """Verify compaction only changes overflowing conversations coherently."""

    def test_estimate_uses_message_string_lengths(self) -> None:
        """The inexpensive estimate is exactly the documented character ratio."""
        messages = [{"role": "user", "text": "hello"}]
        self.assertEqual(estimate_tokens(messages), len(str(messages[0])) / 4)

    def test_short_or_in_budget_transcript_is_unchanged(self) -> None:
        """Normal turns avoid an unnecessary provider summary call."""
        messages = [{"role": "user", "text": "small"}]
        with patch("sudarshan.context.provider.complete") as complete:
            self.assertIs(compact("model", messages, 1000), messages)
        complete.assert_not_called()

    def test_compaction_summarizes_once_and_never_keeps_orphan_tool_result(self) -> None:
        """Overflow uses one dense summary while moving leading tool output into it."""
        messages = [
            {"role": "user", "text": "task " * 400},
            {"role": "assistant", "text": "editing", "tool_calls": [{"name": "write_file", "args": {}}]},
            {"role": "tool", "name": "write_file", "text": "written"},
            {"role": "user", "text": "recent 1"},
            {"role": "assistant", "text": "recent 2", "tool_calls": []},
            {"role": "tool", "name": "read_file", "text": "recent 3"},
            {"role": "user", "text": "recent 4"},
            {"role": "assistant", "text": "recent 5", "tool_calls": []},
        ]
        response = {"text": "files: one.txt; remaining: verify", "tool_calls": [], "usage": {}}
        with patch("sudarshan.context.provider.complete", return_value=response) as complete:
            compacted = compact("model", messages, 100)
        self.assertEqual(compacted[0]["text"], "[Conversation so far, compacted]\nfiles: one.txt; remaining: verify")
        self.assertNotEqual(compacted[1]["role"], "tool")
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(complete.call_args.args[1], COMPACTION_SYSTEM)
        rendered = complete.call_args.args[2][0]["text"]
        self.assertIn("name=write_file", rendered)
        self.assertIn("tool_calls=write_file", rendered)


if __name__ == "__main__":
    unittest.main()
