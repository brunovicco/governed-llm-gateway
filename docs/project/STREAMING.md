# Streaming

Phase 8 adds provider-neutral streaming without changing the authorization boundary established in
Phase 4.

```text
PDP-authorized candidates
        ↓
Phase 5 deterministic ranking
        ↓
Phase 6 runtime health + bounded resilience
        ↓
Phase 8 normalized streaming
```

At every step:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Public API

`POST /v1/generate` is an authenticated SSE endpoint.

Required header:

```text
X-Gateway-API-Key: <credential>
```

The request includes:

- schema version `1.0`;
- request ID;
- dotted workload ID;
- caller-declared risk/data classification;
- messages;
- capability requirements;
- optional tool definitions;
- optional structured-output schema;
- context-token estimate;
- max output tokens;
- optional caller cost/latency ceilings;
- bounded provider timeout.

The endpoint itself is streaming-only. `stream` is fixed to `true`, and the resulting
`GatewayRequest.requirements.streaming` is always true.

Tool-result continuation is rejected before SSE begins because Phase 7 deliberately does not fabricate
provider-native continuation/reasoning state.

## Pre-stream gate

Before returning `200 text/event-stream`, the API completes:

1. gateway credential resolution;
2. trusted effective-context resolution;
3. Policy Router authorization;
4. runtime-health snapshot;
5. deterministic eligibility/ranking;
6. existence of an eligible authorized streaming deployment.

This means failures such as authentication, policy denial, invalid schema/tool contracts, ranking
configuration failure, invariant violation, or no eligible streaming deployment remain ordinary HTTP
responses.

No provider execution begins during this preparation stage.

## Canonical SSE lifecycle

The gateway emits only these event names:

```text
response.started
content.delta
tool_call.started
tool_call.arguments.delta
tool_call.completed
usage.completed
response.completed
response.failed
```

Example framing:

```text
event: content.delta
id: 2
data: {"delta":"hello","event_type":"content.delta","request_id":"...","sequence_number":2}

```

JSON data is emitted with deterministic key ordering and compact separators.

## Sequence semantics

Sequence numbers are positive and monotonic within one public stream.

`response.started` is emitted only when the first semantic provider output is about to become visible.
A provider-native start event alone is internal and does not force a public event.

A successful text stream is typically:

```text
response.started
content.delta
...
usage.completed
response.completed
```

A tool-call stream can include:

```text
response.started
tool_call.started
tool_call.arguments.delta
...
tool_call.completed
usage.completed
response.completed
```

## Replay boundary

The replay boundary is crossed by the first semantic event:

- `content.delta`;
- `tool_call.started`;
- `tool_call.arguments.delta`;
- `tool_call.completed`.

Before that point, a retry of the same deployment or fallback to another already-ranked authorized
candidate may occur under the Phase 6 bounds.

After that point, retry/fallback is forbidden. A provider failure becomes:

```text
response.failed
partial=true
retryable=false
```

This prevents a single public response from silently combining multiple provider executions.

## Usage finalization

Normalized successful streaming requires exactly one final `usage.completed` before
`response.completed`.

The gateway treats the following as invalid provider lifecycle behavior:

- duplicate final usage;
- final usage before semantic output;
- completion before semantic output;
- completion before final usage;
- upstream EOF without normalized completion;
- unknown normalized provider event.

Provider health success is recorded before the public `response.completed` event is yielded.

## Structured output

Provider-native structured output may arrive as text deltas, but it remains provisional until the
provider completes the response.

The complete output is parsed and locally validated against the Phase 7 JSON Schema contract. Native
provider enforcement is not treated as sufficient evidence on its own.

Invalid structured output is a permanent execution failure and is not converted into availability
fallback.

## Tool calls

Tool arguments may be emitted incrementally, but `tool_call.completed` is emitted only after:

1. complete JSON assembly;
2. tool-name correlation with a declared tool;
3. local argument-schema validation.

The gateway never executes the business tool.

Provider correlation IDs are preserved. Missing required correlation state fails closed; it is not
fabricated.

## Provider adapters

### OpenAI Responses

Uses native Responses streaming events and normalizes text, function-call arguments, usage, and
terminal state.

### Anthropic Messages

Consumes the documented Messages event sequence. Partial `input_json_delta` fragments are accumulated
and validated when the content block closes. Provider/server-side tool activity not declared by the
gateway fails closed.

### Gemini

Uses `streamGenerateContent`. Function calls require provider correlation identity before they can be
normalized as gateway tool calls.

### OpenAI-compatible

Streaming is disabled by default. Adapter construction must explicitly opt in to verified streaming
semantics, and final usage support is a separate explicit opt-in.

## Transport and cancellation

Streaming uses `HttpxSseTransport`, separate from the bounded JSON transport used by non-streaming
calls.

Transport controls:

- absolute HTTPS URL required;
- URL userinfo rejected;
- fragments rejected;
- positive timeout required;
- one SSE event limited to 1 MiB;
- timeout and network errors normalized;
- only `content-type` and `retry-after` response headers retained.

The API body wraps the execution generator in `aclosing()`. When the HTTP client disconnects or the
body generator is cancelled, the provider generator is closed, which closes the upstream SSE response
and async HTTP client.

Client cancellation is not recorded as a provider failure.

## Health and fallback

Runtime health remains Phase 6 state. Streaming does not create a new authorization source.

The ranking preparation uses a deterministic health snapshot. Execution then rechecks circuit state
before each bounded attempt. An open circuit can therefore remove/skip a deployment without adding a
new candidate.

## Provenance and privacy

Routing provenance can include:

- policy decision ID/version/digest;
- authorized logical model group;
- registry digest;
- ranking policy/snapshot identity;
- selected provider/model/deployment;
- bounded fallback sequence;
- eligibility rejections.

It does not include:

- gateway/provider credentials;
- Authorization headers;
- arbitrary provider response headers;
- raw provider error bodies;
- prompt/completion content.

Streaming telemetry and OpenTelemetry instrumentation remain Phase 9 work.
