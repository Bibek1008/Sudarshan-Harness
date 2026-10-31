# SUDARSHAN current audit — 31 October 2026

This report describes current source rather than treating repaired historical
findings as outstanding defects. Earlier snapshots remain in Git history.

## Current repairs

Exact core read identities are trusted; suffixes and custom overrides do not
inherit read authority. Exclusive session creation prevents frozen-second filename
collisions while preserving slug limits and append/load/latest behavior. Session
recovery durably handles torn tails and incomplete tool-call suffixes. Provider
parsing rejects empty/unusable candidates, retains valid responses/signatures and
usage defaults, and avoids echoing raw HTTP bodies or network exceptions.
The original dice Tool demonstration is restored and has import/execution coverage.

## Execution backend review

- Local filesystem operations resolve traversal/symlink targets, with a remaining
  resolve/open race. Shell cwd is not confinement. Descendant processes can outlive
  a shell timeout. Custom Python tools remain trusted application code.
- SSH validates connection tokens, uses strict host-key checking and quotes remote
  helper arguments. Remote cwd is not isolation; timeout/disconnect does not prove
  remote process termination. Tests use mocks, not a live host.
- Docker uses no network, a read-only root, dropped capabilities, no-new-privileges,
  non-root defaults, CPU/memory limits and a workspace mount. It rejects option-like
  image names, explicit root configurations and comma-ambiguous mount paths.
  Timeout cleanup targets the generated container name and reports unconfirmed
  cleanup. It never falls back to local execution.
- Docker is not an absolute guarantee: shared kernel, daemon authority, selected
  images, mount contents and cleanup/runtime failure remain relevant. A named
  container user must resolve to a nonzero UID; configuration cannot prove that.
- Policy cannot authenticate arbitrary Python callable identities from a name alone.
  Harness handles registered custom overrides; direct callers remain responsible.
- Sessions are single-writer; exact modification-time ties in latest() have no
  defined ordering. A repaired interruption record does not prove no prior effect.

## Product fleet integration update

- 601cb48 blocks lexical root-equivalent rm/find deletion targets, including
  /tmp/.. and /var/.., while preserving legitimate local cleanup.
- c098d16 adds explicit per-project safe-mode approval for core file edits,
  the required design skill and fixed unittest commands. The test callable uses
  shell=False, the current interpreter, filtered environment and bounded timeout.
  Ordinary Harness and CLI defaults are unchanged. Unknown tools, arbitrary
  shell commands and edits outside the project or to reserved state are refused.
- 831ca6c separates model completion from artifact gates, records failed projects,
  adds bounded repair phases and resumes original sessions for review and repair.
  Every project is independently inspected after the final review. Model reports
  cannot establish acceptance or clear required external/manual checks.
- Filesystem tool confinement is not OS isolation. Generated tests still have the
  host account's authority; a restricted command list cannot make Python safe.
  HTML checks are static prerequisites, not browser gameplay/layout verification.
- All integration tests now use the actual approval factory. The orchestration
  fixture no longer substitutes a permissive Harness policy. It is now tracked.
- No live Gemini build was attempted. All three products remain incomplete.

## Verification evidence

- User-supplied verification result (environment not reproduced here): **73 passed, 0 failures,
  0 skipped**. This is supplied evidence, not an execution reproduced in this checkout.
- Latest local execution after fleet integration: **90 discovered, 89 passed,
  0 failures, 1 skipped** (Python 3.12 on Windows).
- The skipped symlink escape test raises Windows error 1314 because symlink creation
  privileges are unavailable. It is not counted as passed.
- Full command: `python -m unittest discover -v`; verbose log: fleet-integration-test-results.txt.
  The local discovery includes the now-tracked product-preparation fixture.
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
