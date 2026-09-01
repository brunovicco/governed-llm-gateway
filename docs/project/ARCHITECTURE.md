# Architecture

## Context

Applications declare workload intent and requirements without naming provider/model. The Policy Model
Router determines which logical model group is authorized. The gateway operates only inside that
boundary, filters/ranks concrete deployments deterministically, applies bounded runtime resilience,
normalizes structured-output/tool features, and now exposes a provider-neutral streaming lifecycle.

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
  │ authorized logical model group + policy provenance
  ▼
Governed LLM Gateway
  ├─ authorization/registry intersection            Phase 4
  ├─ deterministic eligibility + ranking            Phase 5
  ├─ runtime health / circuit breaker               Phase 6
  ├─ bounded retry / safe fallback                  Phase 6
  ├─ structured output / tool normalization         Phase 7
  ├─ streaming capability + replay boundary         Phase 8
  ├─ final PEP checks
  └─ provider execution / normalized output
       ▼
Provider adapter → provider API
       │ text / structured output / ToolCall / stream
       ▼
Consumer / agent runtime
       └─ authorizes and executes business tools
```

## Fundamental invariant

For every request:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Phase 4 establishes the authorized concrete candidate set. Phase 5 may only remove/order that set.
Phase 6 may retry the same deployment or move through the already-ranked authorized alternatives.
Phase 7 may translate only capabilities of the selected deployment/API family. Phase 8 may stream only
from that same bounded execution sequence. None of these layers may enumerate or authorize a new
logical group after PDP authorization.

## Package topology

### gateway-contracts

Stable provider-neutral immutable types. No provider SDK, FastAPI, HTTP transport, OpenTelemetry SDK,
JSON Schema implementation, or business-domain execution dependency.

The package now includes:

- request/response contracts and routing provenance;
- structured-output/tool contracts from Phase 7;
- `GatewayStreamEvent` and canonical stream-event vocabulary from Phase 8.

### gateway-core

- `domain`: deterministic invariants, model registry, ranking, resilience state, structured-schema
  validation;
- `application`: PDP/provider ports and authorization, ranking, resilience, streaming orchestration;
- `adapters`: strict configuration loading, Policy Model Router transport, provider integrations,
  synchronous JSON transport, and asynchronous SSE transport.

Provider-specific wire semantics remain confined to adapters. The Policy Model Router Python domain is
not imported into gateway contracts/domain; its versioned HTTP API remains the integration boundary.

### gateway-client

Thin consumer boundary. Consumers should eventually hold gateway credentials only, never provider or
PDP credentials.

### gateway-api

FastAPI/Pydantic composition root. Framework types do not leak into core contracts/domain.

Current HTTP surfaces:

- `POST /v1/route/explain` — authenticated metadata-only authorization/ranking explanation, no provider
  inference;
- `POST /v1/generate` — authenticated governed streaming execution via SSE.

## Trust model

Caller identity/risk/classification/environment claims are not authoritative until reconciled through
`EffectivePolicyContext`. Structured-output schemas, tool definitions, messages, token estimates,
limits, and streaming requests are also untrusted caller input.

The PDP receives only prompt-free policy metadata. Messages, structured schemas, and tool definitions
are not copied into the Policy Router wire request.

Provider responses and SSE events remain untrusted until adapter parsing/lifecycle validation succeeds.
Provider feature flags describe wire capability only; they do not grant model authorization.

## Authorization-to-ranking binding

`AuthorizedCandidateSet` binds validated PDP provenance, registry digest, and deployments inside the
authorized logical group. Phase 5 validates registry continuity and the current PMR 1.0 single-group
binding before ranking.

Out-of-group candidate injection is an invariant violation. Phase 6 additionally validates the bounded
`selected + alternatives` execution sequence before the first provider call.

Phase 8 reuses that exact sequence; streaming never re-enumerates the registry.

## Deterministic ranking and runtime health

Phase 5 eligibility evaluates enabled state, trusted environment/data allowance, required capabilities,
context, ranking evidence, pricing, projected cost, and expected latency before scoring. Eligible
candidates use exact `Decimal` scoring and an ascending `deployment_id` tie-break.

`Capability.STREAMING` is an ordinary Phase 5 capability requirement when streaming is requested. It
must be present in registry data and therefore can only narrow the authorized set.

Phase 6 runtime health is mutable operational state. When active it may only remove candidates:

- open circuit → `circuit_breaker_open`;
- unhealthy deployment → `deployment_unhealthy`;
- missing health snapshot → fail closed.

Runtime health is never authorization and is not written into static ranking evidence.

## Runtime resilience boundary

Retry remains same-deployment only, bounded, and restricted to normalized transient availability
failures. Fallback remains bounded to the next already-ranked authorized deployment. Permanent policy,
authentication, configuration, structured-output, and tool-call semantic failures do not become
availability fallback signals.

ADR-0007 establishes replay safety after observed output, external side effects, or opaque provider
continuation state.

## Structured-output and tool boundary

Phase 7 treats structured output as provider-native schema enforcement plus mandatory local
post-provider validation. The gateway uses a bounded Draft 2020-12 subset and rejects remote schema
retrieval, unbounded regex keywords, and unenforced `format` semantics.

Provider-produced business-tool calls are normalized and schema-validated. The gateway does not
execute those tools. `ToolResult` belongs to the application/agent/MCP runtime. Missing provider
correlation/continuation state is never invented.

## Streaming boundary

Phase 8 introduces `ProviderStreamingPort`, normalized provider stream events, `StreamingExecutionService`,
and the public SSE lifecycle.

Canonical public events:

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

### Pre-stream governance

`POST /v1/generate` completes gateway authentication, trusted-context resolution, PDP authorization,
runtime-health snapshot, deterministic ranking, and the presence of an eligible authorized streaming
deployment **before** returning `200 text/event-stream`.

Policy denial, invalid caller/schema/tool contracts, ranking configuration/invariant errors, and no
eligible candidate therefore retain normal HTTP error semantics and do not start provider execution.

### Semantic replay cutoff

A provider-native start event is internal and does not itself cross the replay boundary. The first
content delta or tool-call event does.

Before semantic output, Phase 6 bounded retry/fallback may still apply. After semantic output, provider
failure terminates as `response.failed(partial=true, retryable=false)` with no same-provider retry and
no cross-provider fallback. This prevents hybrid responses composed from multiple executions.

### Usage and completion

A normalized successful stream requires one `usage.completed` before `response.completed`. Duplicate
usage, completion before semantic output/final usage, unknown lifecycle events, or EOF without
completion fail closed.

Provider success is recorded in runtime health before exposing public `response.completed`.

### Cancellation and transport

Streaming uses a dedicated `HttpxSseTransport`, not the blocking JSON transport. It requires HTTPS,
rejects URL userinfo/fragments, bounds event size to 1 MiB, normalizes open/read timeout and network
failures, allowlists safe response headers, and supports explicit/idempotent `aclose()`.

The API body uses `aclosing()` around the execution generator. Client disconnect/cancellation therefore
closes the execution generator, provider generator, upstream SSE response, and HTTP client. Client
cancellation is not recorded as a provider failure.

See ADR-0011 and `docs/project/STREAMING.md`.

## Provider adapter boundary

Provider adapters execute selected concrete models and normalize provider wire behavior. They have zero
authorization authority.

Native streaming support exists for OpenAI Responses, Anthropic Messages, and Gemini
`streamGenerateContent`. Generic OpenAI-compatible streaming and final-usage support require explicit
verified opt-in.

Provider/PDP credentials remain infrastructure concerns and are not copied into routing provenance,
SSE output, normalized errors, or default evidence.

## Evidence and privacy

Routing evidence remains metadata-only by default and includes PDP provenance, registry/ranking
identity, selected deployment, rejection reasons, and bounded fallback progression.

Streaming may expose response content to the requesting client by definition, but it does not add that
content to routing provenance or default evidence. Prompts, completions, structured payloads, tool
arguments/results, credentials, arbitrary provider headers, and raw provider error bodies remain
excluded from default evidence.

OpenTelemetry instrumentation remains Phase 9. Phase 8 does not create telemetry authority or
benchmark-derived ranking evidence.

## Dependency direction

```text
consumer projects → gateway client/API → gateway core/contracts
```

Never invert this dependency. Consumer repositories are integration fixtures/examples, not gateway
runtime dependencies.
