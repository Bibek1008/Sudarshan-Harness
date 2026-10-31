# SUDARSHAN engineering report — current cleanup

## Implementation milestones

Existing architecture and Git history are preserved on main.
Earlier repairs include c3a65c8 (trusted read classification), a7f08de (rm inspection),
0845b73 (API-key naming), ba567cf (session collisions), fdfee7f (empty candidates),
968d4c8 (execution boundaries/dice), b829b1b (custom overrides), and c685647
(credential-safe provider errors and sandbox configuration).
e5519f6 introduced shared shell environment filtering; 067ed56 established safe
defaults and documented explicit yolo risks.

This cleanup adds root/home find denial patterns and two regression methods in
tests/test_find_denials.py (commit 8d61c87). It refreshes AUDIT.md,
ENGINEERING_REPORT.md and HARDENING_REPORT.md to remove stale source claims.
No provider, CLI default or product-builder implementation was rewritten.

## Regression coverage

| Area | Evidence |
| --- | --- |
| Permissions and rm denial | test_hardening.py, test_audit_repairs.py, execution integration tests |
| find root/home denials and legitimate commands | test_find_denials.py, all policy modes before approval |
| Environment and descendants | test_shell_environment.py, real shell probes with fixture credentials |
| Safe defaults, explicit yolo and hard denial | test_policy_defaults.py, test_cli_fleet.py |
| Provider parsing, keys, signatures and error secrecy | test_provider_audit.py, test_hardening.py, test_final_boundaries.py |
| Collision resistance and durable recovery | test_session.py, test_hardening.py, test_audit_repairs.py |
| Execution runtimes and original dice demo | execution test modules and test_backend_hardening.py |

The local product-preparation test and product_fleet.py changes predate this cleanup
and remain outside its commits. The fixture uses a mocked provider and explicit
fixture approval. Local and committed suites may therefore have different counts.
Refer to AUDIT.md for current backend limitations; historical resolved defects
are no longer presented as open work.

## Verification evidence

- User-supplied verification result (environment not reproduced here): **73 passed, 0 failures,
  0 skipped**. This is supplied evidence, not an execution reproduced in this checkout.
- Latest local execution after the find regressions: **76 discovered, 75 passed,
  0 failures, 1 skipped** (Python 3.12 on Windows).
- The skipped symlink escape test raises Windows error 1314 because symlink creation
  privileges are unavailable. It is not counted as passed.
- Full command: `python -m unittest discover -v`; verbose log: cleanup-test-results.txt.
  The local discovery includes the pre-existing untracked product-preparation fixture.
- `python -m compileall -q sudarshan demos tests`: passed.
- `python -m sudarshan --help`: passed; help reports safe as the default.
- `git diff --check`: passed.
- `git check-ignore .sudarshan/sessions/test-session.jsonl`: returned the expected path.
- No existing tests were removed, suppressed or converted from skips to passes.

## Credential and shell environment

Gemini credential precedence is **SUDARSHAN_API_KEY**, then legacy
ODYSSEUS_API_KEY, then generic GEMINI_API_KEY. Empty values fall back.
Tests mock the environment and require no actual key.

Core Bash and LocalExecutionBackend both use safe_shell_environment() from
sudarshan/environment.py. Only PATH, PATHEXT, COMSPEC, SYSTEMROOT, WINDIR,
TEMP and TMP are inherited, with case-insensitive name matching. All other
parent variables are excluded, including provider API keys, unknown credentials,
agent sockets, HOME/USERPROFILE and shell/Python startup-hook variables.
The parent environment is not mutated; provider authentication remains available.
Real-shell tests check direct children and descendants with synthetic credentials.

This is environment filtering, not credential isolation from the OS account.
Allowed runtime paths must be trusted. Files, shell startup configuration, command
arguments and OS services can still expose secrets. No assertion of complete shell
security or sandboxing follows from the allowlist.

## CLI contract and approval risk

Current source defaults to safe for Policy(), Harness(), and interactive and
headless CLI runs. This cleanup does not change that contract. The earlier
headless yolo default was explicitly changed in commit 067ed56 and is historical.
Scripts should specify --mode explicitly when depending on approval behavior.

**Headless --mode yolo skips approval for ordinary operations and is not a sandbox.**
It retains hard-deny checks but does not restrict filesystem, network or process
access. Safe also provides approval checks rather than OS isolation. Without a
library approver, restricted operations are declined; CLI EOF/blank approval is
declined. Raw backend methods require caller policy enforcement.

## Destructive-command inspection

Hard-deny rules precede approval in safe, read-only and yolo. Existing rules cover
broad rm root/home variants, sudo, mkfs, dd if=, curl piped to sh/bash,
git push --force and redirection to /dev/sd devices.

New documented patterns cover obvious root/home find deletion, including
find / -delete, find -L / -type f -delete, quoted root/HOME forms, root globs,
and find / -exec rm or -execdir rm. Common -H/-L/-P/-O options and chained
commands are covered by regression tests; backend Bash suffixes cannot bypass
these denials. Local find ./scratch -type f -delete and root listing still
follow ordinary policy. Tests inspect dangerous strings; they do not execute deletion.

Inspection uses conservative regular expressions and shell tokenization, not a
complete shell parser. It can produce false positives and can miss alternate
path spellings, multiple roots, aliases, shell expansions, nested interpreters,
indirect execution and other destructive programs. It never proves arbitrary
commands safe and does not normalize the actual executed command. Untrusted
commands need appropriately isolated OS execution.

## Product acceptance

| Product | Live build/review evidence | Independent verification | Status |
| --- | --- | --- | --- |
| Artisan Coffee | Not established | Not completed | Incomplete |
| Taskman | Not established | Not completed | Incomplete |
| Viper | Not established | Not completed | Incomplete |

No live product fleet was run for this cleanup. Mocked orchestration tests prove
session/skill/event plumbing only. No provider, SSH, Docker or browser integration
was performed. Product counts, responsive layouts, controls, generated Taskman
tests and Viper gameplay remain unverified. No product result or turn count is
fabricated. Production readiness is not established.
