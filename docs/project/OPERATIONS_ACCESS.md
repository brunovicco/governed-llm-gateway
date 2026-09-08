# Operations Read Access Boundary

## Purpose

PC-20 / OR-4A establishes the authentication and authorization prerequisite for future read-only Operations HTTP surfaces.

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
        ↓
future read-only Operations API
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

## Error separation

Authentication and operations authorization remain distinguishable internal contracts:

- unknown, malformed, or ambiguous Gateway credentials retain `ClientAuthenticationError("gateway credential rejected")`;
- authenticated principals without an operations grant receive `OperationsReadAuthorizationError("operations read access denied")`.

A future HTTP adapter may map those contracts to stable 401/403 responses without serializing principal IDs, grants, credentials, or backend exceptions.

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

## Why no HTTP route yet

`docs/architecture/ADMIN_SURFACES.md` forbids a global unauthenticated catalog response. PC-19 already gives the service graph access to a process-wide operations snapshot, so attaching that snapshot directly to FastAPI before access configuration exists would expose more metadata than ordinary workload credentials are authorized to discover.

PC-20 deliberately adds no `/v1/ops/*` route. The next bounded increment must bind a deployment-owned, secret-free operations access artifact to the already-materialized client authenticator before an HTTP route is attached.

## Deferred

PC-20 does not add:

- operations access JSON/YAML artifact or loader;
- process/deployment settings for operations principals;
- `/v1/ops/*` routes;
- operational-evidence source binding;
- OAuth/OIDC/JWT/mTLS or external IAM integration;
- fleet health aggregation or completeness claims;
- mutation/operator-action endpoints;
- React Gateway Console;
- Phase 14 consumer integrations.

Those remain separate reviewable increments so authentication, descriptive visibility, transport, and mutation authority cannot be collapsed into one implicit admin surface.
