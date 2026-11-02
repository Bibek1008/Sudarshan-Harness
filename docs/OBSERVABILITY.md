# Observability and diagnostics

For setup and the distinction between transcript filenames and telemetry UUIDs,
see [Getting started](GETTING_STARTED.md). See [security](SECURITY.md) for current
privacy/isolation limits and the [final report](../FINAL_PROJECT_REPORT.md) for
release validation; the Phase 4 report retains its historical results.

Sudarshan records local, metadata-only telemetry using the standard library.
It does not send telemetry to a service. Durable Harness runs enable telemetry by
default; persist=False runs default to disabled unless telemetry=True is supplied.
Ephemeral children inherit the parent's explicit setting and have separate telemetry
session UUIDs. Each Harness.run is a new telemetry session, including resumed agent
conversations. No transcript-derived label is used as an identifier.

## Privacy boundary and compatibility

The existing assistant/tool callbacks and transcript JSONL format remain unchanged.
Those transcripts are separate, may contain prompts and tool contents, and retain
their existing recovery semantics. Telemetry opt-out does not disable transcripts.
The new collector accepts only the documented metadata fields. It never receives
prompts, arguments, tool outputs, file contents, thought signatures or exception
messages. CLI stats/trace reject records with unknown fields instead of echoing them.
Model/tool labels are bounded identifier strings: callers must treat those public
identifiers and pricing provenance as metadata, never put secrets in their names.
This is an allowlisted schema, not universal secret discovery or an OS sandbox.

## Schema version 1

Every JSONL record contains schema_version=1, event_id (UUID), session_id (opaque
UUID), timestamp (timezone-aware UTC ISO 8601), event_type, turn (0 before the first
turn), model (bounded identifier), and status. Status is started, success, failed,
denied or interrupted. Optional fields are duration_ms, sanitized error_category,
request_id, call_id, tool, backend, approval, usage and cost. No free-form message,
exception detail, URL, argument or payload field is accepted. IDs correlate model
requests/retries and tool lifecycle/approval decisions. Timestamps are wall-clock
UTC; request/tool durations use monotonic timing. Trace preserves append order.

Event categories: session_started, session_completed, session_interrupted,
model_request_started, model_request_completed, model_request_failed, model_retry,
tool_call_started, tool_call_completed, tool_call_failed, tool_approval_requested,
tool_approval_granted, tool_approval_denied, context_compacted, turn_completed and
execution_timeout. A failed session uses session_completed with status=failed;
a raised interrupt uses session_interrupted. A process crash without a terminal
record is reported as incomplete_or_interrupted; no success is synthesized.

Example (metadata only):

```json
{"schema_version":1,"event_id":"f3f9ef89-6e23-4101-839b-79c252a533b1","session_id":"0a35d4ed-4e41-46de-b532-497ef971dc45","timestamp":"2026-11-01T12:00:00+00:00","event_type":"turn_completed","turn":1,"model":"example-model","status":"success"}
```

Tool names and explicit adapter backend identities are recorded, not commands.
Core file/shell tools identify as local; ordinary custom tools identify as
in_process unless they explicitly provide execution_backend metadata. Structured timeout
exceptions and existing ERROR/BLOCKED result conventions classify failures. Arbitrary
custom tool strings cannot always be classified correctly. Denied calls are counted
separately from execution failures. Safe-mode approval checks emit requested/granted
metadata through the existing Policy decision points. Permanent/read-only denials
and unknown tools remain governed by the unchanged policy.

## Actual token measurements

Gemini response usageMetadata maps promptTokenCount, candidatesTokenCount,
totalTokenCount, thoughtsTokenCount and cachedContentTokenCount to input, output,
total, thought and cached. Only nonnegative integer counts are accepted, excluding
booleans and numeric strings. Each unavailable count is null; available means at
least one measured field exists. Total is never inferred by adding other fields.
The legacy usage.input/output interface remains for compatibility; use the additive
usage_details interface for availability-aware accounting. Legacy missing-field zeros
are never consumed by telemetry.

One logical request has one request_id across transport retries. A retry event adds
no usage. Only successful reported responses contribute actual counts, and request
IDs/event IDs are deduplicated in summaries. Failed/unreceived responses have unknown
usage and can still incur provider-side charges. Compaction requests are accounted
separately; the context module's pre-existing character-based budget estimate is not
an actual usage measurement. Session token_coverage reports measured and successful
request counts for each field. Aggregate values are sums of known measurements;
nulls are not secretly converted to measured zeros.

## Optional estimated costs

Invalid pricing files disable estimates, not the other metrics. No real prices are
bundled and no network pricing lookup occurs. Without valid local
configuration, cost is null/unavailable, including when measured usage is zero.
Create .sudarshan/telemetry/pricing.json with entries keyed by exact model name.
Each entry requires input_per_million and output_per_million (nonnegative decimal
strings), currency (three uppercase letters), source (nonsecret provenance identifier
or URL without query parameters), effective_date (YYYY-MM-DD), and thought_policy.
Supply cached_per_million when cached counts are nonzero.

Template: replace all RATE placeholders with independently verified current rates;
this template is deliberately not executable pricing:

```json
{"YOUR_MODEL":{"input_per_million":"RATE","output_per_million":"RATE","cached_per_million":"RATE","currency":"USD","source":"YOUR_VERIFIED_SOURCE","effective_date":"YYYY-MM-DD","thought_policy":"additional_output"}}
```

The estimator requires measured input/output/cache/thought counts. It subtracts
cached tokens from input before applying the ordinary input rate. additional_output
adds thoughts to candidate output for charging; included_in_output does not. Choose
the policy from the provider's documented billing/count semantics; Sudarshan does
not infer it. Cached counts exceeding input, invalid rates/dates, unspecified thought
policy or missing necessary counts make cost unavailable. Arithmetic uses Decimal.
Each request estimate retains source and effective date; these are provenance,
not a freshness guarantee. Estimates are never actual provider billing. Session and
cross-session estimates require available costs and a single currency; otherwise
they are null. Scope is successful reported requests only, excluding unknown failed
attempt billing. Rotation/corruption suppresses the full session cost estimate.

## Storage, concurrency and bounds

```
.sudarshan/telemetry/
  events/SESSION_UUID.jsonl
  events/SESSION_UUID.1.jsonl
  summaries/SESSION_UUID.json
  pricing.json
  settings.json
  .lock
```

Events are append-only within each segment, flushed/fsynced under a cross-process
lock (msvcrt on Windows, flock on POSIX). A bounded 10-second lock wait fails open
for the agent: telemetry_storage_failed is set without logging raw errors. Schema
programming errors are rejected. Summaries are atomic JSON snapshots written at run
completion; stats always recomputes from valid retained events rather than trusting
a stale cache. Unterminated tails get a newline before the next append. Corrupt lines
are counted/skipped on reading and left intact until normal rotation/retention.

Default bounds: 1 MiB per segment, four segments per telemetry session, 100 recent
sessions. settings.json may contain enabled, max_bytes (4096..16777216), segments
(1..16) and sessions (1..10000). Store constructor arguments can override those
retention bounds. Settings take effect at the next run/store creation; disabling
collection does not interrupt an already-running collector. CLI toggles preserve
configured retention values. Retention removes
only generated session event/summary files, never directories. All telemetry resides
under the existing ignored .sudarshan directory. Segments are processed oldest first;
rotated-away session starts or corrupt records mark reports partial. Counts are for
retained data, not lifetime measurements. Cross-session reports cover retained
sessions only. Abrupt crashes can leave a temporary summary file requiring manual
cleanup; normal write failures clean temporary files automatically.

POSIX files use 0600 and telemetry directories 0700 on creation. Windows inherits
host ACLs; no ACL hardening is claimed. Workspace escape/link checks are performed,
but hostile local filesystem owners can still race metadata paths. Original agent
execution controls are not modified by telemetry.

## CLI

```console
python -m sudarshan stats
python -m sudarshan stats --session SESSION_UUID
python -m sudarshan stats --last 10 --json
python -m sudarshan trace --session SESSION_UUID
python -m sudarshan trace --session SESSION_UUID --json
python -m sudarshan telemetry --disable
python -m sudarshan telemetry --enable
python -m sudarshan --no-telemetry -p "Your task"
```

Use -d WORKDIR to select a workspace. Diagnostics never instantiate a model or make
API calls. stats lists opaque session IDs, timing/status, request/tool/retry counts,
actual measured token fields and optional estimated costs; JSON includes detailed
coverage, error/timeout counts and aggregation. Missing data is a normal empty
result. Invalid UUIDs, settings or inaccessible files produce a generic error and
exit 1 without raw file contents; argument errors exit 2. Reads do not execute or
repair original transcript sessions. Library callers use Harness(..., telemetry=False)
for hard opt-out and inspect last_telemetry_session/telemetry_storage_failed.

## Verification

Run python -m unittest tests.test_observability -v for deterministic mocks, schema,
privacy, usage/cost, corruption, rotation, CLI, thread/process concurrency and recovery
checks. No real Gemini request or real credential is used. See the Phase 4 report
for executed results and unverified platform limitations.
