# ADR-0024 — Explicit local execution deadline

## Status

Accepted design on 2026-09-18; implementation under review.

## Date

2026-09-18

## Context

ADR-0007 and ADR-0011 deliberately distinguish per-attempt provider timeouts from the
`max_latency_ms` selection constraint. ADR-0017 freezes every retained authorized provider request
before HTTP 200; ADR-0018 bounds HALF_OPEN probes without timing out a task across an external
async-generator yield. None of these bounds is a total normal execution budget.

## Decision

- Add deployment-owned `execution_timeout_ms`, optional and off by default. Accept plain integers
  from 1 through 86,400,000 ms (24 hours); reject booleans, coercion and out-of-range input before
  secret materialization. The CLI flag is `--execution-timeout-ms`. No dependency/service is added.
- Start one process-local monotonic budget immediately after canonical request validation in the
  generation coordinator, before trusted-context resolution, health snapshots and PDP authorization.
  Both operational and complexity modes carry that exact budget into immutable streaming preparation
  and execution. Direct streaming preparation starts its own budget; direct already-ranked JSON
  execution starts at executor entry unless an earlier budget is explicitly supplied.
- Cover preparation, cache I/O, health/control awaits, provider execution/reads, retry, fallback and
  backoff. Delay between preparation and iterator consumption, and consumer backpressure, consume
  the same budget. Neither a delta nor a retry renews it. Check before accepting/publishing new
  output and before a provider success report; discard late provider results.
- Leave request schema 1.0, caller request limits, PDP projection, authorization expiry, provider
  per-attempt timeout and HALF_OPEN lease semantics unchanged. Do not rebuild prepared provider
  payloads/headers or widen the ranked authorized set. No authorization cache or business tool
  execution is introduced.
- Expiry is the local, terminal, non-retryable `execution_deadline_exceeded`, not a retryable
  `ProviderError(TIMEOUT)`. Before response commitment return sanitized HTTP 504. After commitment,
  emit canonical `response.failed` with `retryable=false`; `partial` describes semantic events
  actually exposed, not provider-native start or an internal buffered delta. Protocol ingresses
  retain their own error envelopes. Expiry itself creates no provider failure/success, credential
  quarantine, fabricated zero usage, cost settlement or new authorization consumption.
- Bound each owned stream read, never an async-generator timeout scope spanning public yields.
  Cancellation/disconnect propagate and execution/upstream ownership is closed before exposing the
  deadline failure. API response ownership additionally bounds cooperative blocked downstream
  delivery using a finite, one-second terminal-delivery grace and a separate one-second best-effort
  body-cleanup budget. Enabled executions also bound health-handle release to one second; failure
  preserves expiry/cancellation and the existing fenced finite lease recovers ownership. These
  cleanup bounds never authorize
  another provider attempt or semantic event. A disconnected/blocked client is not guaranteed to
  receive a terminal frame. Direct iterator consumers must resume or explicitly close their iterator.

## Alternatives considered

- Reuse `max_latency_ms`: rejected; it would silently change selection semantics.
- Restart a timer per attempt/read: rejected; retries or continuous output would evade the budget.
- Rebuild provider timeout inputs during retry: rejected; it breaks immutable preflight continuity.
- Treat expiry as provider timeout: rejected; it invents provider health failure and permits replay.
- Scope a task timeout across public generator yields: rejected; it can cancel an unrelated caller
  task and violates ADR-0018 ownership.
- Add an external timer/service or new HTTP client: unnecessary for this local opt-in control.

## Consequences

An enabled request may fail before or after partial output despite healthy authorized deployments.
Per-attempt transport bounds and probe leases may expire earlier. Genuine provider outcomes recorded
before expiry remain genuine even if later cache/delivery work consumes the remaining budget;
they do not establish successful client delivery. No successful terminal event is accepted after
expiry. Disabled configuration preserves existing execution behavior.

## Security and privacy impact

The timer only narrows execution: `Gateway allowed set ⊆ PDP authorized set`. Permanent failures and
post-semantic replay rules are unchanged. No new caller authority, credential access, payload logging,
raw exception body, public clock timestamp or benchmark/ranking evidence is added.

## Operational impact

This is a cooperative local execution admission/output bound, not a physical provider cancellation,
hard billing ceiling or end-to-end HTTP SLA. It excludes body upload/parsing before coordinator entry,
external tool work, network transit and separately bounded cleanup. Synchronous Python preparation
cannot be preempted but is checked on return. Cancelling an `asyncio.to_thread` await does not stop
an already-running JSON/PDP worker; its existing transport timeout remains in force and late results
cannot start new gateway work. Event-loop starvation, suspended processes and cancellation-resistant
adapters can delay termination; remote effects cannot be rolled back. Provider credential production
activation remains separately deferred.

## Follow-up

Use credential-free boundary, stalled-await, retry/backoff, fallback, cache, partial-output,
HALF_OPEN, cancellation, protocol and configuration regressions, then the frozen Phase 0 and complete
quality gates. A real credential-backed provider/PDP cancellation proof requires separate explicit
authorization; default CI does not supply one. PDP connection pooling and operational SpendGuard
reservation/settlement remain independent increments.
