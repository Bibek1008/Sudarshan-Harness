"""Versioned benchmark contracts; definitions are trusted repository data."""
from dataclasses import dataclass, asdict
from pathlib import PurePosixPath
import re

STATUSES = {"passed", "failed", "partial", "timeout", "interrupted", "invalid_output", "verifier_error", "inconclusive"}


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("invalid relative artifact path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"..", ".sudarshan", ".env", ".git"} or p.startswith(".env") for p in path.parts):
        raise ValueError("invalid relative artifact path")
    if str(path) != value or path.suffix not in {".py", ".md", ".txt", ".json"}:
        raise ValueError("invalid artifact type or path")
    return value


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    category: str
    version: str
    description: str
    instructions: str
    fixture: str
    verifier: str
    seconds: int
    turns: int
    deliverables: tuple
    criteria: tuple

    def validate(self):
        for value in (self.id, self.category, self.version, self.fixture, self.verifier):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,79}", value):
                raise ValueError("invalid benchmark identifier")
        for value in (self.name, self.description, self.instructions):
            if not isinstance(value, str) or not 1 <= len(value) <= 8192:
                raise ValueError("invalid benchmark text")
        if type(self.seconds) is not int or not 1 <= self.seconds <= 300 or type(self.turns) is not int or not 1 <= self.turns <= 40:
            raise ValueError("invalid benchmark budget")
        if not isinstance(self.deliverables, tuple) or not isinstance(self.criteria, tuple): raise ValueError("artifact and criterion collections must be tuples")
        if not 1 <= len(self.deliverables) <= 16 or not 1 <= len(self.criteria) <= 32 or len(set(self.deliverables)) != len(self.deliverables):
            raise ValueError("invalid benchmark criteria/deliverables")
        for path in self.deliverables: safe_relative(path)
        if any(not isinstance(c, str) or not re.fullmatch(r"[a-z0-9_-]{1,80}", c) for c in self.criteria):
            raise ValueError("invalid criterion identifier")
        if len(set(self.criteria)) != len(self.criteria): raise ValueError("duplicate criteria")
        return self

    def public_metadata(self):
        return {key: value for key, value in asdict(self).items() if key not in {"instructions"}}
