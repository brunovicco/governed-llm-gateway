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

Positive receipt proves Collector delivery only. It does not prove Tempo persistence/queryability,
Grafana visualization, executable-process observability lifecycle, fleet completeness or production
readiness.

## Next operational increment

PC-15 established the local Collector + Tempo + Grafana foundation and PC-16 established deterministic
positive Collector receipt evidence. Before binding observability lifecycle into the executable
Gateway process, the process composition boundary must be audited explicitly so configuration,
flush/shutdown failure and backend availability cannot become authorization, readiness or inference
dependencies.

Langfuse remains optional and, if introduced later, must integrate downstream of OTLP/Collector rather
than through a Gateway SDK dependency.
