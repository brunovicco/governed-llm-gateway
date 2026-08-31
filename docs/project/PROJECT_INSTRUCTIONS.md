# Project Instructions

## Objective

Build a reusable, provider-neutral LLM execution gateway that resolves and invokes only models that
are already authorized by deterministic policy, while retaining explainable routing provenance,
capability enforcement, safe fallback, runtime health handling, cost/latency controls, evaluation-
driven ranking, OpenTelemetry-ready evidence, and privacy-safe auditability.

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
- Availability fallback stays inside the already-authorized boundary.
- Caller-declared classification/risk/identity context is not trusted without validation.
- Provider secrets and Policy Model Router credentials live only in gateway deployment configuration.
- Evidence and traces are metadata-only by default.
- No business consumer repository may become a gateway dependency.
- Registry configuration is untrusted until strict parsing and validation succeed.
- Prompt/message content is never sent to the Policy Model Router.
- Policy-only metadata is never copied into provider execution payloads merely for convenience.

## Development constraints

- Python 3.13+.
- uv workspace.
- Codex Python Engineering Harness, profile `workspace`, governance profile `agentic`.
- Codex is primary builder; Claude Code is independent reviewer.
- Architecture/contracts land before provider work.
- Phase 2 may add safe configuration parsing but no provider inference SDK or provider API call.
- Provider execution begins only in Phase 3.
- Deterministic Policy Model Router runtime integration begins only in Phase 4.
- Operational eligibility/ranking and route explainability begin only in Phase 5.
- Architectural changes require an ADR.

## Phase 4 authority rules

- Project only trusted, prompt-free policy metadata through `PolicyDecisionPort`.
- Treat Policy Model Router success and rejection payloads as untrusted until schema/provenance and
  request correlation checks succeed.
- Fail closed on PDP denial, unavailable/misconfigured state, transport failure, or malformed
  provenance.
- Intersect registry deployments with PDP authorization before any provider execution.
- Never broaden authorization in fallback, ranking, or compatibility code.
- Do not translate `min_context_tokens` into an input-token estimate.
- Do not invent Policy Model Router request fields absent from its versioned wire contract.
- Signed governance runtime authorization remains deferred to the optional governance integration.
