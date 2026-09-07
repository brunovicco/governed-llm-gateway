# Executable Gateway Process

## Purpose

PC-13 adds the first installed executable process boundary for the Governed LLM Gateway. It builds directly on PC-12 and does not reopen deployment artifact loading, ranking selection, authorization, or secret-resolution semantics.

The installed command is:

```text
governed-llm-gateway
```

The command parses explicit non-secret process/deployment arguments, constructs `GovernedDeploymentSettings`, activates the existing governed service graph, and only then hands the already-composed FastAPI application to Uvicorn.

There is no module-level FastAPI singleton and no import-time deployment activation.

## Process sequence

```text
CLI argv
    ↓
parse_server_args(...)
    ↓
GovernedServerSettings
    ├── GovernedDeploymentSettings
    ├── host
    └── port
    ↓
run_governed_server(...)
    ↓
PC-12 activate_governed_deployment(...)
    ↓
all artifact validation
    ↓
environment-backed credential resolution
    ↓
existing PC-9/PC-11 GovernedGatewayServices
    ↓
already-composed FastAPI app
    ↓
UvicornServerRunner
```

## Explicit deployment arguments

The process requires explicit arguments for:

- deployment root;
- model registry artifact;
- provider runtime artifact;
- Gateway client-auth artifact;
- Policy Router runtime artifact;
- exactly one ranking source;
- optional complexity-routing artifact;
- default maximum latency;
- default maximum cost.

Ranking selection preserves PC-11/PC-12 semantics:

```text
--ranking-policy-path <path>
```

or:

```text
--approved-ranking-artifact-path <path>
--expected-ranking-artifact-id sha256:<digest>
```

No configuration directory is scanned. No environment variable selects artifact paths. No newest approved ranking artifact is discovered.

## Credential boundary

The CLI deliberately has no arguments for raw Gateway client credentials, Policy Router credentials, or model-provider API keys.

Runtime artifacts contain only credential references. PC-12 validates all deployment-owned settings and artifacts first, then the existing environment-backed resolvers resolve those references server-side.

Passing an invented CLI flag such as `--provider-api-key` is rejected by argument parsing rather than becoming a new credential path.

## Network binding

The default binding is conservative:

```text
host = 127.0.0.1
port = 8000
```

An operator may explicitly provide another normalized host and a port in `[1, 65535]`.

PC-13 runs exactly one Uvicorn worker. This is deliberate because current runtime health and local operational sample recording are process-local. Multi-worker deployment semantics must not be enabled before shared/fleet completeness and lifecycle behavior are reviewed explicitly.

Uvicorn is an exact runtime dependency rather than an assumed external executable. The package dependency, workspace lock, and runtime dependency audit input are kept synchronized.

## Testability boundary

`ServerRunner` is a small injected port. Default CI can therefore prove that:

- PC-12 activation happens before server handoff;
- the resulting FastAPI application is passed unchanged to the runner;
- exact host/port settings are preserved;
- no socket needs to be opened during contract tests.

`UvicornServerRunner` is the production adapter and delegates to one Uvicorn worker.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

CLI arguments, network bindings, server state and Uvicorn are operational composition only. They cannot authorize, widen, restore, rank outside, or bypass a Policy Router decision.

## Deliberately deferred

PC-13 does not add:

- FastAPI lifespan/startup/shutdown orchestration;
- `/readyz` or liveness endpoints;
- OpenTelemetry exporter creation, flush or shutdown lifecycle;
- explicit graceful-drain policy beyond the ASGI server's existing behavior;
- multiple Uvicorn workers or another multi-process topology;
- Docker or Docker Compose;
- Collector, Tempo, Grafana or Langfuse activation;
- cloud secret managers;
- file watching or runtime configuration reload;
- configuration discovery;
- Phase 14 consumer integration.

Those concerns remain separate increments so lifecycle, health semantics, observability availability and container security can be reviewed independently from the executable process boundary.
