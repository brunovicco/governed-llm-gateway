# Architecture

## Context

Applications declare workload intent and requirements without naming provider/model. The Policy
Model Router determines what logical model group is allowed. The gateway then operates only inside
that authorization boundary, eventually choosing a concrete eligible deployment and executing it
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
  │ authorized model group + policy provenance
  ▼
Governed LLM Gateway
  ├─ validate/correlate authorization provenance
  ├─ intersect authorization with model registry
  ├─ eligibility filter                     (Phase 5)
  ├─ deterministic ranking                  (Phase 5)
  ├─ PEP validation
  └─ execution orchestration
       │
       ▼
Provider adapter → provider API
```

## Fundamental invariant

For each request:

`gateway_eligible_groups ⊆ pdp_authorized_groups`

The gateway can remove candidates because of environment, data policy, capability, health, circuit
state, cost, or latency. It cannot add a logical group/deployment not permitted by policy.

Phase 4 establishes the authorized registry candidate set. Phase 5 begins the operational filters and
ranking that may only reduce that set.

## Package topology

### gateway-contracts

Stable provider-neutral immutable types. It must remain safe for consumer import and therefore has no
provider SDK, FastAPI, database, OpenTelemetry SDK, HTTP client, or business-domain dependency.

### gateway-core

- `domain`: deterministic invariants and gateway-owned concepts;
- `application`: provider-neutral provider/PDP ports and use-case orchestration;
- `adapters`: strict registry loading, Policy Model Router transport, and provider integrations.

The Policy Model Router's Python domain types are not imported as gateway domain/contracts. The
integration boundary is the router's versioned HTTP contract.

### gateway-client

Thin SDK boundary. Consumers eventually hold only gateway credentials. They do not receive provider
or Policy Model Router credentials.

### gateway-api

HTTP composition root. It may depend inward on contracts/core and infrastructure adapters. It must
not push FastAPI/provider/PDP transport types into domain or contracts.

## Trust model

The request schema preserves `risk_level`, `data_classification`, `agent_identity`, and limits because
they are relevant context. These values are **claims** until reconciled with authenticated identity and
policy. Effective security attributes are derived/validated, never accepted solely because a client
sent them.

A client may request stricter treatment. A client may not lower its authoritative classification,
risk restrictions, environment policy, or model authorization.

Phase 4 represents authoritative policy context as `EffectivePolicyContext`. The Policy Model Router
projection uses its trusted client identity, workload, risk, classification, and environment rather
than caller security claims.

## Policy metadata projection

The PDP receives workload/policy metadata only. `GatewayRequest.messages` is not part of the Policy
Model Router request.

The application PDP port accepts `PolicyRequestMetadata`, not `GatewayRequest`, so this privacy
boundary is enforced by type shape in addition to tests.

Policy Model Router responses are also untrusted input. Accepted and rejected decisions are validated
against the expected wire schema and correlated to the originating request/trusted environment before
the gateway treats them as authoritative provenance.

See `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` for the Phase 4 field-level binding.

## Execution boundary

Provider adapters execute concrete models but have no authorization authority. Before a provider
call, the selected deployment must exist in the registry and remain inside the PDP-authorized logical
group/candidate set.

PDP-only security metadata is not copied into provider request payloads. Provider credentials and PDP
credentials remain separate infrastructure concerns.

## Administrative surfaces

Future `/v1/models`, `/v1/route/explain`, `/metrics`, readiness, benchmark, and catalog surfaces are
security boundaries. Implementations must scope returned information to caller authorization or an
explicit administrative role. Global deployment inventories, pricing, health, and policy internals
must not be exposed by default.

## Evidence

Routing evidence is reconstructable without prompt/response storage. Required provenance is defined
in `OBSERVABILITY.md` and the PDP/PEP contract document.

## Dependency direction

```text
consumer projects → gateway client/API → gateway core/contracts
```

Never invert this dependency. Consumer repositories are integration fixtures/examples, not gateway
runtime dependencies.
