# Operations Read Access Boundary

## Purpose

PC-20 / OR-4A establishes the authentication and authorization prerequisite for read-only Operations HTTP surfaces. PC-21 / OR-4B binds that boundary to explicit deployment-owned, secret-free configuration. PC-22 / OR-4C uses those exact composed services to expose the first bounded authenticated endpoint, `GET /v1/ops/overview`.

The Gateway already has an authenticated workload boundary, but workload authorization is not administrative authorization. A credential allowed to execute `rag.answer` or `code.review` must not automatically gain visibility into the process-wide model registry, ranking provenance, or deployment health.

The operations flow is therefore kept separate:

```text
X-Gateway-API-Key
        ↓
existing StaticGatewayClientContextResolver
        ↓ authenticate only
GatewayClientIdentity
        ↓
OperationsReadAccessPolicy
        ↓ exact principal grant
OperationsReadAccessService
        ↓ authorize before read
OperationsReadModelService
        ↓
bounded read-only Operations API
```

No synthetic `GatewayRequest` is created for operations access.

## Reused authentication boundary

`StaticGatewayClientContextResolver.authenticate(...)` exposes only:

- authenticated `client_id`;
- authenticated deployment `environment`.

It reuses the same bounded credential validation and constant-time comparison path as inference authentication. It does not resolve credentials again, contact a secret backend, inspect `allowed_workloads`, construct `EffectivePolicyContext`, call the Policy Router, or grant model authority.

Existing `resolve(...)` semantics remain workload-scoped. After the same credential is authenticated, the requested workload must still be an exact member of the binding's `allowed_workloads`, and the existing monotonic risk/classification reconciliation remains unchanged.

## Operations-read policy

`OperationsReadAccessPolicy` is immutable and secret-free. Its grants are exact `GatewayClientIdentity` values:

```text
(client_id, environment)
```

The policy requires deterministic ordering and unique principals. It supports an empty grant tuple intentionally; empty means deny all.

There are no:

- wildcard principals;
- inferred roles;
- workload-to-admin promotion rules;
- raw API keys;
- credential references;
- provider/model grants;
- mutation permissions.

`OperationsReadAccessService.authorize(...)` first authenticates the Gateway credential and then requires exact principal membership. A valid Gateway credential without a grant receives a sanitized operations authorization failure that does not disclose the configured grant set.

## Deployment-owned grant artifact

PC-21 adds a closed JSON `OperationsReadAccessDocument` containing only:

- `schema_version`;
- `config_version`;
- ordered exact `(client_id, environment)` principals.

The document is loaded in the existing secret-free process bootstrap. Every granted principal must match an identity in the already-loaded Gateway client-auth document before any client, Policy Router, or provider credential is read.

If `operations_access_path` is omitted, the process materializes an explicit deny-all policy. There is no file discovery or permissive fallback.

After validation, the operations access service is built with the same already-materialized `StaticGatewayClientContextResolver` used by inference. It is then carried by identity from `GovernedProcessRuntimeBundle.operations_read_access` into `GovernedGatewayServices.operations_read_access`. Operations authorization therefore performs no second secret resolution.

The executable process accepts only `--operations-access-path`. It has no raw operations credential, wildcard admin, principal injection, or authorization-bypass flag.

See `docs/project/OPERATIONS_ACCESS_ARTIFACT.md` for the artifact schema, bootstrap order, provenance and deployment path semantics.

## HTTP exposure

PC-22 exposes exactly one Operations route:

```text
GET /v1/ops/overview
```

The adapter reuses `X-Gateway-API-Key`, calls the already-composed `OperationsReadAccessService` first, and only after authorization reads the already-composed `OperationsReadModelService`. Missing/invalid credentials return sanitized 401; authenticated principals without a grant return sanitized 403; read-model/invariant failures return sanitized 503.

The overview is deliberately smaller than the internal operations snapshot. It exposes registry/ranking provenance, aggregate `process_local` health counts, and operational-evidence availability state. It does not serialize principal identity, grant metadata, deployment/model/provider identifiers, per-deployment counters, credential references, raw exceptions, or mutable runtime internals.

See `docs/project/OPERATIONS_HTTP.md` for the exact transport and response contract.

## Error separation

Authentication and operations authorization remain distinguishable internal contracts:

- unknown, malformed, or ambiguous Gateway credentials retain `ClientAuthenticationError("gateway credential rejected")`;
- authenticated principals without an operations grant receive `OperationsReadAuthorizationError("operations read access denied")`.

The HTTP adapter maps those contracts to stable sanitized 401/403 responses without serializing principal IDs, grants, credentials, or backend exceptions.

## Authority invariant

The permanent inference invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operations-read authorization controls only visibility of descriptive operational metadata. It cannot:

- authorize a model group or deployment;
- widen or restore a PDP-authorized set;
- change capability eligibility;
- change complexity narrowing or ranking;
- change health/circuit state;
- change retry/fallback eligibility;
- execute a provider request;
- execute a business tool;
- mutate policy, registry, ranking, evidence, or runtime state.

The Policy Router is therefore not called merely to decide whether an authenticated operator may view descriptive operations metadata. This administrative read grant is a separate Gateway surface authorization boundary, not a substitute for model authorization.

## Deferred

PC-22 does not add:

- deployment-detail/model-catalog Operations routes;
- operational-evidence detail/source binding;
- recent routing-history persistence;
- OAuth/OIDC/JWT/mTLS or external IAM integration;
- fleet health aggregation or completeness claims;
- mutation/operator-action endpoints;
- React Gateway Console;
- Phase 14 consumer integrations.

Those remain separate reviewable increments so authentication, descriptive visibility, transport, persistence and mutation authority cannot be collapsed into one implicit admin surface.
