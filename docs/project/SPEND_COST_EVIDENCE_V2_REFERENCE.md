# Private synthetic cost-evidence v2 lookup reference

Date: 2026-09-17. Baseline: merged `main@0ac0193` plus the local native-counter and
[private v2 contract](SPEND_COST_EVIDENCE_V2_CONTRACTS.md) checkpoint. The user continued
slice B of [ADR-0023](../adr/ADR-0023-versioned-cache-category-cost-evidence.md).
This is **finite fixture lookup conformance only**, never a real cost-evidence capability.

## Implemented private scope

`adapters/spend_cost_evidence_v2_synthetic.py` adds frozen/slotted objects with every field
hidden from repr, no public export and no runtime/bootstrap caller:

- `SyntheticSpendCachePreparation`: retains the exact immutable canonical `ProviderRequest`
  fixture, its text-only messages and explicit declared bound. Fixture model and inclusive
  output cap must match. It is not native preparation, dispatch data or tokenization.
- `SyntheticSpendCacheControlSnapshot`: explicit canonical UTC fixture time and a tuple of
  declared current synthetic models. An empty tuple models unavailable/revoked qualification.
  It does not read a clock, authenticate configuration or supply a fresh control authority.
- `SyntheticSpendCacheBounds`: independently constructed finite preparation inventory plus
  one immutable control snapshot; synchronous read-only structural match to the bound port.
- `SyntheticSpendCacheUsageReport`: explicitly registered source for one original bound and
  dispatch; either all complete mandatory counts or explicit inspected incomplete `None`.
- `SyntheticSpendCacheFinality`: independent issued-bound, approved-dispatch and report
  inventories; synchronous read-only structural match to the finality port.

Only literal `synthetic-text-v2` is supported. Real provider/API-family markers and v1 are
rejected even if prices or counters are syntactically valid. Toy prices/counts/caps are fixture
declarations; changing a label, constructing equal objects or passing these tests approves none.
Schemas/tools/results/media, nontext blocks, mutable collections, extra canonical content,
nonfinite/Boolean timeouts, foreign model/output caps and malformed nested facts are refused.

## Lookup, conflicts and fixed fixture control

Preparation and evidence IDs must be unique. A single API/model/profile identity has one
complete model/configuration/pricing/qualification declaration; reusing a pricing digest for
different model contents refuses. Current model snapshots must also be unambiguous.
Lookup never registers a caller's binding or creates/renews evidence.

Under the explicit fixture snapshot, bound lookup requires the exact registered binding,
exact original model declaration and `valid_from <= observed_at < valid_until`.
Missing preparation/current model, removal or expired/not-yet-valid fixture time is
`UNAVAILABLE`; changed registered bindings, prices, configuration, epoch or model details
are `CONFLICT`. A new snapshot is another test-bootstrap object, not a worker refresh API.
An identical reader cannot prove wall-clock freshness and must never be used for real admission.

All failures use the existing closed sanitized `SpendCostEvidenceError` categories.
Foreign family is `UNSUPPORTED`; malformed types or detected nested corruption are
`INVALID_STATE`, with raw exception chaining suppressed. No price/cap/zero/legacy fallback.
Frozen values and revalidation are not ACLs, tamper-proof storage or cryptographic authentication.

## Original exact-attempt usage sources

Fixture dispatches must independently reference a registered bound and match original plan/
policy/registry/retry/allocation facts. Dispatch fences and execution/fallback/attempt slots
are unique; one execution retains one consistent reservation/owner declaration.
Reports must reference registered bounds and dispatches. Report handles, per-dispatch sources
and complete usage-evidence IDs are unique; an incomplete source cannot overwrite a complete
one or register another outcome for the same dispatch.

Finality lookup checks the original bound and entire dispatch, including owner/owner fence,
attribution/window/slot facts and dispatch fence, then the exact report request.
Only a registered inspected incomplete source returns `None`. Missing/foreign/conflicting
reports raise, never complete zero. Explicit all-zero complete counters remain distinct
declarations, not independently proven native zero charge.

Original fixture reports remain readable when another bound reader's current snapshot is
expired, removed or changed. This neither reprices nor erases the original schedule/source.
It proves no actual past dispatch qualification or native finality and releases no real hold.
Unknown-to-known replacement, late reconciliation, ownership recovery and replay are absent.

Known lookup returns the exact retained finality object, including independent input/output/
token/cost excess flags. The flag-preserving projection remains unchanged even at zero price.
No clamp, suspension/invalidation, reservation, settlement write, acknowledgement or release is
implemented. A future actual consumer must handle token violations before new affected-model
admission/claims; this reference is not retrofitted into the v1 admission-memory adapter.

## Verification boundary and next prerequisites

Synthetic tests cover immutable/private surfaces, the canonical-text subset, unsupported
families, fixed window boundaries, changed/removed model declarations, absent versus incomplete
sources, exact owner/slot/report correlation, conflicting inventories, explicit complete zero,
truthful excess/free prices, nested corruption, and concurrent thread/event-loop pure reads.
These are in-process fixture proofs, not source authentication, trusted clock/revocation,
real provider caps/prices/charging/finality, distributed atomicity or durable restoration.

V1 values/ports/references, private v2 arithmetic/ports, native parsers, SpendGuard, both
executors, public contracts/SDK, configuration/rankings, dependencies and gate controls are
unchanged. No provider/PDP I/O, credential read, benchmark, provisioning or serving activation.
Finite tuples are not an operational capacity/retention proof; no production store is selected.

Next is the separate review of slice C's exact adapter-owned native preparation/source and
trusted loading/qualification authority paths. No canonical reconstruction or parser-plus-ID
promotion can substitute for the native source. Remote counting needs separately reviewed
charging/exposure, retention/rate limits, drift, fresh authorization and finite deadlines first.
Native exact-attempt finality, durable accounting/recovery, both executors/HTTP abandonment
cleanup and explicit opt-in rollout remain later increments. No commit/push/PR is included.
