# ADR-0011 — Streaming Normalization

- Status: Accepted
- Date: 2026-09-01
- Phase: 8 — Streaming

## Context

The gateway already owns authorization, deterministic ranking, safe retry/fallback, structured-output
validation, and tool-call normalization. Streaming adds a new trust boundary because provider APIs emit
different event vocabularies, partial payloads, usage timing, terminal signals, and cancellation
semantics.

The existing synchronous JSON transport is deliberately bounded and simple, but it cannot guarantee
prompt upstream closure when an HTTP client disconnects from a long-lived stream. Streaming also makes
replay safety stricter: once semantic output has been observed by the caller, retrying or switching to
another provider can create a hybrid response that never existed at any single provider.

The governing authorization invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Streaming must not introduce a second routing or authorization authority.

## Decision

### Canonical event vocabulary

The public gateway stream uses exactly these normalized event types:

1. `response.started`
2. `content.delta`
3. `tool_call.started`
4. `tool_call.arguments.delta`
5. `tool_call.completed`
6. `usage.completed`
7. `response.completed`
8. `response.failed`

Every event has a positive monotonically increasing sequence number. Routing provenance is carried on
`response.started` and terminal response events; prompt/completion bodies are never added to routing
provenance.

### Authorization and ranking happen before SSE begins

`POST /v1/generate` authenticates the gateway credential, resolves trusted effective context, calls the
PDP, snapshots runtime health, and performs deterministic ranking before returning
`text/event-stream`.

Policy denial, invalid request contracts, ranking configuration failures, authorization invariant
violations, and absence of an eligible authorized streaming deployment therefore remain normal HTTP
errors and do not begin a provider stream.

The execution layer receives only the already-ranked bounded sequence. It never re-enumerates the
global model registry during retry or fallback.

### Streaming capability is explicit

A streaming request requires `Capability.STREAMING` in registry eligibility and verified
`ProviderFeatureSupport.native_streaming` in the selected adapter API family. Final normalized usage
also requires verified `streaming_usage` support.

OpenAI-compatible endpoints receive neither capability by assumption. Both remain explicit adapter
configuration opt-ins.

### Retry and fallback stop at semantic output

Retry/fallback is permitted only while no semantic output has become visible to the client.

Provider `response.started` alone does not cross the replay boundary. The first emitted content delta,
tool-call start, tool argument delta, or completed tool call does.

After that boundary, any provider failure terminates the stream as:

```text
response.failed(partial=true, retryable=false)
```

No same-provider retry or cross-provider fallback is allowed after semantic output. This preserves
ADR-0007 and prevents hybrid responses assembled from multiple provider executions.

### Structured output and tool calls remain provisional while streaming

Structured JSON text and tool arguments may arrive incrementally, but Phase 7 validation guarantees
still apply. A tool call becomes `tool_call.completed` only after complete JSON parsing and local schema
validation. Provider-native structured output is revalidated locally at completion.

The gateway never executes business tools.

### Usage is finalized exactly once

A successful normalized stream must emit one final `usage.completed` before `response.completed`.
Duplicate usage, usage before semantic output, completion before final usage, or an upstream EOF without
a normalized completion are invalid provider responses.

Provider success is recorded in runtime health before the gateway exposes `response.completed` to the
client.

### Cancellation closes upstream resources

Streaming provider adapters use a dedicated asynchronous SSE-over-HTTPS transport. Upstream response
and HTTP client ownership stay with the stream object and support explicit `aclose()`.

The API body wraps execution with `aclosing()`. Client disconnect/cancellation therefore closes the
normalized execution generator, which closes the provider generator and its upstream network stream.
Client cancellation is not recorded as a provider failure.

### SSE transport is bounded and sanitized

The transport requires absolute HTTPS endpoints, rejects URL userinfo and fragments, requires positive
timeouts, bounds one SSE event to 1 MiB, normalizes timeout/network failures, and exposes only safe
response headers (`content-type` and `retry-after`).

Provider credentials, arbitrary response headers, and raw provider error bodies are not surfaced.

### Provider-specific translation remains inside adapters

Native adapters translate their documented protocols into the canonical provider stream events:

- OpenAI Responses streaming;
- Anthropic Messages streaming;
- Gemini `streamGenerateContent`;
- explicitly opted-in OpenAI-compatible chat-completions streaming.

Gemini function calls require a real provider correlation ID; the gateway does not fabricate one.
Unknown or malformed normalized lifecycle transitions fail closed.

## Consequences

### Positive

- one stable public streaming contract across providers;
- deterministic replay boundary;
- authorization remains unchanged by provider failures;
- disconnect propagates to upstream closure;
- usage and partial-result semantics are explicit;
- structured output/tool validation remains consistent with Phase 7;
- provider quirks remain isolated in adapters.

### Trade-offs

- a provider/API family that cannot finalize usage is not eligible for normalized streaming;
- failures after visible output are terminal even when another authorized deployment is healthy;
- pre-stream preparation adds policy/ranking latency before the first SSE byte;
- current runtime health/circuit state remains process-local as decided in Phase 6;
- streaming timeout remains per provider attempt; Phase 8 does not silently redefine policy latency as
a total end-to-end execution deadline.

## Rejected alternatives

### Fallback after partial output

Rejected because it can concatenate outputs from different executions/providers and destroy response
provenance.

### Reuse the blocking JSON transport for SSE

Rejected because cancellation and upstream resource closure would not be reliably represented.

### Treat OpenAI-compatible streaming as universally supported

Rejected because compatibility claims do not prove event or final-usage semantics.

### Execute business tools in the gateway

Rejected because the gateway is a governed model-routing/execution boundary, not the business side-effect
runtime.

### Fabricate missing provider tool-call correlation state

Rejected because synthetic IDs/state would make continuation provenance unverifiable.
