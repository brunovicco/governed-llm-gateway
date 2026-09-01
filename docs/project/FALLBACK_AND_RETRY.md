# Fallback and Retry

Phase 6 implements runtime resilience without changing the authorization decision established by the
Policy Model Router.

Core invariant:

`Gateway allowed set ⊆ Policy Router authorized set`

## Retry versus fallback

Retry and fallback are different operations:

- **retry**: another attempt against the same concrete deployment;
- **fallback**: move to a different deployment already present in the Phase 5 ranked candidate list.

The resilience layer never re-enumerates the global registry and never asks the PDP for a wider group
after an execution failure. The bounded `selected + alternatives` sequence is validated against the
PDP-authorized logical model group before the first provider call.

## Transient failures

Automatic retry/fallback is limited to normalized provider failures that are both `retryable=True`
and classified as:

- `rate_limit`;
- `timeout`;
- `unavailable`;
- `transport`.

Permanent validation/authentication/authorization/configuration failures do not trigger automatic
replay. Missing provider-adapter configuration fails closed rather than skipping silently to another
provider.

## Bounded retry

`RetryPolicy` controls:

- `max_attempts_per_deployment`;
- `max_fallbacks`;
- base backoff;
- maximum backoff;
- jitter ratio.

Backoff is exponential and capped. Jitter is deterministically derived from request ID, deployment ID
and attempt number so the schedule remains reconstructable. A provider `Retry-After` value is treated
as a requested floor but is still capped by the gateway maximum delay.

Provider timeout remains a per-attempt execution bound in Phase 6. The gateway does not silently
reinterpret the Phase 4/5 `max_latency_ms` selection constraint as a total retry deadline. A future
total execution budget requires an explicit contract rather than an implicit semantic change.

## Replay safety boundary

`FallbackSafetyState` blocks automatic retry/fallback after any of these conditions:

- provider/model output has already been observed;
- an external side effect has executed;
- opaque provider reasoning/continuation state has been established.

Phase 6 is text-generation only. Later structured-output, tool and streaming phases must update this
state at their own execution boundaries instead of assuming replay is safe.

## Circuit breaker and runtime health

The initial breaker is per concrete deployment and per process:

`CLOSED → OPEN → HALF_OPEN → CLOSED`

Transient failures increment deployment-local health counters. Reaching the configured consecutive
failure threshold opens the circuit. After cooldown the deployment becomes half-open; a successful
probe closes/reset the circuit and a transient half-open failure reopens it.

Runtime health is distinct from Phase 5 static ranking evidence. When runtime-health filtering is
active:

- `OPEN` circuit → `circuit_breaker_open`;
- `UNHEALTHY` deployment → `deployment_unhealthy`;
- missing health snapshot → fail closed as `deployment_unhealthy` with
  `runtime_health_unavailable`.

`HALF_OPEN`/degraded state remains eligible for a probe. Shared Redis-backed breaker state and richer
active health probing are intentionally deferred until operational evidence shows they are needed.

## Provenance

Successful resilient execution updates `RoutingProvenance.fallback_sequence` with the ordered concrete
deployments actually attempted. Same-deployment retries are represented separately by metadata-only
`ExecutionAttempt` evidence.

Execution attempt evidence may include deployment ID, attempt number, normalized error code/status,
bounded retry delay, latency, and outcome. It must not include prompts, completions, raw provider error
bodies, provider/PDP credentials, Authorization headers, or arbitrary customer payloads.

## Phase 6 acceptance evidence

Contract tests verify:

- HTTP 429-style rate-limit failure retries the same deployment before fallback;
- timeout retry updates deployment health counters;
- 5xx/unavailable and transport failures may fall back to the next authorized ranked deployment;
- permanent failures perform zero retry and zero fallback;
- retry attempt count and fallback count are bounded exactly;
- a malformed fallback candidate outside the authorized model group fails before any provider call;
- missing provider adapter fails closed without fallback;
- side-effect/output/opaque-state boundaries block automatic replay;
- open circuit prevents provider calls and removes the deployment from ranking eligibility;
- cooldown moves the breaker to half-open, success closes it, and transient half-open failure reopens
  it;
- active runtime-health filtering treats a missing deployment snapshot as ineligible;
- identical request/deployment/policy inputs reproduce the same retry-delay sequence.

See ADR-0007 for the architectural decision and rejected alternatives.
