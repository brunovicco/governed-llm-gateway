# ADR-0007 — Fallback Safety Semantics

Status: Accepted  
Date: 2026-08-31

## Context

Phase 4 establishes the authorization boundary and Phase 5 produces an ordered list of concrete,
eligible deployments inside that authorization:

`Gateway allowed set ⊆ Policy Router authorized set`

Phase 6 adds runtime resilience. Retry and fallback can improve availability, but replaying an LLM
request after model output, an external side effect, or provider-specific opaque continuation state
can duplicate actions or change semantics. Availability must never become a mechanism for widening
authorization.

The normative roadmap distinguishes:

- retry: same concrete deployment;
- fallback: a different eligible deployment;
- transient failures: 408/429/5xx/network timeout/connection failure;
- permanent validation/authorization failures: no automatic retry;
- external side effect executed: no cross-provider fallback;
- opaque provider reasoning state: no cross-provider continuation without an explicit replay model.

## Decision

### 1. Retry and fallback are separate operations

Retry always targets the same concrete deployment.

Fallback may move only to the next deployment already present in the Phase 5 ranked candidate list.
The resilience layer never re-enumerates the model registry and never calls the PDP to obtain a wider
set after an execution failure.

Every candidate in the bounded fallback sequence is pre-validated against the PDP-authorized logical
model group before the first provider call. A malformed ranking decision therefore fails before any
partial execution.

### 2. Only transient provider failures are automatically replayable

The initial transient set is:

- `rate_limit`;
- `timeout`;
- `unavailable`;
- `transport`.

The provider adapter must also mark the error `retryable=True`.

Authentication, invalid request, invalid response, unknown/permanent errors, policy denial, registry
or ranking invariant violations are not automatically retried or used to trigger fallback.

### 3. Retry is bounded

`RetryPolicy` defines:

- maximum attempts per deployment;
- maximum number of fallback deployments;
- base backoff;
- maximum backoff;
- jitter ratio.

Backoff is exponential and bounded. Jitter is derived deterministically from request ID, deployment ID
and attempt number. This avoids synchronized retries across requests while keeping one execution's
retry schedule reconstructable in tests/evidence.

A provider `Retry-After` value is respected as a floor subject to the gateway's configured maximum
backoff. The provider cannot force an unbounded sleep.

### 4. Replay safety is explicit

`FallbackSafetyState` represents whether automatic replay remains safe.

Automatic retry/fallback is blocked when any of the following is true:

- provider/model output has already been observed;
- an external side effect has already executed;
- opaque provider reasoning/continuation state has been established.

Phase 6 is text-generation only. Later tool/streaming phases must update this state at their own
boundaries rather than silently assuming replay is safe.

The initial implementation is deliberately more conservative than attempting to infer idempotency
from prompt content.

### 5. Circuit breaker is per concrete deployment

The initial circuit breaker is per process and per deployment.

States:

`CLOSED → OPEN → HALF_OPEN → CLOSED`

Transient failures increment deployment-local failure state. Reaching the configured threshold opens
the circuit. After cooldown, the deployment becomes half-open and may receive a probe. A successful
probe closes/reset the circuit; a transient half-open failure opens it again.

A deployment with an open circuit is operationally ineligible and is represented by the existing
`circuit_breaker_open` rejection reason.

Shared Redis-backed breaker state is deferred until there is evidence it is required; it is not a
Phase 6 prerequisite.

### 6. Runtime health remains distinct from static ranking evidence

Phase 5's `score_snapshot_id` and static availability/reliability dimensions are versioned planning
inputs. Phase 6 runtime health is mutable operational state.

Runtime health may remove a candidate from eligibility, but Phase 6 does not feed recent health back
into the weighted Phase 5 score. Benchmark-driven or telemetry-driven score updates belong to later
phases.

When runtime-health filtering is active, a missing health snapshot fails closed for that deployment.

### 7. Provenance records actual deployment progression

On successful resilient execution, `RoutingProvenance.fallback_sequence` records the ordered concrete
deployments actually attempted. Same-deployment retries are represented separately as execution
attempt evidence rather than duplicating the deployment in `fallback_sequence`.

Execution-attempt evidence contains only metadata such as deployment ID, attempt number, normalized
provider error category/status, bounded retry delay, latency, and outcome. It does not contain prompt,
completion, raw provider error body, API key, or authorization header.

## Consequences

Positive:

- fallback cannot broaden PDP authorization;
- malformed fallback candidates fail before provider execution;
- retry storms are bounded;
- permanent failures are not replayed across providers;
- side-effect/continuation boundaries are explicit and testable;
- open circuits can remove a deployment from eligibility before provider execution;
- runtime availability evidence remains distinct from static ranking/benchmark evidence.

Trade-offs:

- conservative replay blocking can reduce availability after partial execution;
- per-process circuit state is not shared across replicas;
- deterministic jitter is not intended as cryptographic randomness;
- the initial health model is execution-outcome based rather than a complete active-probe system.

## Rejected alternatives

### Re-run authorization to obtain a broader group after failure

Rejected because availability would be allowed to widen authorization.

### Fall back to any registry deployment with the required capability

Rejected because registry membership is not authorization.

### Retry every provider failure

Rejected because permanent validation/authentication failures are not transient and replay can waste
budget or hide configuration defects.

### Infer side-effect safety from prompt text

Rejected because prompt classification is not a reliable idempotency boundary.

### Treat missing health as healthy

Rejected once runtime-health filtering is active because missing operational state must not silently
increase eligibility.

### Put live health directly into the Phase 5 static score

Rejected because it would blur static/versioned ranking evidence with mutable runtime state and pull
telemetry-driven ranking forward.
