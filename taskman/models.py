import datetime
import uuid
from dataclasses import dataclass, asdict


@dataclass
class Task:
    id: str
    title: str
    description: str
    created_at: str
    completed: bool

    @classmethod
    def create(cls, title: str, description: str = "") -> "Task":
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Title cannot be empty or whitespace-only.")
        if not isinstance(description, str):
            raise ValueError("Description must be text.")
        return cls(str(uuid.uuid4()), title, description,
                   datetime.datetime.now().isoformat(), False)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        fields = {"id", "title", "description", "created_at", "completed"}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError("Task must contain exactly id, title, description, created_at, completed.")
        for name in ("id", "title", "description", "created_at"):
            if not isinstance(data[name], str):
                raise ValueError(f"Task {name} must be text.")
        if not data["id"].strip() or not data["title"].strip():
            raise ValueError("Task ID and title must not be empty.")
        if type(data["completed"]) is not bool:
            raise ValueError("Task completed must be a boolean.")
        try:
            datetime.datetime.fromisoformat(data["created_at"])
        except ValueError as exc:
            raise ValueError("Task created_at must be an ISO timestamp.") from exc
        return cls(**data)
