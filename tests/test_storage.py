import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from taskman.storage import Storage, StorageError
from taskman.models import Task


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.json"
        self.storage = Storage(self.path)

    def test_missing_file(self):
        self.assertEqual(self.storage.load(), [])
        self.assertFalse(self.path.exists())

    def test_persistence_after_reload(self):
        tasks = [Task.create("T1", "several words"), Task.create("T2")]
        tasks[0].completed = True
        self.storage.save(tasks)
        self.assertEqual(Storage(self.path).load(), tasks)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_malformed_json_preserved(self):
        for content in (b"invalid json", b"", b"[", b"\xff"):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                with self.assertRaisesRegex(StorageError, "Original file preserved"):
                    self.storage.load()
                self.assertEqual(self.path.read_bytes(), content)

    def test_invalid_structures_and_records(self):
        task = Task.create("Task").to_dict()
        for value in ({}, None, 1, "text", [None], [{}], [{**task, "completed": 1}],
                      [task, task]):
            with self.subTest(value=value):
                content = json.dumps(value)
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaises(StorageError):
                    self.storage.load()
                self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_read_failure(self):
        with patch("builtins.open", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(StorageError, "denied"):
                self.storage.load()

    def test_write_failures_preserve_original_and_clean_temporary(self):
        self.storage.save([Task.create("Original")])
        original = self.path.read_bytes()
        for target in ("taskman.storage.json.dump", "taskman.storage.os.fsync",
                       "taskman.storage.os.replace"):
            with self.subTest(target=target):
                with patch(target, side_effect=OSError("simulated failure")):
                    with self.assertRaisesRegex(StorageError, "simulated failure"):
                        self.storage.save([Task.create("Replacement")])
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_save_preserves_original(self):
        task = Task.create("Original")
        self.storage.save([task])
        original = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.storage.save([task, task])
        self.assertEqual(self.path.read_bytes(), original)

    def test_temporary_creation_failure(self):
        with patch("taskman.storage.tempfile.NamedTemporaryFile", side_effect=OSError("denied")):
            with self.assertRaises(StorageError):
                self.storage.save([])
        self.assertEqual(list(self.path.parent.iterdir()), [])
