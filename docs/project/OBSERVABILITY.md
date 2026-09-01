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
- selected provider/model/deployment when eligible;
- machine-readable candidate rejection reasons.

`score_snapshot_id` in Phase 5 identifies static/versioned ranking configuration. It is **not** an
empirical benchmark snapshot. `benchmark_snapshot_id` remains unset until approved benchmark evidence
is introduced in Phases 10–11.

Later execution/resilience evidence may add retry/fallback sequence, provider usage, latency, outcome,
health/circuit state, and eventually a genuine benchmark snapshot identifier where applicable.

## Privacy boundary

Default evidence/telemetry must not contain prompts, completions, tool arguments/results, provider or
PDP API keys, Authorization headers, arbitrary customer payloads, or unsanitized external error
bodies.

The Phase 5 explain endpoint follows the same rule: it returns routing/selection metadata, not prompt
content or a global provider/model inventory.

## Future tracing

W3C trace context should eventually remain continuous across application → gateway → PDP/provider and
MCP/A2A boundaries without making `a2a-otel-kit` a domain dependency. Phase 9 adds the runtime
OpenTelemetry implementation; it must preserve the evidence and privacy semantics established here.
