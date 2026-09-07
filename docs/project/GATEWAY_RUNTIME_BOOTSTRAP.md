# Gateway Runtime Bootstrap

## Purpose

PC-5 composes the deployment-owned Gateway runtime artifacts and secret-backed resolvers without creating a module-level application singleton or changing model authority.

The bootstrap combines:

- `config/model_registry.yaml`;
- `config/providers/runtime.json`;
- `config/clients/auth.json`.

The checked-in versions of all three artifacts remain empty/fail-closed. Therefore the repository default bootstrap performs no provider or Gateway-client secret reads and enables no deployment or client identity.

## Startup ordering

`bootstrap_gateway_runtime(...)` deliberately separates configuration validation from credential resolution:

```text
load model registry
load provider runtime document
load Gateway client-auth document
validate provider runtime <-> enabled registry API families
        ↓
all structural and cross-artifact gates passed
        ↓
resolve provider credential references
resolve Gateway client credential references
        ↓
immutable GatewayRuntimeBootstrapBundle
```

This ordering is a security boundary. A malformed client-auth artifact cannot cause provider secret access, and a provider-runtime/registry mismatch cannot cause Gateway client secret access.

Provider and client credentials are resolved only after all committed configuration artifacts have passed their deterministic validation gates.

## Runtime bundle

`GatewayRuntimeBootstrapBundle` exposes only validated runtime objects and non-secret provenance:

- validated `ModelRegistry`;
- validated `ProviderRuntimeDocument`;
- validated `GatewayClientAuthDocument`;
- immutable `StaticProviderResolver`;
- immutable `StaticGatewayClientContextResolver`;
- model-registry digest;
- provider-runtime digest and config version;
- client-auth digest and config version.

Raw resolved credentials remain private to the underlying static resolvers. They are not added to bootstrap provenance, configuration documents, logs, traces, errors, or evidence.

## Authority boundary

Runtime bootstrap is composition, not authorization.

It can establish that a provider adapter exists and that a Gateway client credential maps to trusted client/workload context. It cannot authorize a provider, model, deployment, model group, retry, fallback, ranking outcome, or business action.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The operational sequence remains:

```text
authenticated workload
    -> Policy Decision Point authorization
    -> authorized model set
    -> registry/capability eligibility
    -> optional complexity narrowing/ranking
    -> resilience/execution
```

Neither the provider resolver nor the client-auth resolver can widen the Policy Router authorized set.

## Deferred process activation

PC-5 deliberately does not add:

- a module-level FastAPI `app` singleton;
- a `uvicorn` or container process entrypoint;
- live client bindings;
- live provider bindings or model deployments;
- raw credentials in repository artifacts;
- OAuth/OIDC/JWT/mTLS;
- cloud-specific secret-manager adapters;
- changes to PDP, ranking, complexity, health, retry/fallback, or Phase 14 sequencing.

A later process-composition increment may connect this validated runtime bundle to the existing coordinators and HTTP routes. That step must preserve the same validate-before-secret ordering and the existing authorization boundary.
