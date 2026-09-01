# Observability and Evidence

Runtime OpenTelemetry integration begins in Phase 9 using `a2a-otel-kit`. Earlier phases establish the
privacy and provenance contract that telemetry must later carry without changing domain authority.

## Current routing evidence

By Phase 5, metadata-only routing evidence can include:

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

Phase 6 adds metadata sufficient to reconstruct runtime availability handling without storing payloads:

- ordered `fallback_sequence` of concrete deployments actually attempted;
- per-attempt deployment ID and attempt number;
- normalized outcome (`succeeded`, `transient_failure`, `permanent_failure`, `circuit_open`);
- normalized provider error category and bounded HTTP status where applicable;
- bounded retry delay;
- attempt latency;
- per-deployment request/success/transient-failure counters;
- timeout/rate-limit/server-error counters;
- consecutive transient failure count;
- circuit state (`closed`, `open`, `half_open`);
- coarse health status (`healthy`, `degraded`, `unhealthy`).

Same-deployment retries are represented in attempt evidence rather than duplicating a deployment in
`fallback_sequence`.

Runtime health is mutable operational evidence. It is deliberately distinct from static ranking
configuration and future benchmark evidence.

## Privacy boundary

Default evidence/telemetry must not contain prompts, completions, tool arguments/results, provider or
PDP API keys, Authorization headers, arbitrary customer payloads, or unsanitized external error
bodies.

Phase 6 attempt evidence therefore records normalized error codes/status only. It does not retain raw
provider error bodies or arbitrary response headers.

The route-explain endpoint follows the same rule: it returns decision metadata, not prompt content or
a global provider/model inventory.

## Future tracing

W3C trace context should eventually remain continuous across application → gateway → PDP/provider and
MCP/A2A boundaries without making `a2a-otel-kit` a domain dependency. Phase 9 adds runtime
OpenTelemetry; it must preserve the evidence/privacy semantics established here.
