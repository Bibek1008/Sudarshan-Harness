# Audit at cd4e807

Inspected tracked package modules, tests, demos, README, ignore rules, history,
and execution backends. Existing checkout is the cumulative `sudarshan` Git
repository; no separate `Sudarshan-Harness-main` upload was present.

Baseline: Python 3.12.10, 35 discovered tests, 34 passed, one Windows symlink
privilege skip. Worktree was clean. No Gemini credential is configured.

Working under existing tests: basic loop/tool integration, compaction wiring,
memory injection, skill loading, child construction, fleet success smoke check,
local execution and mocked SSH/Docker operation construction.

Reproduced before repair: turn exhaustion raises instead of wrapping up;
quoted HOME and root glob deletion bypass denial; load repairs only in memory
and retains invalid JSON; `.odysseus/` is ignored instead of `.sudarshan/`.

Additional findings: duplicate CLI final output; empty headless prompt selects
interactive mode; skills descriptions are parsed outside front matter; session
names can collide within a second; empty provider candidates cause IndexError.

Security limitations: shell working directories are not OS confinement. Local
and SSH shell commands can access their account's permissions outside the root.
Regex inspection is incomplete shell analysis. File resolve/open operations have
race windows. SSH host tokens beginning with '-' need validation. Docker timeout
currently kills the client without guaranteed container cleanup. Raw backend
calls do not invoke Policy. Arbitrary suffix-based policy read aliases are unsafe
for untrusted custom tool registration. These require separate hardening before
production use; passing unit tests is not a security certification.

Missing coverage: dedicated provider, core tools, CLI, fleet concurrency and
durable recovery regressions. Earlier '35 passed, 1 skipped' reports were wrong:
35 was the total, including the skip. Scripted pirate/memory replies demonstrate
prompt plumbing only, not live model compliance.

Day 5 missing: all three generated products, design skill in their workdirs,
actual build/review turns, same-session review evidence and browser interaction
verification. These cannot be marked passed using scripted provider output.
