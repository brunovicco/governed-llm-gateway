# Tempo Queryability Proof

PC-26 is the first OR-6 increment. It closes the observability gap between positive Collector receipt and
future Grafana/dashboard work by proving that a metadata-only Gateway trace can traverse the checked-in
local pipeline and become queryable from Tempo.

Permanent authorization invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Tempo query success is descriptive operational evidence only. It is not an authorization, routing,
health, readiness or inference-availability input.

## Proven path

The credential-free integration exercises this exact path:

```text
integration span
    -> a2a-otel-kit
    -> OTLP/HTTP
    -> local OpenTelemetry Collector
    -> OTLP/gRPC
    -> local Tempo
    -> Tempo trace-by-ID API
    -> Tempo Search API / TraceQL
```

The test emits a single `llm.gateway.request` span with the integration-only service identity
`governed-llm-gateway-tempo-query-integration`. It sends that span to the existing Collector OTLP/HTTP
receiver at `127.0.0.1:4318/v1/traces`. It does not send spans directly to Tempo.

After exporter flush/shutdown, the test first polls Tempo `GET /api/v2/traces/<trace_id>` and requires
that the returned OTLP trace contain the expected `service.name` and span name. It then polls
`GET /api/search` with a TraceQL query that requires both the exact `resource.service.name` and span
`name`. The proof passes only when Tempo returns the same emitted trace ID with the expected root service
and root span.

Exporter flush alone is insufficient evidence. Collector receipt alone is also insufficient evidence for
PC-26. The new boundary requires a successful downstream Tempo trace retrieval plus TraceQL discovery.

## Tempo 3.0 configuration compatibility

The pinned local image is `grafana/tempo:3.0.3`. Real startup testing exposed that the earlier
`compactor` configuration belonged to the pre-3.0 architecture and is rejected by Tempo 3.0.

The checked-in base configuration now uses the Tempo 3.x compaction/retention contract:

```yaml
backend_worker:
  compaction:
    block_retention: 24h
```

This preserves local storage and the existing 24-hour local retention intent while matching the Tempo
3.0 backend scheduler/worker architecture. The base configuration still receives OTLP/gRPC internally
and still uses only local storage.

The Collector exporter is named explicitly as `otlp_grpc/tempo`, matching the pinned Collector's OTLP
gRPC exporter type and the internal `tempo:4317` endpoint. The `tempo-query` workflow starts the real
pinned Collector and Tempo containers, so configuration parser/startup incompatibilities can no longer
pass solely through static YAML/Compose validation.

Tempo 3.0 also defaults `query_frontend.query_end_cutoff` to `30s` and
`live_store.fail_on_high_lag` to `true`. Those defaults are appropriate for the reusable base stack, but
would deliberately exclude the brand-new trace used by this bounded integration proof. Therefore the
integration-only Tempo config sets:

```yaml
query_frontend:
  query_end_cutoff: 0s

live_store:
  fail_on_high_lag: false
```

Those settings are isolated to `tests/integration/tempo-query.yaml` and are not applied to the reusable
base Tempo configuration.

## Test-only Tempo HTTP exposure

`compose.observability.yml` remains unchanged: Tempo port `3200` is not host-published in the reusable
local observability stack.

`compose.tempo-query.yml` is an integration-only overlay:

```yaml
services:
  tempo:
    ports:
      - 127.0.0.1:3200:3200
```

The overlay is used only for deterministic local/CI query verification. It exposes Tempo HTTP on
loopback, not `0.0.0.0`, and does not add authentication material, SaaS endpoints or provider access.

## HTTP client boundary

The integration test uses only Python stdlib `urllib` for Tempo HTTP queries. Before `urlopen()` is
reached, the test requires the Tempo base endpoint to match the reviewed
`http://127.0.0.1:3200` value and independently validates scheme, host, port, user-info, path, query and
fragment constraints.

The narrow `S310`/`B310` suppression is attached only to the `urlopen()` line after that explicit
loopback validation. It is not a generic repository-wide suppression and no additional HTTP dependency
is introduced for the proof.

## Bounded readiness and failure semantics

Before emitting the integration span, the workflow requires:

- Tempo `GET /ready` to return success;
- the existing Collector OTLP/HTTP receiver to accept the bounded empty-protobuf startup probe;
- both `tempo` and `otel-collector` containers to remain running.

Both Tempo polling phases are bounded. Malformed/non-JSON Tempo responses, a missing trace object,
missing `resourceSpans`, a missing `traces` array, malformed trace entries, trace-ID mismatch, or failure
to observe the expected trace within the polling window fail the integration.

The workflow always executes Compose teardown with volumes, including on failure.

## Privacy and security boundary

The proof is metadata-only. It does not emit or query:

- prompts, messages or completions;
- tool arguments or results;
- documents;
- raw provider responses;
- request/response headers;
- raw exception text;
- API keys, provider credentials or Policy Router credentials.

No provider, PDP, Gateway client credential, Langfuse instance or external observability backend is
required.

## What PC-26 proves

PC-26 proves, for the pinned credential-free local stack, that:

1. `a2a-otel-kit` can export the known Gateway span through the configured Collector;
2. the Collector can forward that trace to the configured Tempo instance;
3. Tempo can return the exact emitted trace by trace ID;
4. Tempo can discover that same trace through bounded TraceQL search;
5. the expected service/span identity can be reconstructed from Tempo responses;
6. the pinned Collector and Tempo configurations are accepted by the real container processes used in
   the proof.

## What PC-26 does not prove

PC-26 does **not** establish:

- Grafana dashboard provisioning or correctness;
- Grafana Explore/deep-link behavior;
- Gateway Console trace links;
- production Tempo authentication, multi-tenancy or durability;
- fleet completeness;
- trace retention beyond the local demo configuration;
- telemetry freshness/SLO guarantees;
- inference readiness or provider reachability;
- authorization, candidate eligibility, ranking or fallback authority;
- one-command end-to-end product demo readiness.

Those remain separate bounded increments.

## CI contract

`.github/workflows/tempo-query.yml` is path-scoped and credential-free. It:

1. validates the combined base + test overlay Compose model;
2. starts only Tempo and the Collector;
3. waits for bounded local readiness;
4. runs only `tests/integration/test_tempo_query.py` with the two explicit loopback endpoints;
5. always tears down containers and volumes.

Static contracts in `tests/contract/test_tempo_query_foundation.py` protect the loopback-only overlay,
Collector-first emission path, stdlib HTTP boundary, Tempo 3.x integration settings and credential-free
teardown behavior. The existing observability-foundation contracts also lock the Tempo 3.x retention
shape and the Collector's internal OTLP/gRPC exporter contract.
