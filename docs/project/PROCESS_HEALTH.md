# Process Health

## Purpose

PC-14 adds bounded process-only liveness and readiness surfaces to the executable Gateway process introduced by PC-13.

The health contract deliberately does not reuse deployment/provider circuit state and does not probe external dependencies. Process health answers only whether this already-bootstrapped ASGI application is serving and whether the configuration/bootstrap boundary completed before it was exposed to the server runner.

## Endpoints

```text
GET /livez
GET /readyz
```

Successful responses are intentionally minimal:

```json
{"status":"live"}
```

and:

```json
{"status":"ready"}
```

No model, provider, policy, registry, ranking, credential, telemetry, trace, build, hostname or environment metadata is returned.

## Liveness semantics

`/livez` means only:

> This process is currently serving its already-composed ASGI application and can answer the liveness request.

It does not prove that the Policy Router, a model provider, an observability backend or any other remote dependency is reachable.

## Readiness semantics

PC-13 does not hand the application to the ASGI runner until PC-12 has successfully:

1. validated deployment settings;
2. resolved explicit deployment-owned artifact paths;
3. loaded and cross-validated process artifacts;
4. validated static or approved ranking selection;
5. validated optional complexity compatibility;
6. resolved the configured server-side credential references;
7. materialized the existing governed service graph.

PC-14 attaches `/livez` and `/readyz` only after that activation returns successfully and before server handoff.

`/readyz` therefore means only:

> This ASGI application passed the complete pre-server deployment/bootstrap boundary for this process.

If bootstrap fails, the runner is never invoked and no ready application is exposed.

## What readiness does not mean

Readiness does not dynamically inspect:

- `InMemoryHealthTracker` deployment circuit state;
- current Policy Router reachability;
- current provider reachability;
- model availability outside the already validated registry/configuration contract;
- OpenTelemetry exporter health;
- Collector, Tempo, Grafana or Langfuse availability;
- fleet or multi-worker completeness.

Provider/deployment health belongs to request-time resilience and candidate narrowing. It must not be confused with whether the Gateway process itself completed bootstrap.

Observability is descriptive. Exporter failure must not make an otherwise valid inference process unavailable.

## Composition safety

`attach_process_health_routes(...)` rejects an existing `/livez` or `/readyz` path before adding either route. This prevents partial or duplicate attachment and keeps process composition deterministic.

The endpoints are intentionally unauthenticated infrastructure surfaces and expose only fixed bounded status values. They have no routing, ranking, authorization or business-action capability.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Process health is operational evidence only. It cannot authorize a provider, model group, model, deployment, fallback, retry, tool, business action or policy expansion.

## Deliberately deferred

PC-14 does not add:

- remote dependency probes;
- provider-health aggregation into readiness;
- FastAPI lifespan-managed readiness transitions;
- graceful-drain/readiness transition semantics;
- OpenTelemetry initialization, flush or shutdown lifecycle;
- readiness failure caused by telemetry export failure;
- multi-worker/fleet readiness aggregation;
- Docker or Kubernetes healthcheck configuration;
- Collector, Tempo, Grafana or Langfuse activation;
- Phase 14 consumer integration.

Those remain separate increments because process readiness, telemetry lifecycle and distributed deployment semantics have different availability and governance boundaries.
