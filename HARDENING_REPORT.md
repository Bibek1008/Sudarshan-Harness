# SUDARSHAN hardening report — current source

## Status

Implemented: explicit tool permissions, conservative rm and find denials,
provider-key precedence, collision-resistant session creation, durable recovery,
robust candidate parsing, credential-safe provider failures, restored dice demo,
shared minimal shell environment and safe defaults.

Tested locally: real local tool effects and shell environment probes; offline
provider, policy, session, CLI and mocked backend/orchestration regression suites.
Verified against a real provider in this cleanup: none.
Not verified: live products, browser interactions, SSH hosts or Docker runtime.

Core Bash shares the local backend's explicit environment allowlist. See the exact names and
scope below. Passing regression tests does not establish production readiness.

## Remaining limitations

Shell policy is incomplete inspection, not OS isolation. Local/SSH commands keep
their account's authority; cwd restrictions do not confine them. Filesystem
resolve/open races and descendant/remote process cleanup risks remain. Docker is
defense in depth, not an absolute guarantee, and exact-name timeout cleanup can
fail during daemon/runtime outages. Custom Python tools are trusted code.
Concurrent session writers are unsupported. Named container users and executable
search paths require trusted configuration.

Commit 8d61c87 adds the find denial patterns and regression cases. This cleanup
leaves the safe CLI default established in 067ed56 unchanged and explicitly
documents the risks of headless --mode yolo.

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
