# governed-llm-gateway engineering contract

## Project

- Runtime: Python 3.13+
- Harness authority: `codex-python-engineering-harness`
- Harness profile: `workspace`
- Governance profile: `agentic`
- Root: virtual uv project (`package = false`)
- Primary builder: Codex
- Independent reviewer: Claude Code
- Current phase: Phase 7 — Structured Output and Tool Normalization
- Phase 1 dependency: completed in `policy-model-router` PR #20
- Phase 2: completed in `governed-llm-gateway` PR #1
- Phase 3: completed in `governed-llm-gateway` PR #2
- Phase 4: completed in `governed-llm-gateway` PR #3
- Phase 5: completed in `governed-llm-gateway` PR #4
- Phase 6: completed in `governed-llm-gateway` PR #5
- Phase 7: implemented on `feat/phase-7-structured-output-tools`, pending independent review/merge

Read, in order:

1. `docs/project/PROJECT_INSTRUCTIONS.md`
2. `docs/project/CURRENT_STATE.md`
3. `docs/project/ARCHITECTURE.md`
4. `docs/project/ROADMAP.md`
5. relevant ADRs under `docs/adr/`, especially ADR-0007 and ADR-0013
6. `docs/project/FALLBACK_AND_RETRY.md`
7. `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`
8. `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`
9. `docs/project/SOURCE_ROADMAP.txt` when a decision is unclear

## Non-negotiable invariant

The gateway is a Policy Enforcement Point and operational selector. It may restrict Policy Model
Router authorization but may never broaden it.

`Gateway allowed set ⊆ Policy Router authorized set`

Any code path that can select or fall back outside the PDP-authorized logical model group is a
security defect. Provider adapters have no authorization authority.

## Architecture boundaries

- `gateway-contracts`: provider-neutral immutable contracts only. No provider SDK, FastAPI,
  database, OpenTelemetry SDK, HTTP client, JSON Schema engine, dynamic imports, or business-domain
  dependencies.
- `gateway-core/domain`: deterministic domain logic, provider-neutral runtime state, and local schema
  validation. No provider SDK, FastAPI, database, or OpenTelemetry SDK.
- `gateway-core/application`: provider-neutral execution/policy/ranking/resilience orchestration;
  no concrete provider or Policy Model Router HTTP implementation.
- `gateway-core/adapters`: provider/configuration/infrastructure implementations.
- `gateway-client`: consumers receive a gateway credential only; no provider or PDP credentials.
- `gateway-api`: composition root. FastAPI/Pydantic types must not leak inward.
- consumer repositories may depend on the gateway; the gateway must never depend on business
  projects such as OpsLens, RAGForge, Getnet, Controlled Autonomy Lab, or Multi-Agent Credit Desk.

## Trust and authorization boundary

Request fields such as `risk_level`, `data_classification`, `agent_identity`, limits, and environment
must not automatically become authoritative security facts. Authentication and policy establish the
effective context. Policy/identity failures fail closed.

The Phase 4 `AuthorizedCandidateSet` is the source of policy-authorized deployments. Phase 5 filters
and ranks only inside it. Phase 6 consumes only the resulting `selected + alternatives` sequence;
resilience must never re-enumerate the global registry or reacquire broader authorization after a
provider failure. Phase 7 may translate only features supported by the already-selected deployment
and cannot grant capability or authorization.

Before the first provider call, every bounded fallback candidate must remain in the
PDP-authorized logical model group.

The Policy Model Router receives only prompt-free `PolicyRequestMetadata`. `GatewayRequest.messages`,
structured-output schema, and tool definitions must never be sent to it. Conversely, PDP-only metadata
must not be copied into provider requests.

Registry/ranking YAML and caller-provided JSON Schemas/tool definitions are untrusted until strict,
bounded validation succeeds.

## Phase 5 ranking rules retained

- filter before score;
- only candidates already authorized by Phase 4 may be evaluated;
- deterministic `Decimal` arithmetic;
- unknown pricing is not free;
- missing ranking input is not a neutral/default score;
- expected latency is versioned planning evidence, not live health;
- ties resolve by ascending `deployment_id`;
- static score evidence remains distinct from future benchmark evidence.

## Phase 6 resilience rules retained

- retry means the same concrete deployment;
- fallback means another deployment already present in the Phase 5 ranked alternatives;
- only normalized retryable `rate_limit`, `timeout`, `unavailable`, and `transport` errors can trigger
  automatic replay;
- permanent validation/authentication/authorization/configuration errors do not retry or fall back;
- retry attempts and fallback count are explicitly bounded;
- exponential backoff and jitter are capped; provider `Retry-After` cannot force unbounded sleep;
- runtime health is mutable operational state and must not be written into Phase 5 static scores;
- an open circuit makes a deployment operationally ineligible;
- when runtime-health filtering is active, a missing health snapshot fails closed;
- circuit state is initially per process and per concrete deployment;
- `FallbackSafetyState` blocks automatic replay after observed provider output, an external side
  effect, or opaque provider continuation/reasoning state;
- fallback/retry evidence is metadata-only.

Provider timeout is a per-attempt bound. Do not silently reinterpret policy/ranking `max_latency_ms`
as a total cross-retry execution deadline. A total execution budget requires an explicit contract.

## Phase 7 structured-output and tool rules

- structured output is provider-native schema enforcement, not prompted JSON;
- structured-output/tool requests still require normal registry capability eligibility;
- validate Draft 2020-12 schemas locally and within bounded size/depth before provider I/O;
- reject remote `$ref` and `$dynamicRef` resolution;
- validate final structured output locally even after native provider enforcement;
- normalize only declared tools and validate provider arguments against their schemas;
- canonical `ToolCall` requires provider correlation; never fabricate missing call IDs;
- the gateway never executes a business tool and never authorizes its side effect;
- `ToolResult` is owned by the application/agent/MCP execution layer;
- generic OpenAI-compatible endpoints get optional feature translation only through explicit verified
  configuration;
- `invalid_structured_output` and `invalid_tool_call` are permanent failures and produce zero
  automatic retry/fallback;
- do not fabricate provider-native continuation/reasoning state after tool execution.

## Explicitly deferred

Do not pull forward:

- Phase 8 streaming, partial structured-output/tool-call deltas, replay, and cancellation semantics;
- Phase 9 OpenTelemetry runtime;
- Phase 10/11 benchmark-derived ranking evidence;
- Phase 13 signed Verifiable AI Governance runtime authorization;
- provider-native `ToolResult` continuation requiring a new canonical transcript/state contract.

`min_context_tokens` remains a capability requirement, not an input-token estimate. Policy Model
Router API 1.0 models required tool calling through the workload policy rule rather than a per-request
field; do not invent a wire field.

Do not change repository policy or architecture without an ADR.

Do not use `from __future__ import annotations`. Quote only individual forward references when needed.

## Privacy and evidence

Evidence is metadata-only by default. Never record prompts, completions, structured output payloads,
tool arguments/results, provider API keys, PDP API keys, Authorization headers, arbitrary customer
payloads, or raw malicious provider/PDP error bodies in logs/traces/evidence.

## Quality gate

Run:

```bash
uv run python scripts/quality_gate.py
```

For the Architecture Gate regression specifically:

```bash
python scripts/phase0_gate.py
```

The Phase 0 regression gate is intentionally frozen to the five contract modules present at the
`phase-0-architecture-gate` tag. Current/future contract tests belong to the repository-wide pytest
quality gate.

`types-jsonschema` is an ephemeral mypy-only dependency. Do not add it to runtime requirements.

Phase 7 acceptance requires verified provider-native structured-output mapping, local output/schema
validation, tool-argument validation, zero business-tool execution authority, fail-closed correlation,
no retry/fallback after semantic structured/tool failures, preserved PDP authorization, and the
complete read-only quality gate to pass.
