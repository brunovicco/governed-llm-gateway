# ADR-0013 — Structured Output and Tool Normalization

Status: Accepted for Phase 7

Date: 2026-09-01

## Context

The gateway already owns provider-neutral model authorization, deterministic deployment selection,
and bounded execution resilience. Phase 7 adds structured-output and client-side business-tool
contracts without transferring business-tool execution authority into the gateway.

Provider APIs expose similar concepts through different wire formats. They also differ in schema
subsets, tool-call correlation, continuation state, and feature availability. Treating those APIs as
behaviorally interchangeable would weaken the provider-neutral contract and the replay-safety boundary
established in ADR-0007.

## Decision

### 1. Structured output is a native capability, not a prompting convention

`Capability.STRUCTURED_OUTPUT` means the selected deployment/API family can enforce a provider-native
schema contract. Prompt-only JSON generation is not treated as equivalent capability.

`StructuredOutputSchema` is the provider-neutral request contract. Provider adapters translate it only
when their API family has explicit native support.

Provider output is parsed and validated again inside the gateway even when the provider reports native
schema enforcement. Invalid JSON or schema mismatch becomes typed
`invalid_structured_output` and fails closed.

### 2. Schema evaluation is local, bounded, and intentionally subsetted

Caller-supplied schemas are untrusted input. Before network execution the gateway:

- validates Draft 2020-12 schema syntax;
- limits serialized schema size to 64 KiB;
- limits recursive schema depth;
- rejects remote `$ref` and `$dynamicRef` resolution;
- permits local fragment references only;
- rejects `pattern` and `patternProperties` in Phase 7 rather than evaluating caller-controlled regular
  expressions;
- rejects `format` in Phase 7 rather than accepting a constraint that the default validator would not
  enforce.

The gateway never performs network retrieval while validating a schema. Phase 7 therefore implements
a documented safe subset of Draft 2020-12 rather than claiming unrestricted schema compatibility.

Property names such as `pattern` remain valid; the restriction applies to JSON Schema keywords, not
ordinary object-property names.

### 3. Business tools remain outside gateway execution authority

`ToolDefinition`, `ToolCall`, and `ToolResult` are canonical provider-neutral contracts.

The gateway may:

- send declared tool definitions to a supported model API;
- normalize a provider-produced tool call;
- validate tool identity and arguments against the declared input schema;
- return the normalized `ToolCall` to the caller.

The gateway must never invoke the business tool. Authorization and execution of business tools remain
with the application, agent runtime, or MCP layer.

`ToolResult` is the canonical result type supplied by that external runtime. Phase 7 does not fabricate
provider-native continuation state to replay a result back into a provider transcript.

### 4. Tool-call correlation IDs are not synthesized

A normalized `ToolCall` requires a non-empty provider correlation ID. When an API/model does not
supply one, the gateway fails closed instead of generating a replacement identifier.

This is intentionally conservative because a synthetic ID cannot prove correspondence with provider
continuation state.

### 5. Provider API-family support and deployment capability remain separate facts

`ProviderFeatureSupport` describes what an adapter/API family can translate. Registry capabilities
describe what a concrete deployment is approved to provide. Neither one grants authorization.

A request can execute the feature only after normal PDP authorization and deployment eligibility have
already selected an appropriate deployment.

The native adapters expose structured-output and tool-call translation for their documented API
families. The generic OpenAI-compatible adapter enables either feature only through explicit endpoint
configuration; compatibility is never inferred from the URL or provider name.

### 6. Structured/tool validation failures are permanent execution failures

`invalid_structured_output` and `invalid_tool_call` are non-retryable provider-normalized failures.
Phase 6 resilience therefore performs neither same-deployment retry nor cross-provider fallback for
these failures.

Automatic repair/retry of schema failures is not part of Phase 7.

### 7. Provider-native continuation remains bounded by ADR-0007

Phase 7 normalizes model-produced tool calls but does not claim lossless provider continuation after a
business tool executes when the canonical request does not preserve the provider's exact continuation
or reasoning state.

This is especially important for APIs that require exact provider-generated blocks, signatures, or
correlation state on subsequent turns. Such state must not be reconstructed from guesses.

## Consequences

- Applications receive one stable tool-call representation across provider API families.
- Structured output has an explicit validation boundary independent of provider claims.
- The Phase 7 schema contract is intentionally narrower than unrestricted Draft 2020-12.
- The gateway remains a model PEP/executor, not a business action executor.
- OpenAI-compatible endpoints cannot silently gain structured-output/tool capabilities.
- Schema validation introduces `jsonschema` as a runtime dependency in `gateway-core` only.
- Provider-native tool-result continuation may require a later explicit canonical transcript/state
  contract before it can be enabled safely.
- Streaming tool-call deltas and partial structured output remain Phase 8.

## Rejected alternatives

### Treat prompted JSON as structured output

Rejected because syntactic prompting does not provide the same enforcement guarantee as a native
schema capability.

### Trust provider-native schema enforcement without local validation

Rejected because provider responses remain external/untrusted input at the gateway boundary.

### Accept regex/format keywords without a bounded enforcement strategy

Rejected because caller-controlled regular expressions can create disproportionate validation cost,
and accepting `format` without an explicit checker would overstate what the local validator enforces.
A later phase may widen the supported schema subset only with explicit safety, compatibility, and test
evidence.

### Execute business tools inside the gateway

Rejected because it would mix model-routing authority with business-action authorization and create a
new side-effect boundary inside the model gateway.

### Automatically retry/fallback after schema or tool-call validation failure

Rejected because these are semantic output failures, not transient availability failures, and replay
could change model behavior or cross a side-effect boundary.

### Synthesize missing provider tool-call IDs

Rejected because generated IDs would not be provider provenance and could not safely correlate later
continuation state.
