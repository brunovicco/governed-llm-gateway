# Routing

## Stage A — deterministic authorization

The Policy Model Router receives prompt-free policy metadata and returns one authorized logical model
group with decision provenance. It performs no inference.

The gateway validates/correlates the decision and intersects the model registry with the authorized
group. The resulting `AuthorizedCandidateSet` is the only source Phase 5 may rank.

## Stage B — deterministic operational selection

Phase 5 performs static/versioned eligibility and ranking inside the Phase 4 authorized candidate set.

Static eligibility is evaluated before score:

1. deployment enabled state;
2. trusted environment and data-classification allowance;
3. required text/vision/tool/structured-output capabilities;
4. sufficient context capacity;
5. static ranking evidence present;
6. versioned pricing evidence present;
7. estimated cost within projected cost ceiling;
8. expected latency within projected latency ceiling.

Unknown pricing is not free. Missing score input is not neutral. Either condition makes the deployment
ineligible.

## Stage C — runtime-health eligibility

Phase 6 introduces a separate mutable runtime-health snapshot. It never changes PDP authorization or
Phase 5 static scores.

When runtime-health filtering is active:

- open circuit → `circuit_breaker_open`;
- unhealthy deployment → `deployment_unhealthy`;
- missing deployment health → `deployment_unhealthy` with `runtime_health_unavailable`.

Half-open/degraded deployments remain eligible for recovery probing. The initial state is per process
and per concrete deployment.

## Stage D — bounded resilient execution

The resilience layer receives only the Phase 5 ranked sequence:

```text
selected → alternative 1 → alternative 2 → ...
```

Before execution, the bounded candidate sequence is checked against the PDP-authorized logical group.
A malformed out-of-group alternative fails before the first provider call.

Retry means another attempt against the same deployment. Fallback means moving to the next deployment
already in this ranked sequence. The resilience layer never re-enumerates the registry and never asks
the PDP for broader authorization after a provider failure.

Automatic replay is allowed only for normalized retryable:

- `rate_limit`;
- `timeout`;
- `unavailable`;
- `transport`.

Permanent provider/configuration failures stop automatic retry/fallback.

Retries use bounded exponential backoff, capped jitter, and bounded handling of provider
`Retry-After`. `RetryPolicy` explicitly limits attempts and fallback count.

`FallbackSafetyState` blocks automatic replay after observed provider output, an external side effect,
or opaque provider continuation/reasoning state.

## Circuit breaker

Per-deployment circuit lifecycle:

```text
CLOSED --transient threshold--> OPEN
OPEN   --cooldown-----------> HALF_OPEN
HALF_OPEN --success---------> CLOSED
HALF_OPEN --transient-------> OPEN
```

An open circuit blocks provider execution and can remove the deployment before ranking. Circuit state
is operational availability evidence, not authorization evidence.

## Authorization invariants

Routing/resilience fails closed when:

- registry digest differs from the registry bound to authorization;
- trusted workload/environment bindings disagree;
- current PMR 1.0 binding contains multiple authorized logical groups;
- any Phase 5 candidate falls outside PDP authorization;
- any bounded Phase 6 fallback candidate falls outside the authorized logical group.

Availability never creates a new candidate or model group.

## Score and tie-break

Each Phase 5 workload ranking policy contains five `Decimal` weights summing exactly to `1`: quality,
reliability, latency, cost, and availability. Eligible candidates are ordered by descending score then
ascending `deployment_id`.

Live Phase 6 health does not alter these weights/scores. Later evidence-driven ranking phases may
explicitly introduce approved telemetry/benchmark-derived inputs.

## Provenance

Selection evidence includes deterministic routing decision ID, PDP policy provenance, authorized
model group, registry digest, ranking-policy version/digest, static score snapshot, selected concrete
identities, alternatives, and rejection reasons.

Phase 6 additionally records:

- `fallback_sequence`: actual ordered concrete deployments attempted;
- metadata-only attempt evidence: deployment ID, attempt number, normalized failure category/status,
  bounded retry delay, latency, and outcome.

Same-deployment retries do not duplicate entries in `fallback_sequence`.

`score_snapshot_id` remains static configuration evidence and `benchmark_snapshot_id` remains unset
until later benchmark phases.

## Explainability

`POST /v1/route/explain` remains authenticated, metadata-only, and no-inference. Its core ranking
service can receive runtime-health snapshots so health-based ineligibility can be explained using the
same semantics, without giving the endpoint or health layer authorization authority.

## Later routing inputs

Phase 7 adds structured-output/tool normalization while preserving ADR-0007 replay safety. Phase 8
adds streaming/partial-output semantics. Phases 10–11 add approved evaluation/benchmark evidence.
