import unittest
import uuid
from taskman.models import Task


class TestModels(unittest.TestCase):
    def test_task_creation(self):
        task = Task.create("Test", "Desc")
        self.assertEqual(task.title, "Test")
        self.assertEqual(task.description, "Desc")
        self.assertFalse(task.completed)
        self.assertEqual(Task.from_dict(task.to_dict()), task)

    def test_unique_full_uuid_ids(self):
        ids = [Task.create("Task").id for _ in range(1000)]
        self.assertEqual(len(ids), len(set(ids)))
        for value in ids:
            self.assertEqual(str(uuid.UUID(value, version=4)), value)
            self.assertEqual(uuid.UUID(value).version, 4)

    def test_empty_titles(self):
        for title in ("", " ", "\t\n"):
            with self.subTest(title=title), self.assertRaises(ValueError):
                Task.create(title)

    def test_invalid_records(self):
        record = Task.create("Task").to_dict()
        invalid = [None, [], {}, {**record, "extra": 1}]
        for field, value in (("id", ""), ("id", 3), ("title", " "),
                             ("title", None), ("description", 1),
                             ("created_at", "bad"), ("created_at", None),
                             ("completed", 1), ("completed", "false")):
            invalid.append({**record, field: value})
        for value in invalid:
            with self.subTest(record=value), self.assertRaises(ValueError):
                Task.from_dict(value)

    def test_legacy_short_id(self):
        record = Task.create("Old task").to_dict()
        record["id"] = "1234abcd"
        self.assertEqual(Task.from_dict(record).id, "1234abcd")
