# Gateway Application Composition

## Purpose

PC-6 adds one explicit FastAPI composition factory for the existing Governed LLM Gateway HTTP surfaces.

`create_gateway_app(...)` mounts:

- `POST /v1/route/explain`;
- `POST /v1/generate`.

The factory receives already-constructed coordinators. It does not load files, read environment variables, resolve credentials, construct the Policy Router adapter, enumerate models, build ranking evidence, or create provider candidates.

## Composition boundary

```text
reviewed application dependencies
    ├─ RouteExplainCoordinator
    ├─ GenerateCoordinator
    ├─ optional ComplexityRouteExplainCoordinator
    ├─ optional ComplexityGenerateCoordinator
    └─ optional a2a-otel-kit Observability
                 ↓
        create_gateway_app(...)
                 ↓
             FastAPI app
        ├─ /v1/route/explain
        └─ /v1/generate
```

The same optional observability instance is passed to both HTTP surfaces so application composition does not introduce a second telemetry path.

Operational mode remains the default on both endpoints. Complexity mode remains explicit and fail closed: requesting `mode=complexity` without the corresponding optional coordinator returns the existing bounded `complexity_routing_unavailable` error.

## Authority boundary

Application composition is dependency wiring only. It cannot authorize a model, model group, provider, deployment, retry, fallback, or business action.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The factory has no direct dependency on the Model Registry, provider runtime configuration, provider secrets, Gateway client secrets, ranking policy, benchmark evidence, or the PDP port. Those dependencies remain behind the coordinators and application services that already enforce the reviewed boundaries.

## Relationship to runtime bootstrap

`bootstrap_gateway_runtime(...)` and `create_gateway_app(...)` solve different problems:

- runtime bootstrap validates deployment-owned registry/provider/client-auth artifacts and builds secret-backed resolvers;
- application composition mounts already-constructed coordinators on one FastAPI object.

PC-6 intentionally does not join those responsibilities into a hidden global bootstrap.

A later process-activation increment may explicitly construct the remaining Policy Router, ranking, complexity, health, resilience, and observability dependencies, then pass the resulting coordinators to this factory.

## Deferred process activation

PC-6 still does not add:

- a module-level `app` singleton;
- import-time environment or secret reads;
- `uvicorn` or container entrypoint configuration;
- Policy Router credential configuration;
- ranking/evidence policy construction;
- production provider/model/client activation;
- cloud-specific secret-manager adapters;
- adaptive provider/model discovery.

Those concerns remain separate increments so startup configuration cannot silently acquire authorization semantics.
