# ADR-0021 — Conservative estimated-spend admission and settlement

## Status

Proposed for implementation review; design approved for internal contracts and continued with a
process-local reference, private cost-bound/finality shapes and synthetic evidence lookup.
Values, application ports and same-process transitions are defined for review only.
**No durable backend, trusted estimator, serving integration or feature activation**
is implemented. Local reference conformance is not distributed/durable admission proof.
This separate opt-in proposal does not change `SpendGuard`, `SpendLedgerPort`, Redis keys,
configuration schemas, public request/SSE contracts, or serving behavior. Remaining implementation
and activation require separately verified and reviewed increments.

## Date

2026-09-17

## Context

The inspected baseline is `main@1aa483794ace6fb98b013b7787998e8b5e0b4477`, containing PR #266.
Repository facts, not live-provider, fleet, or billing claims:

- `domain/spend.py` evaluates already-observed integer micro-USD against a ceiling. Its conversion
  rounds half up. `application/spend.py::SpendGuard.check` reads without reserving; `record` writes
  each applicable limit separately, ignores absent cost/cache hits, and swallows write failures.
  An enabled policy without a ledger also permits checks today. These existing semantics are not
  a fail-closed reservation contract and must not be silently reused as one.
- `adapters/spend_redis.py` atomically increments one bucket and sets its expiry. That operation
  neither admits future spend nor transacts across client/workload and daily/monthly limits.
- `test_spend_guard_concurrency.py` proves observed-spend overshoot with controlled components:
  US$0.90 observed, two allowed checks, two US$0.20 records, then US$1.30 and subsequent refusal.
  Sequential overshoot, exact-ceiling refusal, corruption, cache and scope separation are covered.
- API bootstrap and generation coordinators do not compose these spend components into serving.
  [Spend accounting](../project/SPEND_ACCOUNTING.md) describes that boundary explicitly.
- `application/ranking.py` calculates candidate cost from pinned registry pricing and projected
  input/output counts. The HTTP input estimate is a caller projection, not a trusted upper bound
  on provider-reported usage. Registry context capacity is not proof of charged token counts.
- `StreamingExecutionService.prepare` freezes the bounded authorized candidate sequence and provider
  requests without provider I/O. Runtime streaming checks health, opens attempts and may use the
  cache afterward. It does not implement an all-attempt spend journal. Final response usage alone
  cannot account for earlier failed or abandoned attempts.

The purpose is to close the **admission race for a reviewed estimated-cost model**, not to turn
pinned prices into an invoice or guarantee a provider's eventual bill. A reservation without a
valid cost bound, complete attempt accounting, and retained uncertain exposure would overclaim.

## Decision

### 1. Preserve authorization, replay, and package ownership

Propose an independent narrowing control after fresh authentication/PDP authorization, deterministic
ranking and pure preflight. `Gateway allowed set ⊆ Policy Router authorized set` remains permanent.
A budget receipt grants no model, group, capability, tool execution, or retry authority. It cannot
reuse a consumed governance envelope or replace current expiry/revocation/kill-switch enforcement.

Application ports coordinate admission and an execution journal; immutable, provider-neutral values
belong in `gateway-core/domain`. Concrete storage, trusted cost-bound evidence and provider usage
translation belong in adapters. API/bootstrap owns composition and lifecycle. No database/provider
SDK, FastAPI or telemetry dependency enters contracts/domain; consumers keep gateway credentials only.

Streaming preparation remains synchronous and provider-I/O-free under
[ADR-0017](ADR-0017-deterministic-streaming-preflight.md). A future coordinator performs asynchronous
budget admission **after** pure preparation and **before** constructing the HTTP streaming response;
do not put storage I/O inside `prepare` or an initially lazy execution generator. JSON execution
must use the same budget protocol before provider I/O. Explain-only routes spend nothing and must
not claim reservations. Neither execution path is changed by this proposal.

### 2. Require a verified upper bound, not a padded caller estimate

For each concrete deployment retained by the existing fallback bound, require a reviewed bound on
every usage dimension in the enabled cost model. Evidence must cover the exact frozen provider
request, input expansion/tokenization, enforceable output limits and the pinned pricing version.
Schemas, tools, media, reasoning or provider cache pricing may introduce dimensions not described by
today's two-rate registry metadata. Unknown or unsupported dimensions deny enabled-mode admission;
do not invent a tokenizer-neutral maximum, billing rate, safety multiplier or zero price.

The initial implementation scope should be explicitly reviewed bounded text/API-family combinations.
`context_tokens_estimated`, registry context capacity and `RankedCandidate.estimated_cost_usd` alone
are insufficient evidence. No such trusted estimator capability is supplied today. Choosing and
verifying it is an activation prerequisite, not an assumption justified by this document.

With reviewed upper-bound cost `B[d]` in USD for one attempt at deployment `d`, allocate
`r[d] = ceil(B[d] * 1_000_000)` integer micro-USD. Reject non-finite/negative inputs, inconsistent
dimensions, arithmetic overflow or unsupported backend integer ranges before mutating anything.
Round each bound upward, not through the existing half-up conversion. Use that same pinned model
and upward conversion for settlement; provider-reported `total_cost_usd` is not a trusted replacement
for pricing. Estimated figures remain distinct from bills and from ranking's selection projections.

### 3. Reserve the complete bounded execution plan once

Propose conservative upfront allocation for **every possible bounded attempt**, rather than reserve
only the selected deployment and assume a failed attempt costs nothing. For each prepared candidate,
allocate `r[d]` for each allowed retry slot. Let `R` be their sum. Capture the retry-policy version,
attempt limits, registry/pricing provenance and exact prepared-plan identity with the receipt.
Runtime must not enlarge or rebuild that plan. Unreplayable/tool-result requests remain one
candidate and one attempt, and still require supported cost-bound evidence.

Reservation never enables a retry: [ADR-0007](ADR-0007-fallback-safety-semantics.md) and
[ADR-0011](ADR-0011-streaming-normalization.md) remain authoritative. Permanent failures have no
retry/fallback; semantic output, external effects or opaque state still terminate replay.
Unknown cost on an earlier attempt retains its slot's allocation. A later attempt may use only a
distinct already-reserved slot and only when existing replay rules allow it. Do not recycle unknown
exposure to finance another attempt or request.

This intentionally over-reserves mutually exclusive possibilities and reduces concurrency. It is a
small initial protocol without mid-stream capacity top-ups. More efficient incremental reservation
would require a separate review of post-HTTP-commit denial, multi-scope top-ups and recovery races.

### 4. Admit all applicable limits in one authoritative transition

For every deployment-owned matching client/workload daily/monthly bucket, maintain settled estimates
`S`, all retained allocations `H` (including unknown exposure), and ceiling `L`. Admit only if the
state is validated/initialized, `S + H < L` and `S + H + R <= L` for **every** applicable bucket.
The first condition preserves refusal at an exhausted ceiling even for a zero-cost plan.

Atomically create one owned journal/receipt and add `R` to every applicable bucket, or change none.
With US$0.90 committed/held, ceiling US$1.00 and reservation US$0.20, even the first request refuses.
With US$0.80 and two concurrent US$0.20 reservations, exactly one may succeed. These are required
future conformance cases, **not results from the current observed-spend implementation**.

Attribution comes only from `EffectivePolicyContext.client_id` and its reconciled workload. There is
no authoritative tenant in today's contract; do not add a payload-selected tenant. Use unambiguous
canonical scope tuples and an isolated, versioned adapter keyspace, not legacy colon concatenation.
Unmatched policy scopes remain outside configured coverage; do not advertise a universal budget.

Backend selection must prove atomicity for the complete applicable set plus journal/fences, including
all validation and failure paths. Per-key increments, a partial multi-key write, or the mere presence
of a Lua script are not evidence of an all-or-nothing protocol. Partitioning must colocate the
required transaction or provide a verified transactional alternative; cross-partition support is
not presumed. Read, write, ACL, malformed/corrupt/missing known state and durability/recovery faults
deny enabled-mode admission, without a permissive local fallback or swallowed control write.

### 5. Own and fence every possibly chargeable attempt

Use a gateway-generated opaque execution ID and fenced owner, not caller `request_id` as a globally
trusted idempotency key. Bind the receipt to authenticated attribution, complete scope/window set,
policy epoch, prepared plan and pricing. Identical control retries return the same transition result;
changed bindings, stale owners and conflicting duplicates deny without mutation. Repeating a control
operation is not permission to reopen a provider stream or re-execute a public request.

Before provider I/O, durably claim one exact reserved attempt slot and mark it
`MAY_HAVE_EXECUTED`. A slot permits at most one dispatch; idempotent rechecks must not create a
second execution. A storage timeout is an ambiguous operation, not permission to dispatch anyway:
resolve its authoritative result, or terminate. If marking succeeds and dispatch never occurs,
conservatively retaining that allocation is preferable to assuming zero remote exposure.

There is no atomic transaction between storage and a provider network call. Owner expiry fences
future dispatch/control transitions but does **not** reclaim a possibly executed slot. A crashed,
disconnected or partitioned worker may leave remotely running work. Closure remains best effort;
already delivered content and provider charges cannot be revoked. A recovery owner may reconcile
the exact old journal but must not turn ownership recovery into an inference replay.

The coordinator owns admission cleanup even if HTTP response construction fails or the execution
iterator is never consumed. Close undispatched slots under an atomic owner fence; a recovery owner
may do the same only when the retained journal proves no dispatch claim exists. Do not rely solely
on an async generator's finally block, which may never run for an iterator that was never started.

### 6. Settle each slot idempotently; retain unknown usage

Required future transitions, applied to every original bucket plus journal atomically:

| Slot outcome | Cost treatment |
| --- | --- |
| Fenced, closed without any dispatch claim | Remove that slot's allocation; record zero execution |
| Possibly executed with validated complete usage | Add its estimate `U` to `S`, remove its allocation from `H`, retain an immutable settlement receipt |
| Possibly executed without trustworthy complete usage | Keep its full allocation in `H` as unknown exposure; never report it as measured spend |
| Late/duplicate report | Exact valid duplicate is a no-op; conflict/stale mutation refuses, or enters trusted fenced reconciliation |

A local error, initial 2xx, 401/403/429/5xx, timeout, empty output, partial stream, cancellation or
EOF is not proof of zero provider cost. Cost finality must be established by a reviewed usage
contract, even when local schema/lifecycle validation fails; otherwise keep the full allocation.
Failed earlier attempts and the final successful attempt must all be accounted for independently.
Do not settle only terminal `ProviderExecution.usage` or overwrite earlier unknown slots.

If `U` exceeds the reserved bound, retain the truthful amount and flag the violated cost model;
do not clamp or discard it to keep a test/ceiling green. Suspend further affected-model admissions
until trusted reconciliation/review. The conditional no-admission-overshoot claim no longer holds
for that violated bound, and any excess must be visible as sanitized internal control state.

For a provider success, require acknowledged settlement before exposing public terminal completion.
Partial content may already have been delivered; a failed control write cannot undo it, grant replay
or manufacture success. Never issue a compensating release or assume an ambiguous settlement did
not commit: resolve its exact journal/receipt, preserving either the hold or the committed estimate.
Terminate with sanitized failure when necessary and reconcile from retained authoritative state.
Control-operation retries are bounded and never repeat inference. Cancellation propagates;
finally cleanup attempts bounded control closure and always
preserves upstream closure. Failed/cancelled cleanup leaves held exposure, not a release default.

A verified existing cache hit opens no slot and closes/releases all undispatched allocations; it
does not settle historical usage again or validate provider health/credentials. Keep fresh PDP,
ranking, preflight, authenticated cache identity and selected-deployment matching before lookup.
Under today's lookup ordering, upfront capacity may refuse a would-be hit. Accept that conservative
availability trade-off initially; do not move cache access ahead of authorization to avoid it.

### 7. Define windows, policy epochs, retention and recovery explicitly

Propose attribution of all attempts to the **authoritative UTC admission window**, frozen across
midnight/month boundaries. Settlement never moves cost into the worker's current day. This is a
governance allocation convention, not provider billing-time reconciliation. The journal atomically
binds both daily and monthly windows; validated server-side time/rollover rules are prerequisites.
Uninitialized new buckets require trusted creation; absent previously known buckets are not zero.

Policy versions are fences, not separate fresh balances. Ceiling changes must retain existing
settled/held exposure; a lower ceiling below that exposure denies new work without erasing history.
Scope additions/removals, in-flight policy changes and resets require a separately reviewed migration
with admissions suspended/drained or an explicit consistent carry-forward. This proposal does not
invent hot migration or permit a new epoch/key prefix to escape an old hold.

Owner leases, control deadlines and journal retention require explicit finite deployment settings;
none is derived from `max_latency_ms`, provider timeout or the legacy bucket TTL. Expiry/restart
cannot convert unknown exposure into available capacity. At the retention boundary, stop accepting
old fenced reports/dispatch and conservatively finalize remaining unknown holds at their bound
before pruning compatible journals/buckets/tombstones. Mark these as **conservative allocations**,
not observed usage. Proven finality and replay-horizon rules must prevent late reports recreating
an expired balance. Without that proof, require operator reconciliation and deny rather than prune.

Choose and verify durable authoritative storage, acknowledgement/failover behavior, ACLs and trusted
reconciliation procedures before shared activation. An atomic adapter or retained memory object is
not durable fleet evidence. Lost or ambiguous acknowledged state must produce unknown/deny until
reconciled, not empty balances. Trustworthy bootstrap/recovery and capacity/retention bounds remain
operational prerequisites; no store, cloud service or settings are selected/provisioned here.

## Alternatives considered

- Keep observed-spend only: valid current component scope, but explicitly permits overshoot and
  best-effort undercount. Retain it unchanged rather than call it a hard admission guarantee.
- Reserve the selected attempt only: insufficient to cover charged failed attempts/retries/fallback
  without a separately defined top-up protocol. Proposed upfront allocation favors simplicity.
- Pad caller estimates, use a context-capacity number, or reserve `max_cost_usd`: rejected as a
  verified upper bound; these selection/request figures do not prove complete charge dimensions.
- Release everything on cancellation, timeout, lease expiry or HTTP error: rejected because these
  events do not establish absence of remote execution/cost.
- Reserve limits independently and compensate on failure: rejected as the initial protocol;
  partial admissions, lost compensation and read races need their own proof.
- Implicitly upgrade legacy counters/enable the guard in bootstrap: rejected; legacy absent cost,
  missing ledger and swallowed writes cannot support this different fail-closed contract.

## Consequences

If verified bounds, complete atomic state, fenced dispatch and durable recovery hold, concurrent
admission cannot allocate modeled exposure above a configured ceiling. This is a **conditional
future protocol property**, not current behavior, a live-provider proof or a hard billing ceiling.
Upfront all-attempt allocation and unknown holds reduce availability and require reconciliation.
Unsupported requests may be refused even where existing inference works. Keeping truthful bound
violations means excess remains possible when an external/model assumption fails.

## Security and privacy impact

Budget state only narrows authorized execution. No group widening, authorization decision cache,
permanent-error fallback, business-tool execution or benchmark/ranking modification is added.
Store only necessary private control metadata, amounts, pinned provenance and bounded state; never
store prompts, responses, schemas, tool arguments/results, credentials, prepared headers or raw
provider/backend errors. Private attribution/receipts need scoped ACLs and secure transport; hashes
are not encryption. Do not export journal/owner/client identifiers as unbounded metric labels or
public budget receipts. [ADR-0008](ADR-0008-metadata-only-telemetry.md) remains normative; telemetry
cannot be the admission journal or an availability prerequisite for inference control.

## Operational impact

Serving stays unchanged/off until explicit opt-in and rollout acceptance. Use a closed versioned
configuration/loader with exact policy and estimator provenance; do not add ignored schema 1.0
fields. Coordinate/drain legacy workers and verify authoritative opening balances. Best-effort
historical counters cannot prove a complete initial balance; cold namespaces cannot erase exposure.
Rollback must retain compatible enforcement/journals or drain/disable governed serving, not allow
legacy workers to spend against an opted-in budget. No broad deletion or legacy-key fallback.

Measure admission/dispatch/settlement latency and failure coupling before live rollout. Preserve
health probe ownership, cancellation/upstream closure, deterministic preflight, retry limits and
metadata privacy. Live proof must be separately scoped, governed and use configured credentials;
default CI remains synthetic and credential-free. This design creates no new approved artifacts.

## Follow-up

### Initial internal contract slice (not serving)

`domain/spend_admission.py` defines frozen scope/limit/budget projections, complete reservation
intent, per-attempt allocations, owned/dispatch/settlement receipts, and complete journal/slot
snapshots. Shape validation requires bounded integer micro-USD, upward rounding, private metadata,
canonical dates/digests, exact reserved slots and consistent known/unknown/closed outcomes. It does
not verify policy/plan completeness, trusted bounds, usage finality, receipt issuance or liveness.
`application/spend_admission.py` separates read-only inspection from owned worker transitions and
closed sanitized control failures. No reset, policy-publishing, renewal or recovery-owner capability
is given to workers. These Protocols implement no backend or transaction.

Synthetic tests exercise value/correlation/permission shapes, exact arithmetic, invalid inputs,
private repr and frozen tuples. They do not execute reservation/dispatch/settlement transitions,
concurrency, durable storage, cancellation cleanup, provider I/O or serving enforcement. See the
[contract scope and non-claims](../project/SPEND_ADMISSION_CONTRACTS.md).

### Process-local reference slice (not serving or recovery)

`adapters/spend_admission_memory.py` supplies explicit retained state and separate reader/worker
wrappers. Synthetic bootstrap freezes opening settled/held exposure, one policy epoch/digest,
a finite preapproved intent set with all configured matching buckets, and a required usage validator.
These fixture capabilities do not authenticate clients, estimate provider cost or establish finality.
Workers cannot initialize missing scopes, change ceilings/epochs, renew/reset, publish or recover.

All local wrappers share a state-owned thread lock. Bucket/journal/fence changes are built before
one image publication, with no await/provider/network I/O in the critical section. Conservation,
retained execution/revision manifests and receipt consistency detect modeled partial loss/drift.
Whole-process loss or a newly constructed object cannot prove restoration or safe opening balances.
Capacity refusals retain bounded denial metadata for exact control-result resolution, without
changing exposure or creating an admitted journal. Duplicate results never renew fixed deadlines.

Claims are unique local journal transitions, not reusable permission for provider openings. Only
one unresolved possibly-executed claim per execution is admitted. Exact duplicates can resolve
existing results after close/expiry without mutation; new expired/stale/closed transitions refuse.
Close releases only unclaimed slots and retains unknown exposure. Unknown-to-known/late/conflicting
reports require future trusted reconciliation. No expired-owner cleanup/recovery capability is
supplied. Truthful excess suspends that deployment, including new pending claims; unrepresentable
settlement freezes the reference for reconciliation without publishing partial counters.

Synthetic tests exercise these local transitions, threads/event loops, conflicting/duplicate inputs,
window attribution, state corruption, and pre/post-publication faults or injected cancellation.
They do not exercise real HTTP abandonment/cache/upstream closure, provider finality, storage ACLs,
restart/failover, policy migration, pruning or serving enforcement. See
[reference proof boundary](../project/SPEND_ADMISSION_REFERENCE.md).

### Cost-bound/finality contract continuation (no verified provider capability)

From merged `main@36aa9d6` (PR #267), `domain/spend_cost_evidence.py` defines private version-one
preparation bindings, a deliberately limited two-rate text cost model, declared bounds,
exact-dispatch usage-finality requests and explicit complete usage values. All metadata is
immutable and bounded. Rates use exact rational arithmetic and one upward integer conversion,
independent of caller Decimal context. Allocation/settlement projections preserve correlation;
they do not reserve, verify issuance/finality, acknowledge writes or grant execution/replay.

`application/spend_cost_evidence.py` specifies synchronous no-I/O bound/finality capabilities over
privately retained exact preparation/report handles. Independently issued evidence and trusted
versioned configuration remain adapter obligations, not facts supplied by callers or Protocols.
Unsupported shapes/dimensions and missing/invalid/foreign evidence fail with sanitized errors.
Unknown final usage retains exposure; measured zero requires explicit complete evidence. Truthful
token/cost excess remains visible, including token violations hidden by free prices or micro
rounding; future integration must signal model violations, not discard those flags on projection.

This is the contract portion of slice 3, not its verified estimator, approved API/model list,
provider finality, strict configuration loader or reference/executor integration. Synthetic
contract tests prove shape/correlation/arithmetic/permission boundaries only. See the
[cost evidence scope and non-claims](../project/SPEND_COST_EVIDENCE_CONTRACTS.md).

### Synthetic cost-evidence reference (no real API/model approval)

`adapters/spend_cost_evidence_synthetic.py` freezes independent canonical text preparations, declared
bounds, preapproved dispatches and explicit complete/incomplete usage sources. Read-only wrappers
match port signatures for synthetic tests only; they reject all real provider-family markers and
do not fulfill trusted native tokenization, configuration, evidence issuance or provider finality.
Unknown handles raise, changed registered facts conflict, and ambiguous fixture inventories refuse.
Only an explicitly registered inspected incomplete source returns unknown, never absent reports
or normalized usage defaults. Bound/usage excess is retained, including token violations at zero
prices; generic settlement still needs separate future token-model invalidation integration.

Synthetic tests add independent registration/correlation, strict immutable text shape, private
surfaces, concurrent pure reads and manual known/zero/unknown/excess composition with the existing
local reservation reference. No serving or admission-state implementation changes are made.
Fixture construction/equality is a test assumption, not real authority, restoration or finality.
This extends slice 3's reference evidence, not its real verified capability/configuration proof.
See the [synthetic proof boundary](../project/SPEND_COST_EVIDENCE_REFERENCE.md).

### Remaining implementation slices

The [dated Responses candidate assessment](../project/SPEND_OPENAI_CAPABILITY_ASSESSMENT.md) and
[proposed acquisition design](ADR-0022-bounded-provider-cost-evidence-acquisition.md) identify real
qualification gaps. Design approval continues with a
[pure projection/parser slice](../project/SPEND_OPENAI_INPUT_COUNT_PROJECTION.md), not remote
acquisition, trusted issuance or expanded pricing.
They approve no API/model and change no version-one contracts, runtime or activation status.

Approval and continuation permit the internal slices above, not implicit serving activation.
Suggested separately reviewable slices, with the first two and the contract portion of the third
now defined for review:

1. Internal immutable allocation/journal/fence/receipt values and application ports with validation
   and synthetic tests; no public SDK/SSE change, backend or serving activation.
2. Process-local reference conformance over an explicitly retained state object, never a shared-mode
   fallback or restart/durability claim. Exercise complete transitions, concurrency and faults.
3. Reviewed trusted cost-bound/usage-finality capabilities for explicit API families and bounded
   request shapes; versioned strict configuration/pricing provenance. Reject unsupported shapes.
4. Durable atomic backend and recovery/retention/migration proof, independent of legacy spend,
   health and credential stores. Verify real chosen server/failover behavior, not emulator alone.
5. Both executor/coordinator integrations, pre-HTTP admission, fenced attempt ownership, all-attempt
   accounting, cache/health coordination and bounded lifecycle cleanup; explicit opt-in rollout.

Required test evidence before activation:

- Exact integer arithmetic, upward rounding, non-finite/negative/range rejection, trusted input
  bounds, missing prices and unsupported media/tools/reasoning/cache-pricing dimensions.
- Concurrent same-client/workload daily/monthly admissions; exact-ceiling refusal; one exhausted
  scope prevents **all** mutation. Independent clients remain independent.
- Reserve/dispatch/settle/close duplicate identity, changed bindings, stale owner/epoch, conflicting
  outcomes, crash between journal/dispatch/settlement, and unknown-result control timeouts.
- Retry/fallback cost for every slot, unknown earlier attempts retained, no permanent-error or
  post-semantic/tool-result replay, no widening or reconstruction of the prepared plan.
- Partial/invalid output, trustworthy final usage versus provisional usage, costs above bounds,
  cancellation/disconnect/abandonment, late reports and attempted double dispatch.
- Missing/corrupt/uninitialized state, ACL/outage/write faults, overflow and partial-write prevention,
  ownership expiry, acknowledged-state loss/failover, restart, rollover, policy migration and pruning.
- Valid/invalid cache hits, denial/PDP outage, changed selection, no double historical charge and no
  health/credential recovery from caching. No reservation leak when a response is never consumed.
- Pre-stream sanitized denial with zero provider calls, no successful terminal completion without
  settled control state, upstream closure despite cleanup faults, and content/credential-free
  errors/repr/logs/traces/Operations. Full Phase 0 and canonical quality gates unchanged.

Passing the current repository gate validates value/port and same-process reference conformance,
and preserves existing serving. It does **not** execute the remaining activation test matrix or
prove distributed atomicity, durable recovery, complete cost bounds or serving enforcement.
