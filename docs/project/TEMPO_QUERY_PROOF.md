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
    -> Tempo HTTP Search API / TraceQL
```

The test emits a single `llm.gateway.request` span with the integration-only service identity
`governed-llm-gateway-tempo-query-integration`. It sends that span to the existing Collector OTLP/HTTP
receiver at `127.0.0.1:4318/v1/traces`. It does not send spans directly to Tempo.

After exporter flush/shutdown, the test polls Tempo `GET /api/search` with a TraceQL query that requires
both the exact `resource.service.name` and span `name`. The proof passes only when Tempo returns a trace
whose root service and root span match those expected values and whose trace ID is non-empty.

Exporter flush alone is insufficient evidence. Collector receipt alone is also insufficient evidence for
PC-26. The new boundary requires a successful query from the downstream Tempo store/query surface.

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

## Bounded readiness and failure semantics

Before emitting the integration span, the workflow requires:

- Tempo `GET /ready` to return success;
- the existing Collector OTLP/HTTP receiver to accept the bounded empty-protobuf startup probe;
- both `tempo` and `otel-collector` containers to remain running.

The search poll is bounded. Malformed/non-JSON Tempo responses, a missing `traces` array, malformed trace
entries or failure to observe the expected trace within the polling window fail the integration.

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
3. Tempo can persist/index the trace sufficiently for bounded TraceQL search;
4. the expected service/span identity can be reconstructed from the Tempo search response.

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
Collector-first emission path and credential-free teardown behavior.
