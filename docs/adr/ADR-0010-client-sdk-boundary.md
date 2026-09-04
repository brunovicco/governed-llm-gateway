# ADR-0010 — Client SDK Boundary

Status: Accepted  
Date: 2026-09-03

## Context

Phase 12 publishes the thin async Python client reserved by the Phase 0 workspace boundary.

The project roadmap requires the normal consumer experience to go through the gateway rather than
provider SDKs or provider credentials. Consumer applications should declare the workload and request
requirements while the gateway remains responsible for policy authorization, model selection,
provider execution, retry/fallback, circuit breaking, and routing provenance.

The existing runtime already exposes governed generation through `POST /v1/generate` as normalized
SSE. The provider-neutral contracts package already owns `GatewayRequest`, `GatewayResponse`,
`GatewayStreamEvent`, `RoutingProvenance`, tools, structured-output definitions, and controlled
vocabularies.

The client therefore must remain transport-only. It must not become another routing or resilience
implementation.

## Decision

Phase 12 implements `gateway-client` as a thin asynchronous HTTP/SSE transport over the existing
gateway API and provider-neutral contracts.

### Dependency boundary

The client package may depend on:

- `gateway-contracts`;
- a small HTTP transport dependency (`httpx`);
- Python standard-library modules.

It must not depend on:

- `gateway-core`;
- `gateway-api` internals;
- provider SDKs;
- Policy Model Router;
- benchmark/promotion code;
- provider configuration or credentials.

Consumer projects receive only the gateway URL and gateway credential. Provider credentials remain
server-side.

### Public lifecycle

`GatewayClient` owns one reusable async HTTP client and supports explicit `aclose()` plus async context
manager lifecycle.

`GatewayClient.from_env()` reads the canonical gateway connection environment variables:

- `GOVERNED_LLM_GATEWAY_URL`;
- `GOVERNED_LLM_GATEWAY_API_KEY`.

Missing or malformed configuration fails before a network request. The gateway API key is excluded
from dataclass/client representations and is never included in client exception text.

### Transport security

The initial client accepts only absolute HTTPS gateway base URLs with a host. URL userinfo, query
strings, and fragments are rejected. Redirect following is disabled so the gateway credential cannot
be forwarded implicitly to another origin.

The client sends the credential only as `X-Gateway-API-Key` to the configured gateway endpoint.
Environment-derived proxy/client settings are disabled. The client requests `Accept-Encoding:
identity` and rejects non-identity encoded SSE responses before consuming their body, so bounded
stream accounting cannot be bypassed by transparent decompression.

HTTP/network errors are normalized into client-specific exceptions containing only stable status/code
metadata. Error-body reads are bounded, and non-identity encoded or oversized error bodies are not
parsed or surfaced through exception messages.

### Streaming contract

`stream(...)` performs exactly one `POST /v1/generate` request with `stream=true` and yields validated
`GatewayStreamEvent` objects.

The SSE parser is bounded and incremental. It validates:

- maximum event size;
- maximum total stream size, with a finite configurable safety ceiling;
- response content length when present;
- identity-only content encoding;
- UTF-8 and JSON syntax;
- duplicate JSON keys;
- SSE event/id consistency with the JSON payload;
- exact request-ID correlation with the request sent by the client;
- deterministic positive/contiguous sequence numbers;
- known provider-neutral event/routing/error fields;
- terminal completion/failure semantics.

A normal connection close before `response.completed` or `response.failed` is a protocol failure.

### Convenience generation

`generate(...)` consumes the same normalized stream once and aggregates it into a
`GatewayResponse`:

- content is the ordered concatenation of `content.delta` events;
- completed tool calls are preserved;
- terminal `RoutingProvenance` is preserved exactly;
- `response.completed` maps to `ExecutionStatus.SUCCEEDED`;
- `response.failed` maps to `ExecutionStatus.FAILED` with the normalized `GatewayError`;
- no provider-execution latency is fabricated when it is not present in the SSE contract.

The first client does not infer structured output from text and does not synthesize provider-native
continuation state.

### No client-side retry or fallback

The client performs no automatic retry, fallback, model selection, provider selection, circuit
breaking, or policy decision.

A transport failure is returned to the consumer after the single attempt. This is deliberate: retry
and fallback semantics remain owned by the governed server-side execution path, including the replay
safety rules established in Phases 6–8.

### Explicit request context

The client may provide ergonomic defaults for transport-only values such as request UUID, output-token
ceiling, and provider timeout, but it does not silently invent trusted authorization facts.

Risk level and data classification remain explicit caller inputs to the initial `generate`/`stream`
methods. The server continues to derive/validate effective policy context from authenticated identity.

### Provenance visibility

The client reconstructs the complete routing provenance returned by the gateway, including Phase 11
fields when present:

- policy decision/version/digest;
- authorized model group;
- model registry digest;
- ranking policy version/digest;
- score snapshot identity;
- benchmark snapshot identity;
- score-provenance mode;
- manual override identity;
- provider/model/deployment;
- rejection evidence;
- fallback sequence.

The client does not interpret these fields as authorization. They are inspection/reconstruction
evidence only.

## Consequences

Positive:

- consumer projects need no provider SDK or provider API key;
- one provider-neutral SDK surface replaces provider-specific transports;
- retry/fallback semantics remain centralized and governed;
- consumers can inspect routing provenance without importing gateway runtime code;
- streaming and convenience generation share one protocol implementation;
- credentials and malformed gateway responses fail through a narrow, auditable boundary.

Trade-offs:

- the first convenience `generate` aggregates the existing SSE endpoint rather than using a separate
  non-streaming JSON endpoint;
- consumers must explicitly close long-lived clients or use `async with`;
- strict protocol validation can reject forward-incompatible server fields until the client contract is
  intentionally evolved;
- risk/data-classification inputs remain explicit rather than using potentially unsafe convenience
  defaults.

## Rejected alternatives

### Use provider SDKs inside consumer projects

Rejected because it would distribute provider credentials, model identifiers, retry/fallback behavior,
and provider quirks into every consumer.

### Implement retry/fallback in the SDK

Rejected because the client cannot safely reproduce the gateway's authorization, health,
side-effect/replay, and provider-state boundaries. Duplicate retries could also conflict with the
server's own bounded retry/fallback behavior.

### Follow HTTP redirects automatically

Rejected because a gateway credential could be forwarded to an unintended origin.

### Accept compressed gateway streams transparently

Rejected because transparent decompression complicates bounded transport accounting and can turn a
small encoded response into a much larger decoded stream. The first client therefore requires
identity encoding and fails closed otherwise.

### Return raw SSE dictionaries

Rejected because consumers would need to duplicate protocol parsing and would lose the
provider-neutral immutable contract boundary.

### Fabricate `ProviderExecution` latency while aggregating SSE

Rejected because client-perceived request duration is not the same fact as provider execution latency.

### Default omitted data classification to `public`

Rejected because convenience must not silently weaken caller-declared security context.
