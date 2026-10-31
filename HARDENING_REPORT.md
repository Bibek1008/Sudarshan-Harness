# SUDARSHAN hardening verification — 31 October 2026

## Repository baseline
Existing checkout: C:/Users/User/Documents/Codex/2026-10-31/you-are-building-day-1-of/sudarshan.
Remote: Bibek1008/Sudarshan-Harness. Branch: main. Starting HEAD: b829b1b.
The workspace supplied with this chat contained no repository; the existing checkout
was located under Documents/Codex. No project was recreated, branch reset, or history rewritten.
Direct GitHub access failed DNS resolution; the GitHub connector confirmed the repository.
Local HEAD has not been compared with the current remote HEAD.

Initial status already contained modified AUDIT.md, README.md, demos/product_fleet.py,
and untracked tests/test_product_preparation.py. These were inspected and preserved;
they were not included in this chat's commits.

Actual baseline: 65 discovered, 64 passed, 0 failures, 1 skipped on Python 3.12.
The advertised 54-test baseline was historical.

## Existing repairs verified
| Finding and root cause | Existing repair | Executed evidence |
| --- | --- | --- |
| Custom suffix inherited read authority | Exact read names; extra-tool overrides remapped to restricted names in Harness | test_explicit_read_permissions, test_custom_core_name_override_is_restricted |
| rm operands before flags and HOME parent targets escaped detection | Token inspection plus conservative denial before mode or approval | test_rm_argument_permutations, test_dangerous_forms_in_every_mode |
| Brand-specific API key missing | SUDARSHAN_API_KEY, then intentional legacy ODYSSEUS_API_KEY, then GEMINI_API_KEY | test_key_precedence, test_keys |
| Timestamp session names collided | Exclusive creation and numbered collision suffix, bounded slug retained | test_session_collisions, test_slugged_session_and_latest_selection |
| Empty Gemini candidates caused crash or empty success | Provider-specific error for missing/empty/unusable content | test_empty_provider_responses |
| Missing original dice demonstration | Hand-written Tool, random dice, event printing, allow callback and original task restored | test_dice_demo |
| SSH option-like components | Connection-token validation and strict host-key verification | test_ssh_rejects_option_injection, remote backend tests |
| Docker client timeout left container running | Bounded removal using exact generated container name; unconfirmed cleanup reported | test_docker_timeout_removes_exact_container |

These repairs predate this chat and were not reimplemented. Existing thought-signature
round-tripping, valid text/function calls and missing usage defaults pass offline tests.
Frozen-time session tests create independent records, confirm unique paths and retained
contents, and explicitly set modification times to check latest selection. latest()
continues to mean most recently modified; exact mtime ties have no defined ordering.

## Changes implemented in this chat
1. Provider errors previously embedded raw HTTP bodies and network exception strings.
   Those may echo API keys or request URLs; chained tracebacks could also expose them.
   Errors now retain status/retry context without untrusted details and suppress original
   exception display. Mocked HTTP 400, HTTP 503 and URL errors verify that formatted
   tracebacks do not contain a fixture secret.
2. Provider parsing assumed candidate, content, parts and individual parts had expected
   types. Non-dictionary candidates, malformed parts, numeric text and incomplete function
   calls could raise unrelated errors. Parsing now skips malformed entries and raises
   the existing clear Gemini error when nothing usable remains.
3. Docker image configuration accepted an option-like image token, and user=None,
   root or 0:0 disabled the intended non-root boundary. Configuration now refuses these
   values and ambiguous comma-containing mount paths. Normal defaults remain accepted.
   This tightens intentionally unsafe configuration rather than changing valid Tool APIs.

Added tests/test_final_boundaries.py with three regression methods covering multiple
HTTP/network errors, five malformed candidate shapes and six invalid sandbox settings.
No existing tests were removed or rewritten. Standard library only.

One initial regression run failed because Windows denied cleanup of a default system
temporary directory. The test now uses the repository work/ directory, consistent with
the existing suite. Subsequent complete runs passed.

## Actual verification
- python -m unittest discover -v: 68 discovered, 67 passed, 0 failures, 1 skipped.
- Symlink escape test skipped: Windows privilege error 1314. It was not counted as passed.
- python -m sudarshan --help: succeeded.
- git diff --check and staged diff check: succeeded.
- git check-ignore .sudarshan/sessions/test-session.jsonl: returned the expected path.
- Dice demonstration imports and mocked execution pass.
- Full verbose test transcript delivered separately as test-results.txt.
- Relevant provider and sandbox checks were run before the implementation commit.
- Credential preflight examined presence only; no actual credentials were printed.

## Execution backend review and security limits
Local file operations resolve traversal and symlink targets; tests cover traversal.
Resolve/open races remain. Local shell cwd is not confinement: commands can access
anything the OS account can. Timeout does not guarantee termination of descendants.
The LocalExecutionBackend uses an environment allowlist; the separate core bash tool
still inherits the parent environment, so arbitrary approved commands can read its
credentials. Custom Python tools are trusted application code.

SSH uses strict host-key checks, batch authentication, argument lists and quoted remote
helpers. Tests are mocked. Remote cwd is not a sandbox; remote process termination
after disconnect or timeout is not guaranteed. No live SSH host was exercised.

Docker uses network none, read-only root, dropped capabilities, no-new-privileges,
non-root defaults, CPU/memory limits, a bounded tmpfs, and one workspace mount.
There is no local fallback. Timeout cleanup is tested with mocks only.
Docker is not an absolute guarantee: shared kernel, daemon privileges, unsafe workspace
contents, administrator-selected images and cleanup/runtime failures remain relevant.
Configuration checks do not prove the image's named user resolves to a nonzero UID.
Only trusted application configuration should select images, users and workspace roots.
No live Docker invocation was run.

Policy inspection is conservative and incomplete. Quotes, rm flag permutations,
requested root/home variants and existing dangerous patterns have regression coverage,
but regexes and shlex cannot prove arbitrary shell programs safe. Shell expansion,
nested interpreters and platform-specific syntax remain limitations. Use OS isolation
for untrusted commands. Direct backend methods require caller policy enforcement.
Custom tool identity protections are applied through Harness registration; Policy alone
cannot authenticate a Python callable from a name supplied by an arbitrary caller.

## Product fleet readiness
Inspected existing runner and its uncommitted orchestration regression. Separate project
directories, per-project skills, persistent parent sessions, same-session review,
separate build/review fleets, skill-loading evidence, assistant event counts and ordered
results are covered by the offline orchestration test. Child Harness construction has
persist=False coverage; this runner currently disables subagents.
Existing output directories cause refusal rather than overwrite.

Credential preflight: none of SUDARSHAN_API_KEY, ODYSSEUS_API_KEY or GEMINI_API_KEY
is configured in this process. Running python -m demos.product_fleet actually failed
at this preflight, before creating projects. Default model in source is
gemini-3.1-pro-preview; an explicit model or legacy ODYSSEUS_MODEL can override it.
Provider availability of that model was not verified.

| Product | Live build turns | Live review turns | Independent product verification |
| --- | ---: | ---: | --- |
| artisan-coffee | 0 | 0 | Not built or verified |
| taskman | 0 | 0 | Not built or verified |
| viper | 0 | 0 | Not built or verified |

No browser layout/control checks, visible-word counts, SVG counts, Taskman generated
tests or Viper gameplay checks were performed because products were not generated.
The runner explicitly leaves independent acceptance undetermined; automated independent
product acceptance and further review/repair passes remain outstanding.
Offline orchestration fixtures are not live product evidence.

## Git milestones
Existing history includes c3a65c8 (read classification), a7f08de (command detection),
0845b73 (API keys), ba567cf (collisions), fdfee7f (empty candidates),
968d4c8 (runtime boundaries and dice), b829b1b (custom overrides).
This chat: c685647 — fix: protect provider errors and sandbox configuration.
A subsequent documentation commit records this report. No push or force push performed.

## Acceptance status
Implemented: additional provider and sandbox repairs above.
Tested: offline harness, provider, session, policy, mocked execution backends and fleet orchestration.
Verified against real provider: nothing in this chat.
Not tested: live Gemini, SSH, Docker, generated products and browser interactions.
Known security limitations: shell analysis, host-account access, process cleanup,
filesystem races and container/runtime trust described above.
The full requested objective remains incomplete until credentials and provider access
allow real builds, reviews, independent product verification and any needed repairs.
Passing this suite is not a production-readiness certification.

