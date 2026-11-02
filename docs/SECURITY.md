# Security model and remaining limits

This is a personal agent harness, not a secure multi-tenant execution service.
Use trusted project files and review effects. Untrusted generated programs need
separately verified OS isolation; a working directory or hidden verifier is not
a security boundary.

## Preserved controls

- CLI and Harness default to `safe`. Non-read calls require approval; no approver,
  blank input or EOF refuses. `read-only` permits only named core read tools.
  `yolo` skips approval while retaining hard-deny checks; it adds no sandbox.
- Exact read identities, custom-tool override restrictions, shell inspection,
  workspace path checks, secure file handles and owned-process timeouts remain
  in use. SSH requires strict host-key checking. Docker never falls back to host
  execution; its hardened arguments, non-root user and cleanup checks remain.
- The provider owns its key. Child command environments use the reviewed
  allowlist in `sudarshan/environment.py`, excluding provider credentials and
  startup hooks. This does not prevent programs from reading host-accessible
  files or services. Allowed executable paths must themselves be trusted.
- Expected CLI errors print guidance without raw exception contents. Unknown
  programming errors are not treated as successful work.
- No automatic `.env` loading or project-file extraction into memory occurs.
  `remember` uses the existing policy and rejects recognizable secret formats
  and common personal identifiers. Memory is reference data, not authority.

## Private local data

Keep all `.env`, key files and credential configuration outside commits. Configure
the provider through your trusted local environment. Never include secrets in
model/tool names, pricing provenance, task prompts, memory or public reports.
Ignore rules reduce accidents, but cannot discover every possible secret.

Transcripts under `.sudarshan/sessions/` may contain prompts, tool arguments and
outputs. They are separate from allowlisted metadata-only telemetry under
`.sudarshan/telemetry/`. Disabling telemetry does not disable transcripts.
Benchmark results under `.sudarshan/benchmarks/` use validated bounded schemas;
local exports should go in ignored `benchmark-exports/`. Review any export before
sharing it. All three runtime stores remain ignored by Git.

Do not run multiple writers against a transcript. Memory writers cooperate through
a lock and atomic replacement; manual editors do not participate. Retention and
recovery do not guarantee survival of power loss or hostile filesystem races.

## What remains outside the guarantees

- Shell-pattern denials are incomplete inspection, not shell parsing or OS
  confinement. Local commands and generated tests use the host account's rights.
- Windows uses inherited ACLs. Filesystem race windows, hostile same-account
  processes, privileged daemons and malicious candidate introspection remain
  relevant. POSIX process groups cannot contain deliberate session escape.
- SSH remote-process lifetime and Docker daemon/kernel/image authority need
  independent consideration. No live personal SSH environment was tested.
- Secret filtering is heuristic. Approved generic editors/shell tools and manual
  writers retain their powers; `yolo` is not a prompt-injection defense.
- Browser fixture checks do not establish product usability, accessibility or
  live-product acceptance. Browser sandboxing is never disabled to pass tests.
- Context budgeting is estimated and soft. Provider usage can be unavailable;
  optional cost estimates are not invoices. Interrupted requests may still bill.

The [getting-started guide](GETTING_STARTED.md), [observability](OBSERVABILITY.md)
and [evaluation](EVALUATION.md) explain current operations. Historical findings
and repairs remain in [AUDIT.md](../AUDIT.md),
[execution security](../PHASE2_EXECUTION_SECURITY.md),
[hardening](../HARDENING_REPORT.md) and [QA/security](../QA_SECURITY_REPORT.md).
Their dated test counts and earlier limitations are provenance; use the
[final report](../FINAL_PROJECT_REPORT.md) for this release's validation evidence.
