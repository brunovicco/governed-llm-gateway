# Private Spend Admission Contracts

This is the initial internal contract slice of
[ADR-0021](../adr/ADR-0021-conservative-spend-admission-and-settlement.md), not an enabled budget
feature. The existing [observed-spend components](SPEND_ACCOUNTING.md) remain unchanged and unwired.
No estimator, durable store, executor/coordinator integration, configuration migration or provider
proof is supplied here. A separate [process-local reference](SPEND_ADMISSION_REFERENCE.md) now
exercises the ports with synthetic fixtures. Default serving, retry/fallback, cache, health and
public SDK/SSE schemas are intact.

## Values and correlation

Import these values directly from `gateway-core/domain/spend_admission.py`; they are not public DTOs
or facade exports. Frozen/slotted values and plain tuples bind:

- private client/workload and exact daily/monthly scope dates;
- gateway execution/owner identity, policy epoch and policy/plan/registry/retry provenance;
- ordered contiguous fallback/retry slots, each with deployment, bound and pricing/evidence metadata;
- an owned reservation, exact dispatch claim, known/unknown settlement and complete journal closure.

Identifiers use bounded opaque ASCII shape (128 characters), workloads additionally have nonempty
dotted policy segments, and digests require canonical lowercase SHA-256 shape. Dates are plain dates,
not datetimes; monthly scopes start on day one. Every intent scope must match the attributed client,
optional workload and frozen admission date. Duplicate scopes, mutable collections, unvalidated
nested values, reordered/missing/duplicate slots and changed retry-candidate bounds fail validation.

Amounts/indices are plain integers in the initial nonnegative signed-64-bit range
`0..2**63-1`; ceilings/epochs/attempt numbers are positive. Totals must fit too. A backend with a
smaller supported range must reject it independently. `to_reservation_micros` rounds an already
established Decimal estimate upward with an independent outward-rounding context; it is **not** an
estimator. Non-finite/negative/overflowed amounts and implicit float/string conversions refuse.
Legacy half-up conversion is not changed. Truthful settled excess over a ceiling/bound is retained
when representable, not clamped into a success claim; unrepresentable state requires control failure
and trusted reconciliation, never a zero default.

Unknown usage is `None`, not measured zero, and cannot carry a usage-finality claim. Known usage,
including zero, requires an opaque evidence handle. RESERVED/CLOSED_UNUSED snapshots prove no
dispatch fence; MAY_HAVE_EXECUTED/UNKNOWN require one and carry no measured cost; SETTLED requires
paired cost/evidence. A closed journal covers every original slot and has a closure fence; it can
retain UNKNOWN exposure, never dispatchable slots. Closing is not blanket release.

## Permissions and obligations

`application/spend_admission.py` defines `SpendReservationReadPort` for budget/journal inspection
and `SpendReservationPort` for reserve/current-owner/dispatch/settle/close operations. Reads and the
pure `permits_allocation` predicate acquire nothing. Worker ports cannot publish/reset policy,
renew leases, prune state or acquire recovery ownership. Sanitized control errors carry only the
closed unavailable/invalid-state/conflict/expired category, not backend/provider details.

Construction and equality prove only shape/correlation. They cannot establish authenticated
attribution, complete policy limits/authorized plan/attempt coverage, trustworthy pricing/bounds,
usage finality, store-issued receipts, one dispatch, liveness, idempotent transitions, atomicity or
durability. Those are separately verified caller/adapter obligations. Remaining lifetime metadata
is observational: authoritative fixed deadlines/fences must be checked by the store; reconstructing
or repeating a receipt cannot renew ownership. Nothing here grants authorization or replay.

The future backend must validate every applicable policy bucket and the complete journal in one
transition, not trust caller ceilings or a self-created receipt. Unknown/missing known state fails
closed. Acknowledgement timeout is ambiguous; reconcile the exact journal instead of compensating
release or reopening inference. Unknown/possibly executed holds survive close, expiry and failed
cleanup. Recovery/retention/migration and trusted initialization are not implemented capabilities.

## Privacy and proof boundary

Default repr hides attribution, evidence handles, fences and provenance. This is neither encryption
nor permission to call `dataclasses.asdict` and export private records. Values/journals must not be
serialized into logs/traces/Operations/public responses, or used as high-cardinality metric labels.
No prompts, completions, schemas, tools, credentials, prepared headers or raw backend/provider
errors belong in these records. Default evidence remains governed by ADR-0008.

`test_spend_admission_contracts.py` checks shape, frozen values, precise arithmetic, correlation,
contradictory states and port/permission signatures with synthetic metadata. Existing observed-spend
regressions still deliberately prove overshoot. No reservation backend is exercised; these tests
prove neither concurrent admission nor cancellation/lease recovery, actual Redis/Valkey behavior,
provider acceptance, billing ceilings or endpoint enforcement. Reference tests separately exercise
same-process transitions only; verified estimator/storage/recovery and executor integrations remain
future slices.
