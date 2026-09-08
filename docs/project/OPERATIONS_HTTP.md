# Authenticated Operations HTTP Contract

## Purpose

PC-22 / OR-4C introduced the first read-only Operations HTTP surface after the typed read model (PC-18/PC-19) and the independent authenticated visibility boundary plus deployment-owned grants (PC-20/PC-21) were already in place. PC-23 optionally binds one already-reviewed deployment-owned operational-evidence snapshot into that same read path. PC-24 adds a second bounded read-only projection for the active deployment catalog. PC-34 adds the first bounded OR-9 HTTP cache hardening for this authenticated namespace.

The implemented endpoints are:

```text
GET /v1/ops/overview
GET /v1/ops/deployments
```

They are descriptive operator surfaces, not deployment-detail APIs, evidence-detail APIs, control-plane mutation APIs, or inference authorization surfaces.

## Authentication and authorization order

Both endpoints reuse the existing Gateway credential header:

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
bounded HTTP projection
```

Authorization MUST complete before the operations snapshot is read. Missing/invalid credentials and authenticated-but-ungranted callers therefore cannot observe registry, ranking, health, operational-evidence state, or the deployment catalog.

The endpoints do not construct a synthetic workload, call the Policy Router, resolve a provider, execute inference, resolve another credential, reopen evidence files, or discover artifacts. `OperationsReadAccessService` continues to reuse the already-materialized `StaticGatewayClientContextResolver` established at process startup.

## HTTP failures

The adapter emits stable sanitized failures:

| Status | Code | Meaning |
| --- | --- | --- |
| 401 | `invalid_gateway_credential` | credential is missing or authentication failed |
| 403 | `operations_read_access_denied` | authenticated principal has no exact operations-read grant |
| 503 | `operations_snapshot_unavailable` | the read model or bounded projection cannot be produced safely |

Raw exceptions, principal identifiers, grant contents, credentials, secret references, provider errors, and internal snapshot details are not serialized.

## Cache policy — PC-34

Every HTTP response whose path is under the owned `/v1/ops/` namespace carries:

```http
Cache-Control: no-store
```

The policy is applied outside the individual route return models so it covers both successful projections and sanitized failures, including 401, 403, 503 and unknown Operations paths. This is required because Operations authentication uses the custom `X-Gateway-API-Key` header; intermediary caches must not be relied upon to infer credential-aware cache semantics for that header.

The middleware is namespace-scoped. It does not assign this Operations cache policy to inference, process-health/readiness, provider, PDP, Grafana or unrelated application routes. It does not place a credential in response metadata and does not change authentication, authorization, snapshot ordering, response bodies or inference authority.

`no-store` is bounded cache hardening only. It is not a production browser identity/session architecture, TLS policy, CSRF design or rate-limiting system.

## Overview response boundary

`GET /v1/ops/overview` contains only four bounded sections:

- `registry`: schema/catalog provenance, source date, digest, and deployment count;
- `ranking`: policy provenance, score snapshot identity, and optional ranking-evidence provenance identifiers;
- `health`: `process_local` scope and aggregate healthy/degraded/unhealthy deployment counts;
- `operational_evidence`: availability state only (`not_supplied` or `available`).

The aggregate health count must exactly equal the active registry deployment count. A mismatch fails closed with the sanitized 503 response rather than returning a partial or misleading overview.

PC-23 does not widen the operational-evidence HTTP projection. A configured valid artifact changes only `operational_evidence.state` to `available`; the overview still excludes individual evidence records and provenance fields.

The overview intentionally excludes authenticated principal identity, operations grant metadata, deployment/model/provider identities, per-deployment counters and latency, evidence records, workload authorization, secret/config references, raw provider/Policy Router state, and mutable resilience internals.

## Deployment catalog response boundary

`GET /v1/ops/deployments` exposes the deterministic deployment ordering already supplied by the typed `OperationsSnapshot`. The response declares:

```text
health_scope = process_local
```

Each deployment contains only the approved catalog fields already projected by `OperationsDeploymentSummary`:

- `deployment_id`;
- `provider`;
- `model_id`;
- `model_group`;
- `api_family`;
- `enabled`;
- `capabilities`;
- `modalities`;
- `context_tokens`;
- `max_data_classification`;
- `allowed_environments`;
- `pricing_snapshot_version`;
- coarse process-local health: `status` and `circuit_state`.

PC-24 deliberately excludes mutable execution counters and detailed runtime measurements, including request/success/failure counts, transient failure counts, timeout/rate-limit/server-error counts, consecutive-failure counts, and last latency. It also excludes provider endpoints, credential references, secrets, operations principal/grant metadata, operational-evidence records, and raw SDK state.

`process_local` is a scope claim, not fleet completeness. A deployment health value must not be presented as global or fleet-complete state.

## Composition

`compose_governed_gateway_services(...)` attaches both endpoints to the existing FastAPI application using the exact already-composed access service plus one immutable snapshot reader:

```text
GovernedGatewayServices.operations_read_access
GovernedGatewayServices.operations_snapshot_reader
```

The snapshot reader wraps the exact active `OperationsReadModelService` and the optional `OperationalEvidenceSnapshot` loaded and validated during secret-free application startup. It does not perform artifact I/O per request.

No new secret resolver, network client, PDP adapter, provider adapter, health tracker, or ranking authority is created for the HTTP surfaces.

Operations route attachment owns both `/v1/ops/overview` and `/v1/ops/deployments`. The composition checks both paths before registering either route, so a conflict fails closed before partial attachment. Re-attaching the owned Operations surface also fails closed. PC-34 attaches the no-store middleware only after this conflict check succeeds, so failed/duplicate composition does not partially add a second Operations security layer.

See `docs/project/OPERATIONAL_EVIDENCE_BINDING.md` for the PC-23 startup/binding and non-authority contract.

## Authority invariant

The permanent inference invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operations visibility is descriptive and independently granted. Reading either endpoint cannot authorize models, widen or restore PDP output, change eligibility/complexity/ranking, mutate health/circuit state, affect retry/fallback, execute providers, or mutate runtime configuration.

Health and evidence remain descriptive signals, not authority.

## Deferred

PC-34 still does not add:

- `GET /v1/ops/deployments/{deployment_id}`;
- detailed per-deployment counters or latency;
- operational-evidence detail serialization;
- operational-evidence automatic refresh/discovery or freshness policy;
- recent routing-history persistence or API;
- fleet aggregation/completeness claims;
- production OAuth/OIDC/JWT/mTLS/external IAM;
- browser session/token-exchange architecture;
- rate limiting or CSRF policy;
- operator mutation/control APIs;
- broader React Gateway Console surfaces;
- OR-9 completion;
- OR-10 completion;
- Phase 14 consumer integrations.

Each remains a separate reviewable increment so catalog visibility, evidence lifecycle, persistence, fleet semantics, external identity, mutation authority and browser security architecture are not collapsed into one admin surface.
