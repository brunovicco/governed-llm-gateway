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
- Provider secrets live only in gateway deployment configuration.
- Evidence and traces are metadata-only by default.
- No business consumer repository may become a gateway dependency.
- Registry configuration is untrusted until strict parsing and validation succeed.

## Development constraints

- Python 3.13+.
- uv workspace.
- Codex Python Engineering Harness, profile `workspace`, governance profile `agentic`.
- Codex is primary builder; Claude Code is independent reviewer.
- Architecture/contracts land before provider work.
- Phase 2 may add safe configuration parsing but no provider inference SDK or provider API call.
- Provider execution begins only in Phase 3.
- Architectural changes require an ADR.
