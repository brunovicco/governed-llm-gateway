# Governed Service Composition

## Purpose

PC-9 composes the Gateway's request-time services from an already-materialized PC-8 runtime bundle. PC-19 extends that same composition root with the typed read-only operations model introduced by PC-18.

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
        ├───────────────┐
        ↓               ↓
StreamingExecutionService    InMemoryHealthInspectionAdapter
        ↓               ↓
operational + optional       OperationsReadModelService
complexity coordinators
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

The PC-19 operations read model is descriptive only. It consumes already-active registry/ranking state plus a non-mutating view of process-local health; it has no path back into authorization, routing, provider resolution or retry/fallback decisions.

## Operational versus complexity mode

Operational composition accepts any validated `RankingPolicy`.

Complexity composition additionally requires:

- a validated `ComplexityRoutingDocument`;
- an explicit `EvidenceDrivenRankingPolicy` carrying benchmark/promotion provenance.

Supplying complexity configuration with a static Phase 5 ranking policy fails at composition time. The Gateway does not silently present static scores as benchmark-grounded evidence.

The `DeterministicComplexityEvaluator` is constructed from the versioned assessment policy in the complexity-routing artifact, and the same artifact supplies the complexity quality thresholds.

The operations read model receives the exact effective ranking policy used by the composed service graph. Static ranking therefore stays static in the descriptive projection; evidence-driven ranking preserves its exact benchmark/promotion provenance rather than reloading or inferring evidence.

## Shared runtime state

One `InMemoryHealthTracker` instance is shared by:

- operational generation preflight;
- complexity-aware generation preflight;
- `StreamingExecutionService`;
- the PC-19 operations model through `InMemoryHealthInspectionAdapter`.

This prevents preflight routing from consulting one health state while execution updates another process-local state. The operations model observes the same live tracker but evaluates health on an isolated replica, so opening an operations view cannot materialize unseen state or advance the live circuit breaker.

The same `StaticProviderResolver` from PC-8 is reused by streaming execution. PC-9/PC-19 never reconstruct provider adapters and therefore never re-read provider credentials.

A caller may inject an already-created health tracker or bounded `RetryPolicy`. When omitted, per-process defaults are created without external I/O.

## Observability

An optional `a2a-otel-kit` `Observability` instance is threaded through the PEP, streaming execution, and FastAPI route surfaces.

Observability remains metadata-only and non-authoritative. Backend availability cannot change authorization, candidate eligibility, complexity assessment, ranking, or fallback eligibility.

The operations read model does not depend on observability or an exporter and therefore cannot turn telemetry availability into readiness or execution authority.

## Output bundle

`GovernedGatewayServices` exposes the composed objects needed for verification and process activation:

- FastAPI app;
- shared health tracker;
- typed `OperationsReadModelService`;
- policy enforcement service;
- operational route service;
- streaming execution service;
- operational route/generation coordinators;
- optional complexity route service and coordinators.

Exposing these objects keeps composition testable without module globals or hidden runtime state. PC-19 adds no `/v1/ops/*` route; transport and authentication for operations surfaces remain separately reviewable.

## No secret reads

PC-9/PC-19 accept only an already-materialized `GovernedProcessRuntimeBundle`. No secret resolver is part of the API.

The intended lifecycle is:

```text
PC-8: load all artifacts
PC-8: validate every cross-artifact boundary
PC-8: resolve server-side credentials
PC-8: build runtime adapters
        ↓
PC-9: compose request-time services
        ↓
PC-19: bind the read-only operations projection to the active service graph
        ↓
process/server activation
```

## Deferred operations surface

PC-19 still does not add:

- `/v1/ops/*` HTTP routes;
- operational-surface authentication or authorization;
- operator mutation endpoints;
- operational-evidence source binding;
- shared/fleet health aggregation;
- fleet completeness claims;
- Tempo query verification;
- Grafana dashboards/deep links;
- React/TypeScript Gateway Console;
- Phase 14 integration changes.

Those remain separate increments so descriptive operations state, transport security, fleet semantics, and operator authority are not collapsed into one change.
