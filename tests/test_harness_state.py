from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import json

from sudarshan import memory, session, skills
from sudarshan.harness import Harness
from tests.test_harness_security import WorkspaceCase


class TestState(WorkspaceCase):
    def test_session_round_trip_unicode(self):
        path = session.new_session(self.root, "café name")
        message = {"role": "user", "text": "नमस्ते café"}
        session.append(path, message)
        self.assertEqual(session.load(path), [message])
        self.assertEqual(session.latest(self.root), path)

    def test_duplicate_and_concurrent_session_names(self):
        with patch.object(session.time, "time", return_value=100):
            with ThreadPoolExecutor(max_workers=8) as pool:
                paths = list(pool.map(lambda _: session.new_session(self.root, "same"), range(32)))
        self.assertEqual(len(set(paths)), 32)
        self.assertTrue(all(path.exists() for path in paths))

    def test_corrupt_tail_recovery_and_append(self):
        for tail in (b'{bad', b'\xff', b'[]\n', b'{"role":"invalid"}\n', b'{"role":[]}\n',
                     b'{"role":"assistant","text":"bad","tool_calls":[{}]}\n'):
            with self.subTest(tail=tail):
                path = session.new_session(self.root)
                user = {"role": "user", "text": "good"}
                session.append(path, user)
                with path.open("ab") as handle:
                    handle.write(tail)
                self.assertEqual(session.load(path), [user])
                session.append(path, {"role": "user", "text": "after recovery"})
                self.assertEqual(len(session.load(path)), 2)

    def test_interrupted_calls_repaired_once(self):
        path = session.new_session(self.root)
        session.append(path, {"role": "assistant", "text": "", "tool_calls": [
            {"name": "one", "args": {}}, {"name": "two", "args": {}}]})
        session.append(path, {"role": "tool", "name": "one", "text": "done"})
        repaired = session.load(path)
        self.assertEqual(repaired[-1]["name"], "two")
        self.assertIn("Interrupted", repaired[-1]["text"])
        content = path.read_bytes()
        self.assertEqual(session.load(path), repaired)
        self.assertEqual(path.read_bytes(), content)

    def test_valid_final_record_without_newline(self):
        path = session.new_session(self.root)
        path.write_text(json.dumps({"role": "user", "text": "last"}), encoding="utf-8")
        self.assertEqual(len(session.load(path)), 1)
        session.append(path, {"role": "user", "text": "next"})
        self.assertEqual(len(session.load(path)), 2)

    def test_missing_session_and_resume_boundary(self):
        self.assertIsNone(session.latest(self.root))
        harness = Harness(self.root, persist=False)
        self.assertFalse(harness.resume())
        outside = session.new_session(self.base)
        with self.assertRaises(PermissionError):
            harness.resume(outside)
        with self.assertRaises(PermissionError):
            Harness(self.root, session_path=outside)

    def test_memory_unicode_and_invalid_encoding(self):
        memory.remember(self.root, "Unicode café नमस्ते")
        self.assertIn("Unicode café नमस्ते", memory.build_system_prompt(self.root))
        (self.root / memory.MEMORY_FILE).write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, "original file preserved"):
            memory.build_system_prompt(self.root)
        self.assertEqual((self.root / memory.MEMORY_FILE).read_bytes(), b"\xff")

    def test_memory_symlink_boundary(self):
        target = self.base / "outside.md"
        target.write_text("untouched", encoding="utf-8")
        self.symlink(self.root / memory.MEMORY_FILE, target)
        with self.assertRaises(PermissionError):
            memory.remember(self.root, "injected")
        with self.assertRaises(PermissionError):
            memory.build_system_prompt(self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "untouched")

    def test_session_directory_symlink_boundary(self):
        target = self.base / "outside"
        target.mkdir()
        (self.root / ".sudarshan").mkdir()
        self.symlink(self.root / session.SESSION_DIR, target, directory=True)
        with self.assertRaises(PermissionError):
            session.new_session(self.root)
        with self.assertRaises(PermissionError):
            session.latest(self.root)
        self.assertEqual(list(target.iterdir()), [])

    def test_skill_catalog_and_unknown_name(self):
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\ndescription: Example skill\n---\nContent", encoding="utf-8")
        self.assertEqual(skills.catalog(self.root)["demo"]["description"], "Example skill")
        self.assertIn("Content", skills.read_skill(self.root, "demo"))
        self.assertIn("no skill named", skills.read_skill(self.root, "../outside"))

    def test_skill_symlink_boundary(self):
        target = self.base / "outside.md"
        target.write_text("outside", encoding="utf-8")
        link = self.root / "skills" / "escape" / "SKILL.md"
        link.parent.mkdir(parents=True)
        self.symlink(link, target)
        with self.assertRaises(PermissionError):
            skills.catalog(self.root)

    def test_concurrent_process_session_creation(self):
        import subprocess
        import sys
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        code = "from sudarshan.session import new_session; import sys; print(new_session(sys.argv[1], 'same'))"
        def create(_):
            result = subprocess.run([sys.executable, "-c", code, str(self.root)],
                                    cwd=self.root, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()
        with ThreadPoolExecutor(max_workers=4) as pool:
            names = list(pool.map(create, range(8)))
        self.assertEqual(len(set(names)), 8)

    def test_windows_directory_permission_retry_is_bounded(self):
        import os
        if os.name != "nt":
            self.skipTest("Windows-specific mkdir access-denied retry")
        error = PermissionError("simulated access denied")
        error.winerror = 5
        with patch.object(Path, "mkdir", side_effect=error) as mkdir, patch.object(session.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                session.new_session(self.root)
        self.assertEqual(mkdir.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_windows_extended_path_normalization(self):
        import os
        from sudarshan.paths import _resolved
        if os.name != "nt":
            self.skipTest("Windows-specific extended path syntax")
        value = str(self.root)
        with patch.object(Path, "resolve", return_value=Path("\\\\?\\" + value)):
            self.assertEqual(_resolved(self.root), self.root)
