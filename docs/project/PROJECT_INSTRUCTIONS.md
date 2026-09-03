# Project Instructions

## Objective

Build a reusable, provider-neutral LLM execution gateway that resolves and invokes only models already
authorized by deterministic policy, while retaining explainable routing provenance, capability
enforcement, safe fallback, runtime health handling, structured-output/tool normalization, safe
streaming, cost/latency controls, evaluation-driven ranking, OpenTelemetry-ready evidence, and
privacy-safe auditability.

## Scope

The gateway owns governed model resolution and execution. It is not an agent framework, RAG
framework, MCP tool executor, A2A orchestrator, governance system, LLM judge, prompt platform, or
general API-management product.

## Authority boundaries

1. `policy-model-router` is the PDP. It authorizes logical model groups and emits deterministic
   provenance. It never performs inference.
2. `governed-llm-gateway` is the PEP plus operational selector/executor. It may only narrow the
   authorization already granted.
3. Provider adapters execute/translate inference but have no authorization authority.
4. Applications/agents execute business tools; the gateway never does.
5. Verifiable AI Governance is optional integration, not a core dependency.

## Security invariants

- `Gateway allowed set ⊆ Policy Router authorized set`.
- Unknown/invalid policy and identity states fail closed.
- Ranking, health, retry, circuit logic, fallback, structured-output translation, tool normalization,
  and streaming may never widen PDP authorization.
- Caller classification/risk/identity claims are not trusted without authenticated reconciliation.
- Provider/PDP secrets live only in gateway deployment configuration.
- Evidence and traces are metadata-only by default.
- Consumer repositories never become gateway dependencies.
- Registry/ranking configuration is untrusted until strict parsing/validation succeeds.
- Caller-provided JSON Schemas/tool definitions are untrusted until bounded validation succeeds.
- Prompt/message content, schemas, and tool definitions are never sent to the Policy Model Router.
- PDP-only metadata is never copied into provider payloads for convenience.
- Tool calls never grant business-action authority.
- Streaming provider output cannot create a new authorization/fallback candidate.

## Development constraints

- Python 3.13+.
- uv workspace.
- Codex Python Engineering Harness, profile `workspace`, governance profile `agentic`.
- Codex is primary builder; Claude Code is independent reviewer.
- Provider execution starts in Phase 3.
- Policy Model Router runtime integration starts in Phase 4.
- Operational ranking/explainability starts in Phase 5.
- Runtime health/retry/fallback/circuit breaker starts in Phase 6.
- Structured-output/tool normalization starts in Phase 7.
- Streaming starts in Phase 8.
- OpenTelemetry runtime starts in Phase 9.
- Architectural changes require an ADR.

## Phase 4 authority rules retained

- Project only trusted, prompt-free metadata through `PolicyDecisionPort`.
- Treat PDP responses as untrusted until schema/provenance/correlation validation succeeds.
- Fail closed on denial, unavailable/misconfigured state, transport failure, or malformed provenance.
- Intersect registry deployments with PDP authorization before selection/execution.
- Do not invent Policy Model Router request fields absent from its versioned wire contract.

## Phase 5 ranking rules retained

- Rank only the Phase 4 `AuthorizedCandidateSet`.
- Validate registry-digest continuity before ranking.
- Require exactly one logical model group for the current PMR 1.0 binding.
- Reject candidates outside PDP authorization.
- Perform eligibility before score.
- Use deterministic `Decimal` scoring and ascending `deployment_id` tie-break.
- Unknown pricing and absent score inputs fail closed.
- Expected latency is static planning evidence, not runtime health.
- Keep PDP, registry, ranking-policy, static-score, and future benchmark provenance distinct.

## Phase 6 resilience rules retained

- Retry means another attempt against the same concrete deployment.
- Fallback means moving only to the next already-ranked authorized deployment.
- Pre-validate the bounded fallback sequence against the authorized logical group before the first
  provider call.
- Do not re-enumerate the registry or ask the PDP for a wider group after failure.
- Automatic replay is limited to normalized retryable `rate_limit`, `timeout`, `unavailable`, and
  `transport` errors.
- Permanent validation/authentication/authorization/configuration failures do not trigger retry or
  cross-provider fallback.
- Bound attempts, fallback count, backoff, jitter, and provider `Retry-After` influence.
- Treat runtime health as mutable operational state, separate from static Phase 5 scores.
- Open circuit removes a deployment from eligibility.
- When runtime-health filtering is active, missing health fails closed.
- Initial circuit state is per process and per concrete deployment.
- Block automatic replay after observed provider output, external side effect, or opaque provider
  continuation/reasoning state.
- Preserve metadata-only execution-attempt evidence.
- Provider timeout is per attempt. Do not silently repurpose `max_latency_ms` as a total retry budget.

## Phase 7 structured-output/tool rules retained

- Structured output means provider-native schema enforcement, not prompted JSON.
- Require normal deployment capability before adapter translation.
- Validate caller schemas locally with the bounded Draft 2020-12 subset before provider execution.
- Reject remote `$ref`/`$dynamicRef`; do not perform schema network retrieval.
- Validate provider structured output again locally after provider-native enforcement.
- Normalize only declared tool calls and validate arguments against declared input schemas.
- Require provider correlation for canonical `ToolCall`; do not synthesize missing call IDs.
- The gateway never invokes the business tool. Application/agent/MCP runtime owns authorization,
  execution, side effects, and `ToolResult`.
- Generic OpenAI-compatible structured/tool support requires explicit verified configuration.
- `invalid_structured_output` and `invalid_tool_call` are permanent and do not retry/fallback.
- Do not fabricate provider-native continuation/reasoning state after a business tool executes.

See ADR-0013 and `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`.

## Phase 8 streaming rules

- Require `Capability.STREAMING` in registry eligibility for streaming requests.
- Separately require verified adapter/API-family `native_streaming` and `streaming_usage` support.
- Generic OpenAI-compatible streaming/final usage remain explicit opt-ins.
- `POST /v1/generate` must finish gateway authentication, trusted-context resolution, PDP
  authorization, runtime-health snapshot, ranking, and eligible-candidate check before returning SSE.
- Provider-native start alone does not cross the replay boundary.
- First content/tool-call output crosses the replay boundary.
- Before semantic output, only normal bounded Phase 6 retry/fallback may occur.
- After semantic output, no same-provider retry and no cross-provider fallback; terminate with
  `response.failed(partial=true, retryable=false)`.
- Successful normalized streaming requires exactly one `usage.completed` before
  `response.completed`.
- Unknown lifecycle transitions, duplicate/early usage, early completion, and EOF without completion
  fail closed.
- Provider health success must be recorded before yielding public `response.completed`.
- Cancellation/disconnect must close the execution generator and upstream provider stream and must not
  be recorded as provider failure.
- SSE transport must remain HTTPS-only, bounded, header-sanitized, and explicitly closeable.
- Incremental structured output/tool calls retain Phase 7 local validation semantics.
- Streaming does not add business-tool execution authority or fabricate correlation/continuation state.
- Do not add Phase 9 OpenTelemetry runtime while closing Phase 8.

See ADR-0011 and `docs/project/STREAMING.md`.

## Explainability rules

- `POST /v1/route/explain` remains authenticated, prompt-free, and provider-free.
- It resolves trusted effective context before policy/ranking work.
- Its request contract rejects messages, unsupported schema versions, invalid workloads, and unknown
  fields.
- It is decision-scoped, not a global inventory endpoint.
- Framework types stay in `gateway-api`.

## Deferred work

Do not pull forward:

- Phase 9 OpenTelemetry runtime via `a2a-otel-kit`;
- Phase 10/11 benchmark-derived routing evidence;
- Phase 12 client HTTP transport completion;
- Phase 13 signed Verifiable AI Governance runtime authorization;
- provider-native tool-result continuation that requires a canonical transcript/state contract;
- shared/distributed circuit-breaker state;
- an implicit total streaming deadline derived from policy `max_latency_ms`.

## Quality gates

Canonical repository gate:

```bash
uv run python scripts/quality_gate.py
```

Normal GitHub Actions validation must remain read-only (`contents: read`).

Coverage must be enforced at 80% or higher by both the pytest-cov run and an independent Coverage.py
`coverage report --fail-under=80` check. Do not lower the threshold or exclude new phase code to make a
gate pass.

`jsonschema` is a Phase 7 runtime dependency. `types-jsonschema` is allowed only as an ephemeral mypy
dependency. `httpx` is the Phase 8 adapter-layer asynchronous streaming transport dependency.

`scripts/phase0_gate.py` is frozen to the five contract modules from the
`phase-0-architecture-gate` baseline tag. New phase tests belong to the repository-wide pytest gate.
