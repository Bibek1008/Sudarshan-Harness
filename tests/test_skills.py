"""Day 3 tests: Markdown skill discovery, loading, and behavior injection."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sudarshan.loop as loop
from sudarshan.skills import catalog, catalog_prompt, read_skill


SKILL_TEXT = """---
description: Write in a vivid, friendly pirate voice.
---

# Pirate brand voice

Always use unmistakable pirate-style speech, matey.
"""


class SkillsTests(unittest.TestCase):
    """Verify skills are plain documents that can alter a fresh agent response."""

    def setUp(self) -> None:
        """Create one brand-voice skill in a temporary project workspace."""
        parent = Path(__file__).resolve().parent.parent / "work"
        parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name)
        skill = self.root / "skills" / "brand-voice"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")

    def tearDown(self) -> None:
        """Remove the temporary skill project after each test."""
        self.temporary.cleanup()

    def test_catalog_prompt_and_read_skill(self) -> None:
        """Discovery extracts front matter and loading preserves the full document."""
        available = catalog(self.root)
        self.assertEqual(available["brand-voice"]["description"], "Write in a vivid, friendly pirate voice.")
        self.assertTrue(available["brand-voice"]["path"].replace("\\", "/").endswith("skills/brand-voice/SKILL.md"))
        self.assertEqual(
            catalog_prompt(self.root),
            "Skills available (load one with the use_skill tool when relevant):\n"
            "- brand-voice: Write in a vivid, friendly pirate voice.",
        )
        self.assertEqual(read_skill(self.root, "brand-voice"), SKILL_TEXT)
        self.assertEqual(read_skill(self.root, "missing"), "ERROR: no skill named missing. Available: brand-voice")

    def test_loaded_skill_changes_writing_without_code_changes(self) -> None:
        """A fresh loop receives Markdown skill text and answers with pirate language."""
        system = "Write a welcome sentence.\n\n" + read_skill(self.root, "brand-voice")
        messages = [{"role": "user", "text": "Welcome a new contributor."}]

        def complete(model, prompt, transcript, tools):
            """Return pirate text only after confirming the loaded document is in context."""
            self.assertIn("pirate-style speech", prompt)
            self.assertEqual(tools, [])
            return {"text": "Ahoy, matey—welcome aboard the project!", "tool_calls": [], "usage": {}}

        with patch.object(loop.provider, "complete", side_effect=complete):
            answer = loop.run_loop("test", system, messages, {}, lambda *args: None, lambda call: None)
        self.assertIn("Ahoy", answer)
        self.assertIn("matey", answer)


if __name__ == "__main__":
    unittest.main()
