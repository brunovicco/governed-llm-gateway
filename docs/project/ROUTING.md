# Routing

## Stage A — deterministic authorization

The Policy Model Router receives prompt-free policy metadata and returns one authorized logical model
group with decision provenance. It performs no inference.

The gateway validates/correlates the decision and intersects the model registry with the authorized
group. The resulting `AuthorizedCandidateSet` is the only source Phase 5 may rank.

## Stage B — deterministic operational selection

Phase 5 performs static/versioned eligibility and ranking inside the Phase 4 authorized candidate set.

Eligibility is evaluated before score:

1. deployment enabled state;
2. trusted environment and data-classification allowance;
3. required text/vision/tool/structured-output/streaming capabilities;
4. sufficient context capacity;
5. static ranking evidence present;
6. versioned pricing evidence present;
7. estimated cost within projected cost ceiling;
8. expected latency within projected latency ceiling.

Unknown pricing is not free. Missing score input is not neutral. Either condition makes the deployment
ineligible.

## Stage C — runtime-health eligibility

Phase 6 introduces separate mutable runtime-health state. It never changes PDP authorization or Phase
5 static scores.

When runtime-health filtering is active:

- open circuit → `circuit_breaker_open`;
- unhealthy deployment → `deployment_unhealthy`;
- missing deployment health → fail closed as unavailable health evidence.

Half-open/degraded deployments may remain eligible for bounded recovery probing. State is initially per
process and per concrete deployment.

## Stage D — bounded resilient execution

The resilience layer receives only:

```text
selected → alternative 1 → alternative 2 → ...
```

Before execution, the bounded sequence is checked against the PDP-authorized logical group. A malformed
out-of-group alternative fails before the first provider call.

Retry means another attempt against the same deployment. Fallback means moving to the next deployment
already in this ranked sequence. The resilience layer never re-enumerates the registry and never asks
the PDP for broader authorization after provider failure.

Only normalized retryable `rate_limit`, `timeout`, `unavailable`, and `transport` failures can replay.
Permanent provider/configuration/semantic failures stop automatic retry/fallback.

`FallbackSafetyState` also blocks replay after observed provider output, external side effects, or
opaque provider continuation/reasoning state.

## Stage E — governed streaming execution

A streaming request sets the ordinary capability requirement `Capability.STREAMING`, so Phase 5 can
only select authorized deployments whose registry record advertises streaming.

The selected adapter/API family must separately prove `native_streaming` and final `streaming_usage`
support. These flags are execution compatibility checks and cannot add a candidate.

`POST /v1/generate` performs authentication, PDP authorization, health snapshot, ranking, and eligible
streaming-candidate checks before starting SSE.

During provider execution:

- provider-native start alone is not semantic output;
- retry/fallback may occur only before semantic output;
- first content/tool-call event crosses the replay boundary;
- after that boundary, any provider failure terminates the public stream with
  `response.failed(partial=true, retryable=false)`;
- no provider/model switch occurs after visible output;
- final usage must appear exactly once before successful completion.

This prevents a public response from becoming a hybrid of multiple provider executions.

Client cancellation/disconnect closes the execution generator and upstream provider stream rather than
triggering a new routing decision.

## Circuit breaker

Per-deployment circuit lifecycle:

```text
CLOSED --transient threshold--> OPEN
OPEN   --cooldown-----------> HALF_OPEN
HALF_OPEN --success---------> CLOSED
HALF_OPEN --transient-------> OPEN
```

An open circuit blocks provider execution and can remove a deployment before ranking. Circuit state is
availability evidence, not authorization evidence.

## Authorization invariants

Routing/execution fails closed when:

- registry digest differs from the registry bound to authorization;
- trusted workload/environment bindings disagree;
- current PMR 1.0 binding contains multiple authorized logical groups;
- a Phase 5 candidate falls outside PDP authorization;
- a bounded Phase 6/8 execution candidate falls outside the authorized logical group;
- a streaming candidate lacks required registry or verified adapter streaming capability.

Availability and streaming never create a new candidate or model group.

## Score and tie-break

Each Phase 5 workload ranking policy contains five `Decimal` weights summing exactly to `1`: quality,
reliability, latency, cost, and availability. Eligible candidates are ordered by descending score then
ascending `deployment_id`.

Live health/stream behavior does not mutate these static scores. Later evidence-driven phases may
explicitly introduce approved benchmark/telemetry-derived inputs.

## Provenance

Selection evidence includes deterministic routing decision ID, PDP policy provenance, authorized model
group, registry digest, ranking-policy version/digest, static score snapshot, selected concrete
identities, alternatives, and rejection reasons.

Phase 6/8 execution additionally records actual ordered deployment progression in
`fallback_sequence`. Same-deployment retries are represented separately in attempt evidence rather
than duplicating fallback entries.

Streaming response content is not added to routing provenance. `score_snapshot_id` remains static
configuration evidence and `benchmark_snapshot_id` remains unset until later benchmark phases.

## Explainability

`POST /v1/route/explain` remains authenticated, metadata-only, and no-inference. Runtime health can
participate in the same eligibility semantics without giving the health/explain layer authorization
authority.

## Current and later routing inputs

Phase 7 structured-output/tool normalization and Phase 8 streaming both preserve the same
authorization/ranking boundary. Phase 9 adds metadata-only OpenTelemetry. Phases 10–11 may add approved
evaluation/benchmark evidence without changing PDP authority.
