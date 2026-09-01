# Observability and Evidence

Runtime OpenTelemetry integration begins in Phase 9 using `a2a-otel-kit`. Earlier phases establish the
privacy and provenance contract that telemetry must later carry without changing domain authority.

## Current routing evidence

Metadata-only routing evidence can include:

- request/correlation ID and workload;
- PDP decision ID plus policy ID/version/digest;
- authorized logical model group;
- model-registry digest;
- deterministic routing decision ID;
- ranking-policy version and digest;
- static `score_snapshot_id`;
- selected provider/model/deployment;
- machine-readable candidate rejection reasons.

`score_snapshot_id` identifies static/versioned ranking configuration. It is **not** benchmark
evidence. `benchmark_snapshot_id` remains unset until approved benchmark evidence is introduced in
Phases 10–11.

## Phase 6 resilience evidence

Phase 6 adds metadata sufficient to reconstruct bounded availability handling without storing payloads:

- ordered `fallback_sequence` of concrete deployments actually attempted;
- per-attempt deployment ID and attempt number;
- normalized outcome (`succeeded`, `transient_failure`, `permanent_failure`, `circuit_open`);
- normalized provider error category/status where applicable;
- bounded retry delay and attempt latency;
- per-deployment health/circuit counters/state.

Same-deployment retries are represented separately rather than duplicating a deployment in
`fallback_sequence`. Runtime health is mutable operational evidence, not static ranking/benchmark
evidence.

## Phase 8 streaming evidence

Phase 8 exposes a normalized public stream to the authenticated caller, but streaming payload content
is not automatically converted into observability evidence.

Metadata that can be reconstructed from the stream boundary includes:

- selected deployment and bounded fallback sequence;
- monotonic public stream sequence numbers;
- event categories (`response.started`, content/tool lifecycle, final usage, completion/failure);
- whether a terminal failure occurred before or after semantic output (`partial`);
- normalized terminal error category;
- final normalized token usage;
- cancellation/closure outcome as an operational lifecycle fact, without treating caller cancellation
  as provider failure.

Default logs/traces/evidence must **not** record the actual text deltas, structured-output payload,
tool argument deltas, completed tool arguments/results, or arbitrary SSE `data` values.

Provider response headers are not general evidence. The Phase 8 transport retains only the bounded
safe subset required by execution (`content-type`, `retry-after`).

## Streaming provenance boundary

Routing provenance may appear in `response.started` and terminal public events so the caller can
associate output with the governed decision. It may contain decision-scoped policy/registry/ranking and
selected/fallback identity metadata.

It must not contain:

- prompt/message content;
- completion/content deltas;
- structured payloads;
- tool arguments/results;
- provider/PDP/gateway credentials;
- Authorization headers;
- arbitrary provider response headers;
- raw provider error bodies.

A client disconnect closes the upstream stream but does not create provider-failure evidence. This is
important so later telemetry does not corrupt provider health metrics with consumer-side cancellation.

## Privacy boundary

Default evidence/telemetry remains metadata-only. SDK logging, FastAPI middleware, SSE transport,
exception serialization, retry/fallback handling, and future exporters must not implicitly capture
customer/model payloads.

`POST /v1/route/explain` follows the same rule: decision metadata only, no prompt/global inventory.
`POST /v1/generate` returns requested output to that caller but does not make the output eligible for
background telemetry capture by default.

## Future tracing

W3C trace context should eventually remain continuous across application → gateway → PDP/provider and
MCP/A2A boundaries without making `a2a-otel-kit` a domain dependency.

Phase 9 adds runtime OpenTelemetry and must preserve:

- PDP/PEP authority separation;
- metadata-only defaults;
- Phase 6 retry/fallback reconstruction;
- Phase 8 stream lifecycle/partial/cancellation semantics;
- no payload capture unless a later explicit, governed policy permits it.
