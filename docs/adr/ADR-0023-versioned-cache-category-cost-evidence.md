# ADR-0023 — Versioned cache-category cost evidence

## Status

Proposed for implementation review — user continuation approved the presented design for
the first private values/ports/test slice and continued a separate synthetic-only lookup reference,
now implemented. Real prices, trusted issuance,
native finality, API/model qualification and activation are neither implemented nor approved.
It refines the separate pricing/issuance option left unapproved in proposed
[ADR-0022](ADR-0022-bounded-provider-cost-evidence-acquisition.md). It does not supersede
accepted ADR-0017 or change version-one values, ports, synthetic fixtures or serving semantics.

## Date

2026-09-17

## Context

Baseline: merged `main@0ac0193006c44d1b4294a03146c9ae03e7a84b96` (PR #269), followed by the
local [native usage-counter slice](../project/SPEND_OPENAI_NATIVE_USAGE_COUNTERS.md).
The merged private domain cost evidence supports only `text_input_output_v1`; its synchronous
bound/finality ports exclude cache/reasoning dimensions. Continued slice A adds separate private
v2 declarations/arithmetic/ports, not trusted issuance. The two pure native parsers grant no
trusted issuance, complete-zero evidence, exact-attempt finality or budget authority.
The synthetic reference deliberately accepts no real provider family. None is wired into serving.

Official sources inspected on this date provide a candidate dimension interpretation, not an
immutable account agreement or qualification of the current deployment:

- The cache guide's calculation partitions total input into ordinary, cached and cache-write
  tokens, priced separately. This motivates a **conditional** partitioned model, not permission
  to derive categories from absent fields. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
- Reasoning tokens are billed as output; they are a detail, not an additional generated-token
  charge. [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).
- The current pricing table distinguishes input/cache-read/cache-write/output, context bands and
  processing/residency qualifications. [Pricing](https://developers.openai.com/api/docs/pricing).
- The locally configured Luna page describes a whole-request long-context threshold and
  cache-write multiplier. No threshold, price or snapshot is silently adopted here.
  [Luna reference](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

Engineering inference: a separate narrow version can represent these documented dimensions,
but only independent native/model/profile/usage qualification can make its arithmetic applicable.
Current registry prices, parser conformance and historical live inference do not supply that proof.

## Decision

The private declaration/arithmetic slice and synthetic-only lookup reference are implemented
for review. Source qualification,
trusted issuance, acquisition, native finality and operational integration remain proposed.

### 1. Separate private version and complete pinned schedule

Propose provider-neutral `text_cache_partitioned_v2` values and new no-I/O application ports;
do not add dimensions to `SpendCostShape.TEXT_INPUT_OUTPUT` or reinterpret version-one rates.
Keep native field names, response parsing and issuance in adapters, exact arithmetic in domain,
and any future asynchronous acquisition outside pure preparation/lookup.

The initial schedule describes one qualified local-text API/model/configuration and processing/
region profile. Require a positive input threshold `T`, two complete whole-request bands
(`I <= T`, `I > T`), and four explicit USD-per-million rates in **each** band: ordinary input,
cache read, cache write and inclusive output. No optional/missing rate becomes zero. A free rate
must be explicit. Profile uplifts are already represented in approved rates, not guessed later.
The shape covers no media, schemas/tools/results, hosted tools, remote history, compaction,
background work, flat fees, additive cache-write fees or additional charge dimensions.
Unsupported model/profile/partition/threshold interpretations require another reviewed shape.

Freeze pricing content/version, model/API/configuration identity, qualification/estimator/
usage-contract versions, finite validity and invalidation epoch. A digest-shaped string or
price label authenticates nothing; trusted loading and source qualification remain separate.
Do not invent a dated model snapshot. An alias without a reviewed drift/version guarantee
remains unqualified. No real schedule, production loader, model approval or price refresh is
included in this proposal or its first value/test slice.

### 2. Exact conservative envelope and same-schedule estimate

Require an independently verified total-input cap `I_cap` and an enforceable inclusive-output
cap `O_cap` for the exact retained preparation. Neither caller estimates, context capacity,
normalization defaults nor construction of a count observation establishes either cap.

For admission, use `R_in_max`, the maximum of all six input-category rates across both bands,
and `R_out_max`, the maximum of the two output rates. Propose:

```text
bound_micros = ceil(I_cap * R_in_max + O_cap * R_out_max)
```

Rates are USD per million tokens: conversion to integer micro-USD cancels that denominator.
Independent maxima intentionally over-reserve even when a cheaper band appears predictable;
no cache-hit forecast, monotonic-rate assumption or selection projection reduces the envelope.
Conditional proof: a complete nonnegative input partition sums to at most `I_cap`, every
applicable category rate is bounded by `R_in_max`, and inclusive output is at most `O_cap`.
The resulting exact sum and its single upward conversion bound the same-model estimate.
This proof does not establish the external token caps, partition or schedule applicability.

For independently validated complete final usage, let input/cache-read/cache-write/inclusive-
output be `I/C/W/O`, with mandatory reasoning detail `Q`. Require `C + W <= I`, `Q <= O` and
native total `I + O`. Derive ordinary input as `I - C - W` only under the qualified partition.
Select the **whole-request** band from observed `I`, then propose:

```text
estimated_micros = ceil((I - C - W) * R_ordinary + C * R_read + W * R_write + O * R_output)
```

Do not charge `Q` again, apply marginal threshold pricing, round each category separately or
replace the pinned schedule with current registry/provider-reported money. Require bounded
plain integers and exact finite nonnegative plain Decimals with version-one encoding limits;
calculate with exact rationals independently of Decimal context, then range-check the ceiling
and complete plan sum. No float, guessed multiplier, clamp or half-up conversion.

Keep truthful representable excess and independent input/output/cost violation flags, including
violations hidden by free prices, discounts or micro rounding. Violated qualification must block
new affected-model admissions/claims before continuation; no settlement projection may silently
discard token flags. Unsupported usage or unrepresentable arithmetic preserves exposure and
requires reconciliation, not a partial write or substitution of the bound as measured usage.
All figures are modeled estimates, not provider invoices or a hard billing ceiling.

### 3. Issuance authority is separate from values and parsers

Propose an adapter-owned finite inventory of exact immutable native preparations and provenance.
One authoritative preparation supplies both count projection and dispatch; never rebuild from
canonical messages, accept a public payload hash or qualify caller-constructed observations.
Bind issued input evidence to the exact retained native body/model/input-affecting options,
endpoint/configuration/credential-version identity, plan/policy/registry/retry provenance,
pricing/qualification versions and fixed validity. Do not read/copy secrets into these values.

Only a reviewed trusted acquisition/source path may populate real evidence. A constructor,
raw JSON counter, caller-selected ID, Boolean verification flag or equal dataclass cannot
register/issue it. Public clients and inference workers receive no registration, refresh,
price-publishing, configuration-reset or recovery authority. A synthetic inventory must remain
explicitly synthetic and cannot approve real families. Opaque handles are local correlations,
not authentication tokens, cryptographic attestations or remote portable receipts.

Pure lookup resolves the exact issued facts; missing/foreign/expired/revoked evidence denies
new admission/dispatch. Identical control lookups never extend fixed validity. Changed bytes,
model/profile/price/configuration or inconsistent duplicate sources conflict. Reuse of a bound
does not authorize another public request or dispatch; every eligible original retry/fallback
slot still needs its own allocation and unique fenced claim under ADR-0021.

Do not implement remote counting until charging/retention/rate limits, count-to-dispatch drift,
fresh authorization and finite control deadlines are independently reviewed. If counting can
spend, require a separately proven prior bound/accounting path or deny; no circular assumption
that this generation envelope budgets its own acquisition. No provider I/O inside preflight.

### 4. Complete native finality belongs to one exact claimed slot

Future report ingestion must independently verify a supported native usage/finality contract,
mandatory raw category details, actual model/processing profile, response identity and exact
preparation/execution/owner/slot/dispatch fences under the original schedule. Native content and
raw reports remain sensitive temporary adapter state, never budget-journal/public metadata.
The counter parser does not validate this full exchange or supply report authenticity.

Finality lookup grants no journal acknowledgement, release or replay. Complete measured zero
requires complete exact-attempt evidence. Status/event names, HTTP codes, absent output,
normalized usage, EOF or cancellation prove no zero charge. Initially unqualified failed,
incomplete, cancelled or semantically invalid reports retain the entire slot allocation;
supporting any such case requires independent finality review, not a success-only assumption.

Expiry/revocation/drift blocks new work but never erases held exposure or the original schedule.
Already-executed reports can settle only under their original independently valid contract;
otherwise preserve unknown exposure. Late/unknown-to-known reconciliation is a separately
reviewed fenced capability, never automatic reissuance, repricing or inference replay.
Both executors eventually need all-attempt accounting and acknowledged settlement before public
terminal success; the current final normalized response alone remains insufficient.

## Alternatives considered

- Mutate version-one shapes/ports or call registry input the worst-case rate: changes reviewed
  semantics and hides category, context, provenance and complete-final-usage obligations.
- Charge cache writes in addition to ordinary input, or reasoning in addition to inclusive
  output: inconsistent with the proposed documented partition; not this shape.
- Bound from a cache-hit prediction or the band of an untrusted input projection: may under-reserve.
- Authenticate evidence with equal objects, a payload digest or a caller verification flag:
  validates declarations, not source authority; exposes dictionary-attack/forgery risks.
- Fetch prices during settlement or release on timeout: loses original model continuity or
  manufactures measured zero; retain the original schedule and uncertain exposure instead.
- Implement only pure values first: preferred after design approval; tests must remain synthetic
  and explicitly separate from real issuance/finality qualification and operational guarantees.

## Consequences

The proposed envelope is deliberately conservative and may reduce concurrency. Precise settlement
needs more native evidence and qualification than today's normalization. Separate versioning avoids
corrupting existing private fixtures/contracts. Exact arithmetic can be tested without paid calls,
but does not solve external bounds, drift, complete usage, durability or account billing semantics.

## Security and privacy impact

Budget evidence only narrows the original authorized plan; no group/tool/business/replay authority,
authorization cache, global registry enumeration or permanent-error fallback is added.
Keep native bodies/digests, count/raw reports, credentials/headers and raw errors out of journals
and public/telemetry surfaces. Necessary bounded journal attribution/owner/slot/provenance stays
private under ADR-0021, never including payload hashes or public/unbounded metric identifiers.
Frozen values, repr hiding and ordinary digests are not ACLs, encryption or trusted issuance.
Source/loader authority, capacity/retention and protected configuration remain proof obligations.

## Operational impact

Private declarations/arithmetic/ports/tests and synthetic fixture lookup only today;
no runtime/configuration/dependency/
real-price/ranking changes, paid calls, secret access, backend choice/provisioning or publication.
The local native parser checkpoint is
preserved. Remote acquisition, durable atomic accounting/recovery, HTTP abandonment cleanup,
both executor integrations, migration and explicit opt-in rollout remain separate later work.

## Follow-up

1. Review the [first private contract slice](../project/SPEND_COST_EVIDENCE_V2_CONTRACTS.md)
   and [bounded implementation plan](../project/SPEND_COST_EVIDENCE_V2_PLAN.md).
   Design approval/continuation permits private contracts/tests, not live calls or activation.
2. Verify exact arithmetic/category/context/overflow/zero-price-token-excess contracts; preserve
   all v1 contracts and runtime. Keep synthetic registration visibly non-authoritative.
   The [v2 reference](../project/SPEND_COST_EVIDENCE_V2_REFERENCE.md) tests fixed fixture control
   snapshots and original exact-dispatch report correlation, not native issuance/finality.
3. Independently qualify trusted loading, native preparation/count source issuance and fixed
   drift/validity/invalidation semantics before adding any real lookup capability.
4. Qualify exact-attempt native finality and unknown holds, including failures; no parser-derived
   zero release. Resolve remote-count exposure before any acquisition implementation/use.
5. Require standalone Phase 0 and the unchanged complete gate for each checkpoint. Durability,
   recovery/migration and both executor/rollout acceptance remain under ADR-0021, not this ADR.
