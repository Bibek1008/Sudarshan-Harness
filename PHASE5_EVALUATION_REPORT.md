# Phase 5 evaluation implementation report

## Repository and scope

- Repository: Bibek1008/Sudarshan-Harness, actual clone `publish-clone`.
- Branch: `phase-5-agent-evaluation`.
- Base: `d07a31bd0eae40dd4cd3bc16fe699f67dbf53036` (Phase 4 branch tip).
  Phase 4 core implementation `3da412c301ad82278dd5bd489eeb4483f1bbc1de`
  is included. Main reference inspected was
  `559ba80ac3e5062e337377edc779603cf825c88d`; no changes were made to main.
- Origin: https://github.com/Bibek1008/Sudarshan-Harness.git.
- Working tree was clean before implementation. No existing work was discarded.
- This change is committed locally only. No push, merge or hosted run was performed.

Reviewed Harness, loop, provider, telemetry, session, tools, policy, filesystem and
process execution primitives, CLI, relevant tests and existing CI. Reused Harness,
Policy, WorkspaceFiles, owned-process execution and Phase 4 metadata storage rather
than replacing the architecture. No dependencies were added.

## Implemented behavior

- Dedicated evaluation package: validated task contracts/registry, immutable fixture
  and verifier source snapshots, versioned fingerprints, clean per-trial workspaces,
  independent verification, repeated trials, bounded results, scoring and comparison.
- Ten core v1.0.0 tasks: slug, ledger, median, tests, ranges, port, config, orders,
  unique and csv. They cover the ten requested categories, with three criteria each.
- Agent execution uses a credential-filtered isolated Python bootstrap and existing
  owned-process management. Hidden checks are absent from the agent workspace and
  model messages. Declared artifacts are validated/snapshotted for a separate verifier.
- Safe mode is preserved. Effects are denied by default; explicit workspace-edit
  approval allows only confined write/edit tools. Shell and subagents remain denied.
- Loopback model broker keeps API-key resolution in the parent process; it fixes the
  selected model, uses a random capability, bounds requests/output and propagates
  retries without provider error bodies. Provider requests/backoff respect trial
  deadlines; retries count actual subsequent attempts.
- Execution and verification outcomes are recorded separately. Infrastructure errors
  remain inconclusive/verifier_error; agent claims cannot produce success.
- Task-weighted rates, first-repetition success, category metrics, criterion/artifact
  diagnostics, durations, tool/request counters, retries, token coverage and optional
  Phase 4 cost provenance. Unknown measurements stay null. Partial telemetry cannot
  create complete count averages; observed token subsets have per-field coverage.
- Comparison checks definitions, engine source, commit, policy, prompting, limits,
  repetitions, provider/mode, OS and Python. Mismatches suppress success deltas;
  variation is descriptive and statistical significance is not established.
- CLI list/show/dry-run/explicit live/report/compare/JSON export. Live mode requires
  an explicit model and prints budgets, policy and paid/quota warning before calls.
- Schema-v1 atomic metadata results under ignored `.sudarshan/benchmarks/`, strict
  corruption/content checks, UUID identities, 2 MiB bounds, cross-process locking and
  retention of generated result/report files. No transcripts or raw outputs stored.
- Existing CI matrix is preserved (Windows/Ubuntu, Python 3.10/3.12) and push trigger
  includes this branch. No secrets were added to CI and no live evaluations run in it.

## Executed validation

Environment: Windows AMD64, Python 3.12.10.

| Validation | Observed result |
| --- | --- |
| `python -m compileall -q sudarshan demos tests` | Exit 0 |
| `python -m unittest discover -v` | Ran 342 tests in 68.377s; OK (skipped=13) |
| New evaluation regression tests | 50 passed, no failures/skips |
| Full-suite successful test lines | 330 passed; zero failures/errors |
| `python -m sudarshan --help` | Exit 0; benchmark entry point shown |
| Benchmark list/show core | Exit 0; core suite has ten versioned tasks |
| Core CLI dry-run | Exit 0; model_requests_made=0, no execution/storage |
| Scripted ten-task end-to-end test | 10/10 independently verified; mode=mock |
| Independent verifier/telemetry/reporting/comparison tests | Passed in full suite |
| Separate mocked CLI lifecycle smoke | Correct slug passed; claim-only invalid_output; report rendered; JSON export round-tripped; fair comparison delta=-1 |
| `git diff --check` | Exit 0 |

Unittest accounting: 342 is testsRun. Twelve individual tests were skipped and a
Docker class-setup skip was reported separately, producing displayed skipped=13;
330 individual successful test lines were observed. This explains the arithmetic.

Skip reasons (retained, not substituted for unexpected failures):

- Five POSIX-only tests: process-group use, O_NOFOLLOW swap handling and three live
  descriptor tests require POSIX.
- Six symlink tests: Windows symlink creation privilege unavailable (WinError 1314).
- One POSIX permission-bit test: Windows uses inherited ACLs.
- One class-setup skip: live Docker integration opt-in flag was not set. No live
  Docker security verification was performed. SSH integration remains unverified.

The default execution environment initially denied localhost socket binding
(WinError 10013). Broker tests were rerun with approved process permissions and
passed with real localhost transport and mocked provider completions. No application
security control was disabled and no unexpected failure was converted into a skip.
Full-suite output is local/ignored at `ci-results/phase5-final.log`.

All model responses and usage metadata used in tests/smoke runs were synthetic.
The ten-task result demonstrates evaluator plumbing, not real model capability.
Real Gemini calls: zero. Live model benchmarks: zero. Real pricing lookups: zero.
No `.env` or credential contents were inspected or committed. Synthetic sentinel
tests cover credential exclusion, raw-error rejection and content-free result schemas.

## Fixes verified during implementation

- Count averages now remain null when any trial has missing/partial telemetry;
  regression test also checks token subset coverage.
- Provider deadlines bound transport/backoff; retry metadata survives failed broker
  requests without exposing raw errors. Deadline tests use mocked network calls.
- Fixture/verifier snapshots prevent mutable source files changing subsequent
  repetitions. Engine fingerprints detect source edits during execution.
- Malformed worker/verifier/result data cannot assert a passing task; corrupted
  saved results are preserved and rejected. Atomic-write failure cleanup is tested.
- Planned versus attempted trial counts identify interrupted/incomplete comparisons.

## Remaining limitations and work

- Temporary workspaces, handle-based tool restrictions and owned subprocesses are
  application protections, not OS isolation. Generated Python runs with the host
  account's rights; hostile code could access host resources or influence assertions
  in its verifier interpreter. Use only the controlled harmless tasks. Public hidden
  checks are not private external holdouts and are not an anti-cheating guarantee.
- Worker/verifier environment inheritance excludes API keys, but host-account file
  access and local service access are not blocked by a separate security boundary.
  Windows ACLs are inherited; process groups on POSIX cannot contain deliberate
  session escapes. This implementation does not assert otherwise.
- Parent provider requests can remain in flight or incur billing after cancellation;
  urllib/DNS cancellation is not a hard containment guarantee. Abrupt process/power
  loss can leave scratch or atomic-write temporary files. Normal cleanup is tested.
- Run/report writes are individually atomic, not a two-file transaction. The run is
  authoritative; the cached report is derived. Local JSON is validated, not signed.
- Partial/missing telemetry limits resource comparisons; unavailable pricing yields
  no cost estimate. Synthetic usage/cost tests do not establish provider billing.
- No Ubuntu, Python 3.10 or hosted Phase 5 CI results were produced locally. Those
  matrix jobs remain pending a separately authorized push. Docker/SSH remain as
  described above; no personal server or credentials were used.
- No real model capability, cost-savings or statistically significant superiority
  claim is supported. Real evaluations need separate explicit approval and valid
  account/model configuration; stronger isolation and holdouts need future work.

Architecture, task authoring, formulas, usage, privacy and limitations are documented
in `docs/EVALUATION.md`. The changed-file manifest follows below.

## Changed files (49)

- `.github/workflows/cross-platform.yml`
- `PHASE5_EVALUATION_REPORT.md`
- `README.md`
- `benchmarks/core/fixtures/config/settings.py`
- `benchmarks/core/fixtures/csv/README.md`
- `benchmarks/core/fixtures/ledger/README.md`
- `benchmarks/core/fixtures/median/solution.py`
- `benchmarks/core/fixtures/orders/orders.py`
- `benchmarks/core/fixtures/port/README.md`
- `benchmarks/core/fixtures/ranges/test_public.py`
- `benchmarks/core/fixtures/slug/README.md`
- `benchmarks/core/fixtures/tests/solution.py`
- `benchmarks/core/fixtures/unique/solution.py`
- `benchmarks/core/suite.json`
- `benchmarks/core/tasks/config.json`
- `benchmarks/core/tasks/csv.json`
- `benchmarks/core/tasks/ledger.json`
- `benchmarks/core/tasks/median.json`
- `benchmarks/core/tasks/orders.json`
- `benchmarks/core/tasks/port.json`
- `benchmarks/core/tasks/ranges.json`
- `benchmarks/core/tasks/slug.json`
- `benchmarks/core/tasks/tests.json`
- `benchmarks/core/tasks/unique.json`
- `benchmarks/core/verifiers/checks.py`
- `docs/EVALUATION.md`
- `sudarshan/cli.py`
- `sudarshan/evaluation/__init__.py`
- `sudarshan/evaluation/broker.py`
- `sudarshan/evaluation/cli.py`
- `sudarshan/evaluation/comparison.py`
- `sudarshan/evaluation/metrics.py`
- `sudarshan/evaluation/models.py`
- `sudarshan/evaluation/registry.py`
- `sudarshan/evaluation/reporting.py`
- `sudarshan/evaluation/runner.py`
- `sudarshan/evaluation/scoring.py`
- `sudarshan/evaluation/verifier.py`
- `sudarshan/evaluation/worker.py`
- `sudarshan/provider.py`
- `tests/benchmark_examples.py`
- `tests/evaluation_samples.py`
- `tests/test_benchmark_broker.py`
- `tests/test_benchmark_cli.py`
- `tests/test_benchmark_reporting.py`
- `tests/test_benchmark_runner.py`
- `tests/test_benchmark_scoring.py`
- `tests/test_benchmark_verifier.py`
- `tests/test_evaluation.py`
