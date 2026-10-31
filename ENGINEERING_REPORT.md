# Audit and repair delivery — partial acceptance

## A. Core harness

Provider serialization, thought signatures, key precedence, usage and retries:
covered by offline tests; live Gemini unverified. Loop and filesystem tools:
tested with real local effects and mocked replies. Context, memory and skills:
existing plumbing tests pass; mocked responses do not prove model compliance.
Sessions: torn-byte truncation, durable synthetic responses, idempotence and
continuation covered. Subagents: existing ephemeral-child tests pass. Harness:
existing registration/resume/persistence paths pass. CLI: defaults, headless,
approval, interrupt and single-output behavior tested. Fleet: actual three-thread
barrier verifies concurrency and ordered error/success results. Local execution:
tested. SSH and Docker: mocked only, with unresolved risks below.

## B. Critical repairs

All four were reproduced with failing tests before implementation.

| Defect | Root cause and correction | Regression result |
| --- | --- | --- |
| Turn limit raised | Terminal raise replaced with wrap-up user message and exactly one tool-free call; unsolicited final calls discarded | Passed |
| Quoted HOME deletion allowed | Raw regex did not match quoting/root globs; normalize quotes for inspection, validate input/quoting, expand destructive target patterns | Passed across all three modes, before approval |
| Recovery not durable | load repaired only its return value; now truncate invalid bytes, fsync valid boundary, append/fsync missing results | Passed including repeated load and continuation |
| Wrong ignored directory | .odysseus replaced by .sudarshan | Test and git check-ignore passed for nested project sessions |

CLI additionally fixes duplicate final printing, empty -p interpretation and
headless interrupt exit 130. Public API names remain unchanged.

## C. Security

Hard-deny covers requested rm flag/quote/root forms, sudo, mkfs, dd if=,
curl piped to sh/bash, force push and device redirection. Malformed input fails
closed. Policy permits read tools, asks for effects in safe mode, and preserves
hard-deny in yolo. This is conservative inspection, not complete shell parsing.
Untrusted custom tool registration is not safe; suffix aliasing can classify a
custom tool as read-only. Local/SSH cwd does not confine shell permissions.
Resolve/open races, SSH option-like host validation, Docker timeout cleanup and
remote process termination remain hardening work. Docker is defense in depth.
No claim of production readiness is made.

## D. Executed checks

Baseline: 35 discovered, 34 passed, 0 failed, 1 skipped.
Final: 54 discovered, 53 passed, 0 failed, 1 skipped.
Skip: Windows lacks privilege to create a real symlink.
Commands: python -m unittest discover -q; python -m sudarshan --help;
git diff --check; git check-ignore on nested session path.
CLI imports work. Product runner compiles; actual invocation fails at missing
credential preflight, before creating workspaces. No live provider, SSH or
Docker integration was run. Required coverage is improved but not exhaustive;
additional harness compaction, custom-tool, backend lifecycle and session
collision tests are still needed.

## E. Product results

| Project | Pass/Fail | Build turns | Review turns | Contents |
|---|---|---:|---:|---|
| artisan-coffee | Fail — not built | 0 | 0 | No generated product |
| taskman | Fail — not built | 0 | 0 | No generated product |
| viper | Fail — not built | 0 | 0 | No generated product |

Zero turns reflect credential preflight failure, not successful empty runs.
demos/product_fleet.py prepares the required verbatim skills, independent
workdirs, persistent sessions, build/review fleet phases and turn recording.
The runner itself has not completed a live run. No product or review pass is
claimed. Independent HTML-aware counting, browser controls/game checks and
Taskman subprocess testing remain required, followed by another repair pass
for every failed product.

## F. New Git milestones

- 8ec5312: loop wrap-up, initial audit, defect reproductions.
- 590e8eb: conservative command denial fixes.
- f91b4c3: durable session repair.
- a98d802: correct session ignore rules.
- 19eeee8: CLI fixes, provider and concurrent fleet regressions.
- 262ca85: loop and filesystem tool regressions.
- Final documentation/preparation commit: this report, expanded README,
  live product fleet runner, malformed-command and UTF-8 recovery tests.

## G. Remaining work

Configure a replacement Gemini key locally; a credential posted in chat should
be revoked and is not copied into this repository. Execute live builds/reviews,
verify products independently, run any required additional review, record real
turn counts and commit accepted products. Resolve the security and coverage
gaps listed above. Also address second-resolution session-name collisions,
provider empty candidates, skill front-matter scope and recovery of historical
incomplete call sequences. Final acceptance has NOT been achieved.
