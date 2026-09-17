# Private cost-evidence v2 implementation proposal

Date: 2026-09-17. Baseline: merged `main@0ac0193` plus the local
[native counters checkpoint](SPEND_OPENAI_NATIVE_USAGE_COUNTERS.md).
This is the plan for proposed [ADR-0023](../adr/ADR-0023-versioned-cache-category-cost-evidence.md).
The user continued the presented design for slices A and B, now implemented privately for review;
no trusted issuance, provider/model approval or activation is implemented or accepted.
Its [implemented scope/non-claims](SPEND_COST_EVIDENCE_V2_CONTRACTS.md) are separate from later slices.

## Goal and acceptance boundary

Represent one explicitly qualified local-text cache-partitioned estimate with a complete pinned
two-band schedule, an independently verified native input/inclusive-output envelope and
exact-attempt complete usage. Preserve v1 and existing serving. Accept only explicit counts/
rates/provenance, one exact upward conversion and truthful token/cost violation signals.
Do not treat parser output, direct constructors or synthetic fixtures as real authority.

## Repository evidence and material assumptions

- `domain/spend_cost_evidence.py` is intentionally two-rate version one, exact rational pricing
  and private metadata; `application/spend_cost_evidence.py` exposes synchronous pure ports.
- `adapters/spend_cost_evidence_synthetic.py` is a finite read-only fixture reference, explicitly
  synthetic-only. It cannot approve native Responses by changing an API-family label.
- Native projection/counter modules parse wire facts only. Current JSON/SSE usage normalization
  still loses native category/provenance details; both executor paths are unchanged.
- The proposed three input categories must independently form the complete nonoverlapping
  charged input partition for the qualified model/profile. The native parser's inequalities
  do not prove completeness or charging. Output must include all charged reasoning exactly once.
- The proposed threshold depends on total input and changes whole-request rates. A different
  predicate, additive fee, profile, dimension or unknown server default is unsupported here.
- Neither real immutable prices/model-version behavior, account/region/tier configuration,
  count charging/drift nor full-report finality is qualified by current sources/tests.
  Missing proof means unavailable, not a guessed price/cap or permissive legacy fallback.

## Reviewable slices

### A — private values and pure ports — implemented for review

Implemented files:

- `packages/gateway-core/src/governed_llm_gateway_core/domain/spend_cost_evidence_v2.py`:
  frozen/slotted bounded preparation/schedule/bound/exact-dispatch/complete-usage values;
  separate shape/version, all four rates in both bands, positive input threshold,
  private provenance, fixed validity/epoch declarations and exact rational arithmetic.
- `packages/gateway-core/src/governed_llm_gateway_core/application/spend_cost_evidence_v2.py`:
  new no-I/O read-only bound/finality ports over independently issued retained facts;
  sanitized closed errors, no public registration/refresh/journal/dispatch capability.
- `tests/contract/test_spend_cost_evidence_v2.py`: synthetic values/correlation/arithmetic tests.
- `docs/project/SPEND_COST_EVIDENCE_V2_CONTRACTS.md`: implemented scope and non-claims.

Acceptance: max-across-both-bands category envelope; observed-input whole-request settlement;
single ceiling in micro-USD; mandatory explicit zero versus absence; no reasoning double charge.
Test threshold `T-1/T/T+1`, mixed/full/no cache, cache-write most expensive, nonmonotone bands,
truthful excess switching bands, free-price token violations, low Decimal context and altered
rounding mode, exact/over integer limits, invalid types/precision/provenance, immutable values
and sanitized errors. Allocation/settlement projection is not trusted issuance or a control write.
Do not export these values, extend v1 enums/ports, modify registries or integrate them into the
existing synthetic adapter/admission state/runtime. Any actual source/clock validation is later.

### B — finite synthetic v2 lookup reference — implemented for review

The new `adapters/spend_cost_evidence_v2_synthetic.py` and matching contract tests independently
register finite fixture preparations/bounds under the
[reference proof boundary](SPEND_COST_EVIDENCE_V2_REFERENCE.md),
dispatches and explicit complete/incomplete sources at test bootstrap only. Keep real-family
markers rejected and no worker registration/refresh. Test foreign/missing/changed/expired/
conflicting facts, duplicate sources, concurrent pure reads and known/zero/unknown/excess cases.
This is fixture conformance, not source authentication, restoration, real finality or durability.
Fixed UTC time/current-model declarations are immutable fixture control snapshots, not a live
clock, fresh trusted source or worker refresh capability. Original report lookup never uses
a changed current schedule to reprice or erase its retained sources.
Do not retrofit the v1 memory admission reference to hide new token-invalidation obligations.

### C — qualified native preparation and source issuance

Before code, review the exact files/authority paths for adapter-owned preparation inventory,
trusted loading/qualification, authenticated count-source acquisition and fixed validity/drift.
Retain the exact authoritative preparation for projection and dispatch; no reconstruction or
public payload hash. Test byte/model/options/profile/version changes, revocation/expiry,
conflicting duplicate sources and no validity renewal or widening of the original plan.
Count observations alone cannot be registered as trusted evidence. No fixture real-family bypass.
Remote counting requires its own reviewed charging/exposure, retention/rate limits, fresh
authorization, finite deadline/cancellation/closure and sanitized failure semantics first.
The two-rate v1 capability cannot be used to finance acquisition outside its shape.

### D — complete native exact-attempt finality

Independently review the supported native statuses/lifecycle/usage/model/actual-tier contract and
private ingestion path. Correlate original schedule/issuance with preparation and exact execution/
owner/slot/dispatch fences; never settle a different attempt or assume earlier failures cost zero.
Controlled JSON/SSE fixtures test explicit missing/null/provisional/unknown versus complete zero,
cache partition ambiguity, reasoning inclusion, actual model/tier conflicts, duplicates,
truthful token/cost excess and unsupported failed/incomplete/cancelled/semantic-error states.
Support for a non-success state requires independent finality proof, not an event-name heuristic.
Expiry/change does not erase holds or permit repricing; late reconciliation remains separate.

### E — separately reviewed operational prerequisites

Durable all-scope atomic admission/journal, opening balances, recovery/migration/retention and
real backend/failover tests remain under ADR-0021. Both executors then need fenced all-attempt
accounting, pre-HTTP admission, cache/health coordination, acknowledged settlement before public
terminal success and bounded cleanup even when HTTP response construction fails or the iterator
never starts. No reuse of unknown holds, consumed authorization or inference during recovery.
Explicit opt-in configuration/rollout and separately authorized governed live proof come last.

## Current checkpoint files, risk and verification

The initial design slice changed five documents only: ADR-0023, this plan, the ADR index and
links in ADR-0022/native-counter scope. Continued slice A adds the two private v2 modules,
their contract tests and a scope document. The existing native counter/projection code is preserved.
Continued slice B adds its separate synthetic-only adapter/tests/reference document and scope links.
Main was verified at the same merge SHA. No new rates/models/options/backend/secret are selected.

Main risk: mistaking a proposed formula or a structurally valid report for verified bound/finality.
Separate status/non-claims, source qualification and private authority paths are acceptance criteria.
Pending model/account/drift/finality facts deny real qualification; they are not satisfied by a
Boolean flag or by passing synthetic CI. Repr hiding is not ACLs or encryption.

After edits, review complete documents/citations, link targets and diff scope; run the existing
focused spend/native JSON/SSE matrix, standalone Phase 0, then the unchanged full quality gate.
Preserve existing untracked artifacts/stash and record actual results in the local diary, not
fabricated validation results in this plan. No commit/push/PR or live call is authorized here.
