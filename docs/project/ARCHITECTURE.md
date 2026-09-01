# Architecture

## Context

Applications declare workload intent and requirements without naming provider/model. The Policy
Model Router determines which logical model group is allowed. The gateway then operates only inside
that authorization boundary, filters/ranks concrete deployments deterministically, and later executes
through a provider adapter.

```text
Consumer
  │ GatewayRequest
  ▼
Authentication / workload identity
  │ authoritative EffectivePolicyContext
  ▼
Prompt-free policy projection
  │
  ▼
Policy Model Router (PDP)
  │ one authorized model group + policy provenance
  ▼
Governed LLM Gateway
  ├─ validate/correlate authorization provenance
  ├─ intersect authorization with model registry      (Phase 4)
  ├─ validate registry/authorization binding          (Phase 5)
  ├─ static eligibility filter                        (Phase 5)
  ├─ deterministic ranking + explanation              (Phase 5)
  ├─ PEP validation
  └─ execution orchestration
       │
       ▼
Provider adapter → provider API
```

## Fundamental invariant

For each request:

`gateway_eligible_groups ⊆ pdp_authorized_groups`

The gateway can remove candidates because of environment, data policy, capability, cost, latency,
and later health/circuit state. It cannot add a logical group/deployment not permitted by policy.

Phase 4 establishes the authorized registry candidate set. Phase 5 only filters and orders that set.
It does not re-enumerate the global registry to discover alternatives after authorization.

## Package topology

### gateway-contracts

Stable provider-neutral immutable types. It must remain safe for consumer import and therefore has no
provider SDK, FastAPI, database, OpenTelemetry SDK, HTTP client, or business-domain dependency.

Phase 5 extends routing provenance/rejection vocabularies only with provider-neutral metadata needed
to reconstruct deterministic selection.

### gateway-core

- `domain`: deterministic invariants, model registry, and versioned ranking-policy semantics;
- `application`: provider-neutral provider/PDP ports plus authorization/ranking orchestration;
- `adapters`: strict registry/ranking-policy configuration loading, Policy Model Router transport,
  and provider integrations.

The Policy Model Router's Python domain types are not imported into gateway domain/contracts. The
integration boundary remains the router's versioned HTTP contract.

### gateway-client

Thin SDK boundary. Consumers eventually hold only gateway credentials. They do not receive provider
or Policy Model Router credentials.

### gateway-api

HTTP composition root. Phase 5 introduces the authenticated `POST /v1/route/explain` surface here.
FastAPI/Pydantic request/response types remain outside gateway contracts/domain.

## Trust model

The request schema preserves `risk_level`, `data_classification`, `agent_identity`, and limits because
they are relevant context. These values are **claims** until reconciled with authenticated identity and
policy. Effective security attributes are derived/validated, never accepted solely because a client
sent them.

A client may request stricter treatment. A client may not lower its authoritative classification,
risk restrictions, environment policy, or model authorization.

`EffectivePolicyContext` represents authoritative policy context. The PDP projection and Phase 5
eligibility use trusted client identity/workload/risk/classification/environment rather than
caller-spoofed security claims.

## Authorization-to-ranking binding

The Phase 4 `AuthorizedCandidateSet` binds:

- validated PDP decision/provenance;
- the exact model-registry digest used to derive candidates;
- deployments in the authorized logical model group.

Before ranking, Phase 5 requires that the current registry digest still matches that authorization
snapshot and that exactly one logical group is authorized by the current PMR 1.0 binding. A candidate
outside that group is an invariant violation, not a lower-ranked alternative.

This prevents authorization widening and registry time-of-check/time-of-use substitution across the
Phase 4 → Phase 5 boundary.

## Deterministic ranking

Phase 5 static eligibility evaluates enabled state, trusted environment/data allowance, capabilities,
context capacity, static ranking input availability, versioned pricing, projected cost, and expected
latency before calculating a score.

Eligible candidates are scored using exact `Decimal` arithmetic with workload-specific versioned
weights and a stable ascending `deployment_id` tie-break. No randomness, provider call, wall-clock
value, live health state, or LLM classification participates in Phase 5 ranking.

Live health and circuit-breaker state are Phase 6 inputs and must only narrow the Phase 5/PDP-safe
candidate set.

## Policy metadata projection

The PDP receives workload/policy metadata only. `GatewayRequest.messages` is not part of the Policy
Model Router request. The application PDP port accepts `PolicyRequestMetadata`, not `GatewayRequest`,
so this privacy boundary is enforced by type shape in addition to tests.

Policy Model Router responses are untrusted input. Accepted/rejected decisions are validated against
the expected wire schema and correlated to the originating request/trusted environment before being
treated as authoritative provenance.

See `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` for the Phase 4 field-level binding.

## Explainability surface

`POST /v1/route/explain` performs trusted-context resolution, PDP authorization, static eligibility,
deterministic ranking, and metadata-only explanation. It performs no provider inference.

The request is deliberately prompt-free and closed to unknown fields. It validates schema version and
workload identifier at the HTTP boundary. The response carries only the caller's decision metadata,
not a global deployment inventory.

## Execution boundary

Provider adapters execute concrete models but have no authorization authority. Before provider
execution, a selected deployment must exist in the registry and remain inside PDP authorization.
Phase 6 resilience must preserve the same rule for every retry/fallback candidate.

PDP-only security metadata is not copied into provider request payloads. Provider credentials and PDP
credentials remain separate infrastructure concerns.

## Evidence

Routing evidence is reconstructable without prompt/response storage. Phase 5 adds ranking-policy
version/digest, static score snapshot ID, deterministic routing decision ID, selected deployment, and
candidate rejection reasons alongside existing PDP and model-registry provenance.

Static `score_snapshot_id` is not benchmark evidence; `benchmark_snapshot_id` remains unset until the
benchmark/evidence-driven ranking phases.

## Dependency direction

```text
consumer projects → gateway client/API → gateway core/contracts
```

Never invert this dependency. Consumer repositories are integration fixtures/examples, not gateway
runtime dependencies.
