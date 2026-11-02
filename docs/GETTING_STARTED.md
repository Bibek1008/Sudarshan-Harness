# Getting started

Sudarshan is a personal Python coding-agent harness. Python 3.10 or newer and
Git are enough to run its standard-library code and offline tests. No package
installation, cloud service or plugin setup is required. Docker, SSH and an
installed Chromium browser are optional runtimes for their respective examples
and integration checks.

## Check out and verify

```console
git clone https://github.com/Bibek1008/Sudarshan-Harness.git
cd Sudarshan-Harness
python --version
python -m sudarshan --help
python -m unittest discover -v
python -m sudarshan benchmark run core --dry-run
```

Use `python3` instead of `python` where that is your Python 3 command. Always run
the module from the checkout root: the repository currently has no pip installer
or globally installed `sudarshan` command. An optional `.venv` is fine but requires
no dependencies. The dry-run and tests do not make live Gemini requests. Tests
need permission to use local loopback sockets; optional browser, Docker and
platform-specific checks report explicit skips when unavailable.

## Configure a key only when you want an agent task

Gemini uses `SUDARSHAN_API_KEY`, with `ODYSSEUS_API_KEY` and `GEMINI_API_KEY`
as backward-compatible fallbacks. Configure a trusted local environment without
putting the value in source, command arguments, chat, project memory or Git.
Sudarshan does not load `.env` files. Help, stats, trace and benchmark dry-run
need no provider key.

For a one-process interactive session, this optional standard-library launcher
prompts without echoing the key or storing it in shell history:

```console
python -c "import getpass,os; os.environ['SUDARSHAN_API_KEY']=getpass.getpass('Gemini API key: '); from sudarshan.cli import main; main()"
```

The key remains in that Python process's environment until it exits. This is
convenience, not protection against other software with access to the account.
Do not put credentials in task text. Actual agent tasks consume provider quota
or money; none are started by installation or the offline checks above.

## Select one project root

From the harness checkout, point `-d` at the project you want to work on:

```console
python -m sudarshan -d "../my-project" --mode read-only -p "Inspect this project and explain its structure"
python -m sudarshan -d "../my-project" -p "Add a small module and tests, then verify them"
python -m sudarshan -d "../my-project"
```

These are live-agent examples for you to run after configuring credentials.
The default `safe` mode asks before effects; answer `y` or `yes` to approve only
calls you have reviewed. Blank input and EOF refuse. Headless `-p` still uses
safe mode and may prompt for approval. `read-only` allows only the exact core
read tools. `yolo` skips approvals and is not an OS sandbox; it is not needed
for first use. Hard-deny checks remain active in every mode.

Keep the same project-root `-d` across runs. Memory and metadata stay in that
workspace. A nested directory deliberately does not inherit parent memory.
The model defaults to the value in `sudarshan/provider.py`; use `-m MODEL` or
`ODYSSEUS_MODEL` to select an identifier available to your account. Availability
and pricing are not queried automatically.

## Sessions, memory and debugging

```console
python -m sudarshan -d "../my-project" --resume
python -m sudarshan -d "../my-project" --resume ".sudarshan/sessions/SESSION_FILE.jsonl" -p "Continue verification"
python -m sudarshan -d "../my-project" -p "Reproduce the failing test, fix the cause, and run the relevant tests"
```

Use the actual transcript filename from your own workspace for `SESSION_FILE`.
It is different from a telemetry UUID. Transcript logs can contain task and tool
contents: keep them private and ignored. Resume repairs a torn tail or interrupted
tool-call pair, but does not prove the interrupted tool had no effect. Inspect
changed files before retrying. One writer per transcript is required.

`SUDARSHAN.md` is editable, bounded project memory. Ask the agent to remember an
explicit durable project fact, then review/approve the `remember` tool call.
Its optional `section`, `replaces` and `verified` fields support organization,
corrections, removal and evidence dates. Do not save credentials or personal
data. See [README's memory details](../README.md#state-and-composition) and the
[Phase 6 report](../PHASE6_MEMORY_REPORT.md) for retrieval and concurrency limits.

## Local diagnostics and evaluation

```console
python -m sudarshan stats -d "../my-project" --json
python -m sudarshan trace -d "../my-project" --session TELEMETRY_UUID
python -m sudarshan telemetry -d "../my-project" --disable
python -m sudarshan benchmark list
python -m sudarshan benchmark show core
python -m sudarshan benchmark run core --dry-run --task slug
```

Stats supplies the telemetry UUID to use with trace. Diagnostics are local and
provider-free. `--no-telemetry` disables collection for one agent invocation;
neither opt-out disables transcript persistence. Token estimates for context
management are separate from actual provider usage. See [observability](OBSERVABILITY.md)
and [evaluation](EVALUATION.md) for storage, coverage and bounded reporting.

## Common problems

| Symptom | Action |
| --- | --- |
| `No module named sudarshan` | Run from the harness checkout root using the intended Python interpreter. |
| Workspace/session error | Check `-d`, project permissions and the project-relative `--resume` path. Escaping paths are refused. |
| Task fails before a response | Check local key configuration, network and model availability. Raw provider errors are intentionally not printed. |
| An effect is blocked | Review safe-mode approval; empty/negative input declines it. Do not bypass controls just to make a task pass. |
| No session or telemetry found | Select the same `-d`; transcripts and telemetry IDs are separate. Missing state is normal on first run. |
| Project memory unavailable | Inspect/repair your own memory file, preserving existing facts. Oversized or corrupt memory is skipped. |
| Memory writer busy | Check for a running writer. Remove a stale lock only after confirming no writer is active. |
| Broker tests fail with socket denial | Run tests where localhost networking is permitted. Provider calls in those tests are mocked. |

Read [current security limits](SECURITY.md) before using unfamiliar projects or
executing generated code. The [cleanup report](CLEANUP_REPORT.md),
[release notes](../RELEASE_NOTES.md) and [final project report](../FINAL_PROJECT_REPORT.md)
record release scope and validation. Historical reports retain their original
dates and results.
