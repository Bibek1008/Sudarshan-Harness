# Sudarshan

Sudarshan is the smallest agent harness: a compact, standard-library-only
reference implementation with zero dependencies. Its ten core teaching modules
separate provider I/O, looping, tools, security, context, memory, skills,
sessions, delegation, and orchestration.

## Run it

Set `ODYSSEUS_API_KEY` (or `GEMINI_API_KEY`) before running. From the repository
root, use one of these forms:

```bash
python -m sudarshan
python -m sudarshan -p "Inspect this project and summarize it" -d .
python -m sudarshan --resume
```

The first form is interactive. Headless `-p` runs one task and defaults to the
`yolo` policy; interactive mode defaults to `safe` and asks before effects.
`--resume` restores the newest durable JSONL session or accepts a session path.

| Day | Architecture |
| --- | --- |
| 1 | Gemini provider boundary and deterministic tool loop |
| 2 | Path-confined tools and explicit safety policy |
| 3 | Context compaction, project memory, and Markdown skills |
| 4 | Durable sessions, recovery, subagents, and Harness |
| 5 | CLI and ordered concurrent fleet execution |

## Add a tool

```python
from sudarshan import Harness, tool

@tool("Return a friendly greeting.", name="Person to greet.")
def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"

answer = Harness(extra_tools=[greet]).run("Greet Ada using the tool.")
```
