# Recent Operational Evidence

## Purpose

The Roadmap separates offline benchmark quality from online operational health and allows a future runtime score to combine the latest approved benchmark snapshot with recent operational measurements.

The gateway already has per-process `DeploymentHealthSnapshot` state for circuit breaking and coarse eligibility. That state is intentionally not treated as a reviewed ranking snapshot: it is cumulative process-local state, has no explicit observation window, and currently affects ranking only through health/circuit eligibility.

Issue #69 introduces the first bounded step toward Roadmap online-telemetry ranking: a strict, immutable, content-addressed contract for preserving recent operational measurements. **This increment does not change ranking.**

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

## Current health vs versioned operational evidence

The two concepts remain separate:

```text
InMemoryHealthTracker / DeploymentHealthSnapshot
    -> immediate process-local resilience and eligibility

OperationalEvidenceSnapshot
    -> reviewed recent-window evidence artifact
```

This feature does **not** claim that the existing in-memory tracker can reconstruct a historical time window or p50/p95 latency. A later collector/materializer must obtain those measurements from an appropriate metadata-only runtime source and must preserve collector provenance.

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

No prompts, completions, provider credentials, secrets, or business payloads belong in this evidence contract.

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

## Explicitly not implemented by this increment

- no production operational-evidence collector;
- no OpenTelemetry/metrics backend query;
- no shared health store;
- no online-score normalization policy;
- no change to `StaticDeploymentScore`;
- no change to `OperationalRankingService` score calculation;
- no automatic policy update;
- no Phase 14 consumer migration.

## Next reviewed step

After this contract is stable, the next consumer-agnostic increment may define a metadata-only materializer that produces schema `1.0` evidence from a bounded recent runtime window. Only after that evidence path exists should a separate versioned policy define how recent measurements can influence operational score dimensions.

Issue #18 remains authoritative for Phase 14 sequencing: OpsLens stays deferred, and RAGForge must not start in parallel unless the normative order is explicitly revised.
