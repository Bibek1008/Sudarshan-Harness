"""Day 4 tests: JSONL session creation, torn tails, and interruption repair."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from sudarshan.session import append, latest, load, new_session


class SessionTests(unittest.TestCase):
    """Verify append-only records recover into call-paired conversations."""

    def setUp(self) -> None:
        """Create a temporary work directory in the repository writable area."""
        parent = Path(__file__).resolve().parent.parent / "work"
        parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        """Remove each temporary session workspace."""
        self.temporary.cleanup()

    def test_slugged_session_and_latest_selection(self) -> None:
        """Session names are bounded slugs and latest chooses a recent JSONL file."""
        first = new_session(self.root, "My Session! With Spaces")
        append(first, {"role": "user", "text": "first"})
        second = first.with_name("9999999999-newest.jsonl")
        append(second, {"role": "user", "text": "second"})
        os.utime(first, (1, 1))
        os.utime(second, (2, 2))
        self.assertRegex(first.name, r"^\d+-my-session-with-spaces\.jsonl$")
        self.assertEqual(latest(self.root), second)

    def test_torn_tail_stops_loading_and_unfinished_calls_are_repaired(self) -> None:
        """A hard-stop write preserves earlier records and fills only missing results."""
        path = new_session(self.root)
        append(path, {"role": "user", "text": "make files"})
        append(path, {
            "role": "assistant", "text": "", "tool_calls": [
                {"name": "write_file", "args": {"path": "one.txt"}},
                {"name": "write_file", "args": {"path": "two.txt"}},
            ],
        })
        append(path, {"role": "tool", "name": "write_file", "text": "Wrote one"})
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"role": "assistant"')
        messages = load(path)
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[-1], {
            "role": "tool", "name": "write_file",
            "text": "Interrupted before this ran (process restarted).",
        })

    def test_hard_terminated_worker_leaves_recoverable_call(self) -> None:
        """A killed worker leaves a durable partial call that recovery can pair."""
        path = new_session(self.root, "hard-stop")
        append(path, {"role": "user", "text": "create parts"})
        message = {"role": "assistant", "text": "", "tool_calls": [
            {"name": "write_file", "args": {"path": "part1.txt"}},
        ]}
        code = f"from sudarshan.session import append; append({str(path)!r}, {message!r}); import time; time.sleep(60)"
        worker = subprocess.Popen([sys.executable, "-c", code], cwd=Path(__file__).resolve().parent.parent)
        try:
            deadline = time.monotonic() + 3
            while '"assistant"' not in path.read_text(encoding="utf-8") and time.monotonic() < deadline:
                time.sleep(0.02)
            worker.kill()
            worker.wait(timeout=3)
        finally:
            if worker.poll() is None:
                worker.kill()
        messages = load(path)
        self.assertEqual(messages[-1]["text"], "Interrupted before this ran (process restarted).")


if __name__ == "__main__":
    unittest.main()
