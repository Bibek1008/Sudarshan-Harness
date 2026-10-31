"""Day 3 verification: a compacted multi-tool build with observable evidence."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sudarshan.loop as loop
from sudarshan.context import COMPACTION_SYSTEM, compact
from sudarshan.security import Policy
from sudarshan.tools import core_tools


class DayThreeContextVerification(unittest.TestCase):
    """Execute the specified five-file task through the real loop and core tools."""

    def test_five_files_are_read_back_manifested_and_compacted(self) -> None:
        """Prove context compaction fires during a verified, ordered tool task."""
        parent = Path(__file__).resolve().parent.parent / "work"
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as scratch:
            root = Path(scratch)
            if os.name == "nt":
                # Windows has no wc by default; this workspace-local command preserves the task contract.
                (root / "wc.bat").write_text(
                    "@echo off\nshift\nfor %%F in (%*) do for /f %%A in ('find /v /c \"\" ^< \"%%F\"') do echo %%A %%F\n",
                    encoding="utf-8",
                )
            tools = {tool.name: tool for tool in core_tools(root)}
            content = "ping\n" * 20
            manifest = "".join(f"{name}.txt: 20\n" for name in ("one", "two", "three", "four", "five"))
            replies = []
            for name in ("one", "two", "three", "four", "five"):
                replies.extend([
                    _tool_reply("write_file", {"path": f"{name}.txt", "content": content}),
                    _tool_reply("read_file", {"path": f"{name}.txt"}),
                ])
            replies.extend([
                _tool_reply("bash", {"command": "wc -l one.txt two.txt three.txt four.txt five.txt"}),
                _tool_reply("write_file", {"path": "MANIFEST.md", "content": manifest}),
                _tool_reply("read_file", {"path": "MANIFEST.md"}),
                {"text": "Verified: each file has 20 lines and MANIFEST.md records them.", "tool_calls": [], "usage": {}},
            ])
            regular = iter(replies)
            compactions: list[str] = []

            def complete(model, system, messages, schemas):
                """Supply scripted task turns while recording genuine compact() summary calls."""
                if system == COMPACTION_SYSTEM:
                    compactions.append(messages[0]["text"])
                    return {"text": "Created one.txt through five.txt; continue verification.", "tool_calls": [], "usage": {}}
                return next(regular)

            messages = [{"role": "user", "text": "Create five files and a verified manifest."}]
            events: list[tuple[str, dict]] = []
            with patch.object(loop.provider, "complete", side_effect=complete):
                answer = loop.run_loop(
                    "test", "test", messages, tools,
                    lambda kind, payload: events.append((kind, payload)),
                    Policy("yolo").check,
                    before_turn=lambda transcript: compact("test", transcript, 1500),
                )
            self.assertEqual(answer, "Verified: each file has 20 lines and MANIFEST.md records them.")
            self.assertGreaterEqual(len(compactions), 1, "compaction did not fire")
            self.assertTrue(all((root / f"{name}.txt").read_text(encoding="utf-8") == content
                                for name in ("one", "two", "three", "four", "five")))
            self.assertEqual((root / "MANIFEST.md").read_text(encoding="utf-8"), manifest)
            started = [payload["name"] for kind, payload in events if kind == "tool_start"]
            self.assertEqual(started[:10], [item for name in ("one", "two", "three", "four", "five")
                                            for item in ("write_file", "read_file")])
            self.assertIn("bash", started)
            bash_result = next(payload["text"] for kind, payload in events
                               if kind == "tool_end" and payload["name"] == "bash")
            self.assertGreaterEqual(bash_result.count("20"), 5)


def _tool_reply(name: str, args: dict[str, str]) -> dict[str, object]:
    """Build one verbose scripted tool request so the 1500-token budget overflows."""
    return {"text": "Continuing the verified build. " * 120,
            "tool_calls": [{"name": name, "args": args, "signature": None}], "usage": {}}


if __name__ == "__main__":
    unittest.main()
