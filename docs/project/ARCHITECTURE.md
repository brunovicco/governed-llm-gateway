# Architecture

## Context

Applications declare workload intent and requirements without naming provider/model. The Policy
Model Router determines what logical model group is allowed. The gateway then chooses a concrete,
eligible deployment from that authorized group and eventually executes it through a provider adapter.

```text
Consumer
  │ GatewayRequest
  ▼
Authentication / workload identity
  │ authoritative identity context
  ▼
Policy Model Router (PDP)
  │ authorized model group + policy provenance
  ▼
Governed LLM Gateway
  ├─ validate authorization provenance
  ├─ load versioned registry/ranking inputs
  ├─ eligibility filter
  ├─ deterministic ranking
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

## Package topology

### gateway-contracts

Stable provider-neutral immutable types. It must remain safe for consumer import and therefore has no
provider SDK, FastAPI, database, OpenTelemetry SDK, HTTP client, or business-domain dependency.

### gateway-core

- `domain`: deterministic invariants and gateway-owned concepts;
- `application`: ports/use-case orchestration;
- `adapters`: infrastructure/provider integrations in later phases.

### gateway-client

Thin SDK boundary. Consumers eventually hold only gateway credentials.

### gateway-api

HTTP composition root. It may depend inward on contracts/core and later infrastructure adapters. It
must not push FastAPI/provider types into the domain or contracts.

## Trust model

The request schema preserves `risk_level`, `data_classification`, `agent_identity`, and limits because
they are relevant context. These values are **claims** until reconciled with authenticated identity and
policy. Effective security attributes are derived/validated, never accepted solely because a client
sent them.

A client may request stricter treatment. A client may not lower its authoritative classification,
risk restrictions, environment policy, or model authorization.

## Policy metadata projection

The PDP receives workload/policy metadata only. Message content is not part of the policy routing
request in the initial design.

## Administrative surfaces

Future `/v1/models`, `/v1/route/explain`, `/metrics`, readiness, benchmark, and catalog surfaces are
security boundaries. Implementations must scope returned information to caller authorization or an
explicit administrative role. Global deployment inventories, pricing, health, and policy internals
must not be exposed by default.

## Evidence

Routing evidence is reconstructable without prompt/response storage. Required provenance is defined
in `OBSERVABILITY.md` and the contract draft.

## Dependency direction

```text
consumer projects → gateway client/API → gateway core/contracts
```

Never invert this dependency. Consumer repositories are integration fixtures/examples, not gateway
runtime dependencies.
