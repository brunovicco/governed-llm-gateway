# Governed LLM Gateway

**English** | [Português (Brasil)](README.pt-BR.md)

Reusable provider-neutral LLM execution gateway whose responsibility is **governed model resolution
and execution**.

Status: **Phase 7 — Structured Output and Tool Normalization implemented; under review**.

The project separates authorization, operational selection, execution resilience, and provider feature
normalization:

```text
Application / Agent
       │ workload + requirements + policy metadata
       │ messages + optional schema/tool definitions
       ▼
Policy Model Router (PDP)
       │ authorized logical model group + provenance
       ▼
Governed LLM Gateway (PEP + operational selection)
       │ authorized candidates
       ├─ eligibility + deterministic ranking
       ├─ runtime health / circuit breaker
       ├─ bounded retry / safe fallback
       └─ structured output / tool-call normalization
       ▼
LLM Provider
       │ text / structured output / ToolCall
       ▼
Application / Agent / MCP runtime
       └─ authorizes and executes business tools
```

Core invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may make authorization narrower due to capability, environment/data policy, cost,
latency, health, circuit state, or other operational constraints. It must never make authorization
broader, including during fallback or provider feature translation.

## Current implementation

Phase 0 established the uv workspace, architecture/security boundaries, provider-neutral contract
baseline, ADR-0001 through ADR-0005, and fail-closed authorization invariant.

Phase 1 was completed in `policy-model-router`, generalizing workload and logical model-group
identifiers while preserving deterministic policy decisions and provenance.

Phase 2 completed the strict model registry with safe YAML parsing, closed-schema/semantic validation,
versioned pricing metadata, and deterministic SHA-256 registry provenance.

Phase 3, merged through PR #2, added the provider execution foundation:

- provider-neutral provider request/response/error ports;
- native OpenAI Responses, Anthropic Messages, and Google Gemini `generateContent` adapters;
- explicitly configured OpenAI-compatible chat-completions adapter;
- bounded HTTPS/JSON transport, usage normalization, per-attempt request timeouts, and typed errors;
- no raw non-2xx provider body, credential, or arbitrary response header leakage.

Phase 4, merged through PR #3, added the deterministic Policy Model Router boundary:

- prompt-free `PolicyRequestMetadata` application contract;
- trusted policy projection from `EffectivePolicyContext` rather than caller security claims;
- Policy Model Router `POST /route` wire schema `1.0` adapter;
- strict accepted/rejected decision and provenance validation;
- registry intersection with the PDP-authorized logical model group;
- proof that PDP denial or out-of-authorization deployment selection produces zero provider calls.

Phase 5, merged through PR #4, added deterministic operational selection:

- ADR-0006 for deterministic ranking semantics;
- strict versioned ranking policy and deterministic SHA-256 digest;
- eligibility before scoring for enabled state, trusted environment/data policy, capabilities,
  context, static ranking evidence, pricing, cost ceiling, and expected-latency ceiling;
- deterministic `Decimal` scoring and ascending `deployment_id` tie-break;
- ranking/registry/PDP provenance and machine-readable rejection reasons;
- authenticated `POST /v1/route/explain` that performs authorization + eligibility + ranking only and
  never invokes a provider.

Phase 5 static score inputs are explicitly **not** benchmark evidence. `benchmark_snapshot_id` remains
unset until later evaluation/evidence-driven ranking phases.

Phase 6, merged through PR #5, adds runtime resilience strictly inside the Phase 5 ranked authorized
sequence:

- ADR-0007 for retry/fallback and replay-safety semantics;
- bounded retry against the same concrete deployment;
- bounded fallback only to the next already-ranked authorized deployment;
- normalized transient retry classes: rate limit, timeout, unavailable/5xx, and transport failures;
- permanent validation/authentication/authorization/configuration failures fail closed without
  automatic cross-provider fallback;
- bounded exponential backoff with reconstructable jitter and capped provider `Retry-After`;
- per-process, per-deployment runtime health and circuit breaker state;
- circuit lifecycle `CLOSED → OPEN → HALF_OPEN → CLOSED`;
- open circuit and unhealthy state remove a deployment from operational eligibility;
- `FallbackSafetyState` blocks automatic replay after provider output, external side effects, or
  opaque provider continuation/reasoning state;
- successful resilient execution records actual deployment progression in `fallback_sequence` and
  same-deployment attempts in metadata-only execution evidence.

The resilience layer never re-enumerates the registry or asks the PDP for wider authorization after a
provider failure. All bounded fallback candidates are checked against the authorized logical model
group before the first provider call.

Phase 7 adds structured-output and client-side business-tool normalization:

- ADR-0013 defines the structured-output/tool authority boundary;
- `StructuredOutputSchema` is a named provider-neutral JSON Schema contract;
- `ToolDefinition`, `ToolCall`, and `ToolResult` are hardened canonical contracts;
- caller-provided schemas are validated locally as a bounded Draft 2020-12 subset;
- schemas are limited to 64 KiB and bounded depth, with remote `$ref`/`$dynamicRef` rejected;
- `pattern`, `patternProperties`, and `format` are rejected in Phase 7 until bounded enforcement
  semantics are explicitly supported;
- provider structured output is parsed and validated again locally after native enforcement;
- tool calls are accepted only for declared tools and arguments are validated against their schemas;
- provider correlation IDs are required for canonical `ToolCall` and are never synthesized;
- OpenAI Responses, Anthropic Messages, and Gemini `generateContent` translate their native schema/tool
  wire formats;
- generic OpenAI-compatible endpoints receive structured-output/tool support only through explicit
  verified configuration;
- `invalid_structured_output` and `invalid_tool_call` are permanent failures, so they trigger zero
  automatic retry and zero automatic fallback;
- the gateway never executes business tools.

`ToolResult` is owned by the application/agent/MCP runtime after that runtime authorizes and executes
the business action. Phase 7 does not fabricate provider-native continuation/reasoning state when the
canonical request cannot preserve it losslessly.

See `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` for the detailed Phase 7 contract.

## Structured output and tools

Structured output is a **native model/API capability**, not a prompt convention. Prompting a model to
return JSON is not treated as equivalent to native schema enforcement.

The schema boundary is intentionally defensive:

- Draft 2020-12 syntax with a documented Phase 7 subset;
- 64 KiB serialized schema limit;
- bounded schema depth;
- no external schema-reference retrieval;
- no caller-controlled regex keywords in Phase 7;
- no silently unenforced `format` keyword;
- post-provider local output validation.

Business-tool authority remains outside the gateway:

```text
Gateway → normalizes ToolCall
Application / Agent / MCP runtime → authorizes + executes tool → owns ToolResult
```

The gateway never turns a model-produced tool call into permission to perform an external action.

## Deterministic route explanation

`POST /v1/route/explain` is a metadata-only, no-inference surface. It resolves trusted client context,
obtains the PDP decision, evaluates only the authorized registry candidates, and returns the selected
deployment, alternatives, rejection reasons, and selection provenance.

The endpoint does not accept `messages`. Caller-provided `risk_level`, `data_classification`, or
`agent_identity` are not promoted to authoritative policy facts.

## Policy Router contract notes

`GatewayRequest.requirements.min_context_tokens` is a model-capability requirement, not an input-token
estimate, so it is not silently translated into Policy Model Router `context_tokens_estimated`.

Policy Model Router API 1.0 expresses tool-calling requirements through the workload policy rule, not
a per-request `tool_calling_required` field. The gateway does not invent one.

Some Policy Model Router deployments may require signed runtime authorization. That belongs to the
later Verifiable AI Governance integration. Until then, such a deployment returns 403 and the gateway
fails closed without calling a provider.

## Gemini API note

The current native Gemini adapter remains on `generateContent`. Phase 7 normalizes
`functionDeclarations`/`functionCall` and native JSON-schema configuration without attempting to
reconstruct provider-specific continuation state. A missing provider function-call correlation ID
fails closed rather than being synthesized.

## Repository layout

```text
apps/gateway-api/           HTTP composition root
packages/gateway-contracts provider-neutral contracts
packages/gateway-core/     domain/application/adapters boundary
packages/gateway-client/   thin consumer SDK boundary
config/                    model/ranking/provider configuration
benchmarks/                future benchmark framework
examples/                  future consumers/examples
tests/                     contract/integration/e2e suites
docs/                      durable project sources and ADRs
```

## Validate

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

The quality gate includes Ruff, mypy, pytest/coverage, Bandit, pip-audit, architecture validation,
secret scanning, and the frozen Phase 0 architecture regression gate.

Current Phase 7 hardened validation: **132 tests, 82.62% total coverage, mypy across 58 source files,
and all quality/security gates PASS**. CI is credential-free and uses `contents: read`.

`jsonschema==4.26.0` is the runtime validation dependency in `gateway-core`.
`types-jsonschema==4.26.0.20260518` is used only in the ephemeral mypy environment.

## Source of truth

Start with `docs/project/CURRENT_STATE.md` for continuation,
`docs/adr/ADR-0013-structured-output-and-tool-normalization.md` and
`docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` for Phase 7,
`docs/adr/ADR-0007-fallback-safety-semantics.md` and `docs/project/FALLBACK_AND_RETRY.md` for Phase 6,
`docs/adr/ADR-0006-deterministic-candidate-ranking.md` for Phase 5 ranking semantics,
`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` for the Phase 4 authorization binding, and
`docs/project/SOURCE_ROADMAP.txt` for the original project specification.
