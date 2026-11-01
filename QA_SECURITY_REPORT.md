# Sudarshan Harness QA and Security Review

Date: 2026-11-01. Environment: Windows, Python 3.12.10.

## Scope and baseline

Reviewed all core modules: loop, provider, security, tools, environment, harness,
session, memory, context, skills, subagent, fleet, CLI and package entry points;
execution base/registry/adapter, local, Docker sandbox and SSH implementations.
Also reviewed product approval, artifact verification and fleet orchestration demos.
Existing Taskman tests were preserved. Unrelated work products and sensitive files
were excluded. No real Gemini, Docker or SSH requests were made.

Git status was attempted before edits and failed with `not a git repository`.
This extracted workspace has no Git metadata; pre-existing changes cannot be
identified or attributed using Git.

Baseline: 22 existing Taskman tests passed with explicit `-s tests`; no Harness
tests existed. Default `python -m unittest discover -v` discovered zero tests.
No line/branch coverage percentage was measured; the claims here concern executed
behavioral tests, not exhaustive coverage.

## Confirmed defects and repairs

1. Default discovery skipped the tests directory. Added `tests/__init__.py`.
2. Provider JSON roots, feedback, usage metadata and tool argument shapes could
   trigger incidental exceptions or invalid calls. Added explicit validation,
   safe parse errors and positive retry-count validation. Provider regression tests
   exercise successful responses, missing candidates, malformed data and HTTP
   400/401/403/429/500, timeout/network retry exhaustion and backoff without sleeping.
3. API keys were embedded in request URLs. They now travel in the API-key header;
   model names are validated before constructing the endpoint. Synthetic-key tests
   verify URL exclusion, key precedence, missing-key errors and HTTP-error redaction.
4. Loop replies were indexed without validation. Empty/malformed replies now fail
   explicitly before tool effects. Tests cover final replies, consecutive/multiple
   calls, unknown/blocked calls, execution failures, compaction hooks and turn limits.
5. Tool and fleet exception reports copied arbitrary exception text. These reports
   now retain exception type with a generic failure description. Backend startup,
   timeout and file permission failures suppress raw exception chains/details.
   Synthetic-secret regression tests exercise the affected reporting paths.
6. CLI events/approval prompts displayed credential-shaped arguments and text.
   Added recursive best-effort diagnostic redaction for sensitive field names,
   assignments, bearer tokens and URL key parameters without mutating input.
7. Memory, skills and session metadata lacked consistent resolved workspace checks.
   Added a shared boundary helper, checked constructor/resume paths and latest-session
   targets, and rejected symlink escapes before metadata access. Real and mocked
   boundary tests cover these decisions; real symlink tests are capability-gated.
8. Well-formed JSONL with malformed message fields could break recovery. Validate
   message roles, text, tool results and assistant calls before accepting records.
   Tests cover invalid UTF-8, corrupt tails, invalid shapes, interrupted calls,
   idempotent repair, missing final newline, durable append and resume.
9. Concurrent Windows session-directory creation produced transient access-denied
   errors; Windows resolution also sometimes returned mixed extended-path spelling.
   Added bounded Windows retries and normalized equivalent path spelling. Thread and
   process collision tests and explicit retry/prefix regressions pass. The thread
   test also passed 20 repeated runs (640 session creations).
10. Common Windows recursive removal/disk commands were absent from permanent policy
    denials. Added conservative patterns and tests across safe/YOLO/read-only modes.
    Malformed policy calls now fail closed. Destructive strings are never executed.
11. Missing fleet job names caused the error handler itself to fail. Failed malformed
    jobs now return an unnamed failure record; valid jobs retain ordering.
12. Invalid UTF-8 memory raised a raw decoder error. It now produces a useful error
    while preserving the original bytes; a regression test verifies preservation.

## Execution and orchestration evidence

Actual local Python subprocess and PowerShell execution passed, including nonzero
exit reporting. Unicode filenames/content, native Windows paths, permission errors
and filtered child environments were tested. Docker/SSH invocation, option quoting,
host-key protections, failures and timeouts were mocked. Docker timeout tests verify
cleanup of the exact generated container name and explicit cleanup-failure reporting.
The SSH file helper was executed locally in temporary storage to test traversal
rejection without a connection.

Fleet tests synchronize workers to establish concurrency, preserve input order and
aggregate failed jobs. Subagent tests cover depth limits, failures, clean transcripts
and inherited policy. Product tests cover reserved-path approvals, injection rejection,
finite test timeouts, hidden-content exclusion, missing/placeholder artifacts, digest
changes, skill/manual gates and bounded review/repair phases. These tests do not
establish that generated websites work in a real browser.

## Final validation

- `python -m compileall -q sudarshan demos tests`: exit 0.
- `python -m unittest discover -v`: exit 0; 102 tests, 97 passed, 0 failed/errors,
  5 skipped (6.338 seconds on the final run).
- `python -m sudarshan --help`: exit 0; usage/options displayed without an API call.
- Additional targeted provider, loop, security, state, backend and orchestration
  suites were executed during development. Early failing regressions were repaired;
  the final full-suite result above supersedes those intermediate failures.
- Added 80 Harness tests; preserved all 22 existing Taskman tests.

Every final skip is due to Windows symlink privilege error 1314:

- `TestSecurity.test_core_symlink_escape`
- `TestExecution.test_local_symlink_boundary`
- `TestState.test_memory_symlink_boundary`
- `TestState.test_session_directory_symlink_boundary`
- `TestState.test_skill_symlink_boundary`

Mocked metadata symlink-resolution checks ran successfully; they do not replace a
real symlink integration run under an appropriately privileged account. No backend
integration test is represented as a platform skip: Docker/SSH tests are explicitly
mock-based tests.

## Remaining weaknesses and limits

- Shell policy is an approval boundary, not an OS sandbox. Approved/YOLO commands
  and generated tests can access host files/network and invoke interpreters. Pattern
  denials cannot prove an arbitrary shell program safe or cover every alias/encoding.
- Resolved file paths remain subject to time-of-check/time-of-use symlink races.
  Workspace file tools do not categorically deny sensitive filenames inside a
  workspace. Environment filtering does not prevent filesystem credential access.
- Redaction is heuristic. Arbitrary secrets in ordinary prose, custom event callbacks,
  tool output, custom backend exceptions or durable transcripts are not universally
  sanitized. Request headers must also be protected by external HTTP diagnostics.
- Session logs have one writer; concurrent creation is tested, simultaneous append
  or resume of the same active session is unsupported. Recovery retains the valid
  prefix and truncates at the first invalid record, including subsequent records.
- Local timeout handling does not guarantee descendant-process termination. SSH
  client timeouts do not establish remote command termination. Docker cleanup is
  tested through mocks, not a live daemon. Live integration remains unverified.
- Python 3.12 on Windows is verified. Linux/macOS, real SSH hosts, Docker mount
  semantics and browser interaction are not verified by this run.
- Invalid memory is rejected explicitly; no automatic encoding repair is attempted.
- A transient Windows child-directory lock caused one intermediate temporary cleanup
  failure. The shared test fixture now retries cleanup; the final suite passes.
  The earlier empty temporary directory `tests/tmpqtes4l4l` is retained rather than
  issuing a directory-deletion command under the user's safety constraints.

## Files changed in this review

Production: `sudarshan/provider.py`, `loop.py`, `security.py`, `session.py`,
`memory.py`, `skills.py`, `harness.py`, `fleet.py`, `cli.py`,
`execution/local.py`, `execution/remote.py`, `execution/sandbox.py`.
New helpers: `sudarshan/paths.py`, `sudarshan/redaction.py`.
Tests: new `tests/__init__.py`, `tests/test_harness_provider.py`,
`tests/test_harness_loop.py`, `tests/test_harness_security.py`,
`tests/test_harness_state.py`, `tests/test_harness_execution.py`,
`tests/test_harness_orchestration.py`.
Documentation: this new `QA_SECURITY_REPORT.md`.
