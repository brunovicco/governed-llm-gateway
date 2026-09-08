# Positive Collector Receipt Verification

PC-16 adds a credential-free integration boundary that proves the OpenTelemetry Collector received
known Gateway observability metadata. It intentionally does not exercise Policy Router authorization,
model providers, Tempo queries, Grafana, or the executable Gateway request path.

## Why receipt is separate from flush

`Observability.flush()` confirms that the SDK/exporter completed its bounded flush operation. It does
not prove that the expected telemetry reached a Collector or was written to a deterministic receipt
surface.

The positive-receipt test therefore requires both conditions:

1. the `a2a-otel-kit` exporter flush succeeds within five seconds;
2. bytes appended by the Collector after the test starts contain both the expected Gateway span name
   and the expected service identity.

The receipt assertion never treats pre-existing file content as evidence.

## Test-only topology

```text
pytest integration process
        │
        │ OTLP/HTTP
        ▼
127.0.0.1:4318
        │
        ▼
OpenTelemetry Collector Contrib 0.160.0
        │
        ▼
file/receipt -> .collector-receipts/traces.jsonl
```

The dedicated receipt Collector is defined by `compose.collector-receipt.yml` and uses
`tests/integration/otel-collector-receipt.yaml`.

The container is local-test infrastructure only:

- OTLP/HTTP is published on loopback only;
- the image version is pinned to the PC-15 Collector baseline;
- the root filesystem is read-only;
- all Linux capabilities are dropped;
- `no-new-privileges` is enabled;
- only the test configuration and ephemeral receipt directory are mounted;
- no provider, Policy Router, SaaS backend, Tempo, Grafana, API key, or application secret is required.

## Evidence contract

The integration test emits exactly one metadata-only span through `a2a-otel-kit`:

```text
service.name = governed-llm-gateway-collector-integration
span.name    = llm.gateway.request
```

No prompt, completion, message body, tool payload, document, raw provider response, request header,
response header, credential, or business attribute is attached by this test.

Before emission, the test records the receipt file size. After `flush()` and `shutdown()`, it polls for
at most five seconds and reads only the bytes appended after that recorded offset. The proof succeeds
only when both the stable span name and service identity appear in those appended bytes.

## CI boundary

`.github/workflows/collector-receipt.yml` owns the Docker-based positive-receipt check. It:

1. creates an ephemeral repository-local receipt file;
2. starts only the receipt Collector;
3. performs a bounded loopback OTLP/HTTP startup probe;
4. runs only `tests/integration/test_collector_receipt.py` with explicit endpoint and receipt inputs;
5. always tears the Collector down with volumes and orphans removed.

When the explicit endpoint and receipt-file inputs are absent, the integration test skips cleanly. This
keeps the default Python quality gate credential-free and independent from Docker availability.

## Non-claims

Positive Collector receipt proves only that the expected metadata reached the dedicated receipt
Collector during the integration run. It does not prove:

- that Tempo persisted or can query the trace;
- that Grafana can visualize the trace;
- that the executable Gateway process configures or shuts down observability correctly;
- that a Policy Router or provider request executed;
- that the local observability stack is production-ready;
- fleet completeness, durability, availability, or SLA compliance.

Collector availability is operational evidence only. It cannot alter `/readyz`, provider responses,
retry/fallback, ranking, or authorization.

Permanent invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```
