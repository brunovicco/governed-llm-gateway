# Benchmark Result Evidence

Benchmark results are immutable, versioned offline evaluation evidence. Raw benchmark snapshots are
not authorization sources and are not loaded directly as routing overrides. Phase 11 may consume only
explicitly reviewed and promoted benchmark evidence to rank candidates that are already authorized and
eligible.

## Evidence boundary

Every persisted snapshot must identify:

- benchmark version and deterministic dataset digest;
- runner version and run date;
- provider, exact model identifier, API family, and benchmark configuration for every target;
- per-case status distinguishing model-quality outcomes from provider-availability failures;
- scalar quality plus reviewed per-observation quality components when the workload contract supports
  them;
- aggregated quality components plus availability, latency, TTFT, usage, cost, rate-limit, and fallback
  evidence;
- a content-derived `sha256:` snapshot identifier.

A result must not be described as a "best model" result unless the provider, exact model identifier,
API, configuration, run date, and benchmark version are stated together.

## Snapshot schema evolution

Snapshot history is versioned rather than rewritten:

- schema `1.0` is the historical component-free snapshot contract without target-matrix provenance;
- schema `1.1` is the historical target-matrix provenance extension without quality components;
- schema `1.2` is used when reviewed quality-component evidence is present. Observation
  `quality_metrics` and scorecard `mean_quality_metrics` participate in canonical serialization and the
  content-addressed `snapshot_id`. Target-matrix provenance may coexist only as a complete reviewed
  version/digest pair.

Empty quality-component mappings do not silently upgrade historical 1.0/1.1 snapshots.

The currently reviewed component vocabulary is intentionally bounded to dimensions supported by
existing deterministic workload semantics:

- `schema_validity`;
- `tool_selection_accuracy`;
- `tool_argument_accuracy`;
- `trajectory_success`;
- `grounding`.

Independent PT-BR language quality is not inferred from `rag-ptbr-v1`; it remains a separate explicit
measurement gap.

## Privacy and environment rules

The checked-in benchmark datasets and fixtures are public/synthetic and credential-free by default.
Free-tier and developer endpoints are benchmark/development targets only and must not receive
confidential or private datasets by default.

Persisted score snapshots contain normalized evaluation evidence rather than raw provider responses.
Provider credentials, Authorization headers, arbitrary customer payloads, and private prompts must
never be written to this directory.

## Quality versus availability

A provider timeout, rate limit, or service outage is recorded as `provider_failure`. Such an
observation has neither a scalar quality score nor quality-component metrics and contributes to
availability/error evidence instead. Provider failures therefore do not dilute completed-call model
quality or component means.

A completed provider call that does not satisfy the deterministic scorer is recorded as
`quality_failure`. This keeps offline model-quality evidence separate from operational provider
health.

## Promotion and ranking boundary

Phase 10 creates public/synthetic datasets, deterministic scorers, provider-neutral runners, target
matrices, scorecards, and content-addressed snapshots.

Phase 11 adds a separate explicit promotion boundary. Promotion converts reviewed immutable benchmark
evidence into versioned ranking evidence; it does not make a raw snapshot authoritative, and the
current promotion contract remains scalar. Quality components introduced later are not implicitly
promoted.

Ranking may reorder only candidates already inside the authorized and eligible set. Benchmark targets,
raw snapshots, promoted evidence, quality components, telemetry, and runtime provenance cannot grant a
model/provider/deployment permission or force a benchmark target into execution.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

See `docs/evaluation/BENCHMARK_MATRIX.md`,
`docs/evaluation/BENCHMARK_QUALITY_COMPONENTS.md`, and `docs/project/EVALUATION.md` for the current
reviewed benchmark/evidence contracts.
