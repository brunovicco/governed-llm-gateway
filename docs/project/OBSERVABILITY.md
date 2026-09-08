# Observability and Evidence

OpenTelemetry runtime instrumentation is established by Phase 9 on top of `a2a-otel-kit`. The gateway
adds gateway-specific application spans and bounded attributes while the kit remains responsible for
the vendor-neutral observability foundation, including sanitization, W3C propagation, OTLP/HTTP
lifecycle, flush and shutdown semantics.

Observability is descriptive only. It is never an authorization source and must never alter inference
availability or broaden the candidate set.

Permanent invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Ranking, benchmark evidence, operational evidence, health, telemetry, exporter success, retry and
fallback cannot authorize a deployment rejected by policy.

## Stable Phase 9 vocabulary

The existing runtime names are now treated as a compatibility contract rather than implementation
literals that may be renamed for presentation purposes.

Spans:

| Purpose | Span name |
| --- | --- |
| authenticated gateway request boundary | `llm.gateway.request` |
| prompt-free PDP authorization | `policy.route` |
| one concrete provider attempt | `provider.inference` |
| normalized public streaming lifecycle | `llm.gateway.stream` |

Provider-attempt events:

| Purpose | Event name |
| --- | --- |
| bounded same-deployment retry | `llm.gateway.retry` |
| bounded move to the next already-ranked candidate | `llm.gateway.fallback` |

These names describe execution. They do not create authority. In particular, `provider.inference` may
only exist after the authorization/ranking boundaries have already produced an eligible concrete
candidate.

## Attribute boundary

Gateway-specific attributes pass through `a2a_otel_kit.sanitize_attributes()` with an explicit local
allowlist. The current bounded vocabulary includes:

- `llm.workload`;
- `llm.provider`;
- `llm.model`;
- `llm.deployment`;
- `llm.usage.input_count`;
- `llm.usage.output_count`;
- `llm.latency_ms`;
- `llm.ttft_ms`;
- `llm.fallback_count`;
- `llm.attempt_number`;
- `llm.retry_delay_ms`;
- `llm.partial`;
- `llm.streaming`;
- `routing.decision_id`;
- `routing.policy_id`;
- `routing.policy_version`;
- `routing.policy_digest`;
- `routing.model_group`;
- `registry.digest`;
- `ranking.policy_version`;
- `ranking.policy_digest`;
- `ranking.score_snapshot_id`.

The foundation sanitizer remains deny-by-default, accepts only bounded scalar values, and rejects
sensitive-looking keys even when a caller tries to extend an allowlist.

Avoid adding high-cardinality business values simply because OpenTelemetry can carry them. A new
attribute requires an explicit privacy, cardinality and operational-use justification.

## W3C trace continuity

The Phase 9 contract preserves W3C Trace Context across the gateway boundary and outbound provider
HTTP/SSE transports. Current contract tests verify that provider attempts remain on the gateway trace
and that outbound transports inject the active `traceparent` without leaking provider credentials.

The local Operational Readiness topology established by PC-15 is:

```text
Application / Agent
        │
        ▼
Policy Model Router
        │
        ▼
Governed LLM Gateway
        │
        ▼
   a2a-otel-kit
        │ OTLP/HTTP
        ▼
OpenTelemetry Collector
        │
        ▼
      Tempo
        │
        ▼
     Grafana
```

The checked-in local stack pins Collector, Tempo and Grafana versions, binds host-published ports to
loopback, keeps Tempo internal to the Compose network and contains no SaaS exporter or hardcoded
credential.

A remote observability backend must never become an inference-availability dependency. Export or
flush failure cannot change an otherwise valid provider result.

## Process-owned observability lifecycle

PC-17 owns optional `a2a-otel-kit` lifecycle at the executable Gateway process boundary without moving
telemetry into authorization or readiness.

Observability remains disabled by default. Explicit process opt-in requires both:

```text
--otel-endpoint <http-or-https-OTLP-HTTP-endpoint>
--otel-environment <normalized-environment>
```

The process supplies the complete `ObservabilitySettings` contract explicitly, including the fixed
service identity/version, timeout, log level and log format. Ambient `A2A_OTEL_*` values therefore do
not override process-owned settings. No CLI path exists for OTLP credentials, Authorization headers,
Langfuse configuration or content capture.

Structurally invalid observability settings fail before deployment activation. Operational
`Observability.configure()` failure is different: the process emits a static warning and continues
activation with `observability=None`, preserving `NullGatewayTelemetry`. No Collector reachability
probe is performed.

When configuration succeeds, that exact instance is injected through the existing deployment and
service composition path. The process owns it until the runner exits and performs best-effort
`shutdown()` in a `finally` boundary. Shutdown failure is suppressed with a static warning so it cannot
mask activation/runner behavior or become an inference dependency.

`/livez` and `/readyz` remain derived from successful bootstrap only. Exporter state, Collector
availability, flush success and shutdown success do not participate in either endpoint.

## Routing and authorization evidence

Metadata-only routing evidence can include:

- request/correlation ID and workload;
- PDP decision ID plus policy ID/version/digest;
- authorized logical model group;
- model-registry digest;
- deterministic routing decision ID;
- ranking-policy version and digest;
- ranking score-snapshot identity;
- selected provider/model/deployment;
- machine-readable candidate rejection reasons.

`ranking.score_snapshot_id` identifies the score snapshot used by deterministic ranking. It is not
itself a benchmark evidence artifact. Approved benchmark snapshots remain separately versioned and
reviewed evidence; any relationship between benchmark evidence and active ranking must be explicit in
the ranking-evidence/provenance contract rather than inferred from telemetry.

The explainability surface remains prompt-free and provider-free. Rejected-candidate reason codes are
gateway-produced evidence; a UI must display those codes rather than infer its own reasons.

## Resilience evidence

Availability handling remains reconstructable without payload capture:

- ordered fallback progression across already-ranked authorized deployments;
- concrete deployment and attempt number;
- normalized provider failure category/status where applicable;
- bounded retry delay and attempt latency;
- deployment health/circuit state;
- retry and fallback span events.

Same-deployment retry and cross-deployment fallback remain distinct concepts. Runtime health can only
remove or skip candidates; it cannot resurrect an unauthorized candidate.

Provider failure remains availability evidence and must not be silently reclassified as model-quality
failure.

## Streaming evidence

The normalized public stream exposes requested model output to the authenticated caller, but that
payload does not become telemetry merely because it crosses the gateway.

Metadata that can be reconstructed from the stream boundary includes:

- selected deployment and bounded fallback progression;
- monotonic public sequence numbers;
- normalized event categories;
- partial/non-partial terminal failure state;
- normalized terminal error category;
- final normalized token usage;
- cancellation/closure lifecycle state without treating caller cancellation as provider failure.

## Privacy boundary

Default telemetry is metadata-only.

Do not record implicitly:

- prompts, message bodies or completions;
- content deltas or structured-output payloads;
- tool arguments or tool results;
- documents or provider raw responses;
- raw/unsanitized remote exception text;
- arbitrary request or response headers;
- Authorization headers, API keys or credentials.

Content capture is not part of the current product-readiness cycle. Any future content capture would
require explicit opt-in, redaction/classification, bounded retention and a separately governed policy.

## Operational evidence is not fleet completeness

The gateway intentionally keeps distinct responsibilities:

```text
InMemoryHealthTracker
    -> immediate per-process resilience state
OperationalAttemptRecorder
    -> process-local sample recording
OperationalSampleBatch
    -> content-addressed handoff
OperationalEvidenceSnapshot
    -> reviewed recent-window evidence
```

Process-local evidence must not be presented as fleet-complete telemetry. A future aggregation layer
must make its coverage/completeness semantics explicit before a console or dashboard claims fleet
completeness.

## Collector receipt verification

PC-16 implements the positive-receipt pattern already proven by `a2a-otel-kit`: exporter flush alone
is not proof that a Collector received the expected trace.

The dedicated credential-free integration boundary:

- starts an isolated OpenTelemetry Collector Contrib `0.160.0` on loopback;
- emits one metadata-only `llm.gateway.request` span through `a2a-otel-kit`;
- records the receipt-file size before emission;
- requires exporter flush to succeed;
- reads only bytes appended after the recorded offset;
- requires both the stable Gateway span name and the integration service identity to appear within a
  bounded polling window;
- always tears down the Collector after the job.

The receipt Collector exports only to a local test file. It does not require a provider, Policy Router,
Tempo, Grafana, Langfuse, SaaS backend, API key or application secret. See
`docs/project/COLLECTOR_RECEIPT.md` for the complete boundary and non-claims.

Positive receipt proves Collector delivery only. It does not itself prove Tempo persistence/queryability,
Grafana visualization, process lifecycle correctness, fleet completeness or production readiness.
PC-17 separately proves the executable-process lifecycle contract with deterministic contract tests;
it does not change the narrower meaning of the PC-16 receipt evidence.

## Tempo persistence and queryability verification

PC-26 adds the next bounded downstream proof without making Tempo part of readiness or inference.
The credential-free `tempo-query` integration starts the real pinned Collector and Tempo containers,
emits one metadata-only `llm.gateway.request` span through the Collector OTLP/HTTP boundary, and then
requires the exact emitted trace to be both retrievable by trace ID and discoverable through Tempo
TraceQL search.

The reusable Compose stack keeps Tempo internal. A test-only overlay publishes `127.0.0.1:3200` solely
for the bounded query proof. The Python integration uses stdlib `urllib` and validates the complete
Tempo URL as reviewed loopback HTTP before constructing or opening a request.

Real startup validation also protects the pinned-version configuration contract. Tempo `3.0.3` uses the
Tempo 3.x backend compaction/retention shape under `backend_worker.compaction`; the local 24-hour
retention intent remains explicit. Integration-only recent-query settings are isolated from the reusable
base configuration so the test can query the span it just emitted without changing local-demo defaults.

See `docs/project/TEMPO_QUERY_PROOF.md` for the exact path, failure semantics and non-claims.

Tempo query success proves only the checked-in local Collector-to-Tempo delivery/query path. It does not
establish Grafana dashboard correctness, fleet completeness, production authentication/durability,
telemetry freshness guarantees, provider reachability, inference readiness, or any authorization,
ranking, health, retry or fallback authority.

## Next operational increment

PC-15 established the local observability stack, PC-16 proved positive Collector receipt, PC-17 bound
optional observability lifecycle to the executable process, PC-18 through PC-24 established the bounded
Operations read path, and PC-25 added the first read-only Gateway Console. PC-26 now supplies the
Collector-to-Tempo queryability proof required before Grafana visualization work is justified.

Grafana dashboards, trace correlation/deep links and any Console trace-link work remain separate later
increments and must be re-audited only after PC-26 is certified post-merge. Langfuse remains optional
and, if introduced later, must integrate downstream of OTLP/Collector rather than through a Gateway SDK
dependency.
