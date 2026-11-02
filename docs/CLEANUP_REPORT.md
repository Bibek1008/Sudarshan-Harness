# Phase 7 repository cleanup report

## Audit before deletion — 2026-11-02

The actual repository is `publish-clone`. The audit began from clean main
`727d712bdd41372523f8b628d4e9a06f638edef3`; work is on
`phase-7-final-polish`. Neighboring extracted copies are outside scope.
This report and the individual-file inventory were created before deletion.

The initial repository has 144 tracked files, no identical nonempty tracked
Python/Markdown/JSON/workflow files, and no pip dependencies. Core modules,
backends, evaluation, tests, demos, benchmarks and CI already occupy their
intended directories. No source-module removal or directory reorganization is
justified. Public APIs, standalone demos and intentionally incomplete benchmark
fixtures must not be classified as dead code merely because they are not called
by the default CLI.

### Approved cleanup inventory

- Untracked `.pyc` files inside confirmed `__pycache__` directories. Only
  individual files in the audited manifest may be removed, after resolving and
  checking that each path stays inside this repository and is not tracked.
  Remove a cache directory only after it is empty; no recursive deletion.
- Five ignored Phase 6 logs produced by the preceding work in this chat:
  `phase6-dry-run.log`, `phase6-final-tests.log`, `phase6-help.log`,
  `phase6-tests-local-network.log`, `phase6-tests.log`. Their durable results
  already live in the retained Phase 6 report.
- Local inventory: `ci-results/phase7-cleanup-manifest.json`, listing each exact
  candidate. This generated audit evidence stays ignored, outside the commit.

### Retain deliberately

- All existing tests, benchmark fixtures/verifiers, demos, skills and workflows.
- Every historical phase, audit, security and engineering report. Their dates
  and results are historical evidence, not current release certification.
- `phase3-local-validation.log` and `publish-validation.log`: earlier validation
  evidence, rather than logs created by this cleanup. Both remain ignored.
- `ci-results/`: validation diagnostics, including before/after cleanup results.
- All `.sudarshan` state, session/telemetry data and credential files: do not
  inspect their contents or delete them as part of housekeeping.
- Empty `work/` used by tests, and any unidentified temporary workspace: an empty
  name alone does not prove ownership or justify deletion.
- The `subprocess` import in `demos/product_approval.py`: an existing security
  regression patches that namespace to detect unmanaged execution. Retain the
  test seam and its coverage rather than treating an AST warning as proof.

### Focused changes identified

- Remove six confirmed unused imports in CLI, comparison and execution modules;
  retain imports used by public exports, generated SSH helpers or tests.
- Improve expected CLI failures and argument help without changing safe-mode
  defaults, approval controls or provider APIs.
- Narrow broad root ignore rules to known output locations; add bytecode,
  editor/OS cache, local export and temporary-file patterns. Test that source,
  fixtures, reports, workflows and documentation remain visible to Git.
- Add a first-run guide, current security overview, release notes and final
  report. Link these from README and current observability/evaluation guides;
  preserve historical documents in place so their references remain valid.
- Enable the existing Windows/Ubuntu Python 3.10/3.12 and Docker CI jobs for
  the Phase 7 feature branch. Do not change their security or skip policy.

## Execution and verification

Pending implementation and validation. This section will record individual-file
cleanup counts, code/documentation changes, before/after test results, hosted CI,
final structure and remaining limitations before completion.
