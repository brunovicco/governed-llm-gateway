# Governed Service Composition

## Purpose

PC-9 composes the Gateway's request-time services from an already-materialized PC-8 runtime bundle.

This layer is intentionally pure composition. It does not load files, resolve environment variables, read secrets, call providers, contact the Policy Router, mutate policy, or start an HTTP server.

The composition order is:

```text
GovernedProcessRuntimeBundle
        ↓
PolicyEnforcementService
        ↓
RouteExplainService
        ↓
optional ComplexityRouteExplainService
        ↓
shared InMemoryHealthTracker
        ↓
StreamingExecutionService
        ↓
operational + optional complexity coordinators
        ↓
create_gateway_app(...)
```

## Runtime prerequisite

`compose_governed_gateway_services(...)` requires a materialized `PolicyRouterHttpAdapter` from the PC-8 runtime bundle.

If the Policy Router adapter is absent, composition fails closed. The service layer never substitutes a local allowlist, static model group, ranking result, complexity level, provider availability signal, or checked-in default for a PDP decision.

This is why the intentionally inert repository defaults cannot accidentally become an active Gateway process: the default Policy Router runtime is disabled and materializes no adapter.

## Authority ordering

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The composed PEP calls the deterministic Policy Router first. Operational ranking only receives the resulting authorized candidate set.

Complexity routing is even narrower:

```text
authenticated client
        ↓
Policy Router authorization
        ↓
authorized registry candidates
        ↓
deterministic complexity assessment
        ↓
quality-threshold narrowing
        ↓
ranking
        ↓
streaming execution
```

Complexity never authorizes, widens, or resurrects a rejected candidate.

## Operational versus complexity mode

Operational composition accepts any validated `RankingPolicy`.

Complexity composition additionally requires:

- a validated `ComplexityRoutingDocument`;
- an explicit `EvidenceDrivenRankingPolicy` carrying benchmark/promotion provenance.

Supplying complexity configuration with a static Phase 5 ranking policy fails at composition time. The Gateway does not silently present static scores as benchmark-grounded evidence.

The `DeterministicComplexityEvaluator` is constructed from the versioned assessment policy in the complexity-routing artifact, and the same artifact supplies the complexity quality thresholds.

## Shared runtime state

One `InMemoryHealthTracker` instance is shared by:

- operational generation preflight;
- complexity-aware generation preflight;
- `StreamingExecutionService`.

This prevents preflight routing from consulting one health state while execution updates another process-local state.

The same `StaticProviderResolver` from PC-8 is reused by streaming execution. PC-9 never reconstructs provider adapters and therefore never re-reads provider credentials.

A caller may inject an already-created health tracker or bounded `RetryPolicy`. When omitted, per-process defaults are created without external I/O.

## Observability

An optional `a2a-otel-kit` `Observability` instance is threaded through the PEP, streaming execution, and FastAPI route surfaces.

Observability remains metadata-only and non-authoritative. Backend availability cannot change authorization, candidate eligibility, complexity assessment, ranking, or fallback eligibility.

## Output bundle

`GovernedGatewayServices` exposes the composed objects needed for verification and later process activation:

- FastAPI app;
- shared health tracker;
- policy enforcement service;
- operational route service;
- streaming execution service;
- operational route/generation coordinators;
- optional complexity route service and coordinators.

Exposing these objects keeps composition testable without module globals or hidden runtime state.

## No secret reads

PC-9 accepts only an already-materialized `GovernedProcessRuntimeBundle`. No secret resolver is part of the API.

The intended lifecycle is:

```text
PC-8: load all artifacts
PC-8: validate every cross-artifact boundary
PC-8: resolve server-side credentials
PC-8: build runtime adapters
        ↓
PC-9: compose request-time services
        ↓
future: explicit process/server activation
```

## Deferred activation

PC-9 still does not add:

- a module-level `app` singleton;
- `uvicorn.run(...)`;
- a Docker/CMD process entrypoint;
- real credentials or production activation;
- ranking-policy/evidence compilation from deployment artifacts;
- cloud secret-manager integration;
- OAuth/OIDC/JWT/mTLS;
- Phase 14 integration changes.

A later process-activation increment can choose deployment-owned paths, load routing artifacts, invoke PC-8 once, invoke PC-9 once, and expose the resulting FastAPI application to an ASGI server. That step must not bypass either composition boundary or introduce a second secret-loading path.
