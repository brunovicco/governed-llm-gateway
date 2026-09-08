# Authenticated Operations Overview HTTP Contract

## Purpose

PC-22 / OR-4C exposes the first read-only Operations HTTP surface after the typed read model (PC-18/PC-19) and the independent authenticated visibility boundary plus deployment-owned grants (PC-20/PC-21) are already in place.

The only endpoint added by this increment is:

```text
GET /v1/ops/overview
```

It is an intentionally bounded overview, not a model catalog, deployment-detail API, control plane, or inference authorization surface.

## Authentication and authorization order

The endpoint reuses the existing Gateway credential header:

```text
X-Gateway-API-Key
```

The request flow is fixed:

```text
X-Gateway-API-Key
        ↓
OperationsReadAccessService.authorize(...)
        ↓ exact authenticated (client_id, environment) grant
OperationsReadModelService.snapshot()
        ↓
bounded overview projection
```

Authorization MUST complete before the operations snapshot is read. Missing/invalid credentials and authenticated-but-ungranted callers therefore cannot observe registry, ranking, health, or operational-evidence state.

The endpoint does not construct a synthetic workload, call the Policy Router, resolve a provider, execute inference, or resolve another credential. `OperationsReadAccessService` continues to reuse the already-materialized `StaticGatewayClientContextResolver` established at process startup.

## HTTP failures

The adapter emits stable sanitized failures:

| Status | Code | Meaning |
| --- | --- | --- |
| 401 | `invalid_gateway_credential` | credential is missing or authentication failed |
| 403 | `operations_read_access_denied` | authenticated principal has no exact operations-read grant |
| 503 | `operations_snapshot_unavailable` | the read model or bounded overview invariant failed |

Raw exceptions, principal identifiers, grant contents, credentials, secret references, provider errors, and internal snapshot details are not serialized.

## Response boundary

The response contains only four bounded sections:

- `registry`: schema/catalog provenance, source date, digest, and deployment count;
- `ranking`: policy provenance, score snapshot identity, and optional evidence provenance identifiers;
- `health`: `process_local` scope and aggregate healthy/degraded/unhealthy deployment counts;
- `operational_evidence`: availability state only (`not_supplied` or `available`).

The aggregate health count must exactly equal the active registry deployment count. A mismatch fails closed with the sanitized 503 response rather than returning a partial or misleading overview.

The response intentionally excludes:

- authenticated principal identity;
- operations grant metadata;
- deployment IDs;
- provider names;
- model IDs;
- API families;
- per-deployment counters or latency;
- workload authorization;
- secret/config references;
- raw provider/Policy Router state;
- mutable resilience internals.

## Composition

`compose_governed_gateway_services(...)` attaches the endpoint to the existing FastAPI application using the exact already-composed instances:

```text
GovernedGatewayServices.operations_read_access
GovernedGatewayServices.operations_read_model
```

No new config, secret resolver, network client, PDP adapter, provider adapter, health tracker, or ranking authority is created for the HTTP surface.

Duplicate route attachment fails before a second `/v1/ops/overview` route is registered.

## Authority invariant

The permanent inference invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operations visibility is descriptive and independently granted. Reading the overview cannot authorize models, widen or restore PDP output, change eligibility/complexity/ranking, mutate health/circuit state, affect retry/fallback, execute providers, or mutate runtime configuration.

Health and evidence remain descriptive signals, not authority.

## Deferred

PC-22 does not add:

- `/v1/ops/deployments` or deployment detail;
- operational-evidence detail/source binding;
- recent routing-history persistence or API;
- fleet aggregation/completeness claims;
- OAuth/OIDC/JWT/mTLS/external IAM;
- operator mutation/control APIs;
- React Gateway Console;
- Phase 14 consumer integrations.

Each remains a separate reviewable increment so visibility, persistence, fleet semantics, external identity, and mutation authority are not collapsed into one admin surface.
