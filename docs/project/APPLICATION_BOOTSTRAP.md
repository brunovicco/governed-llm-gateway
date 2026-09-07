# Governed Application Bootstrap

## Purpose

PC-10 closed the startup-order gap between the PC-8 governed process bootstrap and the PC-9 service-composition boundary by staging deployment-owned routing artifacts before any secret materialization.

PC-11 extends that boundary with an explicit runtime path for a previously approved evidence-driven ranking policy. The runtime does not discover benchmark outputs, select a newest artifact, or compile benchmark evidence during startup. A deployment must select one exact approved artifact by content-bound approval identity.

The resulting startup order is:

```text
deployment-owned explicit paths
        ↓
PC-8 process artifact loading/validation
        ↓
exactly one ranking source
  ├─ static Phase 5 ranking YAML
  └─ approved evidence-driven ranking artifact + expected artifact_id
        ↓
optional complexity-routing loading/validation
        ↓
routing compatibility validation
        ↓
NO SECRET READS ABOVE THIS LINE
        ↓
consumer credential materialization
        ↓
Policy Router credential materialization
        ↓
provider credential materialization
        ↓
PC-9 service composition
```

## Public boundary

`GovernedApplicationBootstrapPaths` owns:

- the existing `GovernedProcessBootstrapPaths`;
- exactly one explicit ranking source;
- an optional complexity-routing path.

The ranking source is mutually exclusive:

1. `ranking_policy_path` for the existing static Phase 5/schema `1.0` YAML contract; or
2. `approved_ranking_artifact_path` together with `expected_ranking_artifact_id` for a previously approved schema `1.1` `EvidenceDrivenRankingPolicy`.

Supplying both modes, neither mode, or only one member of the approved-artifact path/identity pair fails closed before secret resolution.

The complexity path defaults to `None`. A checked-in complexity configuration therefore does not activate complexity routing merely because the file exists.

`load_governed_application_artifacts(...)` returns `GovernedApplicationArtifacts`, a secret-free bundle containing:

- the validated PC-8 `GovernedProcessArtifacts`;
- the effective `RankingPolicy`;
- optional `ComplexityRoutingDocument`;
- optional `ApprovedRankingArtifact` when the pinned evidence-driven path is selected.

`materialize_governed_application_services(...)` accepts only that validated bundle, resolves the existing PC-8 server-side secret references, then delegates the service graph to `compose_governed_gateway_services(...)`.

`bootstrap_governed_application_services(...)` is the explicit staged convenience wrapper. It does not discover files, read environment variables by itself, open network connections, start a server, or create global state.

## Approved evidence-driven ranking artifact

PC-11 persists the existing `ApprovedRankingArtifact` contract as a strict JSON runtime artifact instead of introducing a second ranking or approval model.

The document contains:

- document `schema_version`;
- declared `artifact_id`;
- attributable approval metadata:
  - `approval_version`;
  - `approval_date`;
  - `approved_by`;
- the canonical schema `1.1` `EvidenceDrivenRankingPolicy`, including:
  - `policy_version`;
  - `score_snapshot_id`;
  - `source_date`;
  - workload weights and deployment scores;
  - `score_provenance_mode`;
  - `benchmark_snapshot_id`;
  - `promotion_evidence_id`;
  - optional `manual_override_id`.

The loader is closed-schema and rejects duplicate JSON keys. It reconstructs the existing immutable domain objects and recalculates `ApprovedRankingArtifact.artifact_id` from approval metadata plus the exact ranking-policy digest.

Two independent identity checks are required:

```text
recomputed artifact_id == artifact-declared artifact_id
recomputed artifact_id == deployment expected_artifact_id
```

The first detects tampering or stale identity inside the artifact. The second prevents a deployment from silently consuming a different valid approved artifact than the one explicitly pinned for that activation.

The runtime artifact loader does not import `benchmarks/`. Benchmark execution, scoring, promotion, and artifact publication remain offline concerns defined by Phase 11 and ADR-0009.

## Fail-closed routing compatibility

PC-10/PC-11 reuse the PC-9 `validate_governed_routing_inputs(...)` boundary during the no-secret stage.

The existing static ranking loader returns the Phase 5 `RankingPolicy` contract. If an operator explicitly supplies a complexity-routing artifact alongside such a policy, startup fails before secret resolution because benchmark-grounded complexity narrowing requires `EvidenceDrivenRankingPolicy`.

An explicitly pinned approved artifact that materializes an `EvidenceDrivenRankingPolicy` may be paired with an explicitly supplied complexity-routing document. The artifact approval and benchmark provenance make ranking inputs attributable; they do not create authorization authority.

There is no silent fallback from requested complexity mode to static ranking and no implicit activation from the checked-in `config/routing/complexity.json` file.

The permanent authority invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Approved ranking evidence remains operational selection input. It cannot authorize, widen, resurrect, enable, or bypass a PDP decision, registry eligibility, or any business-side-effect boundary.

## Credential boundary

Secret resolver ordering remains owned by PC-8:

```text
consumer → PDP → providers
```

That sequence is operational least privilege only. It does not confer authorization authority.

The stronger startup invariant is:

> No consumer, PDP, or provider secret is resolved until the complete deployment-owned process and routing artifact set supplied for this activation has passed structural, cross-artifact, identity, and routing-compatibility validation.

Tests prove zero secret reads for:

- invalid static ranking policy;
- invalid complexity-routing document;
- explicit complexity routing combined with a non-evidence-driven ranking policy;
- caller-pinned approved artifact identity mismatch;
- approved artifact content or approval metadata tampering with a stale declared identity.

Tests also prove that an explicitly pinned approved evidence-driven ranking policy can enable explicit complexity routing and reach PC-9 without runtime benchmark compilation or discovery.

## Deliberately deferred

PC-11 does not add:

- creation or promotion of real benchmark artifacts;
- automatic selection of newest evidence or approved ranking artifacts;
- ranking-policy self-modification;
- changes to ranking weights, scores, or complexity thresholds;
- a module-level FastAPI application singleton;
- `uvicorn` or another server runner;
- Docker or Docker Compose activation;
- `/readyz` or process-health semantics;
- environment-owned default artifact paths;
- direct environment-variable secret reads;
- new authentication protocols;
- cloud secret-manager adapters;
- OpenTelemetry process lifecycle wiring;
- dashboards, Grafana, Tempo, or Langfuse work;
- Phase 14 consumer integration.

Executable process activation remains a later audited increment after the approved ranking artifact and no-secret startup boundaries are certified.
