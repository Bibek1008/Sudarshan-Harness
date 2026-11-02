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

The audit was committed as `6d7d4ac` before deletion. The first cleanup removed
**109 individually checked files**: 104 `.pyc` files and the five named Phase 6
logs. Seven cache directories were removed only after becoming empty. No tracked
file, historical report, fixture, regression test or example was deleted. No
source files were moved. After validation, a second checked inventory removed
105 regenerated `.pyc` files and seven empty cache directories. These counts
describe cleanup operations; most paths overlap the initial bytecode inventory.
The new release test accounts for the additional bytecode path. Validation logs
and per-file manifests remain ignored in `ci-results/` as local audit evidence.

Six imports were removed: `diagnostics` in CLI, `mean` in evaluation comparison,
`shutil` in SSH, and `shutil`, `subprocess`, `redact` in Docker execution. No dead
module or duplicate helper was safely removable: similar path helpers enforce
different boundaries, and example/public entry points remain useful. Repeated
CLI task-failure/interrupt handling is now one small helper. The intentional
product security test import remains. No dependency was added or removed.

The CLI now rejects negative turn limits before creating a workspace, describes
project-root/resume/model/task options, reports expected failures without raw
exception text, and keeps interactive use available after a failed task. Safe
defaults, policy denials and interrupt exit status remain intact.

The first post-cleanup full run found an intermittent existing memory concurrency
error, not a successful validation: **377 run, 362 passed, 14 skipped, one error**.
A focused reproduction identified NTFS resolving a delete-pending lock to an
internal deleted-file path, plus transient access denied on exclusive creation.
The fix resolves only the stable lock parent, rejects lock links, keeps exclusive
creation and the two-second wait, and validates memory after acquiring the lock.
Three deterministic regressions cover those cases without weakening path checks.
An 80-iteration stress check completed **2,560 writes** with no lost facts or
duplicate entries. Existing thread/process/symlink tests remain in place.

Ignore rules retain `.sudarshan`/credential protection, include compiled/editor/OS
caches and local benchmark export/results locations, and scope `work`, `projects`,
validation logs and test workspaces to intended root locations. The former global
`*.log` pattern is narrowed so fixture logs remain visible. New tests check both
ignored private/runtime paths and visible source/docs/fixtures/workflows.

README now links current onboarding/security/release documentation. Added
`docs/GETTING_STARTED.md`, `docs/SECURITY.md`, `RELEASE_NOTES.md` and
`FINAL_PROJECT_REPORT.md`; observability and evaluation link to the same current
guidance. Installation is accurately described as checkout-based, with no pip
installer. Current local Markdown links were verified. Historical reports remain
unchanged, preserving their original claims and dates.

Baseline: **369 run, 355 passed, 14 skipped, zero failures/errors**, Windows/Python
3.12. Final local and hosted results are recorded in the
[final report](../FINAL_PROJECT_REPORT.md): **380 run, 366 passed, 14 skipped,
zero failures/errors** locally. All five
[hosted jobs](https://github.com/Bibek1008/Sudarshan-Harness/actions/runs/41429719803)
passed for source commit `91ddd67`, including Windows/Ubuntu on Python 3.10/3.12
and three live disposable-Docker tests. Compilation, CLI help, provider-free
diagnostics, benchmark dry-run, Git whitespace and sensitive-file checks are part
of the final gate. Eleven focused regressions are added; no coverage is removed.

The final structure is unchanged apart from the new documents/tests; see the
[layout](../FINAL_PROJECT_REPORT.md#repository-layout). Runtime state, earlier
validation evidence and unidentified temporary workspaces remain ignored and
untouched. Remaining issues are the existing OS-isolation/SSH/race/heuristic
filtering/context-budget limits in [security](SECURITY.md), not an additional
development phase. All intended changes are committed on the feature branch;
the working tree and staged index are clean. No generated files, credential
files, personal identifiers or runtime transcripts were added. The branch
includes fetched main `727d712`; no force-push, reset, history rewrite or unrelated
change was used. Main remains unchanged pending an approved review and merge.
