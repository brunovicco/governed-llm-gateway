# Recent Operational Evidence

Status: **COMPLETE through PR #73 for schema `1.0` plus bounded process-local materialization. Runtime recorder wiring, production/shared sources and online ranking policy remain pending.**

## Purpose

The Roadmap separates offline benchmark quality from online operational health and allows a future runtime score to combine the latest approved benchmark snapshot with recent operational measurements.

The gateway already has per-process `DeploymentHealthSnapshot` state for circuit breaking and coarse eligibility. That state is intentionally not treated as a reviewed ranking snapshot: it is cumulative process-local state, has no explicit observation window, and currently affects ranking only through health/circuit eligibility.

PR #70 introduced the strict, immutable, content-addressed contract for preserving recent operational measurements. PR #73 completes issue #72 by adding a deterministic materialization path from explicit metadata-only provider-attempt samples. **Neither increment changes ranking.**

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

Issue #72 introduces `OperationalAttemptSample`, an immutable application-level contract for one **actual provider attempt**. A sample preserves only:

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

Circuit-open or eligibility skips are not actual provider attempts and therefore are not represented as provider-error samples.

## Deterministic materialization

`OperationalEvidenceMaterializer` reads a complete half-open `[window_start, window_end)` sample window through the `OperationalSampleSource` port and aggregates records by `(runtime_workload, deployment_id)`.

For each record:

- `gateway_request_count` is the number of distinct gateway request IDs with an actual provider attempt on that deployment;
- `provider_attempt_count` is the number of actual provider-attempt samples;
- success/error/rate-limit/timeout counts derive only from explicit sample outcomes;
- `fallback_request_count` is the number of distinct gateway requests where that deployment was actually attempted with `fallback_index > 0`;
- provider p50/p95 latency uses deterministic nearest-rank percentiles over all actual provider-attempt latencies, including failed attempts.

The materializer sorts source samples deterministically, rejects samples outside the requested window, fails closed on duplicate provider-attempt identities and rejects empty windows because schema `1.0` requires non-empty records.

This increment does **not** wire sample recording into `ResilientExecutionService`. That separation is deliberate: a collector/store failure must not become provider-inference failure merely because operational evidence collection is enabled. Runtime recording/composition requires its own reviewed boundary.

## Bounded process-local source

`InMemoryOperationalSampleStore` is a deterministic credential-free source suitable for CI, replay and explicit process-local composition. It is not a distributed observability backend.

The store:

- establishes `coverage_start` at construction time;
- accepts only non-decreasing UTC sample timestamps within source coverage;
- rejects future samples;
- enforces an explicit positive `max_samples` capacity;
- records the latest timestamp whose history may have been evicted;
- rejects requested windows that begin before process coverage;
- rejects windows that may intersect capacity-evicted history;
- rejects windows ending in the future;
- returns samples in deterministic chronological order.

Capacity eviction must never silently convert an incomplete window into apparently complete operational evidence.

## Current health vs versioned operational evidence

The concepts remain separate:

```text
InMemoryHealthTracker / DeploymentHealthSnapshot
    -> immediate process-local resilience and eligibility

OperationalAttemptSample / OperationalSampleSource
    -> explicit timestamped metadata-only provider-attempt observations

OperationalEvidenceSnapshot
    -> reviewed immutable recent-window evidence artifact
```

`InMemoryHealthTracker` still cannot reconstruct a historical time window or p50/p95 latency. Issue #72 does not reinterpret its cumulative counters or last latency as historical evidence.

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

Materialization is evidence production only. `OperationalRankingService`, `StaticDeploymentScore`, candidate eligibility and policy authorization are unchanged.

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

## Explicitly not implemented by issue #72

- no automatic recorder wiring in provider execution;
- no production/shared operational-evidence source;
- no OpenTelemetry/metrics backend query adapter;
- no Redis/shared health or sample store;
- no online-score normalization policy;
- no change to `StaticDeploymentScore`;
- no change to `OperationalRankingService` score calculation;
- no automatic policy update;
- no Phase 14 consumer migration.

## Next reviewed step

After the bounded materializer is merged and validated, a later consumer-agnostic increment may define how real runtime metadata-only attempts are recorded or queried through a production/shared source without making evidence collection part of inference availability. Only after a complete reviewed evidence-production path exists should a separate versioned policy define how recent measurements may influence operational score dimensions.

Issue #18 remains authoritative for Phase 14 sequencing: OpsLens stays deferred, and RAGForge must not start in parallel unless the normative order is explicitly revised.
