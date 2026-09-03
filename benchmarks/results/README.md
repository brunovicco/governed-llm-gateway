# Benchmark Result Evidence

Phase 10 benchmark results are immutable, versioned evaluation evidence. They are not runtime routing
inputs yet.

## Evidence boundary

Every persisted snapshot must identify:

- benchmark version and deterministic dataset digest;
- runner version and run date;
- provider, exact model identifier, API family, and benchmark configuration for every target;
- per-case status distinguishing model-quality outcomes from provider-availability failures;
- aggregated quality, availability, latency, TTFT, usage, cost, rate-limit, and fallback metrics;
- a content-derived `sha256:` snapshot identifier.

A result must not be described as a "best model" result unless the provider, exact model identifier,
API, configuration, run date, and benchmark version are stated together.

## Privacy and environment rules

The initial `gateway-eval-v1` dataset contains only public/synthetic cases. Free-tier and developer
endpoints are benchmark/development targets only and must not receive confidential or private
datasets by default.

Persisted score snapshots contain normalized evaluation evidence rather than raw provider responses.
Provider credentials, Authorization headers, arbitrary customer payloads, and private prompts must
never be written to this directory.

## Quality versus availability

A provider timeout, rate limit, or service outage is recorded as `provider_failure`. Such an
observation has no quality score and contributes to availability/error evidence instead.

A completed provider call that does not satisfy the deterministic scorer is recorded as
`quality_failure`. This keeps model-quality evidence separate from operational provider health.

## Phase boundary

Phase 10 creates datasets, deterministic scorers, provider-neutral runners, target matrices, and
versioned snapshots. The production ranking path does **not** load or consume these snapshots in this
phase.

Evidence-driven ranking belongs to Phase 11 and must preserve the authorization invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Benchmark evidence may eventually rank already-authorized candidates; it must never grant model or
deployment authorization.
