# Phase 3: cross-platform CI and integration verification

## Repository and history

Work was performed in the actual clone at `publish-clone`, remote
https://github.com/Bibek1008/Sudarshan-Harness, starting from pushed commit
1d8ab5c45cf06539db473bb3656943f2028e1d7a. Security helpers and regressions were
present. Branch: `phase-3-cross-platform-ci`. Main was not modified. The pre-existing
untracked publish-validation.log is preserved, not staged or uploaded. No existing
workflow or dependency manifest was present. README documents Python 3.10+ and
zero third-party Python dependencies.

## CI changes

New `.github/workflows/cross-platform.yml` has a fail-fast-disabled matrix for
Windows latest and Ubuntu latest with Python 3.10 and 3.12. No dependency installation
or pip cache is appropriate for this standard-library-only project. Checkout does
not persist credentials; workflow token permission is contents:read. Jobs have
bounded deadlines and upload diagnostic artifacts even on failure.

`scripts/ci_validate.py` executes the required compileall, unittest discovery and
CLI-help commands unchanged as child processes. It forwards exit-code failures,
records timeouts as failures, and saves logs, skip reasons and platform/Python
metadata under ignored ci-results/. Subprocess environments are allowlisted and
exclude provider credentials. Two regression tests inject test failure and timeout
outcomes to verify failure propagation and retained artifacts; they isolate their
mocks from the shared subprocess module to avoid contaminating platform detection.

## Verified Windows result

Environment: Windows 11, Python 3.12.10. Final CI-runner execution:

- `python -m compileall -q sudarshan demos tests`: exit 0.
- `python -m unittest discover -v`: exit 0; Ran 245 tests in 24.990 seconds;
  OK (skipped=15), zero failures/errors.
- Successful test records: 232. There are 13 skipped test methods and two additional
  class-setup skips. Unittest does not include class-setup skips in testsRun, so
  naively subtracting 15 from 245 would undercount successful methods.
- `python -m sudarshan --help`: exit 0.

Actual Windows tests exercised Job Object ownership/gating, three-level descendant
cleanup after timeout, interruption, successful parent completion and abrupt owner
crash; trusted executable resolution and COMSPEC selection; real PowerShell;
Unicode files/content; parent/final-file handle rename protection; root replacement;
and concurrent thread/process session creation. TemporaryDirectory fixtures clean
up disposable workspaces, with bounded Windows cleanup retries where implemented.

Mock-based tests separately cover HTTP/provider behavior, Docker/SSH argv and error
handling, synthetic failure paths, orchestration, and CI-runner failure injection.
No mock result is described as a live backend-isolation result.

The inherited combined suite previously had four failures and fourteen error
records. Reconciled the old subprocess mocks with the owned runner; supplied fake
provider-header credentials to transport tests; used valid tool-call arguments in
session recovery fixtures; and updated assertions to require redacted failures.
All original test scenarios remain. No production security control was weakened.
A POSIX descendant-state assertion now waits a bounded two seconds for kernel
termination/zombie transitions instead of assuming immediate scheduling.

## Ubuntu / Python 3.10 results: NOT EXECUTED

The workflows are committed locally but have not been pushed or run on GitHub,
as requested. WSL enumeration returned Wsl/E_ACCESSDENIED. Therefore no actual
Ubuntu or Python 3.10 pass result is claimed. A green Windows result is not evidence
that the Ubuntu job will pass.

Ubuntu matrix jobs will execute existing real process-group/session, nested-child,
timeout/interruption, symlink, traversal, session and memory checks. New
`tests/test_posix_live.py` adds live FIFO rejection, 0600 file permissions, Unicode
parent-directory operations and a directory-relative TOCTOU adversary that swaps
a path to a symlink while an already-open directory descriptor is retained. An
observer wraps the real os.open syscall; it does not emulate filesystem effects.
These POSIX tests are legitimately skipped on Windows.

## Live Docker integration: NOT EXECUTED locally

Explicit opt-in preflight ran locally and reported: trusted Docker client unavailable;
Ran 0 tests, skipped=1. Docker/sshd executables are not available here. This is not a
Docker pass. The separate Ubuntu/Python 3.12 job opts into `tests/test_live_docker.py`.
It checks trusted-client/daemon/Linux-container availability and records unavailable
integration as not_executed in summary.json. Once a daemon is available, image-pull,
assertion or runtime failures fail the job rather than being skipped.

The test image is the official python:3.12-slim image (mutable tag; no immutable
digest assurance claimed). All mounts point to disposable temporary directories;
there is no host credential mount, privileged flag or Docker socket in containers.
Actual runtime tests assert nonzero uid, inability to write to the read-only root,
loopback-only network interfaces and zero effective capabilities. Live daemon
inspection checks network:none, read-only root, privileged:false, dropped ALL
capabilities, PidsLimit 64, Memory 512MiB and NanoCpus 1e9. Success/failure/timeout
cases check exact generated container names are absent afterward. An argv observer
retains names but delegates every invocation to the real runner. Cleanup targets
only those names. Inspection/worker waits are bounded; tests do not disable limits
or use --no-sandbox. Configuration inspection is not proof of every kernel/resource
boundary under adversarial load.

## SSH assessment: NOT EXECUTED

Only the SSH client is installed locally; no disposable sshd or Docker server is
available. No personal keys, known_hosts or production endpoints were accessed.
An isolated CI server could be built in a future optional job with test-generated
keys, a disposable known_hosts file and loopback-only transport. That provisioning
is not implemented here, so host-key/BatchMode/transport checks currently remain
mocked and the remote file helper is tested locally, not through SSH. Remote
process termination is still explicitly unconfirmed; no SSH integration pass is
claimed. The workflow does not connect to any user server.

## Remaining assurance gaps

Hosted CI, live Docker and Python 3.10 compatibility remain pending a separately
authorized push and actual workflow runs. Real Windows symlinks/junctions/hardlinks
need appropriate privileges. Browser tests skip only on genuine secure-runtime
unavailability; assertions after a successful preflight remain failures. The
workflow never passes --no-sandbox.

POSIX process groups are not cgroups: a descendant can deliberately create a new
session, and abrupt supervisor death is not guaranteed to kill the tree on Linux.
Directory descriptors do not isolate arbitrary shell programs or hostile filesystem
owners. Session/memory metadata still use resolved-path checks. Approved/YOLO shell
commands can access OS-permitted paths and services. Output redaction is heuristic;
there is no claim of complete credential filtering or full OS isolation. No
production regression was observed locally; unexecuted platform branches may still
have defects. Historical phase reports describe their own earlier runs and are
not overwritten with unverified results.

## Local skip records

- setUpClass (tests.test_browser_probe.BrowserProbeTests) ... skipped 'Secure Chromium unavailable: no browser executable found'
- test_posix_session_leader_is_used (tests.test_execution_hardening.TestBackendHardening.test_posix_session_leader_is_used) ... skipped 'POSIX process groups unavailable on Windows'
- test_hardlink_alias_cannot_modify_sibling (tests.test_execution_hardening.TestHandleFilesystem.test_hardlink_alias_cannot_modify_sibling) ... skipped 'hard links unavailable: PermissionError, winerror=5'
- test_posix_symlink_swap_rejected_without_truncation (tests.test_execution_hardening.TestHandleFilesystem.test_posix_symlink_swap_rejected_without_truncation) ... skipped 'POSIX O_NOFOLLOW descriptor test; Windows uses reparse handles'
- test_windows_junction_escape (tests.test_execution_hardening.TestHandleFilesystem.test_windows_junction_escape) ... skipped 'Windows junction creation unavailable: Access is denied.'
- A path that looks local but resolves outside the root is never read. ... skipped "symlink creation is unavailable: [WinError 1314] A required privilege is not held by the client: 'C:\\\\Users\\\\User\\\\Desktop\\\\project\\\\harness\\\\Sudarshan-Harness-main\\\\publish-clone\\\\work\\\\sudarshan-outside.txt' -> 'C:\\\\Users\\\\User\\\\Desktop\\\\project\\\\harness\\\\Sudarshan-Harness-main\\\\publish-clone\\\\work\\\\tmp4gvqtcki\\\\escape.txt'"
- test_local_symlink_boundary (tests.test_harness_execution.TestExecution.test_local_symlink_boundary) ... skipped 'Symlink creation unavailable: OSError, winerror=1314'
- test_core_symlink_escape (tests.test_harness_security.TestSecurity.test_core_symlink_escape) ... skipped 'Symlink creation unavailable: OSError, winerror=1314'
- test_memory_symlink_boundary (tests.test_harness_state.TestState.test_memory_symlink_boundary) ... skipped 'Symlink creation unavailable: OSError, winerror=1314'
- test_session_directory_symlink_boundary (tests.test_harness_state.TestState.test_session_directory_symlink_boundary) ... skipped 'Symlink creation unavailable: OSError, winerror=1314'
- test_skill_symlink_boundary (tests.test_harness_state.TestState.test_skill_symlink_boundary) ... skipped 'Symlink creation unavailable: OSError, winerror=1314'
- setUpClass (tests.test_live_docker.LiveDockerTests) ... skipped 'LIVE Docker not executed: opt-in flag not set'
- test_created_file_permissions_and_parent_operations (tests.test_posix_live.PosixDescriptorTests.test_created_file_permissions_and_parent_operations) ... skipped 'LIVE POSIX descriptor tests require a POSIX OS'
- test_directory_relative_open_survives_path_swap_without_following_link (tests.test_posix_live.PosixDescriptorTests.test_directory_relative_open_survives_path_swap_without_following_link) ... skipped 'LIVE POSIX descriptor tests require a POSIX OS'
- test_fifo_is_rejected_without_blocking (tests.test_posix_live.PosixDescriptorTests.test_fifo_is_rejected_without_blocking) ... skipped 'LIVE POSIX descriptor tests require a POSIX OS'
- OK (skipped=15)
