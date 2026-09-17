# Process-local spend admission reference

This is the second internal slice of [ADR-0021](../adr/ADR-0021-conservative-spend-admission-and-settlement.md).
It implements [private ports](SPEND_ADMISSION_CONTRACTS.md) for synthetic conformance only.
Serving/bootstrap, executors, cache/health, legacy observed-spend components, public contracts,
configuration and dependencies are unchanged. Nothing automatically constructs or activates it.

## Explicit fixture authority

`adapters/spend_admission_memory.py` contains `InMemorySpendAdmissionState`,
`InMemorySpendAdmissionReader` and `InMemorySpendAdmissionWorker`. Construction requires nonempty
immutable opening budget snapshots, finite preapproved reservation intents, a finite positive owner
lease, and an explicit usage validator. Optional clocks default to local monotonic time and UTC.
Callbacks must be synchronous, side-effect-free and non-reentrant; they run under the local lock.

Approved intents bind exact execution/owner/client/workload, dates, policy epoch/digest, provenance,
all configured matching scopes/ceilings and the entire allocation sequence. Requests cannot omit
a configured applicable bucket or edit the approved plan/bound/pricing. One epoch/digest is frozen;
there is no worker publishing, policy mutation, hot migration, reset, pruning or recovery API.
Caller request IDs or a self-created receipt are not accepted as newly issued local ownership.

Bootstrap and usage validation are **synthetic controller facts**, not authentication/ACLs,
EffectivePolicyContext reconciliation, trusted pricing/tokenization bounds or provider finality.
Coverage is only the supplied configured scopes, not a universal budget. Opening held/settled
amounts must be explicit: fresh construction, old observed counters or missing scopes do not prove
recovery/production balances. A missing scope is denied rather than initialized at zero.

## Local transition semantics

One state-owned thread lock serializes wrappers across local threads/event loops. Each operation
builds complete immutable bucket/journal/fence changes before publication; no await or remote I/O
occurs inside a critical section. Opening exposure plus every journal must reconcile exactly.
Retained revision/execution manifests, unique issued fences and state/evidence correlation detect
modeled missing/partial/corrupt images. These checks remain active under optimized Python.

- Reserve requires `S+H<L` and `S+H+R<=L` in every matching daily/monthly/global/workload bucket.
  It allocates every possible bounded attempt, or no capacity. A capacity refusal retains only
  bounded denial metadata so exact retries return their original result, even after capacity frees.
  Infrastructure failures are sanitized control errors, never capacity refusal or permission.
- First admission requires its fixture date to equal validated UTC time. Daily/monthly attribution
  stays frozen thereafter. Reads and exact reserve retries do not renew/re-window ownership.
- Dispatch issues one exact slot claim before any hypothetical provider I/O. Only one unresolved
  MAY_HAVE_EXECUTED slot per execution is allowed. Duplicate resolution returns the original claim;
  the caller still owns at most one actual opening. Receipts do not implement provider idempotency.
- Known validated usage, including zero, transfers the slot's hold to its truthful estimate in all
  original buckets. Unknown keeps its entire bound. Exact duplicates are read resolution; changed
  usage/evidence/fences, cross-execution reports and unknown-to-known updates refuse. Reconciliation
  needs a separate future capability, not a worker's late report.
- Close releases only unclaimed RESERVED slots, turns unresolved claims into UNKNOWN, and retains
  all settled/unknown exposure. Duplicate close resolves the same fenced journal. Explicit close
  models an unused or abandoned execution; no actual cache/HTTP/generator integration is tested.
- New transitions require live ownership and an open journal. Exact already-committed results may
  resolve after close/expiry without mutation. Expiry does not release even unclaimed capacity;
  expired-owner cleanup is deliberately unavailable pending trusted recovery design.
- Representable bound excess is not clamped: that deployment is suspended for future admissions
  and new pending claims, without a worker clearing it. If aggregate arithmetic cannot represent
  truthful usage/exposure, the image remains unchanged and the reference is blocked for reconciliation.

Pre-publication errors leave the prior image; a lost post-publication acknowledgement may have
committed. Resolve the exact retained journal/receipt, never compensate release or repeat inference.
Injected cancellation propagates and keeps whichever whole image was published. There are no
automatic control retries, provider calls, logs/traces, secret reads or public receipt exports.

## Proof boundary and next slices

`test_spend_admission_memory.py` proves synthetic same-process transition/conservation behavior,
concurrent capacity/claim serialization, exact control-result idempotency, fencing/expiry, complete
attempt accounting, scope separation, UTC attribution, excess/overflow and modeled corruption or
pre/post-publication faults. Tests use barriers, not sleeps, with bounded waits. Raw fault details
do not enter sanitized control errors; private metadata is excluded from default repr.

This is not a durable/distributed adapter or shared-mode fallback. All history is lost with the
process; a fresh object/second process is independent and unsafe as restoration. The finite intent
set bounds records but supplies no real admission throughput, storage capacity or retention policy.
There is no proof of real Redis/Valkey protocol, transaction/failover/acknowledgement/ACL behavior,
multi-process/fleet enforcement, validated token/pricing bounds, real provider dispatch/finality,
billing ceilings, HTTP abandonment/upstream closure, coordinator cache ordering, policy migration,
restart/recovery/pruning, or terminal SSE enforcement. State is private, not encrypted or an ACL;
do not serialize journals into logs/Operations/public responses or metric labels.

Next require separately reviewed cost-bound/finality capabilities and strict versioned provenance,
then chosen durable storage plus recovery/migration/retention proof, before executor integration
and an explicit opt-in rollout. Existing authorization and no-replay rules remain prerequisites,
not powers conferred by budget receipts.
