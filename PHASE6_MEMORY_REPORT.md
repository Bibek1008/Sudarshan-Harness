# Phase 6 — Project memory and context improvements

Validated on Windows / Python 3.12 on 2026-11-02. Standard library only;
no vector database, external memory service, or new Python dependency.

## Repository and scope

- Actual Git root: `publish-clone` within the supplied workspace. The neighboring
  `Sudarshan-Harness-main` directory is a source copy without Git metadata.
- The starting working tree was clean on `phase-5-agent-evaluation`.
- Local `main` was `559ba80` and did **not** contain
  `e971459c2226aca0f419bd78e07b20ed31d45f12`.
- Created `phase-6-project-memory` from that Phase 5 commit, preserving the
  Phase 4 observability and Phase 5 evaluation history. Main was not modified.
- Inspected memory, context, harness, sessions, skills, path confinement, policy,
  provider/telemetry integration, and their regression tests before implementation.
  Sessions and skills retain their existing storage formats and boundaries.
- Phase 7 final polish is outside this change and has not been started.

## Features

- Human-editable `SUDARSHAN.md`, with backward-compatible unsectioned bullets.
  Optional sections cover purpose, architecture, directories/modules, conventions,
  build/tests, dependencies, decisions, known limitations, and development history.
- Case/whitespace-normalized duplicate detection; explicit, unique bullet updates
  and deletion using `replaces`. Ambiguous and multiline changes are refused.
  Replacing with an already-saved fact removes only the outdated bullet.
  Surrounding prose and unrelated facts are preserved rather than regenerated.
- Sectioned writes and corrections record update dates. Optional verification
  dates are explicit evidence claims; dates cannot be in the future.
- Project identity is the resolved configured working directory. There is no
  parent traversal or sibling-memory search: use the same project-root `-d`
  across sessions. This preserves the existing permitted workspace boundary.
- Retrieval ranks whole facts by task overlap, verification/update dates, and
  file order; duplicate retrieved facts are suppressed. Core project sections
  and legacy unsectioned facts stay eligible, while other sections need overlap.
- Storage is bounded to 64 KiB, with oversized writes refused without truncation.
  Prompt memory is bounded to 4,800 characters by default; Harness further limits
  it to one eighth of its configured context budget using character estimates.
- Memory refreshes before provider turns, later tasks, and the turn-limit wrap-up.
  Memory is not copied into the durable transcript as a new user message.
- System prompt estimates are reserved before transcript compaction. The original
  task is pinned separately from generated summaries, recent tool interactions
  remain paired, and summary input preserves complete text and tool arguments
  instead of silently truncating each message after 1,000 characters.
- Existing provider and telemetry paths remain in use for compaction. Estimates
  never become measured usage; missing provider usage remains unavailable.
- Cooperating threads/processes use an exclusive writer lock and atomic file
  replacement. Failed replacement preserves the original and cleans temporary
  files. A busy/stale lock times out rather than being stolen.
- Missing memory is normal. Harness skips corrupt/unreadable memory with a safe
  notice, preserving its bytes. Direct APIs fail explicitly. Escaping metadata
  paths remain errors.

## Files changed

| File | Change |
| --- | --- |
| `sudarshan/memory.py` | Safe Markdown mutations, locking, atomic replacement, retrieval and bounds |
| `sudarshan/context.py` | System-text estimator, original-task pinning, complete compaction input |
| `sudarshan/harness.py` | Bounded memory refresh, budget reservation, update/removal tool arguments |
| `sudarshan/loop.py` | Optional callable system prompt, retaining ordinary string support |
| `tests/test_project_memory.py` | 27 focused regression tests using temporary projects |
| `README.md` | Phase 6 usage, safety, limits and recovery instructions |
| `.gitignore` | Exclude memory locks and temporary files |
| `.github/workflows/cross-platform.yml` | Include the Phase 6 branch in existing hosted CI triggers |
| `PHASE6_MEMORY_REPORT.md` | This report |

## Validation

No real Gemini API requests were made. Provider responses in tests were mocked;
the benchmark dry-run explicitly reported `model_requests_made: 0`.

| Check | Result |
| --- | --- |
| `python -m compileall -q sudarshan demos tests` | Passed |
| `python -m unittest discover -v` (final, local networking permitted) | 369 run: 355 passed, 14 skipped, 0 failures/errors |
| `python -m unittest tests.test_project_memory -q` | 27 run: 26 passed, 1 skipped |
| `python -m unittest tests.test_observability tests.test_evaluation -q` | 51 run: 50 passed, 1 skipped |
| `python -m unittest tests.test_benchmark_broker -v` (loopback permitted) | 6 passed |
| `python -m sudarshan --help` | Passed |
| `python -m sudarshan benchmark run core --dry-run` | Passed; zero model requests |
| `git diff --check` | Passed |

The first sandboxed full run had two failures and two errors in existing broker
tests because Windows denied loopback sockets (`WinError 10013`). Those tests
passed with local networking permitted, followed by the successful final full
run. The tests and security policy were not weakened to hide these failures.

The final full suite's 14 skips comprise seven symlink tests without Windows
symlink privileges, five POSIX-only tests, one POSIX-permissions test, and the
optional live Docker test class (opt-in not enabled). These are not passes.
Linux/Python 3.10 results and live Docker results are not claimed here; the
existing hosted Windows/Linux matrix is enabled for the feature branch.

## Security checks

- Memory-tool writes reject recognizable credential assignments, bearer tokens,
  common API key/private-key/JWT formats, credential-bearing URLs, and common
  personal identifiers. Rejected values are not echoed in confirmations/errors.
  Sensitive existing entries/headings are omitted from retrieval without rewriting
  the user's original file.
- No automatic project-file, `.env`, conversation, or personal-data extraction.
  A regression asserts that memory initialization opens only `SUDARSHAN.md`.
- Memory is explicitly reference data; untrusted file contents do not grant
  authority to change instructions or save facts. Remember/update/remove retain
  the normal safe/read-only policy checks. There is no new trusted read-tool name.
- Workspace path checks also cover memory and lock symlinks. Symlink tests are
  present but skipped locally due to missing Windows privilege.
- Corrupt UTF-8, binary NUL content, oversized memory, ambiguous replacements,
  metadata/newline injection, stale locks, and interrupted atomic replacement
  have non-destructive regressions.
- Concurrent thread and process tests verify no lost facts and no duplicate
  cooperating writes. The repository's original sessions/security/evaluation/
  telemetry regression coverage continues to pass.
- Only the explicitly listed implementation, test, workflow and documentation
  files are intended for the commit. Test workspaces, logs, runtime state,
  credential files and memory lock/temp files are excluded.

## Remaining limitations

- Retrieval uses simple word overlap, not semantic search. Synonyms may miss
  relevant optional sections. Core/legacy facts can still compete for limited
  space, and oversized individual facts are omitted intact. Dates are writer
  claims, not independently verified truth. Contradictions need explicit updates.
- The configured directory is the project root; nested launches deliberately
  do not inherit parent memories. No global memory or automatic Git-root discovery.
- Credential/identifier detection is conservative pattern matching, not proof
  that arbitrary prose contains no secret. False positives are possible. Generic
  approved write/shell tools and manual editors retain their existing powers;
  `yolo` is not an isolation or prompt-injection security boundary.
- Manual editors do not participate in the cooperative lock. A crash can leave
  a stale lock that needs inspection/removal. Power-loss durability and hostile
  simultaneous filesystem replacement are not guaranteed. Existing resolve/open
  race limitations remain; no new OS sandbox is claimed.
- The transcript budget remains a soft compaction trigger, not a hard provider
  token/window limit. Recent tool groups, original constraints, complete summary
  input, and provider-generated summaries can exceed tiny budgets; tool schemas
  are not counted by the character estimator. Compaction quality still depends
  on the provider, while original task text remains pinned deterministically.
- Complex multiline/fenced Markdown should be edited manually. A memory file
  already exceeding 64 KiB must be reduced manually before API updates resume.

The feature branch is intended for review and push only. No merge to main and
no Phase 7 implementation are part of this work.
