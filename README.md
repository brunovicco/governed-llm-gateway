# Governed LLM Gateway

**English** | [Português (Brasil)](README.pt-BR.md)

Reusable provider-neutral LLM execution gateway whose responsibility is **governed model resolution
and execution**.

Status: **Phase 5 — Deterministic Operational Ranking and Explainability implemented; under review**.

The project separates authorization from operational selection:

```text
Application / Agent
       │ workload + requirements + policy metadata
       ▼
Policy Model Router (PDP)
       │ authorized logical model group + provenance
       ▼
Governed LLM Gateway (PEP + operational selection)
       │ eligible ranked deployment
       ▼
LLM Provider
```

Core invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may make authorization narrower due to capability, environment/data policy, cost,
latency, health, or other operational constraints. It must never make authorization broader.

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

Phase 4, merged through PR #3, added the deterministic Policy Model Router boundary:

- prompt-free `PolicyRequestMetadata` application contract;
- trusted policy projection from `EffectivePolicyContext` rather than caller security claims;
- Policy Model Router `POST /route` wire schema `1.0` adapter;
- strict accepted/rejected decision and provenance validation;
- registry intersection with the PDP-authorized logical model group;
- proof that PDP denial or out-of-authorization deployment selection produces zero provider calls;
- no PDP-only metadata copied into provider execution payloads.

Phase 5 adds deterministic operational selection inside that Phase 4 candidate set:

- ADR-0006 for deterministic ranking semantics;
- strict versioned `ranking_policy.yaml` with duplicate-key/unknown-field rejection and SHA-256 digest;
- workload-specific `Decimal` weights for quality, reliability, latency, cost, and availability;
- eligibility before scoring: deployment enabled state, trusted environment/data allowance,
  capabilities, context capacity, static ranking evidence, pricing evidence, cost ceiling, and
  expected-latency ceiling;
- unknown pricing and missing ranking evidence fail closed;
- deterministic weighted score and ascending `deployment_id` tie-break;
- routing provenance includes PDP policy provenance, registry digest, ranking-policy version/digest,
  score snapshot ID, selected provider/model/deployment, and machine-readable rejection reasons;
- registry drift after authorization, candidate-set authorization widening, and ambiguous multi-group
  authorization fail closed;
- authenticated `POST /v1/route/explain` that performs authorization + eligibility + ranking only and
  never invokes a provider;
- explain requests reject prompt/messages, unsupported schema versions, and invalid workload IDs.

Phase 5 static score inputs are explicitly **not** benchmark evidence. `benchmark_snapshot_id` remains
unset until the evaluation/evidence-driven ranking phases.

## Deterministic route explanation

`POST /v1/route/explain` is a metadata-only, no-inference surface. It resolves trusted client context,
obtains the PDP decision, evaluates only the authorized registry candidates, and returns the selected
deployment, alternatives, rejection reasons, and selection provenance.

The endpoint does not accept `messages`. Caller-provided `risk_level`, `data_classification`, or
`agent_identity` are not promoted to authoritative policy facts; the injected trusted context resolver
and PDP boundary remain authoritative.

## Policy Router contract notes

`GatewayRequest.requirements.min_context_tokens` is a model-capability requirement, not an input-token
estimate, so it is not silently translated into Policy Model Router `context_tokens_estimated`.

Policy Model Router API 1.0 expresses tool-calling requirements through the workload policy rule, not
a per-request `tool_calling_required` field. The gateway does not invent one.

Some Policy Model Router deployments may require signed runtime authorization. That belongs to the
later Verifiable AI Governance integration. Until then, such a deployment returns 403 and the gateway
fails closed without calling a provider.

## Gemini API note

Google recommends its Interactions API for new projects as of June 2026, while `generateContent`
remains supported. The initial Gemini adapter deliberately uses `generateContent` because the current
provider-neutral request owns canonical conversation messages but not the exact model-generated
Interaction steps required for lossless stateless Interactions history. The gateway does not fabricate
provider reasoning/state merely to translate between APIs.

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

Current Phase 5 implementation validation: **94 tests, 83.43% total coverage, mypy across 49 source
files, and all quality/security gates PASS**. CI is credential-free and uses `contents: read`.

## Source of truth

Start with `docs/project/CURRENT_STATE.md` for continuation, `docs/adr/ADR-0006-deterministic-candidate-ranking.md`
for Phase 5 ranking semantics, `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` for the Phase 4
authorization binding, and `docs/project/SOURCE_ROADMAP.txt` for the original project specification.
