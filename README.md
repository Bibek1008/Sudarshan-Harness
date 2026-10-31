# Sudarshan

Sudarshan is a compact Python 3.10+ agent harness with zero third-party Python
dependencies. Its teaching modules
separate provider I/O, looping, tools, security, context, memory, skills,
sessions, delegation, and orchestration.

Clone the repository and run from its root; no pip install is required. On
systems where Python is named `python3`, substitute that for `python` below.
Gemini requests use `ODYSSEUS_API_KEY`, falling back to `GEMINI_API_KEY`.
Set credentials in your local environment, never in source or session prompts.
The default model is `gemini-3.1-pro-preview`; override with `-m` or
`ODYSSEUS_MODEL`. API access and usage billing are separate from this package.

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

## State and composition

`Harness` combines `core_tools`, `Policy`, prompt memory and skills with
`run_loop`. The provider translates neutral messages and round-trips Gemini
thought signatures. A turn-limit wrap-up disables tools and returns a final
report. `before_turn` compacts overflow using one factual summary call and
retains recent messages without a leading orphaned tool response.

`SUDARSHAN.md` is durable project memory injected into each new system prompt;
the `remember` tool appends facts. `skills/<name>/SKILL.md` is discoverable via
`catalog_prompt`; `use_skill` loads the full document on demand.

Sessions live in `.sudarshan/sessions/` (ignored by Git). Resume truncates torn
JSONL bytes and durably appends missing interruption responses. This is a
single-writer log: do not run two writers against the same session. A repair
notice does not prove a tool had no external effect before the crash; inspect
files before retrying. Child agents share workspace and policy but have fresh
context and `persist=False`; delegation depth is capped at two.

`run_fleet(jobs, make_harness, max_workers=4)` constructs independent harnesses
concurrently and returns name/ok/report dictionaries in input order. Jobs have
`name`, `workdir`, and `task`. Use separate workdirs for independent effects.

## Security and execution

`safe` asks before non-read tools; `read-only` blocks them; `yolo` allows them.
Hard-deny rules run first in every mode, including backend-prefixed tools.
They cover common destructive rm, sudo, mkfs, dd, curl-to-shell, force-push,
and disk-device redirection forms. Malformed command quoting is refused.
Regex and token checks cannot establish arbitrary shell safety.

Filesystem tools validate resolved paths, but shell commands use the host
account's permissions. A cwd is not a sandbox. Resolve/open race windows remain.
Use only trusted workspaces and inspect commands; untrusted code needs separate
OS isolation. Policy applies through the loop/tool adapter, not raw backend calls.

`execution/` supplies a registry, structured results, local operations, SSH
operations (system SSH with strict known-host checking and remote Python file
validation), and a Docker backend. Docker uses no network, a read-only root,
dropped capabilities and a designated workspace mount. Docker and SSH are
external runtimes, not Python dependencies. Containers are not an absolute
security guarantee; timeout cleanup and remote process lifetime need further
hardening. See AUDIT.md for unresolved risks.

## Verification and live product proof

```bash
python -m unittest discover -v
python -m sudarshan --help
python -m demos.product_fleet
```

Unit tests use mocks for provider/SSH/Docker boundaries. The last command requires
a configured Gemini key and creates fresh `projects/` workspaces, then runs
build and review fleets with identical per-project sessions. It records actual
assistant turns and observed skill loads. It has not yet been live-verified;
generated reports do not establish product acceptance. Browser interaction
testing, visible-copy counts and Taskman subprocess tests must be checked
independently. Do not treat the current repository as production hardened.
