# Phase 2: execution security and isolation hardening

Date: 2026-11-01. Verified host: Windows, Python 3.12.10.

The existing tools, Policy, ExecutionBackend interface and Local/Docker/SSH backend
classes are retained. Shared process/file primitives replace weaker duplicated
operations. This is execution hardening, not a claim of host filesystem or network
isolation. No real Gemini requests, Docker daemon commands or SSH connections were
made. Sensitive files were not inspected. Git status remains unavailable because
this extracted workspace is not a Git repository.

## Findings, severity and exploitability

Severity assumes an attacker can influence approved commands or concurrently modify
workspace files. Safe-mode approval still precedes model-requested effects.

| Finding | Severity / prerequisite | Evidence and repair |
| --- | --- | --- |
| Immediate-child timeout cleanup allowed descendants/background work to survive | High: an approved command spawns children | Confirmed from the old subprocess lifecycle. New live Windows regressions verify nested children stop after timeout, interrupt, success and abrupt owner exit. |
| Resolved-path checks followed by separate opens allowed link/ancestor replacement races | High: concurrent workspace writer | Old check-then-open sequence confirmed by inspection. Handle-based operations replace it. Real Windows tests verify final-file and parent rename denial while open, and rejection of a replaced root. Actual symlink/junction exploits were not executed because creation privileges are unavailable. |
| Docker and SSH client processes inherited the full host environment | High: malicious/interposed client or inherited child | Source confirmed inheritance. All client invocations now use an allowlisted environment via the shared runner. Actual local subprocess tests exclude synthetic key and unknown secret variables; Docker/SSH invocation tests remain mocked. |
| Backend executable lookup could select a workspace/current-directory client | High: attacker controls executable placement/search context | Resolver now searches absolute PATH entries, excludes the configured local workspace/current repository, and rejects Windows batch clients. Tests resolve inert disposable files; no fake executable is run. Host PATH/configuration must still be trusted. |
| Output was accumulated without a memory bound before truncation | Medium: approved command emits excessive output | Bounded stream capture retains at most 12,000 bytes per stream and stops commands beyond 1 MiB per stream. Actual flood regression passes. |
| Abbreviated/obfuscated Windows destructive commands missed existing patterns | Medium: approved/YOLO shell input | Inspection-only tests cover recursive parameter abbreviations, case, backticks/carets and aliases. Patterns strengthened; no destructive command is executed. |
| Inherited COMSPEC could select an unexpected Windows shell | Medium: untrusted parent environment | Runner selects cmd.exe from GetSystemDirectoryW. Live synthetic-COMSPEC regression passes. |
| Error/capture paths could disclose command text or emit thread tracebacks | Medium: failure involving sensitive-looking arguments/output | Cleanup failures and backend adapter exceptions use generic errors with suppressed chains. Credential-shaped output is redacted. Synthetic-secret regressions pass. Redaction is not universal secret detection. |
| Generated-test demo helpers bypassed core process lifecycle controls | High: generated test spawns descendants | Product approval and verification helpers now use the same owned runner; timeout-routing regressions prevent fallback to unmanaged execution. |
| Docker cleanup was limited to timeout, not interruption or failed client exit | Medium: interrupted/disconnected client | Exact-name cleanup attempted after exceptions, interrupts and nonzero exits, with explicit unconfirmed-cleanup reporting. Verified only through mocks. |

## Process lifecycle protections

Windows uses an unnamed non-inheritable Job Object with KILL_ON_JOB_CLOSE and an
active-process limit of 64. A trusted Python wrapper starts with `-I -S`, waits on
a private stdin gate, and cannot launch the requested command until assignment to
the Job succeeds. Assignment failure stops before gate release. No breakaway flag
is granted. Normal completion also closes the Job and stops background descendants.
A live test deliberately exits the owner without Python cleanup and verifies the
three test-owned descendants stop. This manages ordinary OS descendants, not
processes created indirectly through external services or other users.

POSIX uses a new session/process group and SIGKILL cleanup on completion, timeout
or interruption. That branch has not run on this Windows host. A descendant that
calls setsid/changes process group can escape group cleanup; abrupt parent death
also lacks a Linux cgroup-style kill guarantee. Do not treat this as hostile-process
isolation. A delegated cgroup/service or independently verified container is needed
for stronger Linux containment.

Timeouts must be finite, positive and at most 3600 seconds. Output capture is bounded
in memory; no shared temporary capture file is created. Standard input is disabled
for commands. Reader failures are explicit and do not print background tracebacks.
Cleanup has additional bounded waits, so total return time can exceed the command
execution timeout. Windows process-count, command deadline and output limits do not
bound all CPU, RAM, disk, handles or external-service resource consumption.

## Filesystem protections and remaining races

Core read/write/edit/grep and Local file operations share WorkspaceFiles. The SSH
file helper ships the same source primitive rather than retaining a weaker copy.
Reads/edits are limited to 1,048,576 text characters. Oversized writes are rejected
before opening/truncation. Edit holds one handle for its read/modify/write sequence.

Windows opens and retains directory handles for root ancestors and file parents
without FILE_SHARE_DELETE, checks reparse metadata, and validates the final file
handle before truncation. Symlinks, junctions/other reparse points, multiple hard
links, alternate data streams, device names, drive-relative/absolute paths and
ambiguous trailing-dot/space names are rejected. Root identity is checked. This
intentionally also rejects in-workspace links previously accepted by canonicalization.

POSIX uses directory-relative opens with O_NOFOLLOW, checks regular-file type/link
count before truncation, and avoids reopening a checked path. Platforms lacking
required descriptor primitives fail closed. This is implemented but not exercised
on the current host. A hostile directory owner can still move an already opened
subtree, create aliases after inspection, manipulate mounts or act outside the tool
API; full filesystem isolation is not established. Directory listing is filtered
but is not a transactional filesystem snapshot. Session/memory metadata routines
retain the earlier resolved-path design; they are not converted by this phase.

Writes/edits flush and fsync, but are not transactional replacements: a disk/write
failure or crash can leave partial contents. There is no new delete file tool.
Arbitrary approved shell commands can still write or delete any OS-accessible path.

## Backend-specific assurance

| Backend | Verified here | Mocked or unverified |
| --- | --- | --- |
| Local | Real Windows Job ownership, nested cleanup, owner crash, blocked gate, PowerShell/Python execution, filtered synthetic environment, output bounds/redaction, held file/parent handles and root replacement | POSIX behavior; real hardlink/junction/symlink creation; hostile native code/services; comprehensive resource isolation |
| Docker | Local shared-runner behavior only; argument/cleanup tests inspect generated calls | No live daemon/image/mount/isolation test. Added --pids-limit 64 and --init; retained network none, read-only root, dropped capabilities, non-root user, memory/CPU limits and no-new-privileges. Exact container-name cleanup is mocked. Host mount validation can race with container operations; a writable bind mount is not a protected secret store. |
| SSH | File helper executed locally for traversal and Unicode roundtrip; quoting and error behavior tested | No connection or remote cleanup verified. Strict host-key and BatchMode flags retained. Local client uses filtered environment/owned lifecycle. Remote command invokes absolute /usr/bin/env and /bin/sh with an empty environment and fixed PATH, without a login-shell request. Initial SSH server-shell startup/configuration is outside this control. Timeout explicitly reports remote termination unconfirmed. |

Docker client resolution assumes trusted host PATH, executable and daemon. Existing
Docker configuration inherited through arbitrary environment variables is no longer
passed through; configure intended endpoints through a trusted explicit setup.
SSH agent environment is excluded. Explicit identity-file/server configuration may
still grant credentials to the SSH client. No credential file was opened by this
review. Remote environments require the configured Python and POSIX env/sh paths;
Windows remote shell support is not claimed. Source-only SSH helper composition
requires installed Python source to be available to inspect.getsource.

## Commands that can leave the workspace

`cd ..`, PowerShell Set-Location, Python os.chdir/open, absolute executable operands
and interpreter/file APIs can leave a starting cwd. One regression demonstrates
os.chdir into a sibling disposable directory; it never accesses user files. Safe
mode requires approval and read-only blocks shell calls. YOLO is not isolation.
Shell syntax/regex inspection cannot establish that an approved program is safe.
The added process ownership and secure file tool primitives do not change that.

The environment allowlist prevents automatic inheritance of API-key variables and
unknown credential variables in these execution paths. It cannot prevent code from
reading host credential files, workspace secrets, explicitly supplied secret
arguments, service-mediated data or other OS-accessible sources. PATH/TEMP/runtime
values are trusted host inputs. Diagnostic redaction handles recognized labels and
bearer/URL forms, not arbitrary values, encoded secrets or fragments split by output
truncation. File-tool contents and durable transcripts are not universally redacted.

## Final executed validation

- `python -m compileall -q sudarshan demos tests`: exit 0.
- `python -m unittest discover -v`: exit 0; 137 tests in 14.341 seconds,
  **128 passed, 0 failures/errors, 9 skipped**.
- `python -m sudarshan --help`: exit 0 and expected options displayed.
- Targeted hardening, execution and orchestration suites also ran during development.
- Baseline was 102 tests; 35 adversarial/regression tests were added. Existing test
  scenarios remain, with mocks moved to the new runner/file primitive boundaries.

All tests use disposable temporary workspaces for files and own the processes they
launch. No destructive command was executed on the repository/user filesystem.
No real Gemini/API request or live Docker/SSH operation occurred. No security
control was disabled and no --no-sandbox option was used.

### Every final skip

1. POSIX session/process-group test: not available on Windows.
2. POSIX O_NOFOLLOW test: Windows uses a different handle mechanism.
3. Real hardlink alias test: PermissionError, WinError 5.
4. Real Windows junction test: creation returned Access is denied.
5. Existing Local symlink test: WinError 1314, symlink privilege unavailable.
6. Existing core-tool symlink test: same WinError 1314.
7. Existing memory symlink test: same WinError 1314.
8. Existing session-directory symlink test: same WinError 1314.
9. Existing skill symlink test: same WinError 1314.

Windows reparse/multi-link metadata decisions also have mocked-handle regressions;
those are not substitutes for the skipped real-link integration tests. A POSIX CI
run and privileged Windows link/junction tests remain necessary before broader
platform assurance. No line/branch coverage percentage is claimed.

## Changed files in Phase 2

New: `sudarshan/execution/process.py`, `sudarshan/execution/filesystem.py`,
`tests/test_execution_hardening.py`, and this report.
Modified: `sudarshan/execution/local.py`, `sudarshan/execution/sandbox.py`,
`sudarshan/execution/remote.py`, `sudarshan/execution/base.py`, `sudarshan/tools.py`,
`sudarshan/security.py`, `demos/product_approval.py`, `demos/product_verify.py`,
`tests/test_harness_execution.py`.

The previous QA_SECURITY_REPORT.md records the earlier phase and is not overwritten.
The pre-existing empty temporary directory documented there is left untouched.
