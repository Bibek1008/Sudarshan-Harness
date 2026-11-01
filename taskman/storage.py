import json
import os
import tempfile
from taskman.models import Task


class StorageError(Exception):
    """Storage cannot be read or written safely."""


class Storage:
    def __init__(self, filepath: str):
        self.filepath = os.fspath(filepath)

    def load(self) -> list[Task]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            raise StorageError(f"Cannot read storage '{self.filepath}': {exc}. Original file preserved.") from exc
        try:
            if not isinstance(data, list):
                raise ValueError("Storage must contain a JSON list of tasks.")
            tasks = []
            ids = set()
            for index, record in enumerate(data):
                try:
                    task = Task.from_dict(record)
                    if task.id in ids:
                        raise ValueError("Duplicate task ID.")
                except ValueError as exc:
                    raise ValueError(f"Invalid task record {index + 1}: {exc}") from exc
                ids.add(task.id)
                tasks.append(task)
            return tasks
        except ValueError as exc:
            raise StorageError(f"Invalid storage '{self.filepath}': {exc} Original file preserved.") from exc

    def save(self, tasks: list[Task]):
        temporary = None
        try:
            records = [task.to_dict() for task in tasks]
            ids = set()
            for record in records:
                task = Task.from_dict(record)
                if task.id in ids:
                    raise ValueError("Duplicate task ID.")
                ids.add(task.id)
            directory = os.path.dirname(os.path.abspath(self.filepath))
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                             prefix=".taskman-", suffix=".tmp", delete=False) as handle:
                temporary = handle.name
                json.dump(records, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.filepath)
            temporary = None
        except (OSError, ValueError, TypeError) as exc:
            raise StorageError(f"Cannot save storage '{self.filepath}': {exc}") from exc
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise StorageError(f"Cannot remove temporary file '{temporary}': {exc}") from exc
