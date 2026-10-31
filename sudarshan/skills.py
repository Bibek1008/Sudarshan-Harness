"""Day 3: file-based skills that change behavior without changing code.

Each skill is an inspectable Markdown document beneath one workspace directory.
Discovery is deterministic, loading returns original text, and missing names
produce a usable catalogue error instead of an exception.
"""

import re
from pathlib import Path


SKILLS_DIR = "skills"


def catalog(workdir: str | Path) -> dict[str, dict[str, str]]:
    """Discover workspace ``SKILL.md`` files and their front-matter descriptions."""
    root = Path(workdir).resolve() / SKILLS_DIR
    if not root.is_dir():
        return {}
    result: dict[str, dict[str, str]] = {}
    for skill_file in sorted(root.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        match = re.search(r"^description:\s*(.+?)\s*$", text, flags=re.MULTILINE)
        description = match.group(1).strip().strip('"\'') if match else ""
        result[skill_file.parent.name] = {"description": description, "path": str(skill_file)}
    return result


def catalog_prompt(workdir: str | Path) -> str:
    """Render available skills as compact instructions for an agent system prompt."""
    available = catalog(workdir)
    if not available:
        return ""
    lines = ["Skills available (load one with the use_skill tool when relevant):"]
    lines.extend(f"- {name}: {entry['description']}" for name, entry in available.items())
    return "\n".join(lines)


def read_skill(workdir: str | Path, name: str) -> str:
    """Return a named skill document or a readable error listing valid names."""
    available = catalog(workdir)
    if name not in available:
        names = ", ".join(available) or "(none)"
        return f"ERROR: no skill named {name}. Available: {names}"
    return Path(available[name]["path"]).read_text(encoding="utf-8")
