# Authenticated Operations Overview HTTP Contract

## Purpose

PC-22 / OR-4C exposes the first read-only Operations HTTP surface after the typed read model (PC-18/PC-19) and the independent authenticated visibility boundary plus deployment-owned grants (PC-20/PC-21) are already in place. PC-23 optionally binds one already-reviewed deployment-owned operational-evidence snapshot into that same read path.

The only implemented endpoint remains:

```text
GET /v1/ops/overview
```

It is an intentionally bounded overview, not a model catalog, deployment-detail API, evidence-detail API, control plane, or inference authorization surface.

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
DeploymentOperationsSnapshotReader.snapshot()
        ↓ already-composed OperationsReadModelService
bounded overview projection
```

Authorization MUST complete before the operations snapshot is read. Missing/invalid credentials and authenticated-but-ungranted callers therefore cannot observe registry, ranking, health, or operational-evidence state.

The endpoint does not construct a synthetic workload, call the Policy Router, resolve a provider, execute inference, resolve another credential, reopen evidence files, or discover artifacts. `OperationsReadAccessService` continues to reuse the already-materialized `StaticGatewayClientContextResolver` established at process startup.

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
- `ranking`: policy provenance, score snapshot identity, and optional ranking-evidence provenance identifiers;
- `health`: `process_local` scope and aggregate healthy/degraded/unhealthy deployment counts;
- `operational_evidence`: availability state only (`not_supplied` or `available`).

The aggregate health count must exactly equal the active registry deployment count. A mismatch fails closed with the sanitized 503 response rather than returning a partial or misleading overview.

PC-23 does not widen the operational-evidence HTTP projection. A configured valid artifact changes only `operational_evidence.state` to `available`; the response still excludes individual evidence records and provenance fields.

The response intentionally excludes:

- authenticated principal identity;
- operations grant metadata;
- deployment IDs;
- provider names;
- model IDs;
- API families;
- per-deployment counters or latency;
- operational-evidence records, collector identity, timestamps, or `evidence_id`;
- workload authorization;
- secret/config references;
- raw provider/Policy Router state;
- mutable resilience internals.

## Composition

`compose_governed_gateway_services(...)` attaches the endpoint to the existing FastAPI application using the exact already-composed access service plus one immutable snapshot reader:

```text
GovernedGatewayServices.operations_read_access
GovernedGatewayServices.operations_snapshot_reader
```

The snapshot reader wraps the exact active `OperationsReadModelService` and the optional `OperationalEvidenceSnapshot` that was loaded and validated during secret-free application startup. It does not perform artifact I/O per request.

No new secret resolver, network client, PDP adapter, provider adapter, health tracker, or ranking authority is created for the HTTP surface.

Duplicate route attachment fails before a second `/v1/ops/overview` route is registered.

See `docs/project/OPERATIONAL_EVIDENCE_BINDING.md` for the PC-23 startup/binding and non-authority contract.

## Authority invariant

The permanent inference invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operations visibility is descriptive and independently granted. Reading the overview cannot authorize models, widen or restore PDP output, change eligibility/complexity/ranking, mutate health/circuit state, affect retry/fallback, execute providers, or mutate runtime configuration.

Health and evidence remain descriptive signals, not authority.

## Deferred

PC-22/PC-23 do not add:

- `/v1/ops/deployments` or deployment detail;
- operational-evidence detail serialization;
- operational-evidence automatic refresh/discovery or freshness policy;
- recent routing-history persistence or API;
- fleet aggregation/completeness claims;
- OAuth/OIDC/JWT/mTLS/external IAM;
- operator mutation/control APIs;
- React Gateway Console;
- Phase 14 consumer integrations.

Each remains a separate reviewable increment so visibility, evidence lifecycle, persistence, fleet semantics, external identity, and mutation authority are not collapsed into one admin surface.
