# Project Instructions

## Objective

Build a reusable, provider-neutral LLM execution gateway that resolves and invokes only models that
are already authorized by deterministic policy, while retaining explainable routing provenance,
capability enforcement, safe fallback, runtime health handling, cost/latency controls,
evaluation-driven ranking, OpenTelemetry-ready evidence, and privacy-safe auditability.

## Scope

The gateway owns governed model resolution and execution. It is not an agent framework, RAG
framework, MCP tool executor, A2A orchestrator, governance system, LLM judge, prompt platform, or
general API-management product.

## Authority boundaries

1. `policy-model-router` is the PDP. It authorizes logical model groups and emits deterministic
   provenance. It never performs inference.
2. `governed-llm-gateway` is the PEP plus operational selector. It filters/ranks only inside the
   authorization already granted.
3. Provider adapters execute inference but have no authorization authority.
4. Applications/agents execute business tools; the gateway never does.
5. Verifiable AI Governance is an optional upstream/downstream governance integration, not a core
   dependency.

## Security invariants

- `Gateway allowed set ⊆ Policy Router authorized set`.
- Unknown/invalid policy and identity states fail closed.
- Ranking, health filtering, retry, and fallback may never widen PDP authorization.
- Caller-declared classification/risk/identity context is not trusted without validation.
- Provider secrets and Policy Model Router credentials live only in gateway deployment configuration.
- Evidence and traces are metadata-only by default.
- No business consumer repository may become a gateway dependency.
- Registry/ranking configuration is untrusted until strict parsing and validation succeed.
- Prompt/message content is never sent to the Policy Model Router.
- Policy-only metadata is never copied into provider execution payloads merely for convenience.

## Development constraints

- Python 3.13+.
- uv workspace.
- Codex Python Engineering Harness, profile `workspace`, governance profile `agentic`.
- Codex is primary builder; Claude Code is independent reviewer.
- Architecture/contracts land before provider work.
- Provider execution begins only in Phase 3.
- Deterministic Policy Model Router runtime integration begins only in Phase 4.
- Operational eligibility/ranking and route explainability begin only in Phase 5.
- Runtime resilience begins only in Phase 6.
- Architectural changes require an ADR.

## Phase 4 authority rules

- Project only trusted, prompt-free policy metadata through `PolicyDecisionPort`.
- Treat Policy Model Router success/rejection payloads as untrusted until schema/provenance and
  request-correlation checks succeed.
- Fail closed on PDP denial, unavailable/misconfigured state, transport failure, or malformed
  provenance.
- Intersect registry deployments with PDP authorization before selection/execution.
- Do not translate `min_context_tokens` into an input-token estimate.
- Do not invent Policy Model Router request fields absent from its versioned wire contract.
- Signed governance runtime authorization remains deferred to the optional governance integration.

## Phase 5 ranking rules

- Phase 5 receives the Phase 4 `AuthorizedCandidateSet`; it must not query the global registry to
  broaden the candidate set.
- Validate that the current registry digest matches the digest bound to authorization before ranking.
- Require exactly one authorized logical model group for the current Policy Model Router 1.0 binding.
- Reject any candidate whose model group falls outside PDP authorization.
- Perform eligibility before score.
- Use deterministic `Decimal` scoring and an explicit ascending `deployment_id` tie-break.
- Ranking-policy weights and score inputs are strict, versioned configuration with deterministic
  digests.
- Unknown pricing and absent score inputs make a deployment ineligible rather than free/neutral.
- Expected latency is a static/versioned planning input in Phase 5, not live health evidence.
- Preserve separate provenance for PDP policy, model registry, ranking policy, and static score
  snapshot.
- Do not populate `benchmark_snapshot_id` from Phase 5 static score configuration.

## Phase 5 explainability rules

- `POST /v1/route/explain` is authenticated and prompt-free.
- It resolves trusted effective context before PDP/ranking work.
- It performs no provider inference.
- Its request contract is closed and rejects `messages`, unsupported schema versions, and invalid
  workload identifiers.
- It may expose only metadata necessary to explain the caller's authorized decision; it is not a
  global model/catalog inventory endpoint.
- API framework types stay in `gateway-api` and must not leak into contracts/domain.

## Deferred work

Do not pull forward:

- Phase 6 live health, bounded retry, fallback, or circuit-breaker behavior;
- Phase 7 structured-output/tool normalization;
- Phase 8 streaming;
- Phase 9 OpenTelemetry runtime;
- Phase 10/11 benchmark-derived routing evidence;
- Phase 13 signed Verifiable AI Governance runtime authorization.

## Quality gates

The canonical repository gate is:

```bash
uv run python scripts/quality_gate.py
```

GitHub Actions must remain read-only during normal validation (`contents: read`). Temporary artifact
generation permissions are development scaffolding only and must never remain in a review-ready PR.

`scripts/phase0_gate.py` is a frozen regression check for the five contract modules present at the
`phase-0-architecture-gate` baseline tag. New phase tests belong to the repository-wide pytest gate.
