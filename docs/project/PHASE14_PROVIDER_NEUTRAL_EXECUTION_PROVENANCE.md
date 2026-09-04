# Phase 14 — Provider-neutral execution provenance

## Context

Real consumer integrations need to retain runtime evidence without teaching consumers provider-specific response shapes or allowing evidence metadata to become authorization authority.

The OpsLens Phase 6 Gate 6.4 Bedrock baseline exposed a useful evidence gap after terminal `ProviderExecution` was first added to the SDK: the gateway could preserve provider/model/deployment, measured provider-attempt latency, token counts and optional cost, but it still discarded provider response identity, finish reason, retry/fallback position and optional detailed token accounting.

This change expands the existing provider-neutral evidence contracts. It does not add consumer-specific contracts and it does not grant new execution authority.

## Evidence model

`GatewayResponse.request_id` remains the gateway correlation identifier.

`ProviderExecution.provider_request_id` is distinct. It is populated only when the normalized provider stream supplied a provider response identifier. The gateway must not synthesize a provider request identifier from its own request ID.

`ProviderExecution.finish_reason` is populated only when the provider-normalized terminal event supplied a finish reason.

`ProviderExecution.attempt_number` and `fallback_index` are gateway-observed orchestration provenance:

- `attempt_number` is the concrete provider invocation attempt number and is always positive;
- `fallback_index` identifies the position in the gateway fallback sequence and is zero-based;
- neither field authorizes a retry, fallback, model or deployment. They describe what the runtime already did.

`Usage` retains required normalized input/output token counts and may additionally retain provider-returned:

- `total_tokens`;
- `cache_read_input_tokens`;
- `cache_write_input_tokens`;
- `total_cost_usd`.

Optional evidence remains `None` when the provider/runtime did not supply it. Unknown values are never rewritten to zero. When a provider supplies `total_tokens`, the normalized contract requires it to equal input plus output tokens.

## Latency boundary

`ProviderExecution.latency_ms` retains the Phase 14 terminal-evidence definition established previously: elapsed time from the start of the concrete provider attempt to normalized provider completion. It is not consumer end-to-end latency and it is not automatically provider-native latency metadata.

Consumers that need their own wall-clock or client elapsed measurement must measure that boundary themselves and keep it distinct from provider-attempt evidence.

## Streaming and SDK propagation

The evidence chain is:

```text
normalized provider events
 -> StreamingExecutionService
 -> terminal GatewayStreamEvent.execution
 -> SSE API payload
 -> gateway-client codec
 -> GatewayClient.generate()
 -> GatewayResponse.execution
```

Provider response identity is checked for consistency when both start and completion events expose it. Contradictory provider response IDs fail closed instead of being silently normalized.

The SDK preserves invalid wire values long enough for the immutable contract validators to reject them. For example, wire `attempt_number=0` is not converted to the default value `1`.

## Authority boundary

Runtime evidence is not authorization evidence by itself.

Provider/model/deployment, request IDs, finish reason, usage, cost, latency, attempt number and fallback index may be used for audit, observability, evaluation and post-execution policy evidence. They must not be interpreted by a consumer as permission to broaden a workload, generate SQL, execute a tool, choose a provider/model, retry an operation or bypass the gateway policy decision.

Consumers remain responsible for deterministic business/domain validation after model output when their architecture requires it.

## Compatibility

The new provider-specific-detail fields are optional where the gateway cannot prove a value. Existing providers are not required to fabricate cache-token totals, provider IDs or finish reasons they do not expose.

`attempt_number` and `fallback_index` have deterministic gateway defaults for direct first-attempt execution (`1` and `0`) because they are gateway-observed orchestration facts, not inferred provider metadata.
