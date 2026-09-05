# Multimodal Gateway Response Normalization v1

Status: provider-neutral benchmark-response boundary after the multimodal gateway execution plan stabilized.

## Purpose

This boundary converts one terminal `GatewayResponse` into the existing benchmark `ProviderCall` evidence contract.

It does not submit a request, choose a provider, authorize a model, or publish ranking evidence.

## Successful responses

A successful gateway response must include terminal `ProviderExecution` evidence. The normalizer maps:

- execution latency to benchmark `latency_ms`;
- normalized input/output token usage to benchmark units;
- normalized total cost to `cost_usd` when present;
- execution `fallback_index` to benchmark `fallback_count`;
- structured output, when present, to benchmark output;
- otherwise JSON-decodable content to benchmark output.

If successful text content is not valid JSON, the original text is preserved as benchmark output. It is then evaluated by the deterministic workload scorer and becomes model-quality evidence rather than provider-availability failure.

This distinction is important for `multimodal-analysis-v1`: an image request that completed but answered in the wrong format is a quality failure, not an outage.

## Failed responses

A terminal gateway response with `status = failed` requires provider-neutral `GatewayError` evidence and is converted to `BenchmarkProviderFailure`.

The stable gateway error code becomes the benchmark provider-failure code. Terminal execution latency is preserved when available.

No provider-specific exception object or raw provider payload is copied into benchmark evidence.

## Evidence integrity

A successful response without terminal `ProviderExecution` evidence fails closed because it cannot produce a complete normalized `ProviderCall` record.

Structured output is recursively constrained to JSON-compatible values before it is admitted into benchmark evidence.

## Authorization boundary

Response normalization happens after the normal gateway execution path. It cannot expand an authorized set and has no effect on model eligibility or policy decisions.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Benchmark output, latency, usage, errors, fallback evidence, and scores remain evaluation/availability evidence only.

## CI boundary

Default CI exercises this adapter with provider-neutral contract objects only. It performs no network call, requires no API key, and does not fetch the multimodal fixture.

A later live executor may compose:

1. multimodal execution-plan materialization;
2. an already-authorized gateway client call;
3. this response normalizer;
4. the existing deterministic benchmark runner/scorer.

That composition remains a separate reviewed increment.
