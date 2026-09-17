# ADR-0019 — Versioned provider credential-binding availability

## Status

Proposed for review; **not implemented or accepted**. This record changes no serving behavior,
provider error code, configuration schema, secret resolver, or retry/fallback contract. Acceptance
and separately verified implementation increments are required before enabling the proposed feature.
ADR-0018 is reserved by the separate HALF_OPEN correction; this proposal does not depend on that
unpublished implementation or copy its changes.

## Date

2026-09-16

## Context

The inspected Gateway baseline is `origin/main@e482f6b4c7e59648171d26e382e89d71f59e4d05`.
The following are implementation facts, not live-provider or production claims:

- `adapters/provider_common.py::require_success_payload` maps HTTP 401 **and** 403 to permanent
  `ProviderErrorCode.AUTHENTICATION`. `streaming_common.py::open_provider_sse` uses that normalizer
  for failed stream openings. Non-success bodies are not retained as structured diagnostic evidence.
- `application/provider.py::is_transient_provider_error` excludes authentication. Resilient JSON and
  streaming execution do not retry/fall back on it. The transient circuit breaker is not a
  credential-validity registry; a CLOSED circuit after an authentication failure is consistent with
  [ADR-0007](ADR-0007-fallback-safety-semantics.md), not proof that credentials were accepted.
- Provider runtime bindings are keyed by `(provider, api_family)`. Several deployments can share
  that adapter and its credential; the current schema does not describe a shared credential identity
  across different adapter bindings or an immutable secret-material version.
- `ProviderSecretResolver.resolve(reference)` returns only a string. `build_static_provider_resolver`
  resolves credentials once and constructs adapters holding that value. `process_bootstrap.py`
  materializes that resolver after secret-free artifact validation. There is no versioned provider
  credential refresh/publication lifecycle today.
- [ADR-0017](ADR-0017-deterministic-streaming-preflight.md) freezes provider-native prepared stream
  state before HTTP 200, including credential-bearing transport headers. A later rotation cannot
  safely replace headers in that plan or rebuild it during retry.

An offline reproduction using the actual runtime factory, JSON adapter, execution service, and
in-memory health tracker, with an injected synthetic HTTP transport, exercised both 401 and 403.
For each status, two executions produced two permanent authentication outcomes, one provider attempt
per execution, no fallback, and a CLOSED circuit. Replacing the synthetic resolver's material after
bootstrap left its read count at one and the second attempt still presented the first material.
Existing contract tests also cover shared deployment bindings, permanent failures, transport
sanitization, partial output, and explicit continuation. These observations establish the gap; they
do not establish that any real key was revoked or that every 403 has the same cause.

## Decision

### 1. Add an independent, narrowing availability plane

Propose an explicit credential-binding availability plane, not a transient health condition. The
enforcement intersection remains:

```text
PDP-authorized deployments
  ∩ registry/capability/classification eligibility
  ∩ credential-binding availability
  ∩ runtime health and existing deterministic ranking requirements
```

Each plane may remove candidates only. Neither secret presence, recovery, a successful provider
request, nor a rotation can grant a group/model/capability/data allowance or create ranking evidence.
Do not encode credential rejection as a timeout/5xx, open the transient breaker to represent it, or
let a health success clear credential quarantine. Credential recovery also does not reset health.

### 2. Distinguish an adapter binding, a credential binding, and its material

A deployment-owned opaque `credential_binding_id` identifies one declared authentication scope.
That scope includes the relevant provider principal/realm and approved endpoint/API-family bindings.
One adapter binding must map to exactly one such identity; multiple deployments inherit the identity
of their adapter. Different adapter bindings may share it only when configuration explicitly declares
equivalent authentication scope and the credential authority validates coherent material/version
mapping. Equal secret strings or equal reference text alone do not establish that equivalence.

The trusted credential authority publishes an immutable generation token containing:

- the opaque binding ID;
- a monotonically increasing binding epoch;
- an opaque, authority-issued material identity;
- the exact backend secret version and secret-free runtime/authentication-scope provenance needed
  to verify that the constructed adapter belongs to this token.

The epoch changes on an intentional activation, not on process restart, request ID, local UUID,
unrelated config-version change, or a change in the registry. The material identity must remain the
same for unchanged secret material, including an alias or backend version that republishes the same
value. No public hash of a credential is introduced. Confidential equality/history reconciliation
belongs to the trusted credential authority, not consumers, logs, registry data, or ranking evidence.
An authority unable to establish this binding/version/material relationship must fail closed for
the opted-in feature; a plain string-only environment resolver cannot manufacture the guarantee.

Quarantine is retained for the rejected `(credential_binding_id, material_identity)`, not just the
latest epoch. Restarting, relabeling unchanged material, or rolling back to a known rejected material
therefore cannot restore availability. Tombstone retention must cover all activatable versions;
retiring history requires first making those versions impossible to activate.

### 3. Separate credential rejection from an ambiguous access denial

Keep all current authentication/access-denial outcomes permanent and non-retryable. Add a separate
internal, bounded credential-rejection fact only where an API-family-specific contract establishes
that the presented generation was rejected for its declared authentication scope.

- A reviewed classifier may use HTTP 401 as evidence that **this binding/material was rejected**
  at its configured provider authentication boundary. This is not proof of global key revocation.
  Proxy/custom-endpoint semantics require their own verified classification; a generic compatibility
  label is insufficient. Unreviewed 401 semantics terminate the request without global quarantine.
- HTTP 403 alone is ambiguous: model/resource permission, policy, region, endpoint, or other access
  conditions may differ within a provider. It must not quarantine shared material by status alone.
- An explicit invalid/revoked-credential provider reason may narrow the binding only after a separate
  reviewed, bounded allowlist classifier supplies that fact. The existing transports do not expose
  such error-body evidence; this proposal does not add arbitrary error-body parsing or logging.
- In-stream errors likewise need explicit classification. A malformed response, exhausted quota,
  unknown error, local exception, or cancellation is not credential-rejection evidence.

The observation must name the generation actually used by the prepared attempt, never whichever
generation happens to be current when its error arrives. Updating availability must not depend on
best-effort telemetry. If recording quarantine fails, the triggering execution still terminates and
that worker denies further admissions for the affected generation until authoritative state can be
reconciled; it must not silently continue with a healthy local default. Other in-flight replicas may
have been admitted before the observation and cannot be claimed physically stopped.

### 4. Make recovery owned and generation-fenced

Proposed state vocabulary and admission behavior:

| State for the active token | Admission / transition |
| --- | --- |
| `PENDING_VALIDATION` | Atomically claim one bounded validation owner across the binding, then enter `VALIDATING` |
| `VALIDATING` | Only that owner can execute its already-authorized concrete attempt; other requests are narrowed out |
| `AVAILABLE` | Concurrent governed attempts allowed while local material matches the authoritative token |
| `QUARANTINED` | Reject all deployments sharing that binding/material; no timer/restart/health success clears it |

New, genuinely different material enters `PENDING_VALIDATION` after version-bound resolution and
local deterministic adapter construction. Loading or syntactically accepting a secret is not proof
that a provider accepted it. Validation uses one ordinary, freshly authorized and ranked request;
there is no out-of-group model forcing, unauthenticated background inference, or probe that executes
business tools. No new benchmark or ranking artifact is produced. Until that request exists, the
binding remains pending rather than being declared valid.

The validation owner has a locally generated attempt ID, finite deployment-configured lease, and
generation fence. Idempotent owner rechecks cannot renew the lease. A complete, locally validated
provider success from the current live owner promotes the token to `AVAILABLE`; an initial 2xx,
partial delta, cache hit, or late completion is insufficient. Proven binding rejection quarantines
its material. An ambiguous/permanent non-credential error, transient error, local failure,
cancellation, disconnect, or expiry releases validation ownership without proving recovery. Existing
health/retry/backoff bounds continue to apply independently; no new same-request replay is granted.

Shared transitions are atomic compare-and-set operations on the exact token/owner. Only the current
live validation owner can promote its token; an ordinary concurrent success cannot undo quarantine.
Successful promotion returns a fenced completion receipt before retiring validation ownership, so
publication can validate that receipt/current token without treating its own completed lease as a
new owner. A late outcome cannot promote, reset, or replace the current token. Valid rejection
evidence for a retired token may retain quarantine on **its own material**, including preventing a
later rollback; it cannot quarantine a genuinely different newer material. If the same material was
reactivated before that late rejection arrived, its quarantine must also block that active epoch:
epoch relabeling is not recovery. Duplicate reports are idempotent. Lease expiry removes ownership,
never quarantine/history.

The validation lease needs its own explicit finite configuration and deployment evaluation; it is
not a reinterpretation of `max_latency_ms` or a total execution SLA. If a health recovery probe is
also required, execution must own both admissions for that same attempt and release both in finally.
Rank/snapshot reads cannot claim either probe. Do not reuse the deployment-health key or its TTL.

### 5. Rotate centrally without rewriting an execution plan

Propose a versioned secret-resolution adapter and a separately owned refresh lifecycle. Consumers
continue to hold Gateway credentials only. A trusted deployment controller publishes the current
binding token and version locator; each Gateway worker fetches **that exact** backend version,
validates the secret-free config/cross-artifact mapping first, and builds an immutable local adapter
bundle before atomically swapping its local reference. This is not a request-driven attempt to
discover arbitrary credentials or an endpoint/config auto-discovery feature.

Missing versions, failed resolution, mismatched material metadata, unavailable shared state, or a
stale local bundle make the binding unavailable on that replica. It may not execute the old bundle
while waiting for refresh. Rotation is recovery infrastructure with sanitized errors, bounded
timeouts, explicit start/stop ownership, and no import-time tasks or secret reads. Central publication
and worker refresh do not redeploy consumers; this capability is proposed, **not present today**.

All deterministic prepared headers/payloads still belong to the captured token. Preparation remains
synchronous and provider-I/O-free as in ADR-0017; secret refresh is outside it. Runtime checks the
shared token and availability before every concrete attempt, and checks its captured fence before
accepting a result or publishing another semantic stream event/completion. An epoch change or
quarantine invalidates the old attempt locally; upstream closure is best effort. Never replace its
credential, rebuild its payload, or splice another generation's response into the same plan.

Each check/transition has an explicit linearization point, not an atomic transaction with remote
provider execution or network delivery. Rotation, suspension, and partitions can leave old provider
calls physically running; already-delivered content cannot be revoked. The design guarantees bounded
valid local/shared admission and fenced subsequent decisions, not instantaneous global cancellation.
Per-event control reads add cost/availability coupling that must be measured before rollout.

### 6. Do not add permanent-error fallback

A credential-rejected attempt, a stale/mismatched token, or unavailable credential control terminates
the current execution without retry/fallback—even before semantic output. If it races with an
already-prepared candidate, do not silently skip it as though the error were transient. After output,
external effects, or opaque continuation, existing terminal partial/no-replay semantics remain.
Tool-result continuation remains single-candidate/single-attempt.

A **new** request may select another deployment after normal authentication, fresh PDP authorization,
credential-availability narrowing, and deterministic ranking within the same single authorized group.
It cannot reuse a spent Governance/PDP envelope or bypass expiry, revocation, or kill switch. If all
candidates are removed, return a sanitized unavailable outcome, not a broader group or a config
bypass. A future proposal to replay permanent failures requires a separate amendment to ADR-0007;
this ADR explicitly does not make that amendment.

Credential filtering must precede cache lookup too. Validation owners bypass response caching because
a cached answer cannot validate new material. An AVAILABLE binding may use the existing cache only
under its current authenticated authorization/ranking/selection checks; it must not acquire health
success or credential-recovery evidence from a hit. This record changes no cache identity schema.

## Alternatives considered

- Treat 401/403 as transient: rejected; changes replay authority and confuses access policy with
  availability. The triggering permanent failure remains terminal.
- Open/reset the circuit on credential rejection/rotation: rejected; deployments may share material
  and transient health has a different lifecycle. A health probe cannot validate a missing version.
- Quarantine every 403 globally: rejected; the current category loses the evidence required to infer
  credential invalidity, and unrelated deployments could lose availability incorrectly.
- Block only the first concrete deployment: insufficient for several deployments/replicas sharing
  the same authentication binding.
- Identify material by a public key hash, raw secret/reference, process UUID, or config digest:
  rejected; privacy, restart, and cross-replica/version consistency fail in different ways.
- Resume after a TTL or an unchecked restart: rejected; it republishes known rejected material.
- Resolve “latest” on each retry or rewrite prepared headers: rejected; violates immutable preflight,
  token attribution, and replay boundaries.
- Process-local quarantine only: useful as a test/single-worker implementation, but not a fleet
  guarantee. Shared mode must never silently fall back to process-local permissive state.
- Have clients rotate provider credentials or execute probes: rejected; it leaks deployment concerns
  into consumers and can evade the normal PDP/ranking path.

## Consequences

The proposal bounds repeated use of known rejected material across its declared binding and defines
recovery without redeploying consumers. It adds a trusted version/material authority and refresh
lifecycle absent from today's runtime, not merely an `if status == 401` patch. A new key may remain
pending if no eligible, governed validation request arrives. False rejection classification can
reduce availability; uncertain provider contracts must not receive a classifier by assumption.
Shared-control/secret-version outages fail closed in enabled mode. Concurrent admitted requests and
remote cancellation remain bounded non-claims rather than an assertion of zero invalid provider calls.

## Security and privacy impact

Provider credentials remain in adapters/secret infrastructure. Core generation/admission objects
carry opaque metadata only. Credential values, public secret hashes, secret references, version
locators, material identities, prepared headers, provider bodies, and raw backend errors must not be
exported through public contracts, logs/traces, Operations, or metric labels. Allow only sanitized
state/outcome categories and existing descriptive provider/deployment evidence; do not introduce
unbounded binding/version labels. [ADR-0008](ADR-0008-metadata-only-telemetry.md) still governs evidence.

The deployment controller alone advances tokens; authenticated worker observations can narrow the
exact generation they used. Shared storage needs separately scoped ACLs, validated bounded records,
secure transport, and a durable/quarantine-preserving recovery procedure. State loss must produce
unknown/deny until trusted reconciliation, not a new AVAILABLE default. Arbitrary callers cannot
publish a generation, choose a backend version, claim recovery, or clear quarantine.

## Operational impact

Default serving behavior stays unchanged until explicit feature activation. Activation requires a
versioned configuration/secret-resolution contract, a trusted publisher, complete scope mapping,
refresh lifecycle, and the selected deployment's shared-store durability/recovery guarantees. Redis/
Valkey may implement the application port, but existing health TTLs and Redis atomicity alone do not
establish durable quarantine or consistency after failover. Do not claim that an acknowledged write
can never be lost without proving the chosen operational model.

Coordinate/drain workers that cannot enforce the new generation contract before enabling it; mixed
legacy/static workers cannot satisfy fleet quarantine. Preserve existing registry/ranking artifacts,
PDP policy, classification/capability ceilings, health history, and approved benchmark evidence.
Schema 1.0 remains closed: new metadata cannot be inserted as ignored fields. Publish a separately
reviewed versioned loader/provenance migration. Never reset quarantine to roll back; keep compatible
enforcement or disable/drain serving until the control state is reconciled.

## Follow-up

### Implementation slices after design acceptance

1. Add provider-neutral generation/state/admission contracts in `gateway-core/domain` and ports in
   `application`; no provider SDK, FastAPI, telemetry, or raw secret types in domain/contracts.
2. Add a versioned secret-result boundary, explicit binding/scope mapping, closed versioned artifact,
   and deterministic provenance in `adapters/provider_runtime.py` / `provider_runtime_json.py`.
   Version-bound material identity needs a trusted publisher/backend adapter, not inference from
   today's environment string. Choose/verify that operational adapter before fleet activation.
3. Add process-local conformance fixtures and an atomic shared availability adapter, independent of
   `health_redis.py`; implement leases, quarantine retention, stale-token fencing, and fail-closed
   missing/corrupt/unavailable control state. Scope publisher and worker mutation rights separately.
4. Integrate pre-ranking filtering, pure preflight token capture, per-attempt/publication checks,
   and finally cleanup into both executors. Wire a bounded, explicitly owned refresh lifecycle in
   Gateway composition/bootstrap. Do not amend PDP, retry, group fallback, tool execution, or cache
   eligibility to make validation easier.
5. Add only reviewed API-family rejection facts. Initial compatibility/provider semantics must be
   evidenced before enabling quarantine; 403-only and arbitrary in-stream failures remain ambiguous.

### Required test and rollout evidence

- Both execution paths: proven rejection terminates once, zero retry/fallback; unknown 401/403,
  resource denial, quota, malformed errors, and partial/tool/opaque continuation do not grant replay.
- Shared deployments/bindings: quarantine propagates to the declared authentication scope only;
  different material/principals/realms remain independent. Equal strings/references are not implicit
  global grouping. Missing scope mapping/version metadata fails before secret/provider I/O.
- Rotation: same material after restart/alias/new backend version stays quarantined; distinct
  centrally published material validates without consumer redeploy. Failed/mismatched version fetch
  never executes the old adapter, and returned raw backend details never enter public evidence.
- Concurrency: one validation owner per binding across replicas, idempotent rechecks, bounded expiry,
  cancellation/abandonment recovery, duplicate reports, late success/failure, retired-material
  rejection, epoch races, rollback, and simultaneous health/credential admission cleanup.
- Preflight: prepared headers remain immutable; rotation between preparation/attempt/publication
  never silently replaces the credential, selects a new group, reuses a spent envelope, or publishes
  an old completion as the new generation. Cache hits cannot validate or restore credentials.
- Control failure: missing/corrupt records, ACL denial, outage, controller failure, and state loss/
  failover preserve unknown/deny and quarantine on reconciliation. No permissive local fallback.
- Privacy: synthetic secrets/references/version locators/provider bodies/backend exceptions absent
  from errors, traces, logs, metrics, Operations and repr; exact allowlisted metadata only.
- Measure control-read/refresh overhead and choose bounded validation/refresh timeouts before live
  rollout. Live checks must be separately authorized, use existing configured credentials, preserve
  governed selection, and produce no new benchmark/ranking artifacts by default.

Verification for this documentation-only proposal: focused existing provider/runtime/resilience/
streaming regressions, `uv run python scripts/quality_gate.py`, and `git diff --check`. The baseline
reproduction proves current behavior only; none of the proposed availability or rotation guarantees
can be claimed from those tests before their implementation and shared-server/rollout validation.
