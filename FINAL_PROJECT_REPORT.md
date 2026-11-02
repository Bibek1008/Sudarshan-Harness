# Final project report — Phase 7

## Scope and provenance

The final planned milestone starts from merged main
`727d712bdd41372523f8b628d4e9a06f638edef3`, containing Phases 1–6 and Phase 6
commit `c3abda43dbf99a83a823045b88b217a64ede0ea0`.
Work is isolated on `phase-7-final-polish` in the actual `publish-clone` Git
repository. The cleanup audit was committed before deletion as `6d7d4ac`.
No neighboring source copy is changed. Main is not modified by this milestone.

The work covers repository hygiene, small CLI usability/error improvements,
installation/configuration guidance, current security documentation and final
integration verification. Existing architecture and dependencies remain intact.

## Preserved integration

| Boundary | Final behavior and regression coverage |
| --- | --- |
| Provider and loop | Neutral messages, call order, thought signatures, retries and tool-free turn-limit report |
| Tools and policy | Safe default, explicit effects, exact read trust, path checks and permanent denials |
| Execution | Secure file primitives, owned processes, filtered environments, strict SSH, constrained Docker |
| Memory and context | Project-local Markdown, safe corrections/removal, bounded retrieval, original-task pinning and paired recent tools |
| Sessions | Durable JSONL, torn-tail/interrupted-call repair, same-workspace resume, one writer per log |
| Telemetry | Local metadata-only events; actual usage remains distinct from estimates and unavailable fields |
| Evaluation | Versioned public fixtures, independent verification, bounded workers/broker and explicit live opt-in |
| Examples | Standalone Taskman, teaching demos and optional product/browser verification retained |

No public module or regression test was removed. The cleanup removed confirmed
unused imports rather than replacing working implementations. See the
[cleanup report](docs/CLEANUP_REPORT.md) for individual-file safeguards and retained
historical material, and [release notes](RELEASE_NOTES.md) for user-visible changes.

## Validation

Before cleanup on Windows/Python 3.12: `python -m unittest discover -v` ran
369 tests in 56.290 seconds: **355 passed, 14 skipped, zero failures/errors**.
Local loopback networking was permitted for mocked benchmark broker tests.

After cleanup and the reproduced NTFS lock-race repair, the final local full
suite ran **380 tests in 55.634 seconds: 366 passed, 14 skipped, zero failures or
errors**. Compilation and CLI help passed. Benchmark dry-run reported zero model
requests, and provider-free stats completed. Markdown links, Git whitespace,
tracked/planned filenames, recognizable credential values and non-fixture email
addresses were checked without opening credential files. No real Gemini request
was made by these release checks. Hosted CI results are recorded below once run.
First-run missing-credential handling uses an empty test environment and a blocked
network mock. Existing scripted tests cover safe coding, multi-file creation,
debugging, sessions, memory, telemetry and independent benchmark verification;
these checks do not establish live model quality.

The 14 local skips are seven symlink checks without Windows privilege, five
POSIX-only checks, one POSIX-permissions check and the opt-in live Docker class.
The earlier post-cleanup 377-test run failed one existing concurrent-memory test;
it was investigated rather than counted as a pass. NTFS transiently resolves a
delete-pending lock into its internal deleted-file location and can deny its
replacement. The focused repair retains exclusive creation and link/path checks,
resolves only the stable parent, validates memory while locked and bounds Windows
retries. Three new regressions passed, followed by an 80-iteration/2,560-write
stress check with no loss or duplicate facts and the successful final full run.

The other eight added regressions cover CLI error/first-run behavior and ignore
boundaries. Existing safe coding, multi-file, debugging, session, memory, telemetry,
benchmark and security coverage remains intact. No regression was deleted or
reclassified to make validation pass.

### Hosted CI

The existing four Windows/Ubuntu Python 3.10/3.12 jobs and separate Ubuntu Docker
job are enabled for `phase-7-final-polish`. Execution and job results will be
linked after the reviewed source commit is pushed. No live Gemini request is
part of that workflow.

## Repository layout

```text
.github/workflows/    Hosted Windows/Ubuntu and optional-runtime validation
benchmarks/          Versioned definitions, public fixtures and verifiers
demos/               Teaching and product-verification examples
docs/                Getting started, security, observability, evaluation, cleanup
scripts/             CI validation entry point
skills/              Workspace skill example
sudarshan/           Provider, loop, policy, tools, context, memory and state
  execution/         Local, SSH and Docker backends with shared primitives
  evaluation/        Benchmark orchestration, broker, verification and reports
taskman/             Standalone demonstration CLI
tests/               Existing coverage plus focused release regressions
README.md            Overview and current documentation entry points
RELEASE_NOTES.md     Final milestone changes and compatibility
*_REPORT.md, AUDIT.md and other historical reports retained at the root
```

Local caches, validation logs and `.sudarshan` stores stay ignored. Historical
root reports remain in place to preserve existing links. No credential or runtime
session/telemetry content is intended for the commit. Filename and recognizable
secret-value checks passed before publishing the feature branch; arbitrary-secret
discovery is not claimed. Synthetic security fixtures and reserved example-domain
SSH/user identifiers are retained as regression coverage.

## Remaining issues and completion boundary

See [security limits](docs/SECURITY.md) for authoritative current caveats. In
particular, safe approval is not OS isolation; Windows ACLs are inherited; local
filesystem races and hostile same-account programs remain possible; live SSH
process lifetime is not certified; secret detection is heuristic; memory locks
may need stale-lock recovery; and context budgeting is a soft character estimate.

There is no bundled model pricing or automatic model-availability lookup. No live
Gemini benchmarking, product build, real-world acceptance, or personal SSH test
was run. Optional/platform-specific skips remain visible. Python 3.10 and Ubuntu
results require the hosted matrix, rather than being inferred from local Windows.

This feature branch is committed/pushed for review, with no automatic merge to
main. After successful review and an approved merge, planned development is
complete: use Sudarshan for personal work and make maintenance fixes as needed.
No additional development phases are planned.
