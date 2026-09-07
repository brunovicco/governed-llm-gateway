# Governed Application Bootstrap

## Purpose

PC-10 closes the startup-order gap between the PC-8 governed process bootstrap and the PC-9 service-composition boundary.

PC-8 already guarantees that model-registry, provider-runtime, Gateway client-auth, and Policy Router runtime artifacts are validated before any consumer, PDP, or provider secret is resolved. PC-9 intentionally accepts an already-materialized runtime plus already-loaded routing inputs.

A deployment composition root must not bridge those boundaries by resolving credentials first and discovering an invalid ranking or complexity artifact afterward.

PC-10 therefore adds one outer staged boundary:

```text
deployment-owned explicit paths
        ↓
PC-8 process artifact loading/validation
        ↓
ranking-policy loading/validation
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
- one explicit ranking-policy path;
- an optional complexity-routing path.

The complexity path defaults to `None`. A checked-in complexity configuration therefore does not activate complexity routing merely because the file exists.

`load_governed_application_artifacts(...)` returns `GovernedApplicationArtifacts`, a secret-free bundle containing:

- the validated PC-8 `GovernedProcessArtifacts`;
- the loaded `RankingPolicy`;
- optional `ComplexityRoutingDocument`.

`materialize_governed_application_services(...)` accepts only that validated bundle, resolves the existing PC-8 server-side secret references, then delegates the service graph to `compose_governed_gateway_services(...)`.

`bootstrap_governed_application_services(...)` is the explicit two-stage convenience wrapper. It does not read environment variables by itself, open network connections, start a server, or create global state.

## Fail-closed routing compatibility

PC-10 reuses the PC-9 `validate_governed_routing_inputs(...)` boundary during the no-secret stage.

The existing static ranking loader returns the Phase 5 `RankingPolicy` contract. If an operator explicitly supplies a complexity-routing artifact alongside such a policy, startup fails before secret resolution because benchmark-grounded complexity narrowing requires `EvidenceDrivenRankingPolicy`.

There is no silent fallback from requested complexity mode to static ranking and no implicit activation from the checked-in `config/routing/complexity.json` file.

The permanent authority invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Routing configuration remains operational input. It cannot authorize a provider, model group, model, deployment, fallback, retry, or business action.

## Credential boundary

Secret resolver ordering remains owned by PC-8:

```text
consumer → PDP → providers
```

That sequence is operational least privilege only. It does not confer authorization authority.

PC-10's stronger startup invariant is:

> No consumer, PDP, or provider secret is resolved until the complete deployment-owned process and routing artifact set supplied for this activation has passed structural, cross-artifact, and routing-compatibility validation.

Tests prove zero secret reads for:

- invalid ranking policy;
- invalid complexity-routing document;
- explicit complexity routing combined with a non-evidence-driven ranking policy.

## Deliberately deferred

PC-10 does not add:

- a module-level FastAPI application singleton;
- `uvicorn` or another server runner;
- Docker or Docker Compose activation;
- `/readyz` or process-health semantics;
- environment-owned default artifact paths;
- direct environment-variable secret reads;
- new authentication protocols;
- cloud secret-manager adapters;
- evidence-driven ranking artifact promotion/ownership;
- changes to ranking scores or complexity thresholds;
- OpenTelemetry process lifecycle wiring;
- dashboards, Grafana, Tempo, or Langfuse work;
- Phase 14 consumer integration.

Evidence-driven deployment artifact ownership must be designed explicitly before a file-based production composition root can enable complexity routing. Executable process activation remains a later audited increment after this no-secret startup boundary is certified.
