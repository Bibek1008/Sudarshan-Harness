# Sudarshan

Sudarshan is a compact Python 3.10+ agent harness with zero third-party Python
dependencies. Its teaching modules
separate provider I/O, looping, tools, security, context, memory, skills,
sessions, delegation, and orchestration.

Clone the repository and run from its root; no pip install is required. On
systems where Python is named `python3`, substitute that for `python` below.
Gemini requests use `SUDARSHAN_API_KEY`, then legacy `ODYSSEUS_API_KEY`
(backward compatibility), then generic `GEMINI_API_KEY`. Empty values fall back.
Set credentials in your local environment, never in source or session prompts.
The default model is `gemini-3.1-pro-preview`; override with `-m` or
`ODYSSEUS_MODEL`. API access and usage billing are separate from this package.

## Run it

Set `SUDARSHAN_API_KEY` in your local environment before running. From the repository
root, use one of these forms:

```bash
python -m sudarshan
python -m sudarshan -p "Inspect this project and summarize it" -d .
python -m sudarshan --resume
```

The first form is interactive. Headless `-p` runs one task. Both forms and
`Harness()` default to `safe`, which asks before non-read tools. Without an
approver, the library refuses these operations; CLI EOF or a blank response
also refuses approval. Unattended execution requires an explicit policy choice.
Use `--mode yolo` only when you intend to skip approval.
**Headless risk:** `-p ... --mode yolo` permits ordinary shell commands without
approval under your OS account, including file changes and network access.
It is not a sandbox. Headless mode currently defaults to `safe`, just like
interactive mode; this cleanup preserves that CLI contract. Older revisions
defaulted headless runs to `yolo`, so scripts should pass `--mode` explicitly.
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
`Policy("yolo")` is not a sandbox. It skips approval while preserving hard-deny
checks; it does not confine files, processes or network access. Safe mode also
provides approval checks rather than OS isolation.
Hard-deny rules run first in every mode, including backend-prefixed shell tools.
Only the exact core read identities bypass approval. Custom and backend read
names default to restricted; suffixes grant no trust. Harness also restricts
custom tools that override a built-in reader's name.
They cover common destructive rm, sudo, mkfs, dd, curl-to-shell, force-push,
and disk-device redirection forms. Malformed command quoting is refused.
Root/home `find` deletion is also hard-denied: for example `find / -delete`,
`find -L / -type f -delete`, `find "$HOME" -delete`, and
`find / -exec rm {} \;` (also `-execdir`). The rules recognize common
`-H`, `-L`, `-P` and `-O` options, quotes and chained commands. Local cleanup
such as `find ./scratch -type f -delete` still follows the selected policy.
Regex and token checks cannot establish arbitrary shell safety.
These are conservative patterns, not a shell parser or an exhaustive list of
destructive programs. Other path spellings, multiple roots, aliases, expansion,
indirect execution and nested interpreters can evade inspection. False positives
are also possible. Use an appropriately isolated OS sandbox for untrusted code.
Lexical root equivalents such as `/tmp/..` and `/var/..` are now rejected for
both `rm` and destructive `find` forms. This normalization is inspection only;
it does not resolve remote symlinks or prove any other path safe.

Filesystem tools validate resolved paths, but shell commands use the host
account's permissions. A cwd is not a sandbox. Resolve/open race windows remain.
Use only trusted workspaces and inspect commands; untrusted code needs separate
OS isolation. Policy applies through the loop/tool adapter, not raw backend calls.

Core Bash and the local execution backend share a minimal inherited environment:
only `PATH`, `PATHEXT`, `COMSPEC`, `SYSTEMROOT`, `WINDIR`, `TEMP` and `TMP`
(matched without case sensitivity). Every other parent variable is excluded,
including `SUDARSHAN_API_KEY`, legacy `ODYSSEUS_API_KEY`, `GEMINI_API_KEY`,
unrelated credentials, agent sockets and shell/Python startup hooks. The provider
keeps its own environment; filtering does not remove its configured API key.
The allowlist is defined in `sudarshan/environment.py`; there is no automatic
pass-through for additional variables. Programs that require other settings must
receive them through a deliberately reviewed configuration change.

Allowed runtime values and executable lookup paths must be trusted. Filtering
prevents credential inheritance, not access to secrets in files, command text,
OS services or shell startup files. It does not make local commands a sandbox.

`execution/` supplies a registry, structured results, local operations, SSH
operations (system SSH with strict known-host checking and remote Python file
validation), and a Docker backend. Docker uses no network, a read-only root,
dropped capabilities and a designated workspace mount. Docker and SSH are
external runtimes, not Python dependencies. Containers are not an absolute
security guarantee. Docker timeout cleanup targets the exact named container and
reports unconfirmed cleanup. Remote process lifetime still needs further
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

### Automated product approvals and acceptance

The fleet explicitly constructs `Policy("safe", approver)` for each project;
ordinary Harness and CLI defaults remain safe. The approver permits only
project-relative `write_file`/`edit_file`, `use_skill("design-engineering")`,
and these exact test commands:

```text
python -m unittest discover
python -m unittest discover -v
python -m unittest discover -s tests -v
```

The fleet's Bash callable executes the selected command as an argument list
using the current Python interpreter, without a shell, with the shared filtered
environment and a maximum 120-second timeout. Arbitrary commands, chaining,
unknown tools/skills, absolute edit paths, traversal escapes and edits to skills,
sessions or Git state are not automatically approved. Core filesystem tools
also resolve and reject paths outside their project root.

**This strategy is not an OS sandbox.** Generated tests are executable Python
with the host account's permissions, including possible filesystem/network
access outside the project. The guarantee above covers filesystem tool paths,
not arbitrary generated programs; resolve/open races remain. Use OS isolation
for untrusted generated code. Do not assume an approved test command is safe
merely because its argument list is restricted.

Model final text is recorded separately from artifact checks. Each phase must
load the required skill. Missing or insufficient files trigger a bounded build
repair before review; reviews resume the original parent session. Failed reviews
receive another repair/review attempt. Blocked projects remain explicitly in
the report, and every project is independently checked after the final review.
Evidence is saved after phases and returned in original input order. Existing
project directories or run evidence cause refusal rather than overwrite.

The independent verifier checks HTML prerequisites and runs Taskman's generated
tests plus a separate add/list/done/stats/rm lifecycle using a temporary store.
Taskman uses global `--store PATH` and a JSON tasks list with stable `id`, `title`
and boolean `done` fields. At least ten tests must actually execute successfully.
HTML counting excludes scripts/styles and obvious inline hidden content, but
cannot infer computed CSS visibility or establish interaction behavior. Static
hooks do not prove gameplay, responsive design or accessibility. Browser checks
and manual assessment of meaningful test coverage remain required; the runner
keeps acceptance incomplete while those checks are outstanding. Model-written
verification reports cannot clear these independent manual gates.

### Recording independent acceptance

Verification reports expose `automated_passed`, `manual_pending`, `manual_passed`
and `final_accepted` separately. `automated_ok` and `accepted` remain compatible
aliases for automated and final success. Automated success never grants final
acceptance. Fleet results also require the review phase to have passed.

After independently performing every item in `manual_required`, a human can use
`record_manual_verification` from `demos.product_verify`:

```python
result = verify_product("artisan-coffee", project_path)
# Populate only with real observations; missing/failed checks remain pending.
checks = {requirement: {"passed": True, "evidence": observation}
          for requirement, observation in independently_observed_checks.items()}
record_manual_verification("artisan-coffee", project_path, evidence_path,
                           reviewer="Reviewer name", checks=checks)
result = verify_product("artisan-coffee", project_path,
                        manual_evidence=evidence_path)
```

Import both functions from `demos.product_verify`. Evidence must be outside the
agent's project, name a reviewer, cover every required check with literal `True`
and nonempty evidence, and match the current artifact digest. Any project-file
change invalidates it (runtime state and bytecode caches are excluded). Protect
the evidence with host permissions: this is an explicit attestation, not a
cryptographic identity guarantee. Recheck an existing project directly rather
than rerunning the fresh-workspace fleet. The fleet API also accepts a mapping
of product names to evidence paths via `run_products(..., manual_evidence=...)`.

Static visibility checks conservatively exclude common class/ID rules using
display:none, visibility:hidden/collapse, opacity zero or clipping, plus common
visually-hidden classes, aria-hidden, hidden ancestors, scripts and styles.
They count only unsuppressed sections and SVGs. They do not compute the CSS
cascade, external stylesheets, media queries, geometry or JavaScript visibility;
conditional CSS may therefore undercount and unfamiliar hiding may be missed.
The report labels this method `conservative_static`, never browser verification.

A trusted browser adapter can be supplied as `browser_probe` to `verify_product`
or `run_products`. It receives `(index_path, viewport_width)` and must return
integer `words`, `sections` and `svgs` measured with actual computed visibility.
The verifier requests 360/768/1280 and uses the minimum counts. Adapter provenance
is the caller's responsibility; interaction checks still require evidence.
No browser engine is bundled. The optional standard-library ChromiumProbe now
executes deterministic fixture checks in installed headless Edge/Chrome. See
LIVE_BUILD_READINESS.md for configuration, observed coverage and limitations.
These fixture observations are not live-product acceptance.

Browser-dependent tests run `browser_capability_preflight()` once before their
class executes. The preflight loads a controlled local page with the same
filtered environment, temporary profile, secure arguments and browser sandbox
as the actual probe. It tries discovered installations without disabling sandbox
security. The returned `BrowserCapability` includes `available`, `executable`
and the launch reason. A missing executable, refused launch, timeout or absent
controlled DOM observation makes the runtime unavailable; unittest reports the
specific reason and skips only the browser test class. Browser-independent
regressions still run. Unexpected adapter errors remain errors.

After preflight succeeds, the selected executable is retained for the viewport
and Viper fixtures. No subsequent assertion, observation error or product
failure is converted into a skip. Root/container environments must provide a
browser configuration that supports its sandbox to run these tests; the suite
never weakens browser security to make them pass.
