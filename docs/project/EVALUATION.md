# Evaluation

Gateway routing is treated as empirical optimization. Runtime code must not encode personal model
preferences such as "model X is always best for agents".

## Phase 5 static ranking evidence

Phase 5 introduced deterministic ranking before the benchmark framework existed. Its
`score_snapshot_id` identifies **static, versioned ranking input configuration** only.

It is not benchmark evidence and must not be represented as `benchmark_snapshot_id`.

Static Phase 5 inputs provide a reproducible bridge to later empirical routing while preserving:

- workload-specific versioned weights;
- deterministic score calculation;
- ranking-policy digest provenance;
- explicit rollback/replay of configuration;
- no hard-coded model preference in application logic.

## Phase 10 evaluation boundary

Phase 10 implements an offline-first, provider-neutral evaluation framework under `benchmarks/`.
It is deliberately outside the gateway runtime packages: benchmark code and result artifacts do not
become an execution dependency of `gateway-core`, `gateway-api`, or provider-neutral contracts.

The framework provides:

- strict versioned public/synthetic datasets;
- a strict, fully identified provider/model/API/configuration target matrix;
- deterministic local scorers with no model-as-judge or network dependency;
- a provider-neutral `BenchmarkExecutor` port and `BenchmarkRunner`;
- distinct quality and provider-availability observation states;
- deterministic scorecard aggregation;
- canonical dataset digests and immutable content-derived snapshot identifiers;
- versioned snapshot persistence suitable for review and later Phase 11 consumption;
- benchmark code included in Ruff, mypy, Bandit, architecture validation, and repository coverage.

## Initial dataset

`benchmarks/datasets/gateway-eval-v1.json` is schema `1.0`, benchmark version `gateway-eval-v1`, and
explicitly classified `public`.

The initial dataset contains ten public/synthetic cases, two per roadmap workload:

- `structured_extraction`;
- `rag_ptbr`;
- `code_generation`;
- `tool_use`;
- `agent_orchestration`.

Unknown dataset fields, unsupported workload identifiers, malformed JSON-compatible values, and
non-public Phase 10 data classification fail closed before provider execution.

## Deterministic scorers

The initial bounded scorer registry contains:

- `exact_json` — exact normalized JSON equality;
- `contains_all` — deterministic required-string coverage;
- `mapping_fields` — exact expected field/value coverage;
- `ordered_sequence` — positional sequence accuracy.

Scorer references are validated for the complete dataset before the first provider call. An unknown
scorer therefore cannot create a partial benchmark run.

These scorers are intentionally simple and auditable. More sophisticated evaluators may be added in
later benchmark versions only with explicit semantics and reproducibility evidence.

## Initial target matrix

`benchmarks/runners/targets-v1.json` records matrix version `phase10-targets-v1`. Every target records:

- provider;
- exact model identifier;
- API family/surface;
- benchmark configuration;
- source date.

The initial matrix contains development/benchmark targets for NVIDIA, Groq, OpenRouter, and Google
Gemini, plus paid/control targets for OpenAI Responses and Anthropic Messages.

Free-tier or developer-access endpoints are benchmark/development targets only. They must not receive
confidential/private evaluation fixtures by default.

A result must not be described as a "best model" result unless provider, exact model, API,
configuration, run date, and benchmark version are stated together.

## Quality versus availability

Offline quality evidence and provider availability are intentionally distinct.

A completed provider call is scored deterministically and becomes either:

- `succeeded`; or
- `quality_failure`.

A timeout, rate limit, provider outage, or other failed provider call becomes `provider_failure` and
has `quality_score = None`.

Therefore a 429 or timeout cannot silently become a zero-quality model result. Provider failures
contribute to availability/error evidence instead.

Scorecards aggregate independently:

- availability rate;
- quality success rate among completed calls;
- mean quality score among completed calls;
- latency p50/p95;
- TTFT p50/p95 where present;
- normalized input/output usage;
- total benchmark cost;
- rate-limit error count;
- fallback frequency;
- stable provider error counts.

Online gateway runtime health and circuit-breaker state remain separate mutable operational evidence.

## Snapshot reproducibility

A dataset digest is derived from canonical JSON over the complete ordered benchmark case content.
A benchmark snapshot identifier is a `sha256:` digest over:

- snapshot schema version;
- benchmark version;
- runner version;
- run date;
- dataset digest;
- exact benchmark targets and configurations;
- normalized observations;
- aggregated scorecards.

Changing a target configuration changes the snapshot ID. Rebuilding the same evidence produces the
same ID and canonical JSON.

Persisted artifacts are stored under:

```text
benchmarks/results/<benchmark-version>/<snapshot-sha256>.json
```

Persistence is immutable/idempotent: an existing snapshot ID with different content fails closed.
Raw provider responses are not part of the score snapshot contract.

## CI and live-provider boundary

Default CI is credential-free and deterministic. It validates loaders, scorers, aggregation,
reproducibility, failure classification, privacy-oriented result structure, and architecture rules
without live PDP/provider calls.

Live-provider benchmark execution must remain explicitly separated under the existing
`live_provider` pytest marker or an equally explicit manual benchmark workflow. Credentials must not
be required by the default quality gate.

## Phase 11 boundary

Phase 10 produces evaluation evidence only. Production ranking does **not** import, load, or consume
benchmark result snapshots in this phase, and `benchmark_snapshot_id` remains unset in runtime routing
provenance.

ADR-0009 remains deferred to Phase 11, where approved benchmark snapshots may influence ordering only
inside the already-authorized candidate set.

The authorization invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Benchmark evidence may eventually rank already-authorized candidates; it must never grant model or
deployment authorization.
