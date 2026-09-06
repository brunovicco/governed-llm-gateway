# Recent Operational Evidence

Status: **Schema `1.0` and bounded process-local materialization are COMPLETE through PR #73. Issue #75 adds optional best-effort runtime attempt recording for both bounded executors. Production/shared sources and online ranking policy remain pending.**

## Purpose

The Roadmap separates offline benchmark quality from online operational health and allows a future runtime score to combine the latest approved benchmark snapshot with recent operational measurements.

The gateway already has per-process `DeploymentHealthSnapshot` state for circuit breaking and coarse eligibility. That state is intentionally not treated as a reviewed ranking snapshot: it is cumulative process-local state, has no explicit observation window, and currently affects ranking only through health/circuit eligibility.

PR #70 introduced the strict, immutable, content-addressed contract for preserving recent operational measurements. PR #73 completed issue #72 by adding a deterministic materialization path from explicit metadata-only provider-attempt samples. Issue #75 adds an optional process-local recorder boundary for the existing non-streaming and streaming executors. **None of these increments changes ranking or authorization.**

## Snapshot provenance

Operational evidence schema `1.0` records:

- `snapshot_version`;
- `collector_id`;
- `collector_version`;
- UTC `window_start`;
- UTC `window_end`;
- UTC `captured_at`;
- canonical content-derived `evidence_id`;
- deterministically ordered records.

The window must be positive and `captured_at` cannot precede `window_end`.

The public `create_operational_evidence_snapshot(...)` factory derives the canonical schema `1.0` `evidence_id` using the same content payload used by strict snapshot verification. Materializers therefore do not import private hashing helpers or duplicate identity semantics.

## Record semantics

Each record is keyed by:

```text
(runtime_workload, deployment_id)
```

It preserves explicitly named measurements:

- `gateway_request_count`;
- `provider_attempt_count`;
- `successful_provider_attempt_count`;
- `provider_error_count`;
- `rate_limit_error_count`;
- `timeout_count`;
- `fallback_request_count`;
- `provider_latency_p50_ms`;
- `provider_latency_p95_ms`.

These are evidence fields, not routing scores. The contract deliberately does not invent normalization functions for `reliability`, `latency`, `cost`, or `availability`.

The counters fail closed when they contradict one another. In particular:

- successful provider attempts plus provider errors must equal provider attempts;
- rate-limit and timeout counts cannot exceed provider errors;
- fallback requests cannot exceed gateway requests;
- p95 latency cannot be lower than p50 latency.

## Metadata-only attempt samples

PR #73 introduced `OperationalAttemptSample`, an immutable application-level contract for one **actual provider attempt**. A sample preserves only:

- UTC completion timestamp (`observed_at`);
- gateway request UUID;
- dotted runtime workload;
- deployment ID;
- positive attempt number;
- non-negative fallback index;
- bounded outcome (`succeeded` or `provider_error`);
- bounded provider-error kind (`rate_limit`, `timeout`, or `other`) when the outcome is an error;
- non-negative provider-attempt latency in milliseconds.

No prompt, completion, message content, tool payload, business payload, provider credential or secret belongs in this sample contract.

Circuit-open, provider-resolution, capability or eligibility skips that occur before a provider call are not actual provider attempts and therefore are not represented as provider-error samples.

## Deterministic materialization

`OperationalEvidenceMaterializer` reads a complete half-open `[window_start, window_end)` sample window through the `OperationalSampleSource` port and aggregates records by `(runtime_workload, deployment_id)`.

For each record:

- `gateway_request_count` is the number of distinct gateway request IDs with an actual provider attempt on that deployment;
- `provider_attempt_count` is the number of actual provider-attempt samples;
- success/error/rate-limit/timeout counts derive only from explicit sample outcomes;
- `fallback_request_count` is the number of distinct gateway requests where that deployment was actually attempted with `fallback_index > 0`;
- provider p50/p95 latency uses deterministic nearest-rank percentiles over all actual provider-attempt latencies, including failed attempts.

The materializer sorts source samples deterministically, rejects samples outside the requested window, fails closed on duplicate provider-attempt identities and rejects empty windows because schema `1.0` requires non-empty records.

## Best-effort runtime recording

Issue #75 adds the `OperationalAttemptRecorder` application port and optional recorder dependencies to both `ResilientExecutionService` and `StreamingExecutionService`.

The recorder boundary is deliberately **process-local, synchronous, non-networked and best-effort**. It is not a remote delivery interface. When no recorder is configured, the existing execution path remains semantically unchanged.

For an actual provider call with a schema-`1.0`-representable terminal outcome:

- provider latency continues to use the existing monotonic execution clock;
- completion provenance uses a separate offset-aware UTC clock;
- success records `OperationalSampleOutcome.SUCCEEDED`;
- rate-limit errors record `PROVIDER_ERROR/RATE_LIMIT`;
- timeout errors record `PROVIDER_ERROR/TIMEOUT`;
- other normalized `ProviderError` values record `PROVIDER_ERROR/OTHER`;
- retry attempt numbers and actual fallback indices are preserved exactly.

Operational recording happens only after the outcome is terminal enough to support the sample contract. In particular, streaming success is recorded only after final-usage and response-identity validation completes.

Evidence collection is never an inference-availability dependency. A recorder exception is swallowed so it cannot replace a successful provider result, hide a provider error, change retry/fallback behavior, alter replay-safety behavior, or delay execution on remote I/O.

## Completeness invalidation

Schema `1.0` intentionally does not fabricate a provider error for outcomes it cannot faithfully represent. Caller cancellation, generator close and unexpected non-`ProviderError` exceptions after a provider attempt has started therefore create a **completeness gap**, not a fake provider-error sample.

`OperationalAttemptRecorder.invalidate_completeness(...)` lets a source conservatively advance the latest timestamp through which complete runtime history cannot be proven. A failure while recording a representable terminal sample also attempts this invalidation best-effort.

`InMemoryOperationalSampleStore` tracks this as `incomplete_through`. Requested windows whose start is at or before that boundary fail closed. A later window starting strictly after the boundary may be materialized again when its own coverage is otherwise complete.

This boundary is intentionally conservative: it may reject more historical data than strictly necessary, but it must never certify a false-complete operational window.

## Bounded process-local source

`InMemoryOperationalSampleStore` is a deterministic credential-free source and recorder suitable for CI, replay and explicit process-local composition. It is not a distributed observability backend.

The store:

- establishes `coverage_start` at construction time;
- accepts only non-decreasing UTC sample timestamps within source coverage;
- rejects future samples and future completeness gaps;
- enforces an explicit positive `max_samples` capacity;
- records the latest timestamp whose history may have been evicted;
- records the latest conservative incomplete-runtime boundary;
- rejects requested windows that begin before process coverage;
- rejects windows that may intersect capacity-evicted history;
- rejects windows that may intersect incomplete runtime history;
- rejects windows ending in the future;
- returns samples in deterministic chronological order.

Capacity eviction, cancellation or recording failure must never silently convert an incomplete window into apparently complete operational evidence.

## Current health vs versioned operational evidence

The concepts remain separate:

```text
InMemoryHealthTracker / DeploymentHealthSnapshot
    -> immediate process-local resilience and eligibility

OperationalAttemptRecorder
    -> optional best-effort local production of metadata-only samples

OperationalAttemptSample / OperationalSampleSource
    -> explicit timestamped metadata-only provider-attempt observations

OperationalEvidenceSnapshot
    -> reviewed immutable recent-window evidence artifact
```

`InMemoryHealthTracker` still cannot reconstruct a historical time window or p50/p95 latency. The operational sample store is a separate process-local evidence boundary and does not reinterpret health counters as historical evidence.

## Authority boundary

Permanent invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operational evidence cannot:

- authorize a model, provider, deployment, model group, or business tool;
- restore a candidate excluded by policy, governance, capability, data/environment constraints, cost ceilings, latency ceilings, health, or circuit state;
- force a benchmark/provider target into execution;
- modify ranking weights;
- self-promote;
- rewrite active policy;
- create an adaptive or bandit policy loop.

Runtime recording and materialization are evidence production only. `OperationalRankingService`, `StaticDeploymentScore`, candidate eligibility and policy authorization are unchanged.

## Relationship to benchmark evidence

Offline benchmark evidence and online operational evidence remain separate artifacts:

```text
approved benchmark snapshot
        │
        ├── offline quality / grounding / tool accuracy / schema evidence
        │
recent operational evidence snapshot
        │
        └── online latency / provider errors / rate limits / timeouts / fallback evidence
```

A future combination step must be explicit, versioned, deterministic, reversible, auditable, and subordinate to authorization and eligibility.

## Explicitly not implemented by issue #75

- no remote/networked recorder sink in provider execution;
- no production/shared operational-evidence source;
- no OpenTelemetry/metrics backend query adapter for materialization;
- no Redis/shared health or sample store;
- no online-score normalization policy;
- no automatic loading of operational evidence into ranking;
- no change to `StaticDeploymentScore`;
- no change to `OperationalRankingService` score calculation;
- no automatic policy update;
- no Phase 14 consumer migration.

## Next reviewed step

After issue #75 is merged and validated, a later consumer-agnostic increment may define a production/shared metadata-only source or exporter that is decoupled from provider execution and has explicit completeness semantics. Remote delivery must not become a required provider-execution dependency. Only after a complete reviewed evidence-production path exists should a separate versioned policy define how recent operational measurements may influence score dimensions.

Issue #18 remains authoritative for Phase 14 sequencing: OpsLens stays deferred, and RAGForge must not start in parallel unless the normative order is explicitly revised.