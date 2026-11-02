"""Project-local dotenv API-key loading without environment leakage."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sudarshan import provider
import sudarshan.loop as loop
from sudarshan.harness import Harness


class ProjectDotenvTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env_path = self.root / ".env"
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def with_project_env(self):
        token = provider.PROJECT_ENV_FILE.set(self.env_path)
        self.addCleanup(provider.PROJECT_ENV_FILE.reset, token)

    def test_reads_supported_key_from_project_env(self):
        self.env_path.write_text(
            "# project credentials\nexport SUDARSHAN_API_KEY='from-dot-env' # local key\n",
            encoding="utf-8",
        )
        self.with_project_env()
        self.assertEqual(provider.api_key(), "from-dot-env")

    def test_process_environment_takes_precedence_over_project_env(self):
        self.env_path.write_text("SUDARSHAN_API_KEY=from-file\n", encoding="utf-8")
        self.with_project_env()
        os.environ["GEMINI_API_KEY"] = "from-process"
        self.assertEqual(provider.api_key(), "from-process")

    def test_dotenv_uses_existing_key_priority(self):
        self.env_path.write_text(
            "GEMINI_API_KEY=third\nODYSSEUS_API_KEY=second\nSUDARSHAN_API_KEY=first\n",
            encoding="utf-8",
        )
        self.with_project_env()
        self.assertEqual(provider.api_key(), "first")

    def test_missing_dotenv_key_has_safe_guidance(self):
        self.with_project_env()
        with self.assertRaisesRegex(RuntimeError, "project's .env"):
            provider.api_key()

    def test_harness_scopes_dotenv_to_its_project_and_resets_after_run(self):
        self.env_path.write_text("SUDARSHAN_API_KEY=workspace-key\n", encoding="utf-8")
        harness = Harness(
            self.root, enable_subagents=False, persist=False, telemetry=False
        )

        def fake_complete(*args):
            self.assertEqual(provider.api_key(), "workspace-key")
            return {"text": "connected", "tool_calls": [], "usage": {}}

        with patch.object(loop.provider, "complete", side_effect=fake_complete):
            self.assertEqual(harness.run("test provider configuration"), "connected")

        with self.assertRaises(RuntimeError):
            provider.api_key()

    def test_only_supported_key_names_are_read(self):
        self.env_path.write_text(
            "SOME_OTHER_SECRET=ignored\nGOOGLE_API_KEY=also-ignored\n",
            encoding="utf-8",
        )
        self.with_project_env()
        with self.assertRaises(RuntimeError):
            provider.api_key()

    def test_unclosed_quote_fails_without_echoing_secret(self):
        self.env_path.write_text('SUDARSHAN_API_KEY="partial-secret\n', encoding="utf-8")
        self.with_project_env()
        with self.assertRaisesRegex(ValueError, "Unclosed quote"):
            provider.api_key()


if __name__ == "__main__":
    unittest.main()
