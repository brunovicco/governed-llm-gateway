# Executable Gateway Process

## Purpose

PC-13 adds the first installed executable process boundary for the Governed LLM Gateway. Later
process-readiness increments add bounded health and optional observability ownership without reopening
deployment artifact loading, ranking selection, authorization, or secret-resolution semantics.

The installed command is:

```text
governed-llm-gateway
```

The command parses explicit non-secret process/deployment arguments, constructs
`GovernedServerSettings`, optionally configures process-owned observability, activates the existing
governed service graph, and only then hands the already-composed FastAPI application to Uvicorn.

There is no module-level FastAPI singleton and no import-time deployment activation or observability
configuration.

## Process sequence

```text
CLI argv
    ↓
parse_server_args(...)
    ↓
GovernedServerSettings
    ├── GovernedDeploymentSettings
    ├── host
    ├── port
    └── optional explicit ObservabilitySettings
    ↓
run_governed_server(...)
    ├── best-effort Observability.configure(...)
    │       └── failure -> observability=None
    ↓
PC-12 activate_governed_deployment(..., observability=...)
    ↓
all artifact validation
    ↓
environment-backed credential resolution
    ↓
existing governed service graph
    ↓
attach bootstrap-derived /livez and /readyz
    ↓
UvicornServerRunner
    ↓
finally: best-effort Observability.shutdown(...)
```

Observability does not move into the authorization path. The existing deployment/application
composition already accepts an injected `Observability` facade; the executable process only owns when
that optional facade is created and released.

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

No configuration directory is scanned. No environment variable selects artifact paths. No newest
approved ranking artifact is discovered.

## Optional process observability

Observability remains disabled by default. With no observability arguments, `server.py` does not call
`Observability.configure()` and the existing service composition uses `NullGatewayTelemetry`.

OTLP/HTTP tracing is enabled explicitly with:

```text
--otel-endpoint http://127.0.0.1:4318/v1/traces
--otel-environment development
```

An optional positive timeout can be supplied with:

```text
--otel-timeout-seconds 10
```

Endpoint and environment are an atomic opt-in pair. Supplying only one, or supplying a timeout without
that pair, is rejected before deployment activation. Endpoint/environment values must be normalized,
and the `a2a-otel-kit` settings validator still enforces the HTTP(S) endpoint and positive-timeout
contract.

The executable process owns these fixed observability values:

```text
service.name    = governed-llm-gateway
service.version = 1.0.0
log.level       = INFO
log.format      = json
```

Every `ObservabilitySettings` field is supplied explicitly by the process. Ambient `A2A_OTEL_*`
environment values therefore cannot override the CLI-owned process contract.

There is deliberately no CLI argument for OTLP headers, Authorization values, API keys, Langfuse,
content capture, or another SaaS-specific exporter. OTLP authentication remains deferred until it has
a separately reviewed credential boundary.

### Failure semantics

Two failure classes are intentionally different:

1. **structurally invalid process configuration** fails before deployment activation;
2. **operational observability configuration/shutdown failure** degrades telemetry only.

`run_governed_server()` catches operational `Observability.configure()` failure, emits only a static
warning without raw exception text, and activates the Gateway with `observability=None`. It does not
probe the configured endpoint or require a Collector to be reachable before serving.

When configuration succeeds, the same instance is injected through `activate_governed_deployment()`
and remains owned by the server process for the duration of the runner. A `finally` boundary performs
best-effort shutdown after normal runner return or after activation/runner failure. Shutdown failure is
suppressed with a static warning so it cannot mask the original process outcome.

The `a2a-otel-kit` shutdown contract performs bounded flush/release. Exporter flush success or failure
is observability evidence only and never changes a provider result.

## Credential boundary

The CLI deliberately has no arguments for raw Gateway client credentials, Policy Router credentials,
model-provider API keys, or OTLP credentials.

Runtime artifacts contain only credential references. PC-12 validates all deployment-owned settings
and artifacts first, then the existing environment-backed resolvers resolve those references
server-side.

Passing an invented CLI flag such as `--provider-api-key`, `--otel-api-key`, or `--otel-headers` is
rejected by argument parsing rather than becoming a new credential path.

## Network binding

The default Gateway binding is conservative:

```text
host = 127.0.0.1
port = 8000
```

An operator may explicitly provide another normalized host and a port in `[1, 65535]`.

The optional OTLP endpoint is an exporter destination, not a server binding and not a readiness target.
The process does not probe Collector, Tempo, Grafana, or another telemetry backend.

The Gateway runs exactly one Uvicorn worker. This is deliberate because current runtime health and
local operational sample recording are process-local. Multi-worker deployment semantics must not be
enabled before shared/fleet completeness and lifecycle behavior are reviewed explicitly.

Uvicorn is an exact runtime dependency rather than an assumed external executable. The package
dependency, workspace lock, and runtime dependency audit input are kept synchronized.

## Health boundary

`/livez` and `/readyz` remain bootstrap-derived process surfaces. Observability enablement, exporter
state, Collector reachability, flush success and shutdown state do not participate in either endpoint.

This separation is deliberate: telemetry availability cannot become inference availability.

## Testability boundary

`ServerRunner` is a small injected port. Default CI can therefore prove that:

- deployment activation happens before server handoff;
- the resulting FastAPI application is passed unchanged to the runner;
- exact host/port settings are preserved;
- optional observability is injected through the existing composition path;
- configuration failure degrades to null telemetry;
- owned observability shuts down on normal return and exceptional paths;
- shutdown failure cannot mask a runner/activation error;
- no socket or telemetry backend needs to be opened during contract tests.

`UvicornServerRunner` is the production adapter and delegates to one Uvicorn worker.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

CLI arguments, observability configuration, network bindings, server state and Uvicorn are operational
composition only. They cannot authorize, widen, restore, rank outside, or bypass a Policy Router
decision.

## Deliberately deferred

The executable process still does not add:

- Collector, Tempo, Grafana or Langfuse availability to readiness;
- direct Tempo persistence/query verification;
- Grafana dashboards or trace deep links;
- OTLP authentication/TLS client credential ownership;
- explicit graceful-drain policy beyond the ASGI server's existing behavior;
- multiple Uvicorn workers or another multi-process topology;
- Dockerizing the Gateway process;
- cloud secret managers;
- file watching or runtime configuration reload;
- configuration discovery;
- Phase 14 consumer integration.

Those concerns remain separate increments so lifecycle, health semantics, observability availability
and container security can be reviewed independently.
