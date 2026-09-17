# ADR-0018: Exclusive, fenced HALF_OPEN admission

## Status

Proposed; implemented for review. Requires a coordinated rollout of health writers.

## Date

2026-09-16

## Context

Both `InMemoryHealthTracker` and `RedisDeploymentHealthTracker` currently admit every
caller in HALF_OPEN. Execution also calls `allow_request` before the candidate, before
the attempt and when deciding to retry. A boolean consumed by the first check would
therefore reject the very probe it admitted. Snapshots used for ranking must not consume
execution admission. Redis already provides shared state; this is a correction of that
existing adapter, not the introduction of another distributed subsystem.

Cancellation must not count as provider failure. An abandoned owner must not block a
deployment forever, and its late response must not close a newer probe's circuit.

## Decision

- Admission returns an immutable deployment/attempt/generation handle or no admission.
  Attempt IDs are locally generated, unrelated to caller-supplied request IDs. Rechecking
  the same live probe owner is idempotent and does not renew its lease. A completed or
  expired handle is never reused for another execution attempt.
- CLOSED admits concurrent calls. OPEN rejects until cooldown. HALF_OPEN atomically
  admits one owner, with a finite `probe_lease_seconds` (default 60 seconds). Snapshots
  may advance cooldown/expire ownership, but never claim a probe.
- Both execution paths acquire exactly once per concrete attempt, after deterministic
  preparation, and release in `finally`, including cancellation, disconnect and local
  exceptions. JSON bounds its probe await; streaming bounds each upstream read by the
  remaining probe lifetime and checks the deadline before accepting another event.
  No task-wide timeout spans an async-generator yield. Consumer backpressure consumes
  probe lifetime too. Probe reads and semantic publication also check the existing
  handle without acquiring/renewing ownership, fencing replica loss and suspension.
  This limit applies only to HALF_OPEN and is **not** an execution
  SLA or a reinterpretation of selection `max_latency_ms`.
- Success from a valid probe closes the circuit. A transient probe failure opens it
  again with a new cooldown. Permanent failure releases ownership without proving
  health or becoming transient; existing no-replay behavior remains unchanged.
  Cancellation, release and lease expiry leave HALF_OPEN available for a new owner.
- Generations fence circuit mutations from earlier CLOSED attempts and retired probes.
  Late CLOSED outcomes may update cumulative traffic counters, but cannot reset/open
  the current circuit. Retired probe outcomes are ignored, including success; execution
  must not publish a retired probe as successful. Uncorrelated health reports retain
  existing CLOSED counter behavior, but cannot close/open a recovering circuit.
- Redis performs each transition in one single-key Lua script, uses server `TIME` by
  default, and accepts an injected clock only for deterministic tests. Its key TTL
  must outlive cooldown and probe lifetime. Lease expiry is not key deletion.

## Alternatives considered

- A one-shot boolean: blocks the owner's repeated checks and cannot fence completion.
- An owner without expiry: stalls permanently after worker death.
- Lease expiry without generation fencing or execution bounds: admits a replacement
  while the old worker can still publish success or change the replacement's state.
- Heartbeat renewal: adds a background-task lifecycle and permits an indefinitely
  occupied probe. A bounded diagnostic probe is sufficient for this focused fix.

## Consequences

Long HALF_OPEN streams may terminate at the probe limit even if CLOSED streams would
continue. Lease expiry is recovery from missing completion, not evidence that a provider
returned a transient error. A lease cannot guarantee physical exclusion at a remote
provider after process suspension or network partition: only one valid local/shared
owner is admitted. Provider cancellation/closure is best effort; old handles are fenced.
All retries/fallback remain bounded and inside the already-ranked authorized group;
semantic output, external effects and continuation still prohibit replay.

## Security and privacy impact

Health only narrows PDP authorization. Admission IDs contain no credentials, prompts,
payloads or client identity and are not added to logs, traces or public contracts.
Redis errors propagate fail-closed; there is no silent local-health fallback.
401/403 classification and credential-binding availability are not changed here.

## Operational impact

Do not run old boolean-admission writers concurrently with this implementation: they
do not understand ownership and fencing. Drain/stop all old workers before enabling the
new writers against the existing keyspace. Existing counters and OPEN cooldown are
preserved; an ownerless existing HALF_OPEN key can be claimed normally. Use the same
policy/keyspace across replicas. Server time eliminates replica wall-clock skew from
production lease decisions; its availability is required. Normal CLOSED calls gain no
implicit total deadline. Cache hits acquire no probe and fabricate no health outcome.

## Follow-up

Verify concurrency, fencing, cancellation and expiry in the credential-free gate and
the opt-in Redis/Valkey matrix. Evaluate the probe lifetime under deployment-specific
streaming/backpressure conditions before rollout. Credential availability, cache
isolation and explicit total-execution deadlines remain separate increments.
