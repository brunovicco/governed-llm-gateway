# Governed LLM Gateway

Reusable provider-neutral LLM execution gateway whose responsibility is **governed model resolution
and execution**.

Status: **Phase 4 — Policy Router integration implemented; under review**.

The project separates authorization from operational selection:

```text
Application / Agent
       │ workload + requirements + policy metadata
       ▼
Policy Model Router (PDP)
       │ authorized logical model group + provenance
       ▼
Governed LLM Gateway (PEP + operational selection)
       │ concrete eligible deployment
       ▼
LLM Provider
```

Core invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may make authorization narrower due to capability, health, environment, cost, latency,
or other operational constraints. It must never make authorization broader.

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
- bounded HTTPS/JSON transport, usage normalization, request timeouts, and typed errors;
- no raw non-2xx provider body, credential, or arbitrary response header leakage.

Phase 4 adds the deterministic Policy Model Router boundary:

- prompt-free `PolicyRequestMetadata` application contract;
- trusted policy projection from `EffectivePolicyContext` rather than caller security claims;
- `POST /route` adapter bound to Policy Model Router wire schema `1.0`;
- trusted client identity selects the PDP credential and becomes `agent_name`;
- strict success/rejection response schemas and SHA-256 policy-digest validation;
- accepted decisions are correlated to the gateway `request_id` and trusted environment;
- `422 no_viable_model_group` rejection provenance is additionally bound to request ID, workload,
  and environment;
- PDP timeout, transport, auth, authorization, rate-limit, configuration, denial, and malformed
  response paths fail closed;
- registry candidates are intersected with the PDP-authorized logical group;
- provider execution is impossible after a PDP denial or for a deployment outside authorization;
- policy metadata is not copied into provider execution payloads.

The Policy Model Router never receives `GatewayRequest.messages`. The provider adapter never receives
PDP-only metadata.

Phase 4 deliberately does **not** choose the best deployment. `authorize_candidates` establishes the
authorized candidate set; `execute_selected` enforces an externally supplied deployment only to prove
the PEP boundary. Deterministic operational filtering/ranking starts in Phase 5.

## Policy Router contract notes

The current Policy Model Router request contract distinguishes input-token estimation from model
capability requirements. Therefore `GatewayRequest.requirements.min_context_tokens` is not silently
translated into `context_tokens_estimated`; the latter is supplied as execution metadata by the
caller of the policy application service.

Policy Model Router API 1.0 also expresses tool-calling requirements through the workload policy rule,
not a per-request `tool_calling_required` field. The gateway does not invent one.

Some Policy Model Router deployments may require signed runtime authorization. That belongs to the
later Verifiable AI Governance integration. Until then, such a deployment returns 403 and the gateway
fails closed without calling a provider.

## Gemini API note

Google recommends its Interactions API for new projects as of June 2026, while `generateContent`
remains fully supported. The initial Gemini adapter deliberately uses `generateContent` because the
current provider-neutral request carries canonical conversation messages but not the exact
model-generated Interaction steps required for lossless stateless Interactions history. The gateway
will not fabricate provider reasoning/state merely to translate between APIs.

## Repository layout

```text
apps/gateway-api/          future HTTP composition root
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
secret scanning, and the Phase 0 architecture regression gate.

Current Phase 4 implementation validation: **73 tests, 83.38% total coverage, all quality/security
gates PASS**. CI uses fake transports and requires neither provider nor Policy Model Router
credentials.

## Source of truth

Start with `docs/project/CURRENT_STATE.md` for continuation,
`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` for the bound Phase 4 integration contract, and
`docs/project/SOURCE_ROADMAP.txt` for the original project specification.
