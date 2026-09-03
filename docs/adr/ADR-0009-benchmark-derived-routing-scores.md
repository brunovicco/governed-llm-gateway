# ADR-0009 — Benchmark-Derived Routing Scores

Status: Accepted  
Date: 2026-09-03

## Context

Phase 5 established deterministic operational ranking from explicit static/versioned score inputs.
Phase 10 added reproducible benchmark datasets, deterministic scorers, provider/model/API/configuration
provenance, quality-vs-availability evidence, and immutable content-derived benchmark snapshots.

Phase 11 may now use approved benchmark evidence to affect deployment ordering, but it must preserve
the authority boundary established earlier:

`Gateway allowed set ⊆ Policy Router authorized set`

Benchmark evidence is evidence, not authorization. A benchmark result must never make an unauthorized,
disabled, incapable, unhealthy, over-budget, or otherwise ineligible deployment eligible.

The roadmap also requires manual override, rollback, visible benchmark provenance, and no automatic
self-modification.

## Decision

Phase 11 uses an explicit promotion boundary between benchmark results and runtime ranking.

The flow is:

`immutable benchmark snapshot -> explicit approval/promotion -> versioned ranking evidence -> runtime ranking`

Runtime code does not discover the newest benchmark result, scan `benchmarks/results/`, or automatically
change ranking policy after a benchmark run. A newly generated snapshot has no routing authority until
an operator explicitly promotes it.

### Approved snapshot identity

Every promoted benchmark-derived ranking artifact records the exact immutable Phase 10
`benchmark_snapshot_id` (`sha256:...`) from which its empirical inputs were derived.

The snapshot identity is part of routing provenance and therefore changes when a different approved
snapshot is promoted.

### Ranking policy remains the runtime authority for ordering

The runtime continues to consume a strict, versioned ranking policy. Phase 11 extends that policy's
score provenance so empirical benchmark inputs can be distinguished from Phase 5 static inputs.

Promotion compiles approved benchmark evidence into explicit ranking inputs. Runtime ranking does not
import the Phase 10 benchmark runner or execute benchmark logic on the request path.

### Authorization and eligibility remain prior gates

Benchmark-derived scores are evaluated only after the PDP-authorized candidate set and normal gateway
eligibility gates are established.

Promotion cannot:

- add a model group to PDP authorization;
- add a deployment to the model registry;
- enable a disabled deployment;
- bypass provider/environment/data-classification restrictions;
- bypass capability/context/cost/latency checks;
- bypass runtime health or circuit-breaker state.

The benchmark-derived policy can only influence the ordering of deployments that are already eligible.

### Quality and availability evidence remain distinct

Phase 10 `provider_failure` observations do not become quality score zeroes. Promotion must preserve the
distinction between empirical task quality and provider availability/reliability evidence.

A snapshot lacking sufficient completed quality observations for a deployment/workload fails closed for
benchmark-derived quality promotion instead of inventing a neutral/default quality score.

### Manual override

Manual override is an explicit versioned configuration choice, never an in-memory mutation. An override
may replace a promoted benchmark-derived score input or select an earlier approved ranking artifact,
but it must carry provenance explaining that the effective value is operator-supplied.

Manual override cannot broaden PDP authorization or bypass eligibility.

### Rollback

Rollback means selecting a previously approved, immutable ranking-policy artifact and its referenced
benchmark snapshot. No benchmark file is edited in place.

Because both policy and snapshot identities are content/version bound, rollback is observable in
routing provenance and reversible by another explicit promotion.

### No automatic self-modification

Benchmark runs, score changes, provider telemetry, or observed runtime outcomes never write active
ranking configuration automatically in Phase 11.

Any future adaptive optimization requires a separate bounded/versioned/auditable decision and is
outside this ADR.

## Provenance requirements

A Phase 11 routing decision must expose enough metadata to identify:

- ranking policy version and digest;
- effective score-provenance mode;
- approved `benchmark_snapshot_id` when benchmark-derived evidence is active;
- manual-override provenance when an override is active;
- selected deployment and ranked alternatives/rejections as already defined by the routing contract.

Prompt/message content is not required for this provenance and remains outside default routing evidence.

## Consequences

Positive:

- changing an approved benchmark snapshot changes routing evidence deterministically;
- unapproved benchmark results have zero runtime authority;
- benchmark provenance is visible and auditable;
- rollback is a configuration operation rather than data mutation;
- manual overrides are explicit and attributable;
- Phase 10 benchmark code stays off the runtime request path;
- benchmark evidence cannot widen authorization.

Trade-offs:

- benchmark promotion requires an explicit operator-controlled step;
- a snapshot can exist without affecting runtime until promoted;
- ranking artifacts may duplicate normalized score values derived from the immutable snapshot, by design,
  so runtime does not depend directly on benchmark infrastructure.

## Rejected alternatives

### Automatically load the newest benchmark snapshot

Rejected because filesystem/order recency would become implicit routing authority and would violate the
manual promotion, rollback, and no-self-modification requirements.

### Let the benchmark runner update active ranking configuration

Rejected because evaluation code would gain production routing authority and benchmark execution could
silently change runtime behavior.

### Treat provider failure as task-quality failure

Rejected because rate limits, timeouts, and outages are availability evidence, not proof of poor model
quality.

### Allow benchmark evidence to reintroduce an ineligible deployment

Rejected because ranking is subordinate to PDP authorization and gateway eligibility.

### Import the repository-level `benchmarks/` package into the request path

Rejected because Phase 10 is an offline evaluation source root. Runtime should consume promoted,
validated ranking artifacts, not benchmark execution machinery.
