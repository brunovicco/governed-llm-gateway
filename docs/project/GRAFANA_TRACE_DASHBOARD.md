# Grafana Tempo Dashboard Proof

PC-27 adds the first bounded Grafana visualization proof for the Governed LLM Gateway operational-evidence track.

The capability is deliberately narrow: a file-provisioned, read-only Grafana dashboard queries the already-provisioned local Tempo datasource for real traces containing the stable `llm.gateway.request` span. Grafana remains an evidence surface only. It does not participate in authorization, ranking, health, retry, fallback, provider execution, startup readiness, or inference availability.

Permanent invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Implemented capability

The checked-in local stack provides:

- the existing provisioned Tempo datasource with UID `tempo` and `editable: false`;
- a file-backed dashboard provider with `allowUiUpdates: false`;
- one dashboard with UID `governed-llm-gateway-traces` and title `Governed LLM Gateway — Traces`;
- one read-only table panel, `Recent gateway request traces`, with exactly one TraceQL query:

```traceql
{ span:name = "llm.gateway.request" }
```

The dashboard is intentionally small. PC-27 does not introduce a general dashboard framework, synthetic metrics, cost estimates, mutation controls, provider calls, Policy Router calls, or a second operational source of truth.

PC-52 (see `docs/project/GATEWAY_CONSOLE.md`'s "Per-request trace navigation" section) adds one more panel
to this same dashboard: `Selected request trace`, a Tempo `traces` panel querying `${traceId}` from a
`traceId` textbox dashboard variable, reached from the Console's own per-request trace link. The dashboard
still has no synthetic data, mutation controls, or second source of truth — the added panel only ever
shows a real Tempo trace for a real trace ID, or nothing.

## Local topology and network boundary

The reusable local path remains:

```text
Gateway / a2a-otel-kit
        │ OTLP/HTTP → 127.0.0.1:4318
        ▼
OpenTelemetry Collector
        │
        ▼
      Tempo
        │ internal Compose network
        ▼
     Grafana
        │
        └── 127.0.0.1:3000
```

The `observability` Compose network remains `internal: true`. Tempo is not host-published by the reusable base Compose file. Grafana and the OpenTelemetry Collector are each attached to both the internal `observability` network and a separate `grafana-host-access` bridge, so their explicitly loopback-bound `127.0.0.1:3000` and `127.0.0.1:4318` ports remain reachable from the local host while Collector-to-Tempo traffic stays on the internal evidence network.

The extra bridge is not an authorization or provider network and does not publish Tempo. The contract test protects this topology so a future change cannot silently replace the local-only boundary with `0.0.0.0` exposure or remove the internal observability network.

**PC-52 fixed a real bug in this exact topology.** `otel-collector` declared the `127.0.0.1:4318:4318`
host port mapping from the start, but was attached only to the `internal: true` `observability` network —
an internal network cannot have any of its containers' ports published to the host, so Docker silently
dropped the mapping and `http://127.0.0.1:4318` was unreachable from any host process. This had never
been caught because the credential-free `collector-receipt` CI proof uses an entirely separate,
non-internal-networked Compose file (`compose.collector-receipt.yml`), and no workflow previously sent a
real span through this specific stack from a host process. Building the Console's per-request trace
navigation (PC-52) was the first thing that actually exercised this path, surfacing the bug immediately.
The fix adds `otel-collector` to `grafana-host-access` alongside `grafana`; Tempo remains on the internal
network only, unpublished, exactly as before.

## Run locally

To start only the components required to inspect the provisioned dashboard:

```bash
docker compose -f compose.observability.yml up -d tempo grafana
```

Open:

```text
http://127.0.0.1:3000
```

The checked-in Grafana configuration enables anonymous `Viewer` access and disables the login form for this local demonstration only. It must not be presented as a production authentication configuration.

To run the complete local observability path, including the OpenTelemetry Collector:

```bash
docker compose -f compose.observability.yml up -d
```

The dashboard displays real Tempo query results. An empty table means no matching trace is currently available in the selected Grafana time window; the UI does not fabricate sample traces or synthetic metrics.

Stop the stack with:

```bash
docker compose -f compose.observability.yml down --volumes --remove-orphans
```

## Automated proof

The credential-free `grafana-dashboard` workflow:

1. validates the checked-in Compose model;
2. starts the real pinned Tempo and Grafana containers;
3. waits for the loopback Grafana health endpoint within a bounded window while requiring both services to remain running;
4. retrieves dashboard UID `governed-llm-gateway-traces` from the Grafana API;
5. requires Grafana to report `meta.provisioned == true`;
6. requires the expected title and exactly two reviewed panels;
7. requires both panels to use datasource UID `tempo` and exactly one TraceQL target each;
8. requires the `Recent gateway request traces` panel to keep its stable-span query and result limit,
   and the `Selected request trace` panel to query the `${traceId}` dashboard variable;
9. requires exactly one `traceId` textbox template variable;
10. emits container logs on failure and always tears the stack down.

The workflow requires no provider credential, Policy Router credential, Grafana credential, Tempo credential, SaaS account, or application secret. It does not create the dashboard through the Grafana API; provisioning must come from the checked-in files.

The static contract test additionally rejects broad Grafana host exposure, Tempo host exposure in the reusable base Compose file, fake operational backends, mutation-oriented dashboard terms, credentials in the workflow, and drift from the reviewed network boundary.

## Status semantics

PC-27 uses three distinct states:

- **implemented** — the reviewed provisioning, dashboard, Compose topology, contract test, and CI workflow exist on the branch;
- **proven in CI** — the branch workflow has successfully booted the real containers and verified the provisioned dashboard contract;
- **certified** — only after the reviewed branch is squash-merged with its validated immutable head SHA and all required post-merge `main` gates are green.

Branch success must not be described as post-merge certification.

## Non-claims

PC-27 does **not** prove or provide:

- production Grafana authentication, authorization, TLS, HA, backup, durability, or retention design;
- fleet-complete telemetry or a telemetry freshness SLA;
- production observability readiness;
- provider or Policy Router reachability;
- gateway inference readiness;
- authorization, routing, ranking, health, retry, fallback, or circuit-breaker authority from Grafana or Tempo;
- prompt, completion, tool argument/result, document, credential, or customer-payload capture;
- Langfuse or another SaaS observability dependency.

PC-52 is the later reviewed increment this document anticipated for a Gateway Console deep link and
trace-correlation contract — see `docs/project/GATEWAY_CONSOLE.md`'s "Per-request trace navigation"
section and `docs/project/CURRENT_STATE.md` for the real trace it proved.

Telemetry remains metadata-only by default, and evidence remains descriptive rather than authoritative.
