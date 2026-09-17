# Private partitioned-cache cost-evidence v2 contracts

The user continued the presented [ADR-0023](../adr/ADR-0023-versioned-cache-category-cost-evidence.md)
design for its first private values/ports/test slice. Based on merged `main@0ac0193` and the
local native-counter checkpoint, this implements **declarations and pure arithmetic only**.
It authenticates no preparation, count/report, price, API/model, profile, clock or qualification.
Version-one shapes/ports/fixtures, legacy SpendGuard, serving, configuration, routing,
dependencies and existing JSON/SSE normalization are unchanged. No public export is added.

## Separate adapter-neutral private version

`domain/spend_cost_evidence_v2.py` defines `text_cache_partitioned_v2`, schema `2.0`, with
frozen/slotted values; all fields are hidden from repr:

- `SpendCachePreparedBinding`: bounded private preparation/deployment/API/model/profile IDs,
  configuration and original policy/plan/registry/retry provenance, inclusive output limit.
- `SpendCacheRates`: four mandatory exact ordinary-input/cache-read/cache-write/output rates.
- `SpendCacheCostModel`: both complete bands, positive input threshold, pinned pricing and
  qualification provenance/epoch, fixed canonical UTC validity declarations.
- `SpendCacheCostBound`: mandatory input cap, same-model/profile/configuration binding,
  estimator/usage-contract/evidence declarations, fixed window contained in the schedule.
- `SpendCacheUsageFinalityRequest`: exact allocated cost/plan/policy/registry/retry correlation
  with a declared dispatch receipt and mandatory private report handle.
- `SpendCacheUsageFinality`: six mandatory bounded plain integer counters and evidence ID;
  explicit zero is accepted as a declaration, not independently verified complete-zero usage.
- `SpendCacheSettlementProjection`: retains the exact finality and its independent input/
  output/token/cost violation flags alongside an internally derived generic settlement.
  It does not suspend a model, write/acknowledge a journal or release capacity.

Reuse of existing private validators preserves v1 encoding/range rules, not its two-rate
pricing meaning. Rates require finite nonnegative plain Decimals, at most 12 fractional
places and bounded encoding/magnitude. Counts/fences/amounts use signed 64-bit bounds;
Boolean/subclass/fractional/missing values cannot substitute. Canonical UTC windows use
plain datetimes with literal `datetime.UTC`, ordered strictly; no current clock is read.
Provenance must be canonical, IDs bounded, nested values of exact expected types.
Construction/equality validates declarations, not issuer identity or privileged tampering.

## Exact arithmetic and truthful violations

Admission arithmetic uses the maximum of all six input-category rates across both bands
and the independent maximum output rate, multiplied by supplied input/inclusive-output caps.
One upward integer conversion follows the entire sum. USD-per-million times token counts is
already micro-USD. No forecasted cache hit, chosen cheap band or monotonic-rate assumption.

Complete declared usage requires `cache_read + cache_write <= input`, `reasoning <= output`
and `total = input + output`. Only this explicitly partitioned shape derives ordinary input.
Observed total input selects the whole-request band (`input <= threshold` versus greater).
Each category is priced once; reasoning is included in output, never added twice. Exact
rational arithmetic is independent of Decimal context/rounding/traps; no float, half-up,
per-category rounding, provider-reported money or current-price refresh is used.

Truthful representable excess is retained, including input/output violations at zero price
or below a micro rounding boundary. The projection keeps the full finality instead of
returning only a generic outcome that loses these flags. Future consumers must inspect
them and invalidate/suspend affected qualification before new admission/claims; that control
is **not implemented here**. Overflow rejects without a partial control write or cost clamp.
Figures are conditional modeled estimates, not invoices or a real provider billing ceiling.

## Pure ports and authority still missing

`application/spend_cost_evidence_v2.py` declares separate synchronous no-I/O bound/finality
Protocols. Only independently trusted retained native sources and fresh qualified control
snapshots may fulfill them. These Protocols implement no source inventory, trusted loader,
clock/epoch/expiry verification, evidence issuance, complete usage or configuration refresh.
There is no worker/public evidence-registration or budget/dispatch/recovery capability.
The standard Protocol metaclass's class registration is not evidence-source registration.

An inspected supported incomplete report may yield `None`; missing/foreign/unqualified/
conflicting sources must raise closed sanitized evidence errors, never normalized zero.
Fixed window shapes do not establish liveness; expiry/drift cannot erase old holds or prices.
Native parser output cannot be promoted into trusted finality by supplying an ID or flag.
Actual report/model/tier/lifecycle/source authority and execution/owner/slot fences must be
independently verified before finality can release any reserve in a later integration.

## Verification and next scope

Synthetic contract tests exercise versions, all frozen/private fields, exact types/rates/
windows/provenance, model/profile/configuration and dispatch/allocation correlation,
threshold boundaries, whole-request pricing, cache-write/max-rate envelopes, nonmonotone
bands, explicit zero/absence, reasoning inclusion, exact integer ceilings/overflow, hostile
Decimal context, independent excess flags and flag-preserving settlement projections.
An exhaustive small-partition oracle checks the conditional envelope under toy schedules.
These tests do not prove actual provider caps/prices/finality or distributed accounting.

A separate finite **synthetic-only** v2 lookup reference is now implemented for review;
see its [fixture proof boundary](SPEND_COST_EVIDENCE_V2_REFERENCE.md). It does not change these
domain values/ports or provide actual source qualification, fresh trusted control or release.
Real preparation/count issuance and exact-attempt native finality remain unimplemented.
Resolve remote counting's own charging/exposure, retention/rate limits, fresh authorization
and finite deadlines before
any remote acquisition. Durable all-scope accounting/recovery, both executor integrations,
HTTP abandonment cleanup, explicit opt-in rollout and separately scoped live proof remain
later prerequisites. No provider/PDP credential read, paid call, benchmark/ranking artifact,
backend/provisioning, commit/push/PR or runtime activation is included.
