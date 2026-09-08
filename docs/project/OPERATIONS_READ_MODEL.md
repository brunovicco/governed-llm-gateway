# Read-Only Operations Model

## Purpose

PC-18 / OR-3A establishes the first typed operations projection for the Governed LLM Gateway. It is deliberately an application-layer read model, not an HTTP API and not a control plane.

The projection consumes only already-validated Gateway-owned state:

```text
ModelRegistry
RankingPolicy
process-local health
optional reviewed OperationalEvidenceSnapshot
        │
        ▼
OperationsReadModelService
        │
        ▼
OperationsSnapshot
```

No provider, Policy Router, secret resolver, filesystem loader, telemetry exporter or remote backend participates in snapshot construction.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The operations model is descriptive only. Reading it cannot:

- authorize a model or deployment;
- widen an authorized set;
- resurrect a rejected candidate;
- change ranking or complexity narrowing;
- change retry/fallback behavior;
- execute a provider call;
- mutate Policy Router state;
- alter readiness.

OR-4 may later expose this model over HTTP, but that API must remain a read-only projection unless a separate governed operator-action design is reviewed.

## Registry projection

`OperationsRegistrySummary` preserves exact active registry provenance:

- schema version;
- catalog version;
- source date;
- deterministic registry digest;
- deployment count.

Each `OperationsDeploymentSummary` is derived from one immutable `ModelDeployment` and includes bounded registry metadata plus one process-local health snapshot. Deployment ordering is canonical by `deployment_id`.

The initial projection does not calculate spend, cost savings, fleet availability or provider SLA from registry metadata.

## Ranking projection

`OperationsRankingSummary` preserves exact active ranking provenance:

- schema version;
- policy version;
- source date;
- deterministic policy digest;
- score snapshot identity.

Benchmark/promotion provenance is exposed only when the effective policy is an `EvidenceDrivenRankingPolicy`. Static ranking therefore reports no benchmark snapshot, promotion evidence or manual override identity rather than inferring a relationship that does not exist.

Ranking evidence remains evidence, not authorization.

## Process-local health

The existing `InMemoryHealthTracker.snapshot()` and `snapshots()` methods belong to the execution/resilience path. Their reads may deliberately materialize missing state and advance an expired open circuit to half-open.

An operations surface must not change live resilience state merely because an operator opened a dashboard.

`InMemoryHealthInspectionAdapter` therefore evaluates the current health view on an isolated in-memory replica of the tracker. The replica may perform the normal effective circuit evaluation, while the live tracker remains unchanged.

The resulting `OperationsSnapshot.health_scope` is always:

```text
process_local
```

This is not fleet health and must not be labeled as such by a later API or UI.

A native tracker inspection API is intentionally deferred. If future tracker state becomes unsuitable for safe replication, the adapter can be replaced behind `DeploymentHealthInspectionPort` without changing the operations model contract.

## Operational evidence absence

Operational evidence is optional input to the initial read model.

Absence is represented explicitly as:

```text
state = not_supplied
```

It is not converted into:

- zero requests;
- zero provider errors;
- zero fallbacks;
- zero latency;
- healthy fleet status.

Those values would be fabricated evidence.

When a verified `OperationalEvidenceSnapshot` is supplied, the projection preserves only its reviewed provenance:

- content-derived evidence ID;
- snapshot version;
- collector ID/version;
- window start/end;
- capture timestamp;
- record count.

PC-18 does not relabel that evidence as fleet-complete and does not re-run materialization inside the read path.

## Deliberately deferred

PC-18 does not add:

- `/v1/ops/*` HTTP routes;
- recent routing-history persistence;
- shared/fleet health aggregation;
- fleet completeness claims;
- provider or Policy Router probes;
- Tempo query/persistence verification;
- Grafana dashboards or deep links;
- React/TypeScript Gateway Console;
- operator mutation endpoints;
- operational-surface authentication policy;
- Phase 14 consumer integrations.

These remain later OR increments so transport, authentication, fleet semantics and operator authority can be reviewed independently from the typed read model.
