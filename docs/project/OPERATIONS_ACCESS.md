# Operations Read Access Boundary

## Purpose

PC-20 / OR-4A establishes the authentication and authorization prerequisite for future read-only Operations HTTP surfaces. PC-21 / OR-4B binds that boundary to explicit deployment-owned, secret-free configuration before any Operations route exists.

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

`docs/architecture/ADMIN_SURFACES.md` forbids a global unauthenticated catalog response. PC-19 already gives the service graph access to a process-wide operations snapshot, while PC-20 and PC-21 now provide the authenticated visibility boundary and explicit deployment grant configuration required before transport can be safely attached.

PC-21 deliberately still adds no `/v1/ops/*` route. The next bounded increment may add a first authenticated read-only endpoint only if authorization occurs before the process-wide read model is read and no new secret, PDP, provider or mutation path is introduced.

## Deferred

PC-21 does not add:

- `/v1/ops/*` routes;
- operational-evidence source binding;
- recent routing-history persistence;
- OAuth/OIDC/JWT/mTLS or external IAM integration;
- fleet health aggregation or completeness claims;
- mutation/operator-action endpoints;
- React Gateway Console;
- Phase 14 consumer integrations.

Those remain separate reviewable increments so authentication, descriptive visibility, transport, persistence and mutation authority cannot be collapsed into one implicit admin surface.
