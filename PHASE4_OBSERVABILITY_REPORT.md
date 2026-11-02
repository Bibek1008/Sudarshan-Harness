# Phase 4 — observability, token accounting and diagnostics

## Repository and scope

Actual clone: Bibek1008/Sudarshan-Harness, starting from verified main commit
559ba80ac3e5062e337377edc779603cf825c88d. Work is on phase-4-observability.
Main and the remote are not modified by this phase. The pre-existing untracked
publish-validation.log is preserved and excluded from staging. No .env or credential
file was read. No live Gemini request, pricing lookup, Docker test or SSH connection
was made in this phase. The earlier hosted Phase 3 results do not validate this
new observability code on Ubuntu; Linux/Python 3.10 verification remains pending.

The implementation plan reused provider/loop/Policy/Harness/context boundaries,
preserved the existing transcript callbacks and session file format, and added a
separate fixed-schema metadata collector, local diagnostics and regression tests.
Execution restrictions, subprocess ownership and file security behavior are unchanged.

## Implemented

- Version 1 events for session lifecycle, logical model requests, failed requests,
  retries, tool lifecycle, safe-mode approvals, denials, compaction, completed turns
  and timeouts. Opaque UUID session/request/call/event identities, UTC timestamps,
  monotonic durations, model/backend labels, status and categorical errors are used.
- Metadata is explicitly validated: no prompts, arguments, responses, signatures,
  commands, file contents, exception messages or unknown payload fields are accepted.
  Trace readers reject injected/invalid records rather than echoing their contents.
- Gemini extracts input/output/total/thought/cache counts from actual usageMetadata.
  Missing/malformed values remain null. The additive usage_details result carries
  availability, while the old usage interface and neutral callbacks remain compatible.
  Character-based context estimates never enter actual token accounting.
- Retries are correlated to one logical request. Only successful reported usage is
  aggregated; event/request IDs are deduplicated. Failed attempt usage/billing stays
  unknown. Compaction requests are independently accounted for.
- Cost estimation uses only explicit user-supplied per-model rates, currency, source,
  date and thought billing policy. Cached input is not charged twice. Invalid/missing
  pricing makes cost unavailable without disabling other metrics. Decimal arithmetic
  is used. Estimates are never labeled actual billing; no prices are bundled.
- Session summaries include timing/status, turns, requests/retries, per-field measured
  token coverage, cost, tool outcomes and timeouts. Cross-session aggregation respects
  unavailable costs and currency differences. Retained-data partial reports are marked.
- JSONL append/fsync uses a cross-process lock with bounded waits. Events rotate into
  bounded segments with bounded recent-session retention. Completed summaries use
  atomic snapshots; diagnostics recomputes from validated retained events. Corrupt
  records are counted/skipped without silently rewriting them. Normal failed summary
  writes clean up their unique temporary files.
- POSIX modes are restrictive on creation; Windows uses inherited ACLs. Telemetry is
  already ignored by .sudarshan/. Settings support persistent opt-out and retention;
  library/CLI hard opt-out avoids starting the collector.
- stats/trace/telemetry CLI routes support human/JSON output and session/last filters
  without constructing a model. Original interactive, headless and resume paths remain.
- Tool.execution_backend is additive diagnostic metadata. Core tools identify local,
  backend adapters identify their actual backend and ordinary custom tools default to
  in_process. No inference from an arbitrary tool prefix is needed.

## Verification actually executed

Environment: Windows 11, Python 3.12.10.

- `python -m compileall -q sudarshan demos tests`: completed, exit 0.
- `python -m unittest discover -v`: Ran 289 tests in 48.254 seconds;
  OK (skipped=16), zero failures/errors.
- There are 275 successful test records and 14 skipped test methods. Two additional
  class-setup skips are included in the displayed skipped=16 but not testsRun.
- `python -m sudarshan --help`: completed, exit 0; diagnostics and opt-out flags shown.
- The observability suite adds 44 tests. Its last standalone run before the final
  backend-identity regression ran 43 tests successfully (one platform skip); the
  complete run above includes all 44 tests and the existing suite.

Behavior verified with realistic mocked model/provider responses includes:
successful sessions, multiple tools, safe approval, denial without execution,
timeout exceptions, failed model requests, an HTTP 429 followed by a successful
response, exactly-once successful usage, interrupted sessions, missing usage,
malformed usage/pricing, costs/cache/thought policies, mixed currencies, compaction,
existing transcript recovery, CLI stats/trace/JSON/toggles and disabled mode.

Actual local filesystem/process tests verify eight-thread event writing, three
independent Python writer processes with native Windows file locking, torn-tail
append, corruption preservation, single/multiple segment rotation, session retention,
atomic-write failure cleanup, and safe agent continuation on telemetry storage failure.
Privacy fixtures assert sentinel prompts, responses, arguments, signatures, file
contents, tool outputs and synthetic secrets never appear in telemetry files.
All generated event/pricing/settings fixtures live in TemporaryDirectory workspaces.
The only tracked pricing data is explicitly fake test-fixture data, not real rates.

## Skips and limitations

The existing 15 local skip records remain: unavailable secure Chromium class setup,
POSIX-only methods on Windows, missing Windows symlink/hardlink/junction privileges,
and the opt-in live Docker class. The new 16th skip is the POSIX permission-mode
assertion on Windows, where ACL semantics apply. Linux telemetry locking/permissions,
Python 3.10 observability behavior, live Gemini usage and provider billing are not
verified in this phase. Hosted CI has not been triggered because no push is requested.

Retention is intentionally finite: counts cover valid retained records, not lifetime
billing. Rotation or corruption marks summaries partial and suppresses full-session
cost. Failed/unreceived requests may incur unknown provider costs; estimates cover
successful reported responses only. Optional cache/thought fields must be available
before estimating cost; absent fields are not assumed zero. A configured pricing
source/date is provenance, not a guarantee that rates are current. Currency conversion
is not attempted. Request estimates retain their pricing source/date in event records.

Each Harness.run has a fresh telemetry UUID, including resumed agent transcripts;
children have independent telemetry sessions, aggregated by stats rather than charged
to their parent twice. Persist=False defaults to no telemetry unless explicitly
enabled; children inherit the parent setting. Settings changes take effect for the
next collector, not halfway through an active session. Telemetry disable does not
disable or erase existing conversation transcript persistence or legacy callbacks.

Native locks serialize cooperating writers, not hostile processes. Metadata paths
are checked for escapes/links but not a complete TOCTOU sandbox against a hostile
filesystem owner. Windows ACL hardening is not implemented. Normal failed writes
clean temporary files, but abrupt OS crashes can leave temporary snapshots requiring
manual cleanup. Append and summary snapshots are not a two-file transaction; summaries
are treated as caches and never authoritative. Power-loss durability of directory
metadata is not guaranteed. Large manual/untrusted files are outside the guarantees
on collector-generated file sizes. No age-based cleanup or external telemetry service
is introduced.

Public model/tool/provenance identifiers must not contain secrets. Arbitrary custom
tool strings use existing ERROR/BLOCKED conventions and cannot always be classified
perfectly. Storage failure flags are exposed to callers; raw storage errors are not
logged. No full OS isolation, universal secret discovery, actual Google invoice
reconciliation or unbounded historical analytics is claimed.

## Changed files

- New `sudarshan/telemetry.py`: schema, usage/cost helpers, storage, summaries, collector.
- `sudarshan/provider.py`: additive usage_details and retry metadata hook.
- `sudarshan/loop.py`: model/tool/turn timing and lifecycle hooks.
- `sudarshan/context.py`: compaction request accounting and compaction event.
- `sudarshan/harness.py`: run-scoped collector, status, opt-out and child inheritance.
- `sudarshan/security.py`: metadata-only requested/granted approval hooks; same decisions.
- `sudarshan/tools.py`, `sudarshan/execution/base.py`: optional backend identity metadata.
- `sudarshan/cli.py`: stats/trace/settings and hard opt-out.
- New `tests/test_observability.py`: 44 regression/privacy/reliability tests.
- `tests/test_provider_audit.py`: validates additive usage_details while retaining old assertions.
- New `docs/OBSERVABILITY.md`, this report, and README.md documentation link.

No generated telemetry/session/pricing files or validation logs are staged. Existing
Git history is preserved. Completion is a local commit on phase-4-observability;
there is no automatic push or merge.
