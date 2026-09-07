# Staged Governed Process Bootstrap

## Purpose

PC-8 closes a startup-ordering gap between the existing Gateway runtime bootstrap and the Policy Router runtime bootstrap.

Before PC-8, each bootstrap was fail closed within its own scope, but a future process composer could call them sequentially and resolve Gateway client or provider credentials before discovering a later Policy Router/client-auth mismatch.

The governed process bootstrap makes the cross-runtime ordering explicit:

```text
load model registry
load provider runtime
load Gateway client auth
load Policy Router runtime
        ↓
validate every closed schema
validate provider runtime ↔ model registry
validate Policy Router client IDs ↔ Gateway client-auth client IDs
        ↓
NO SECRET HAS BEEN READ
        ↓
resolve Gateway client credentials
resolve Policy Router credentials
resolve provider credentials
        ↓
materialized runtime adapters
```

## Two explicit stages

`load_governed_process_artifacts(...)` is the no-secret stage.

It returns an immutable `GovernedProcessArtifacts` value containing:

- the validated model registry;
- the validated provider-runtime document;
- the validated Gateway client-auth document;
- the validated Policy Router runtime document.

`GovernedProcessArtifacts.__post_init__` reruns both cross-artifact gates, so direct construction cannot bypass the provider/runtime or Policy Router/client-auth consistency boundaries.

`materialize_governed_process_runtime(...)` is the secret stage. It accepts only a validated `GovernedProcessArtifacts` value and builds:

- `StaticGatewayClientContextResolver`;
- optional `PolicyRouterHttpAdapter`;
- `StaticProviderResolver`.

`bootstrap_governed_process_runtime(...)` is only a convenience wrapper over those two stages and preserves the same ordering.

## Credential ordering

After all no-secret validation succeeds, credentials are resolved in this deterministic order:

```text
consumer → Gateway
Gateway → Policy Router
Gateway → model providers
```

This is a least-privilege startup preference, not an authorization rule. If consumer or PDP credential materialization fails, provider credentials are not touched unnecessarily.

The credential classes remain independent:

- `GatewayClientSecretResolver` resolves credentials presented by consumers to the Gateway;
- `PolicyRouterSecretResolver` resolves credentials used by the Gateway to call the deterministic Policy Router;
- `ProviderSecretResolver` resolves credentials used by the Gateway to call model providers.

No raw credential is stored in `GovernedProcessArtifacts`, configuration digests, routing evidence, telemetry, or checked-in defaults.

## Authority boundary

The staged bootstrap changes startup composition only. It does not authorize workloads, model groups, models, deployments, retries, or fallbacks.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The validated artifacts can establish that runtime dependencies are coherently configured. Only an accepted Policy Router decision establishes the upstream logical model-group authorization for a request.

Registry metadata, runtime enablement, credential presence, complexity, ranking, benchmark evidence, health, telemetry, retry, and fallback remain non-authoritative.

## Checked-in defaults

The repository defaults remain intentionally inert:

- empty model registry;
- empty provider runtime;
- empty Gateway client-auth bindings;
- disabled Policy Router runtime with no endpoint or bindings.

Running both bootstrap stages over those defaults performs zero secret reads and creates no active Policy Router adapter.

## What PC-8 does not do

PC-8 does not add:

- a module-level FastAPI `app` singleton;
- a `uvicorn` or container process entrypoint;
- real credentials or live external calls;
- production model/provider/client activation;
- ranking-policy or complexity-policy loading into the process;
- health/resilience/observability service composition;
- OAuth/OIDC/JWT/mTLS or cloud secret-manager adapters;
- Phase 14 integration changes.

## Next composition slice

A later process-composition increment can safely build the PEP, operational and complexity route services, health tracker, streaming execution service, coordinators, observability, and `create_gateway_app(...)` on top of `GovernedProcessRuntimeBundle`.

That later wiring must consume the already-materialized runtime bundle rather than re-reading deployment secrets or recreating an independent Policy Router/client-auth relationship.
