"""Day 3 tests: durable Markdown memory and fresh prompt-only recall."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sudarshan.loop as loop
from sudarshan.memory import MEMORY_FILE, build_system_prompt, remember


class MemoryTests(unittest.TestCase):
    """Verify saved facts become system context for a separate conversation."""

    def setUp(self) -> None:
        """Create a writable workspace inside the repository test area."""
        parent = Path(__file__).resolve().parent.parent / "work"
        parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        """Remove the temporary project memory after each test."""
        self.temporary.cleanup()

    def test_remember_appends_and_prompt_includes_memory(self) -> None:
        """A durable fact is written as Markdown and injected into the base prompt."""
        self.assertEqual(remember(self.root, "The deployment region is Pune."), "Remembered in SUDARSHAN.md")
        prompt = build_system_prompt(self.root, "Extra instruction.")
        self.assertIn("Project memory (SUDARSHAN.md):", prompt)
        self.assertIn("- The deployment region is Pune.", prompt)
        self.assertIn("Platform:", prompt)
        self.assertIn(str(self.root.resolve()), prompt)
        self.assertIn("Extra instruction.", prompt)
        self.assertEqual((self.root / MEMORY_FILE).read_text(encoding="utf-8"), "- The deployment region is Pune.\n")

    def test_fresh_loop_answers_from_system_memory_without_tools(self) -> None:
        """A separate transcript can answer a saved fact before making tool calls."""
        remember(self.root, "The release codename is Kestrel.")
        system = build_system_prompt(self.root)
        messages = [{"role": "user", "text": "What is the release codename?"}]

        def complete(model, prompt, transcript, tools):
            """Assert the fresh provider request receives memory only via its system text."""
            self.assertIn("The release codename is Kestrel.", prompt)
            self.assertEqual(tools, [])
            return {"text": "The release codename is Kestrel.", "tool_calls": [], "usage": {}}

        with patch.object(loop.provider, "complete", side_effect=complete) as provider_call:
            answer = loop.run_loop("test", system, messages, {}, lambda *args: None, lambda call: None)
        self.assertEqual(answer, "The release codename is Kestrel.")
        self.assertEqual(provider_call.call_count, 1)
        self.assertEqual(len(messages), 2)


if __name__ == "__main__":
    unittest.main()
