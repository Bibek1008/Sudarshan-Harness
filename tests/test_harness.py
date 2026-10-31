"""Day 4 tests: Harness persistence, crash repair, and isolated subagents."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sudarshan.loop as loop
from sudarshan.harness import Harness
from sudarshan.session import append, new_session


class HarnessTests(unittest.TestCase):
    """Exercise the composed Day 4 spine with deterministic provider replies."""

    def setUp(self) -> None:
        """Create a writable test project under the repository work area."""
        parent = Path(__file__).resolve().parent.parent / "work"
        parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        """Remove the temporary harness project after each test."""
        self.temporary.cleanup()

    def test_run_persists_and_resume_loads_messages(self) -> None:
        """Event-arrived assistant and tool messages are available to a new harness."""
        replies = iter([
            _call("write_file", {"path": "note.txt", "content": "saved"}),
            _final("created note"),
        ])
        harness = Harness(self.root, enable_subagents=False)
        with patch.object(loop.provider, "complete", side_effect=lambda *args: next(replies)):
            self.assertEqual(harness.run("create a note"), "created note")
        self.assertIsNotNone(harness.session_path)
        resumed = Harness(self.root, enable_subagents=False)
        self.assertTrue(resumed.resume())
        self.assertEqual([message["role"] for message in resumed.messages], ["user", "assistant", "tool", "assistant"])

    def test_interrupted_session_repairs_then_finishes_all_requested_files(self) -> None:
        """An abruptly incomplete five-file task resumes with paired interruption notices."""
        path = new_session(self.root, "parts")
        calls = [{"name": "write_file", "args": {"path": f"part{number}.txt", "content": f"part {number}"}}
                 for number in range(1, 6)]
        calls.append({"name": "write_file", "args": {"path": "SUMMARY.md", "content": "five parts"}})
        append(path, {"role": "user", "text": "Create part1.txt through part5.txt one at a time, then SUMMARY.md describing each"})
        append(path, {"role": "assistant", "text": "", "tool_calls": calls})
        (self.root / "part1.txt").write_text("part 1", encoding="utf-8")
        append(path, {"role": "tool", "name": "write_file", "text": "Wrote part1.txt"})
        harness = Harness(self.root, enable_subagents=False)
        self.assertTrue(harness.resume())
        self.assertIn("Interrupted before this ran", harness.messages[-1]["text"])
        replies = iter([
            _call("write_file", {"path": f"part{number}.txt", "content": f"part {number}"})
            for number in range(2, 6)
        ] + [
            _call("write_file", {"path": "SUMMARY.md", "content": "part1 through part5"}),
            _final("recovered and completed"),
        ])
        with patch.object(loop.provider, "complete", side_effect=lambda *args: next(replies)):
            self.assertEqual(harness.run("continue the task"), "recovered and completed")
        self.assertTrue(all((self.root / name).is_file()
                            for name in ["part1.txt", "part2.txt", "part3.txt", "part4.txt", "part5.txt", "SUMMARY.md"]))

    def test_two_subagents_are_ephemeral_and_parent_runs_tests(self) -> None:
        """Children return independent reports while only the parent writes one session."""
        if os.name == "nt":
            (self.root / "python3.bat").write_text("@echo off\npython %*\n", encoding="utf-8")
        utils = "def slugify(text):\n    return '-'.join(text.lower().split())\n"
        tests = """from utils import slugify
assert slugify('Hello World') == 'hello-world'
assert slugify('A B') == 'a-b'
assert slugify('one') == 'one'
assert slugify('  two  words ') == 'two-words'
assert slugify('UP DOWN') == 'up-down'
"""
        replies = iter([
            _call("spawn_agent", {"task": "Write utils.py with slugify(text)."}),
            _call("write_file", {"path": "utils.py", "content": utils}),
            _final("utils.py written"),
            _call("spawn_agent", {"task": "Write test_utils.py with five asserts."}),
            _call("write_file", {"path": "test_utils.py", "content": tests}),
            _final("test_utils.py written"),
            _call("bash", {"command": "python3 test_utils.py"}),
            _final("Both child reports succeeded and I ran the tests."),
        ])
        harness = Harness(self.root)
        with patch.object(loop.provider, "complete", side_effect=lambda *args: next(replies)):
            answer = harness.run("Use spawn_agent twice, then run python3 test_utils.py yourself and report.")
        self.assertIn("ran the tests", answer)
        self.assertTrue((self.root / "utils.py").is_file())
        self.assertTrue((self.root / "test_utils.py").is_file())
        sessions = list((self.root / ".sudarshan" / "sessions").glob("*.jsonl"))
        self.assertEqual(len(sessions), 1)


def _call(name: str, args: dict[str, str]) -> dict[str, object]:
    """Return one neutral scripted assistant tool-call response."""
    return {"text": "", "tool_calls": [{"name": name, "args": args, "signature": None}], "usage": {}}


def _final(text: str) -> dict[str, object]:
    """Return one neutral scripted final assistant response."""
    return {"text": text, "tool_calls": [], "usage": {}}


if __name__ == "__main__":
    unittest.main()
