# Local Observability Foundation

## Purpose

PC-15 adds the first reproducible local OpenTelemetry Collector, Tempo, and Grafana foundation for the Governed LLM Gateway.

It implements the topology already defined in `OBSERVABILITY.md` without changing Gateway authorization, routing, inference, readiness, or telemetry lifecycle semantics.

```text
Governed LLM Gateway
        │
        │ OTLP/HTTP
        ▼
OpenTelemetry Collector
        │
        │ OTLP/gRPC
        ▼
      Tempo
        │
        │ query API
        ▼
     Grafana
```

The stack is local development and operational-readiness infrastructure. It is not a production deployment blueprint.

## Pinned components

The stack uses exact released image tags verified on 2026-09-07:

| Component | Image |
| --- | --- |
| OpenTelemetry Collector Contrib | `otel/opentelemetry-collector-contrib:0.160.0` |
| Grafana Tempo | `grafana/tempo:3.0.3` |
| Grafana | `grafana/grafana:13.2.1` |

Floating tags such as `latest` are not allowed by the contract tests.

## Start the foundation

Validate the Compose model without starting containers:

```text
docker compose -f compose.observability.yml config --quiet
```

Start the local stack:

```text
docker compose -f compose.observability.yml up -d
```

Stop it:

```text
docker compose -f compose.observability.yml down
```

Persistent local trace and Grafana state use named Docker volumes. Removing those volumes is an explicit operator action and is not performed by the commands above.

## Host boundaries

Only two ports are published to the host:

```text
127.0.0.1:4318 -> Collector OTLP/HTTP
127.0.0.1:3000 -> Grafana UI
```

Tempo is not published to the host. It is reachable only on the Compose-internal `observability` network.

The network is declared `internal: true`, preventing the observability containers from becoming general outbound-network clients.

## Collector pipeline

The Collector accepts traces through OTLP/HTTP and forwards them only to Tempo:

```text
receivers:  [otlp]
processors: [batch]
exporters:  [otlp/tempo]
```

The internal exporter endpoint is:

```text
tempo:4317
```

There is no SaaS exporter, Langfuse SDK, direct Datadog integration, or credential-bearing header in the checked-in configuration.

The Gateway's permanent telemetry privacy boundary remains unchanged: prompts, completions, tool payloads, documents, raw provider responses, arbitrary headers, credentials, and unsanitized remote exceptions are not telemetry merely because an OTLP pipeline now exists locally.

## Tempo storage

Tempo runs as a local single-binary service and receives OTLP/gRPC only on the internal Compose network.

Trace storage is local:

```text
backend: local
traces: /var/tempo/traces
wal: /var/tempo/wal
```

The data path is backed by the `tempo-data` named volume. This is intentionally not representative of production object-storage or HA requirements.

## Grafana provisioning

Grafana is provisioned with exactly one default Tempo datasource:

```text
http://tempo:3200
```

The datasource deliberately uses the Compose service name rather than `localhost`; Grafana and Tempo communicate over the internal network.

The local UI uses anonymous Viewer access and disables the login form and sign-up. No administrator password is committed. This is acceptable only because the UI is bound to loopback and the stack is explicitly local-development infrastructure.

## Container hardening

Each service declares:

- `read_only: true` for the container root filesystem;
- `cap_drop: [ALL]`;
- `security_opt: [no-new-privileges:true]`.

Writable state is bounded to explicit named volumes or tmpfs mounts:

- Tempo: `/var/tempo` plus `/tmp`;
- Grafana: `/var/lib/grafana`, `/var/log/grafana`, and `/tmp`;
- Collector: no persistent writable path.

These settings reduce local container privilege but do not replace production runtime hardening, image provenance policy, network policy, TLS, authentication, or orchestration controls.

## CI validation

The default Python contract suite validates:

- exact image pins;
- loopback-only published ports;
- internal network configuration;
- least-privilege Compose settings;
- exact Collector trace pipeline;
- local-only Tempo storage;
- Grafana internal datasource wiring;
- absence of secret-like configuration keys and Langfuse wiring.

A dedicated credential-free GitHub Actions workflow additionally executes:

```text
docker compose -f compose.observability.yml config --quiet
```

It validates the Compose model without starting containers, downloading images, contacting a SaaS backend, or requiring credentials.

## What this increment does not prove

A valid Compose model does not prove that a trace emitted by the Gateway reached Tempo.

Likewise, exporter `flush()` success is not deterministic evidence that the expected trace was received by the Collector or persisted in Tempo.

Positive receipt remains a separate e2e boundary. That future check should emit a known metadata-only trace and verify its expected service/span identity through a deterministic Collector/Tempo receipt surface.

## Availability boundary

Collector, Tempo, and Grafana are descriptive infrastructure. Their failure must not:

- make `/readyz` fail;
- alter a valid provider response;
- widen or narrow the authorized candidate set;
- create a retry or fallback;
- authorize a model or deployment;
- change ranking.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Deliberately deferred

PC-15 does not add:

- Gateway-owned `Observability.configure()` or shutdown lifecycle wiring;
- positive Collector/Tempo trace-receipt e2e;
- dashboards or alerts;
- metrics or logs pipelines beyond the current trace foundation;
- Langfuse deployment or integration;
- production storage or HA;
- TLS, auth proxy, Kubernetes manifests, or cloud deployment;
- Docker packaging for the Gateway;
- Phase 14 consumer integration.
