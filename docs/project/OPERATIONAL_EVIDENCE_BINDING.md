# Deployment-Owned Operational Evidence Binding

## Purpose

PC-23 binds an optional already-reviewed `OperationalEvidenceSnapshot` into the active read-only Operations surface without granting operational evidence any inference, routing, resilience, or authorization authority.

The core evidence contract and strict JSON loader already existed before this increment. PC-23 does not introduce a second schema or an automatic evidence collector. It closes the deployment-activation gap between that existing artifact and `GET /v1/ops/overview`.

## Explicit deployment selection

The executable process accepts one optional non-secret argument:

```text
--operational-evidence-path <path>
```

The path is handled like the other deployment-owned artifacts:

- relative paths resolve against the explicit `deployment_root`;
- relative paths cannot escape `deployment_root`;
- absolute paths remain explicit and are not discovered;
- no directory scan, glob, `latest` lookup, timestamp selection, or default evidence artifact exists;
- raw evidence JSON is not accepted through the CLI;
- operational evidence introduces no secret reference.

When the path is omitted, the existing explicit state remains:

```json
{"operational_evidence":{"state":"not_supplied"}}
```

## Secret-free startup order

Operational evidence is loaded during `load_governed_application_artifacts(...)`, before environment-backed client, Policy Router, or provider credentials are materialized.

The startup order is therefore:

```text
explicit deployment paths
        ↓
process artifacts + ranking + optional complexity
        ↓
optional OperationalEvidenceSnapshot load
        ↓
content/schema validation
        ↓
active-registry deployment cross-validation
        ↓
NO SECRET READS COMPLETED
        ↓
client / Policy Router / provider secret materialization
        ↓
service composition
```

Malformed, tampered, or registry-incompatible operational evidence fails before any environment-backed secret lookup.

## Existing evidence invariants

PC-23 reuses the existing `OperationalEvidenceSnapshot` domain contract and `load_operational_evidence(...)` adapter. The artifact already enforces, among other invariants:

- closed schema version `1.0`;
- normalized collector/snapshot identifiers;
- UTC-aware timestamps;
- `window_start < window_end`;
- `captured_at >= window_end`;
- non-empty canonical record ordering;
- unique `(runtime_workload, deployment_id)` records;
- internally consistent request/attempt/error/fallback counters;
- `p95 >= p50`;
- a verified `sha256:` content-derived `evidence_id`.

PC-23 adds one deployment-specific compatibility gate: every evidence `deployment_id` must exist in the already-loaded active `ModelRegistry`.

Evidence is allowed to cover only a subset of active deployments. Missing records never mean zero traffic, zero errors, or healthy state.

## Immutable process binding

`GovernedApplicationArtifacts` carries the exact validated optional snapshot into service composition.

`DeploymentOperationsSnapshotReader` then binds:

```text
OperationsReadModelService
        +
OperationalEvidenceSnapshot | None
```

for the lifetime of the process.

The HTTP request path does not reopen the artifact, scan storage, refresh evidence, read secrets, call the Policy Router, or contact a provider. A successful authenticated overview read only asks the already-composed reader for a snapshot.

When evidence is bound, the bounded PC-22 HTTP response changes only the availability state:

```json
{"operational_evidence":{"state":"available"}}
```

The individual evidence records, workload IDs, deployment IDs, counters, latency values, collector identity, timestamps, and `evidence_id` remain outside the PC-23 HTTP response.

## Authority invariant

The permanent inference invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operational evidence is descriptive metadata only. Loading, validating, binding, or displaying its availability cannot:

- authorize a model or deployment;
- widen or restore PDP output;
- affect capability eligibility;
- change complexity assessment or narrowing;
- alter deterministic ranking;
- mutate process-local health/circuit state;
- affect retry or fallback;
- execute a provider;
- change readiness;
- acquire mutation authority.

No code in PC-23 feeds operational evidence into the routing or inference decision path.

## Deferred

PC-23 intentionally does not add:

- `GET /v1/ops/evidence/operational` or evidence-detail serialization;
- evidence freshness/maximum-age policy;
- fleet completeness or cross-process aggregation;
- automatic file watching, refresh, newest-artifact discovery, or polling;
- automatic ranking consumption or promotion from operational evidence;
- routing-history persistence;
- operator mutation APIs;
- external IAM;
- React Gateway Console;
- Phase 14 consumer integrations.

Those capabilities require independent contracts because freshness, completeness, persistence, external identity, and mutation authority have materially different security and operational semantics.
