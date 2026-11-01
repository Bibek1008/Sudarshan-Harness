import unittest
from unittest.mock import Mock, patch
from sudarshan import loop
from sudarshan.tools import Tool


def reply(text="", calls=None):
    return {"text": text, "tool_calls": calls or []}


class TestLoop(unittest.TestCase):
    def execute(self, responses, tools=None, guard=None, turns=3, before_turn=None):
        messages, events = [], []
        with patch.object(loop.provider, "complete", side_effect=responses) as complete:
            result = loop.run_loop("test", "system", messages, tools or {},
                                   lambda *event: events.append(event), guard or (lambda call: None),
                                   max_turns=turns, before_turn=before_turn)
        return result, messages, events, complete

    def test_final_response(self):
        result, messages, events, complete = self.execute([reply("done")])
        self.assertEqual(result, "done")
        self.assertEqual(messages[-1]["role"], "assistant")
        self.assertEqual([event[0] for event in events], ["assistant"])
        self.assertEqual(complete.call_count, 1)

    def test_multiple_calls_and_consecutive_turns(self):
        run = Mock(side_effect=["one", "two", "three"])
        tool = Tool("read_file", {"schema": {"name": "read_file"}}, run)
        call = {"name": "read_file", "args": {"path": "file"}}
        result, messages, events, _ = self.execute([
            reply(calls=[call, call]), reply(calls=[call]), reply("done")], {tool.name: tool})
        self.assertEqual(run.call_count, 3)
        self.assertEqual([m["text"] for m in messages if m["role"] == "tool"], ["one", "two", "three"])
        self.assertEqual(sum(event[0] == "tool_start" for event in events), 3)
        self.assertEqual(result, "done")

    def test_unknown_tool_and_denied_tool(self):
        call = {"name": "unknown", "args": {}}
        _, messages, _, _ = self.execute([reply(calls=[call]), reply("done")])
        self.assertIn("unknown tool", messages[1]["text"])
        tool = Tool("unknown", {}, Mock())
        _, messages, _, _ = self.execute([reply(calls=[call]), reply("done")], {"unknown": tool}, lambda call: "denied")
        tool.run.assert_not_called()
        self.assertEqual(messages[1]["text"], "BLOCKED: denied")

    def test_tool_exception_does_not_expose_secret(self):
        tool = Tool("test", {}, Mock(side_effect=ValueError("synthetic-secret")))
        _, messages, _, _ = self.execute([reply(calls=[{"name": "test", "args": {}}]), reply("done")], {"test": tool})
        self.assertIn("ValueError", messages[1]["text"])
        self.assertNotIn("synthetic-secret", str(messages))

    def test_maximum_turns_final_report_cannot_execute_tools(self):
        tool = Tool("test", {}, Mock(return_value="ok"))
        call = {"name": "test", "args": {}}
        result, messages, _, complete = self.execute([reply(calls=[call]), reply("wrap", [call])], {"test": tool}, turns=1)
        self.assertEqual(result, "wrap")
        self.assertEqual(tool.run.call_count, 1)
        self.assertEqual(complete.call_args.args[-1], [])
        self.assertEqual(messages[-1]["tool_calls"], [])
        self.assertIn("Turn limit", messages[-2]["text"])

    def test_zero_and_negative_budget(self):
        self.assertEqual(self.execute([reply("wrap")], turns=0)[0], "wrap")
        with self.assertRaises(ValueError):
            self.execute([], turns=-1)

    def test_malformed_and_empty_responses_fail_before_execution(self):
        tool = Tool("test", {}, Mock())
        for response in (None, {}, [], reply(""), {"text": 1, "tool_calls": []},
                         reply(calls=[None]), reply(calls=[{"name": "test", "args": []}])):
            with self.subTest(response=response), self.assertRaises(RuntimeError):
                self.execute([response], {"test": tool})
        tool.run.assert_not_called()

    def test_before_turn_keeps_list_identity(self):
        seen = []
        def compact(messages):
            seen.append(messages)
            return [{"role": "user", "text": "summary"}]
        _, messages, _, _ = self.execute([reply("done")], before_turn=compact)
        self.assertIs(messages, seen[0])
        self.assertEqual(messages[0]["text"], "summary")
