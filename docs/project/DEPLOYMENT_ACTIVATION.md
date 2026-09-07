# Deployment Activation

## Purpose

PC-12 adds the deployment-owned activation boundary above the staged PC-11 application bootstrap.

The repository already had strict runtime artifacts, secret-free validation, server-side secret resolvers, governed service composition, and a pure FastAPI application factory. What remained intentionally absent was one typed place where a deployment declares the exact artifact paths, ranking source, optional complexity configuration, and Policy Router projection ceilings that should be used for one activation.

PC-12 fills only that gap. It does not start a server.

## Activation sequence

```text
GovernedDeploymentSettings
        ↓
validate deployment root, ranking-source coherence and projection defaults
        ↓
resolve explicit artifact paths
(no scanning, globbing or newest-artifact discovery)
        ↓
PC-11 load_governed_application_artifacts(...)
        ↓
validate process + ranking + optional complexity artifacts
        ↓
NO SECRET READS ABOVE THIS LINE
        ↓
EnvironmentGatewayClientSecretResolver
EnvironmentPolicyRouterSecretResolver
EnvironmentProviderSecretResolver
        ↓
PC-11 materialize_governed_application_services(...)
        ↓
existing PC-9 GovernedGatewayServices + FastAPI app
```

The environment mapping itself may be supplied explicitly for tests or defaults lazily to the process environment through the existing resolver contracts. Artifact paths and non-secret routing settings are never inferred from environment-variable naming conventions by this boundary.

## Deployment settings

`GovernedDeploymentSettings` owns:

- one absolute `deployment_root`;
- model-registry path;
- provider-runtime path;
- Gateway client-auth path;
- Policy Router runtime path;
- exactly one ranking source:
  - static ranking-policy path; or
  - approved evidence-driven ranking artifact path plus exact expected artifact identity;
- optional complexity-routing path;
- positive default maximum latency;
- positive default maximum cost.

Relative artifact paths are resolved against `deployment_root`. Their resolved path must remain inside that root. This prevents a deployment-relative declaration such as `../other/registry.yaml` from silently escaping the reviewed deployment tree.

Absolute artifact paths are accepted as explicit operator-owned declarations. They are not rewritten under `deployment_root`.

Path resolution does not scan a directory, discover a newest artifact, select a benchmark result, or compile benchmark evidence.

## Ranking selection

Ranking selection stays identical to PC-11 semantics.

A deployment must choose exactly one mode:

```text
static ranking policy
```

or:

```text
approved EvidenceDrivenRankingPolicy artifact
+ exact expected artifact_id
```

Supplying both modes, neither mode, or an incomplete approved-artifact pair fails before artifact loading and therefore before credential materialization.

PC-12 does not change ranking weights, deployment scores, complexity thresholds, benchmark promotion, rollback, or manual-override semantics.

## Credential boundary

`activate_governed_deployment(...)` deliberately performs the secret-free stage first:

1. materialize bootstrap paths and `PolicyProjectionDefaults` from settings;
2. load and validate every application artifact through PC-11;
3. only after successful validation, construct the existing environment-backed secret resolvers;
4. materialize the governed application services.

Invalid deployment settings or invalid process/ranking/complexity artifacts therefore fail before environment-backed credential lookup.

Credential references remain in deployment artifacts; raw credentials remain server-side environment values and do not participate in deterministic configuration provenance.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Deployment settings are composition input only. They cannot authorize a provider, model group, model, deployment, fallback, retry, tool, business action, or policy expansion.

The Policy Router remains the request-time authorization source. Registry eligibility, ranking, complexity, health, retry, fallback, benchmark evidence, operational evidence, configuration paths, and credential availability cannot widen the accepted Policy Router decision.

## Deliberately deferred

PC-12 does not add:

- module-level FastAPI application singleton;
- `uvicorn`, gunicorn or another executable server runner;
- host, port or worker settings;
- FastAPI lifespan/startup/shutdown hooks;
- `/readyz` or liveness semantics;
- OpenTelemetry exporter lifecycle wiring;
- Docker or Docker Compose topology;
- Collector, Tempo, Grafana or Langfuse activation;
- cloud secret-manager adapters;
- runtime file watchers or reload;
- configuration directory discovery;
- automatic newest approved-artifact selection;
- Phase 14 consumer integration.

Those concerns remain independent increments so process lifecycle, health semantics, observability availability and container security can each be reviewed without reopening the authorization/configuration boundary.
