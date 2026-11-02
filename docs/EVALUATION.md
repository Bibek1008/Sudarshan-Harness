# Agent evaluation and benchmarking

For installation and provider-free first checks, see [Getting started](GETTING_STARTED.md).
Current [security limits](SECURITY.md) and [release validation](../FINAL_PROJECT_REPORT.md)
apply alongside this evaluation-specific protocol. Phase 5 results remain
historical engineering evidence, not live model-performance measurements.

The evaluation package measures controlled software-engineering tasks with independent
verification. It reuses Harness, safe Policy, Phase 4 telemetry, workspace file
primitives and the owned-process runner. It does not replace the agent loop.
Everything uses the Python standard library. No live evaluation runs automatically.

## Entry points

```console
python -m sudarshan benchmark list
python -m sudarshan benchmark show core
python -m sudarshan benchmark run core --dry-run
python -m sudarshan benchmark run core --dry-run --task slug --runs 3
python -m sudarshan benchmark report RUN_UUID
python -m sudarshan benchmark export RUN_UUID --json
python -m sudarshan benchmark compare FIRST_UUID SECOND_UUID
```

Use -d WORKDIR on run/report/export/compare. Dry-run, listing, reporting, export and
comparison do not instantiate a model provider or make API requests. Run requires
exactly one of --dry-run or --live. Invalid identifiers and corrupt data produce
bounded generic errors without echoing private values or raw outputs.

Only after separately authorizing paid/quota-consuming requests, a user may run:

```console
python -m sudarshan benchmark run core --live --model YOUR_GEMINI_MODEL --runs 3 --approve-workspace-edits
```

Replace YOUR_GEMINI_MODEL with a model identifier available to your account; the
engine does not query availability or pricing. Live mode requires an explicit model
name, prints model/budgets/policy and a cost/quota warning before requests, and uses
the configured provider in the parent process. No API key is printed or put in a
trial file, result, command argument or agent-worker environment. The application
does not load .env files. Development and automated tests use scripted/mocked
responses only. Mock scores are pipeline checks, not model-performance evidence.

## Versioned definitions and the core suite

benchmarks/core/suite.json lists ten task IDs. Each tasks/ID.json defines a unique
ID, name, category, semantic version, description, instructions, fixture ID, verifier
version, expected deliverables, named criteria, seconds and turns. fixtures/ contains
only public workspace files. verifiers/checks.py contains the independent checks,
not reference solutions. TaskRegistry rejects duplicate IDs and invalid schemas.

| ID | Category | Independent outcome |
| --- | --- | --- |
| slug | coding | Whitespace-aware slug function |
| ledger | application | Multi-file JSON persistence and totals |
| median | debugging | Odd/even median, no input mutation, empty error |
| tests | testing | Generated unittest suite passes and catches two behavioral mutants |
| ranges | tdd | Range parser against visible and additional cases |
| port | validation | Port range/type/ASCII validation |
| config | modification | Extend config while preserving name validation |
| orders | refactoring | Preserve totals and remove duplicate loop logic |
| unique | regression | Stable uniqueness including unhashable values |
| csv | multistep | Separate parser/statistics modules and error behavior |

Each current task has three named criteria. Definitions default to 90 seconds and
12 total model turns. The inherited final wrap-up consumes a reserved turn; normal
loop turns receive turns-1 so the total stays bounded. Requests can also include
context compaction. A broker allows at most 2*turns logical requests per trial;
provider retries have their own bounded attempt count and remaining-time limit.
Runs are limited to 1..20 repetitions, at most ten selected tasks/200 trials,
1..300 task seconds, 1..40 turns and a separate 15-second verifier budget. Process
cleanup and report storage add bounded overhead beyond these execution budgets.
There is no unlimited auto-repair/retry benchmark loop.

Suite fingerprints hash versioned manifest/task/fixture/verifier text with SHA-256,
UTF-8/LF normalization and relative paths. Fixtures and verifier source are captured
as snapshots before trials. Each worker copies only that fixture snapshot. The
engine source fingerprint separately covers the current sudarshan Python sources,
including uncommitted code; a trial rejects an engine change during evaluation.
Commit SHA, OS/architecture and Python version are also recorded. This identifies
dirty-source differences without pretending the parent commit contains new code.

To add a trusted suite, add a name/suite.json manifest, tasks/*.json, matching public
fixtures and a verifiers/checks.py protocol implementation. Definitions must pass
Task.validate and file/path limits. Bump task/suite/verifier versions when semantics
change, and test both correct and incorrect candidates. Custom suites must retain
the bounded budgets and output protocol. Do not place secrets or hidden solutions
in fixtures. The supplied core suite is small and public; memorization and training
contamination are possible and it is not a comprehensive SWE capability benchmark.

## Trial and verification lifecycle

A new disposable directory is created per trial. Public fixture files go into its
agent workspace. Private worker configuration and the verifier snapshot remain in
sibling control locations outside that workspace. No prior task state, transcript,
.env, repository tree or hidden checks are copied into it. A fresh Harness uses
persist=False (no conversation transcript) and local Phase 4 telemetry.

Safe policy is always used. Without --approve-workspace-edits, effectful tools are
denied. That flag explicitly approves confined write_file/edit_file operations
only. Shell commands and subagents remain denied/disabled. The agent can read the
public visible TDD tests but cannot run arbitrary test commands through this policy.
That restriction is recorded so model comparisons use the same authority. Denied
approvals are measured, not silently bypassed with YOLO.

The parent invokes the trusted agent worker through run_owned. In live mode an
authenticated, bounded loopback broker forwards requests to the selected Gemini
provider. The worker gets a short-lived capability, not the provider credential;
proxy environment hooks are bypassed for loopback. Provider request deadlines bound
transport/backoff against the task deadline. Retries are relayed as metadata even
when generation fails. A timeout or interrupt stops the ordinary owned process tree.

The agent process stops before verification starts. Only declared deliverables are
read through secure workspace handles, validated for path/type/syntax and size
(64 KiB per artifact), and copied into a different disposable verifier workspace.
Links/reparse paths, traversal, unsupported artifact types and missing files cannot
be promoted to success. No agent final-response claim is consulted.

The hidden verifier runs in another owned, isolated-startup Python process with a
filtered environment, bounded output and a 15-second deadline. It emits only
schema version and named Boolean check outcomes. Import/syntax failures are invalid
output; infrastructure/protocol errors are verifier_error; known provider/transport
failures are inconclusive, with execution_status separate from verification.status.
Every result records whether checks actually executed. Missing artifacts do not
masquerade as executed failed assertions. A pass requires completed execution,
complete validated deliverables and all independent criteria passing.

Statuses: passed, failed, partial, timeout, interrupted, invalid_output,
verifier_error and inconclusive. Partially correct behavior or incomplete artifacts
are partial but never passing. Interrupted runs stop scheduling additional trials.
Comparisons flag a run with fewer attempts than planned as incomplete.

## Metrics and denominators

- attempted_trials is actual attempted task/repetition pairs; planned_trials comes
  from selected tasks * repetitions. run_complete makes early interruption explicit.
- Task success rate = passed attempts / attempted attempts, including operational
  failures. Status counts distinguish failed behavior from provider/infrastructure
  limitations; do not interpret operational failures as pure model incapability.
- First-attempt rate = passed repetition-1 attempts / attempted repetition-1 tasks.
- Verification pass rate is the mean per-attempt fraction of named criteria passed;
  attempts without executed verification contribute zero operational score. A task
  with many assertions cannot dominate this task-weighted measure.
- independent_check_pass_rate is a separate diagnostic over checks actually executed,
  not a task-success weighting. Unknown/unexecuted check data remains unavailable.
- Artifact completion is the mean validated-present / required artifact fraction per
  attempt, with unverified attempts zero. Invalid syntax does not count as validated.
- Validation diagnostics cover checks in category validation. Error-handling checks
  are the declared core IDs empty, invalid, range, types, regression and errors_empty.
  Regression failures cover failed executed checks in category regression. Custom
  suites should use these conventions or report unsupported diagnostics as unavailable;
  no arbitrary composite code-quality grade is invented.
- Turns, logical requests, tool outcomes, denials, retries and agent timeouts are
  projected from Phase 4 metadata. Wall-clock time is measured independently and
  includes worker/verification/cleanup; median and population standard deviation
  describe observed trials. Average successful-task duration uses passed attempts.
- Tokens are actual reported metadata in real runs and explicitly simulated metadata
  in mock runs, never character estimates. Per-trial coverage and partial flags
  identify missing/incomplete telemetry. Aggregate token coverage reports measured
  requests and successful requests represented in available telemetry for each field;
  these counts exclude trials with no telemetry. Token sums are observed subsets when
  coverage is incomplete. Count averages are null if any trial has missing or partial
  telemetry. Unknown values are null, not measured zero.
- Estimated cost requires available measured fields, complete request coverage and
  valid configured rates from the existing Phase 4 pricing file. No rate is hardcoded
  or fetched. The agent does not receive that pricing file. Input/cache/thought
  semantics use the existing explicit pricing policy. Each trial retains source,
  effective date and currency; a pricing configuration hash records configuration
  differences. Estimates are not Google billing and exclude unknown failed-attempt
  charges. Total cost is unavailable if any attempt lacks a cost or currencies differ.
- Cost per success including failed attempts = available estimated cost of all
  attempts / number passed. It is null for zero passes or incomplete cost data.

## Repeated trials and comparisons

Every repetition starts clean, including failed/denied trials. Comparison checks suite
and engine fingerprints, task versions, limits, repetitions, approval policy, provider
configuration, prompt configuration, source commit, OS/Python and live/mock mode.
Different model IDs are intentional. Incomplete or mismatched runs are flagged;
no success-rate delta is presented for unfair configurations. Pricing differences
are reported separately and no cost-savings assertion is made. Per-repetition rates
and population standard deviation describe variation, not statistical significance.
A handful of runs does not establish significance or general model superiority.

## Result storage and privacy

.sudarshan/benchmarks/runs/UUID.json is the authoritative schema-v1 result.
reports/UUID.json is a derived summary cache. Reports and export read the validated
run, recompute its summary and reject unknown content fields, mismatched identities,
invalid pass claims, malformed JSON and duplicate JSON keys. Results contain no
instructions, prompts, hidden test code, reference solutions, arguments, raw outputs,
API credentials or workspace paths. Public identifiers/provenance must not be used
as secret-carrying channels. This schema does not make locally forged data authentic.

Writes use the existing cross-process metadata lock and fsynced atomic JSON replacement.
Run IDs are random full UUIDs; existing IDs are not overwritten. A 2 MiB result bound
and 1..1000 recent-run retention (default 100, run --retention N) bound generated run
and cached-report files. Retention removes generated files only, never directories.
The two files are not one transaction: a cache write failure can leave an authoritative
run available. Process/power loss can leave disposable scratch or temporary files;
normal operation/error paths clean owned temporary data. All storage is already
ignored under .sudarshan/. JSON export is to stdout, not an implicit external upload.

## Security and verification limits

Local directories and hidden-from-workspace tests are NOT OS containment. Controlled,
harmless tasks only. A hostile Python candidate can inspect the verifier interpreter,
read other host-accessible files or attempt to influence checking; the current system
is not an adversarial anti-cheating boundary. Public checks can be memorized. Strong
untrusted-code evaluation needs a separately verified sandbox/account plus external
holdouts; do not run this local verifier on arbitrary hostile submissions.

Windows Job Objects own ordinary descendants; POSIX process groups cannot contain
processes that deliberately create new sessions. Parent-host credentials are not
inherited by workers/verifiers, but the same OS account may access host files or
services outside the API. Windows ACLs are inherited. Loopback broker capabilities
are not defenses against a hostile host owner. In-flight provider requests may still
complete or bill after client timeout; urllib DNS cancellation is not guaranteed.
No requests are issued automatically to refresh rates or validate credentials.

Run `python -m unittest discover -v` for all tests. The broker tests need localhost
socket permission and mock every provider completion; they never make a real model
request. Existing cross-platform CI runs these tests without --live CLI invocations.
A test-only run_suite(mock_scripts=...) interface supplies deterministic model replies;
it is not exposed as a production model benchmark and reports mode=mock.
