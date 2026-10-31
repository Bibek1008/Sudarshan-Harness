"""Day 2: a deliberately small, path-confined tool library.

Tools expose JSON schemas to the model and ordinary callables to the loop.
Every filesystem operation resolves against one real workspace root, mutations
report their scope plainly, and bounded output keeps transcripts useful.
"""

import fnmatch
import inspect
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from .environment import safe_shell_environment


IGNORED_DIRECTORIES = {".git", "node_modules", "__pycache__", ".venv"}


@dataclass
class Tool:
    """A model-visible schema paired with the callable that implements it."""

    name: str
    spec: dict[str, Any]
    run: Callable[..., Any]


def tool(description: str, **params: str) -> Callable[[Callable[..., Any]], Tool]:
    """Decorate a function as a string-parameterized harness tool.

    Parameter descriptions are supplied by keyword, while required parameters
    are derived from the function signature.  String schemas are intentional:
    individual tools own any parsing they need.
    """
    def decorate(fn: Callable[..., Any]) -> Tool:
        signature = inspect.signature(fn)
        arguments = list(signature.parameters.values())
        required = [arg.name for arg in arguments
                    if arg.default is inspect.Parameter.empty]
        properties = {
            arg.name: {"type": "string", "description": params.get(arg.name, "")}
            for arg in arguments
        }
        schema = {
            "name": fn.__name__,
            "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required},
        }
        return Tool(name=fn.__name__, spec={"schema": schema}, run=fn)
    return decorate


def core_tools(workdir: str) -> list[Tool]:
    """Return the standard tools, confined to the real path of ``workdir``."""
    root = os.path.normcase(os.path.realpath(workdir))

    def resolve(path: str) -> str:
        """Resolve one supplied path and reject targets outside the workspace."""
        target = os.path.normcase(os.path.realpath(os.path.join(root, path)))
        try:
            inside = os.path.commonpath([root, target]) == root
        except ValueError:
            inside = False
        if not inside:
            raise PermissionError(f"{path!r} escapes the working directory")
        return target

    def matching_files(pattern: str):
        """Yield workspace files whose relative path or basename matches a glob."""
        for directory, names, files in os.walk(root):
            names[:] = [name for name in names if name not in IGNORED_DIRECTORIES]
            for name in files:
                filename = os.path.join(directory, name)
                relative = os.path.relpath(filename, root).replace(os.sep, "/")
                if pattern == "**/*" or fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern):
                    yield resolve(relative), relative

    @tool("Read a text file with line numbers.", path="Path relative to the workspace.")
    def read_file(path: str) -> str:
        """Read a workspace file, numbering lines and bounding very large files."""
        with open(resolve(path), encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
        total = len(lines)
        shown = lines[:4000]
        output = [f"{number}\t{line}" for number, line in enumerate(shown, 1)]
        if total > 4000:
            output.append(f"... truncated after 4000 lines ({total} total lines)")
        return "\n".join(output)

    @tool("Write a text file, creating parent directories when necessary.",
          path="Path relative to the workspace.", content="Complete file contents.")
    def write_file(path: str, content: str) -> str:
        """Write text inside the workspace and report the number of characters."""
        target = resolve(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)
        return f"Wrote {len(content)} chars to {path}"

    @tool("Replace one exact snippet in a text file.", path="Path relative to the workspace.",
          old="Exact text to replace.", new="Replacement text.")
    def edit_file(path: str, old: str, new: str) -> str:
        """Replace a unique snippet, returning guidance when it is ambiguous."""
        target = resolve(path)
        with open(target, encoding="utf-8", errors="replace") as handle:
            content = handle.read()
        matches = content.count(old)
        # Exact-once replacement prevents a model edit from silently spreading.
        if matches == 0:
            return "ERROR: snippet not found — read the file and copy it exactly"
        if matches > 1:
            return f"ERROR: snippet appears {matches} times — include more context to make it unique"
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content.replace(old, new, 1))
        return f"Edited {path}"

    @tool("Run a shell command in the workspace with captured, bounded output.",
          command="Shell command to run.", timeout="Timeout in seconds.")
    def bash(command: str, timeout: str = "120") -> str:
        """Run a command in the workspace, returning both standard output streams."""
        try:
            completed = subprocess.run(
                command, shell=True, cwd=root, capture_output=True, text=True,
                env=safe_shell_environment(),
                timeout=float(timeout),
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: timed out after {timeout}s"
        output = completed.stdout + completed.stderr
        if len(output) > 12000:
            output = output[:6000] + "\n... output truncated ...\n" + output[-6000:]
        return output or f"(exit {completed.returncode}, no output)"

    @tool("List workspace files matching a glob.", pattern="Glob for relative paths or basenames.")
    def list_files(pattern: str = "**/*") -> str:
        """List up to 500 matching files, excluding dependency and VCS trees."""
        matches = sorted(relative for _, relative in matching_files(pattern))
        if len(matches) > 500:
            return "\n".join(matches[:500] + [f"and {len(matches) - 500} more"])
        return "\n".join(matches)

    @tool("Search text files with a regular expression.", regex="Regular expression to search for.",
          pattern="Glob for relative paths or basenames.")
    def grep(regex: str, pattern: str = "*") -> str:
        """Search matching files line by line and return at most 200 hits."""
        expression = re.compile(regex)
        hits: list[str] = []
        for filename, relative in matching_files(pattern):
            with open(filename, encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    if expression.search(line):
                        text = line.rstrip("\r\n")[:200]
                        hits.append(f"{relative}:{number}: {text}")
                        if len(hits) == 200:
                            return "\n".join(hits)
        return "\n".join(hits)

    return [read_file, write_file, edit_file, bash, list_files, grep]
