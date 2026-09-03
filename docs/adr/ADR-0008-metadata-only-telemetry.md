# ADR-0008 — Metadata-only Telemetry

- Status: Accepted
- Date: 2026-09-03
- Phase: 9 — OpenTelemetry

## Context

The gateway now has deterministic policy authorization, operational ranking, bounded retry/fallback,
structured-output/tool normalization, and governed streaming. These decisions already produce
metadata sufficient to reconstruct why a deployment was selected and how execution progressed.

Phase 9 must make that evidence observable without creating a second source of authorization, leaking
customer/model payloads, or coupling provider-neutral contracts/domain logic to OpenTelemetry.

The repository already owns `a2a-otel-kit`, whose current boundary provides explicit lifecycle,
W3C trace-context propagation, deny-by-default attribute sanitization, and an `Observability` facade.
Creating a second telemetry framework inside the gateway would duplicate lifecycle/privacy semantics
and increase the chance that the gateway and downstream agent/A2A/MCP runtimes diverge.

The core authorization invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Telemetry is evidence only. It has no routing, ranking, health, retry, fallback, or authorization
authority.

## Decision

### Reuse `a2a-otel-kit` as the telemetry foundation

Phase 9 depends on `a2a-otel-kit==0.6.0` at runtime rather than introducing a second tracing harness.
The gateway injects an `Observability` instance at composition/application boundaries. Importing the
package does not configure a global tracer or perform network I/O.

`gateway-contracts` and `gateway-core/domain` remain free of both `a2a_otel_kit` and
`opentelemetry`. The architecture gate explicitly rejects either dependency in those layers.

### Metadata is allowlisted, payloads are denied

The gateway extends the `a2a-otel-kit` sanitizer with a small Phase 9 allowlist for routing/execution
metadata. Eligible attributes include:

- workload;
- routing decision ID;
- policy ID/version/digest;
- authorized logical model group;
- registry digest;
- ranking policy version/digest and static score snapshot ID;
- selected provider/model/deployment;
- attempt/fallback counts;
- normalized input/output token counts;
- latency and streaming TTFT;
- streaming/partial flags;
- bounded retry delay;
- stable normalized error categories and HTTP status where already available.

Default telemetry must not contain:

- prompts/messages;
- completions/content deltas;
- structured-output payloads;
- tool argument deltas, completed arguments, or tool results;
- JSON Schema/tool definition bodies;
- provider/PDP/gateway credentials;
- Authorization/cookie/arbitrary request headers;
- arbitrary provider response headers;
- raw provider/PDP error bodies;
- remote exception messages or stack traces that can contain payload data.

External policy/provider/gateway boundaries therefore create spans with `record_exception=False` and
set only a stable sanitized error category/status on failure.

### Canonical span topology

Phase 9 uses these primary span names:

```text
llm.gateway.request
  ├─ policy.route
  └─ provider.inference
```

For a streaming response, the pre-stream governance span must still end before the long-lived SSE body
is consumed so Phase 8 HTTP/pre-stream semantics remain explicit. The gateway captures the W3C context
of `llm.gateway.request`, ends that span, then continues it in:

```text
llm.gateway.request
  └─ llm.gateway.stream
       └─ provider.inference
```

The stream span therefore remains in the same trace and becomes the parent for provider attempts during
SSE execution. It does not change authorization or replay semantics.

### Retry and fallback are span events

Each concrete provider attempt receives its own `provider.inference` span. Same-deployment retry and
cross-deployment fallback are represented as bounded metadata-only events:

- `llm.gateway.retry`;
- `llm.gateway.fallback`.

The event payload includes only attempt/deployment/count/delay metadata. Provider error messages and
request/response content are excluded.

`llm.latency_ms` records provider-attempt latency. Backoff is operational evidence and must not be
interpreted as model inference latency.

### Streaming metrics remain content-free

Streaming provider spans may record:

- TTFT measured at the first semantic content/tool event;
- final input/output token usage;
- total provider-attempt latency;
- whether a terminal failure followed partial semantic output.

The actual semantic event content is never copied into traces.

Client cancellation is represented as `outcome=cancelled` and continues to be excluded from provider
failure/health accounting.

### W3C context propagation is narrow and explicit

The API accepts only the W3C `traceparent` and optional `tracestate` headers for trace continuation.
Arbitrary inbound headers are not forwarded as telemetry or provider/PDP metadata.

The shared JSON and SSE transports inject the current W3C context into outbound PDP/provider requests.
This preserves one trace across application → gateway → PDP/provider while keeping provider credentials
and transport-specific headers outside exported telemetry.

Propagation uses the stateless `a2a-otel-kit` W3C helpers; Phase 9 does not install a process-global
propagator as a side effect of import.

### Telemetry is optional at execution boundaries

Application services keep their existing behavior when no `Observability` instance is supplied. This
preserves deterministic tests and avoids making tracing availability a hidden routing prerequisite.

Exporter/configuration lifecycle belongs to the composition/deployment boundary. The gateway does not
turn telemetry exporter health into policy, ranking, retry, fallback, or provider-health state.

## Consequences

### Positive

- one trace can span caller, gateway, PDP, provider, and later A2A/MCP boundaries;
- routing and fallback evidence becomes operationally searchable without prompt storage;
- privacy behavior is centralized and deny-by-default;
- the gateway reuses the same tracing foundation as the broader agentic ecosystem;
- provider/policy remote error text cannot enter spans through automatic exception recording;
- contracts/domain remain telemetry-framework independent.

### Trade-offs

- payload-level debugging is intentionally unavailable in default traces;
- some provider-specific diagnostic detail is reduced to normalized categories;
- streaming uses a separate child span after pre-stream governance so a long-lived SSE response does
  not keep the request-preparation span open;
- application/API layers now have a runtime dependency on the shared observability facade even though
  contracts/domain do not.

## Rejected alternatives

### Record prompts/completions with redaction

Rejected. Redaction is not a sufficiently strong default boundary for regulated or confidential data,
and it would make telemetry correctness depend on payload inspection.

### Automatic `record_exception=True` at external boundaries

Rejected because exception strings and traceback context can include raw provider/PDP payloads.

### Global OpenTelemetry configuration at import time

Rejected because library imports must not create exporter/network side effects or make tests/processes
share implicit telemetry state.

### Add tracing fields to provider-neutral contracts/domain

Rejected because telemetry is an operational concern and must not contaminate authorization/business
contracts.

### Rebuild tracing instead of using `a2a-otel-kit`

Rejected because the existing shared kit already owns lifecycle, sanitization, and W3C propagation and
is intended for reuse across gateway/A2A/MCP boundaries.
