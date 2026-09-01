# Architecture

## Context

Applications declare workload intent and requirements without naming provider/model. The Policy
Model Router determines which logical model group is allowed. The gateway operates only inside that
authorization boundary, filters/ranks concrete deployments deterministically, executes with bounded
runtime resilience, and normalizes supported structured-output/tool-call features.

```text
Consumer
  │ GatewayRequest
  │ messages + optional structured schema/tool definitions
  ▼
Authentication / workload identity
  │ authoritative EffectivePolicyContext
  ▼
Prompt-free policy projection
  ▼
Policy Model Router (PDP)
  │ one authorized model group + policy provenance
  ▼
Governed LLM Gateway
  ├─ validate/correlate authorization provenance
  ├─ intersect authorization with model registry      (Phase 4)
  ├─ validate registry/authorization binding          (Phase 5)
  ├─ static eligibility + deterministic ranking       (Phase 5)
  ├─ runtime-health eligibility / circuit state       (Phase 6)
  ├─ bounded retry / safe fallback                    (Phase 6)
  ├─ structured-output/tool contract validation       (Phase 7)
  ├─ final PEP validation
  └─ provider execution / response normalization
       ▼
Provider adapter → provider API
       │ text / structured output / ToolCall
       ▼
Consumer / agent runtime
       └─ authorizes and executes business tools
```

## Fundamental invariant

For each request:

`gateway_eligible_groups ⊆ pdp_authorized_groups`

The gateway may remove candidates because of environment, data policy, capability, cost, latency,
runtime health, or circuit state. It cannot add a logical group/deployment not permitted by policy.

Phase 4 establishes the authorized registry candidate set. Phase 5 filters/orders that set. Phase 6
may retry the same selected deployment or move only through the already-ranked alternatives; it does
not re-enumerate the registry or ask the PDP for broader authorization after failure. Phase 7 can
translate only features supported by the already-selected deployment/API family and has no authority
to widen authorization.

## Package topology

### gateway-contracts

Stable provider-neutral immutable types. It has no provider SDK, FastAPI, database, OpenTelemetry SDK,
HTTP client, JSON Schema engine, or business-domain dependency.

Routing provenance/rejection vocabularies carry provider-neutral metadata needed to reconstruct
selection and execution progression. Phase 7 adds `StructuredOutputSchema`, hardened `ToolDefinition`,
`ToolCall`, and `ToolResult` contracts while keeping business-tool execution outside this package and
the gateway runtime.

### gateway-core

- `domain`: deterministic invariants, model registry, ranking-policy semantics, provider-neutral
  resilience state, and structured-output/tool schema validation;
- `application`: provider-neutral provider/PDP ports plus authorization, ranking, resilience, and
  execution-contract orchestration;
- `adapters`: strict configuration loading, Policy Model Router transport, and provider integrations.

The Phase 7 JSON Schema engine is isolated in `gateway-core`; it does not leak into the public
contracts package. The Policy Model Router's Python domain types are not imported into gateway
domain/contracts. Its integration boundary remains the versioned HTTP contract.

### gateway-client

Thin SDK boundary. Consumers eventually hold only gateway credentials, not provider or PDP secrets.

### gateway-api

HTTP composition root. It owns FastAPI/Pydantic types and the authenticated
`POST /v1/route/explain` surface; framework types do not leak into contracts/domain.

## Trust model

Caller `risk_level`, `data_classification`, `agent_identity`, limits, and environment remain claims
until reconciled with authenticated identity/policy. `EffectivePolicyContext` represents authoritative
policy context.

Structured-output schemas and tool definitions are also caller-controlled input. They do not grant
model authorization and remain untrusted until provider-neutral validation succeeds.

The PDP projection and operational eligibility use trusted context. Availability/resilience logic
receives no authority to reinterpret identity or policy failures as transient availability failures.

## Authorization-to-ranking binding

The Phase 4 `AuthorizedCandidateSet` binds validated PDP provenance, the registry digest, and concrete
deployments inside the authorized logical group.

Phase 5 validates registry continuity and current PMR 1.0 single-group semantics before ranking. A
candidate outside the group is an invariant violation rather than an alternative.

This prevents authorization widening and registry TOCTOU substitution across Phase 4 → Phase 5.

## Deterministic ranking and runtime health

Phase 5 static eligibility evaluates enabled state, trusted environment/data allowance, capabilities,
context, ranking input availability, versioned pricing, projected cost, and expected latency before
scoring. Eligible candidates use exact `Decimal` scoring and a stable ascending `deployment_id`
tie-break.

A structured-output or tool-call request still depends on the normal Phase 5 capability filter. Phase
7 adapter feature support is an additional execution boundary, not an alternate authorization path.

Phase 6 runtime health is a separate mutable input. When health filtering is active, it can only
remove candidates:

- open circuit → `circuit_breaker_open`;
- unhealthy deployment → `deployment_unhealthy`;
- missing health snapshot → fail closed as unavailable health evidence.

Runtime health is never written back into Phase 5 static ranking scores. Telemetry/benchmark-driven
score evolution belongs to later phases.

## Runtime resilience boundary

Phase 6 consumes only the Phase 5 `selected + alternatives` sequence. The bounded sequence is checked
against `RoutingProvenance.authorized_model_group` before the first provider call.

Retry:

- same concrete deployment;
- normalized retryable transient failures only;
- bounded attempts and capped exponential backoff/jitter.

Fallback:

- next already-ranked deployment only;
- bounded number of alternatives;
- no global registry enumeration or policy widening.

`FallbackSafetyState` stops automatic replay after observed provider output, an external side effect,
or opaque provider continuation/reasoning state.

Phase 7 adds two permanent normalized semantic failures:

- `invalid_structured_output`;
- `invalid_tool_call`.

Neither failure triggers same-deployment retry nor cross-provider fallback. They are semantic output
failures rather than availability failures.

Circuit state is initially per process and per concrete deployment. The lifecycle is
`CLOSED → OPEN → HALF_OPEN → CLOSED`. Shared state is deferred until operational evidence requires it.

Provider timeout remains a per-attempt bound. Phase 6 does not reinterpret selection
`max_latency_ms` as an implicit total retry deadline; a cross-retry execution budget requires its own
explicit contract.

See ADR-0007 and `docs/project/FALLBACK_AND_RETRY.md`.

## Structured-output and tool boundary

Phase 7 treats structured output as provider-native schema enforcement, not a prompting convention.
Prompted JSON does not satisfy the same capability contract.

`StructuredOutputSchema` is validated before provider execution. The core validates Draft 2020-12,
bounds serialized schema size and depth, and rejects remote `$ref`/`$dynamicRef` resolution. Provider
responses are parsed and validated again locally even after native schema enforcement.

`ToolDefinition` describes a business tool. Provider-produced calls are normalized to `ToolCall` and
validated against the declared schema. The canonical tool call requires a provider correlation ID; the
gateway does not synthesize one when absent.

`ToolResult` is owned by the application/agent/MCP runtime after that runtime authorizes and executes
the business action. Phase 7 does not reconstruct provider-native continuation state when the exact
provider-generated transcript/reasoning state is not represented canonically.

Native provider adapters translate the documented API-family features. The generic OpenAI-compatible
adapter keeps structured output and tool calling disabled unless explicitly configured for a verified
endpoint.

See ADR-0013 and `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`.

## Policy metadata projection

The PDP receives workload/policy metadata only. `GatewayRequest.messages`, structured-output schema,
and tool definitions are not part of its wire request. The application PDP port accepts
`PolicyRequestMetadata`, not `GatewayRequest`.

Accepted/rejected Policy Model Router responses remain untrusted until strict schema/provenance and
request/environment correlation checks succeed.

See `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`.

## Explainability surface

`POST /v1/route/explain` performs trusted-context resolution, PDP authorization, eligibility,
deterministic ranking, and metadata-only explanation. It performs no provider inference and does not
expose a global deployment inventory.

Phase 6 core ranking can consume a runtime-health snapshot so route explanation can later include the
same health-based eligibility semantics without changing authorization authority.

## Execution boundary

Provider adapters execute concrete models but have zero authorization authority. PDP-only security
metadata is not copied into provider payloads. Provider and PDP credentials remain separate
infrastructure concerns.

Phase 7 adapters may translate prompt messages, the structured-output schema, and tool definitions
needed for provider inference. They must not execute returned tool calls or turn tool definitions into
new authorization facts.

Phase 6/7 execution evidence carries only normalized metadata and never raw provider error bodies,
prompts/completions, tool arguments/results, or secrets.

## Evidence

Routing evidence remains reconstructable without prompt/response storage. It includes PDP provenance,
registry digest, ranking-policy provenance, selected identities, and rejection reasons.

Phase 6 adds actual deployment progression in `fallback_sequence` and separate metadata-only attempt
evidence for same-deployment retries, normalized failures, retry delays, latency, and outcome.

Phase 7 does not add tool arguments, tool results, structured payloads, prompts, or completions to
default evidence. Only bounded outcome/error-category facts may be recorded later through the
metadata-only observability layer.

Static `score_snapshot_id` is not benchmark evidence; `benchmark_snapshot_id` remains unset until the
benchmark/evidence-driven phases.

## Dependency direction

```text
consumer projects → gateway client/API → gateway core/contracts
```

Never invert this dependency. Consumer repositories are integration fixtures/examples, not gateway
runtime dependencies.
