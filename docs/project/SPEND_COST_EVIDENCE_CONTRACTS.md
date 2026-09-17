# Private spend cost-bound and usage-finality contracts

These private contracts continue [ADR-0021](../adr/ADR-0021-conservative-spend-admission-and-settlement.md)
from merged `main@36aa9d6` (PR #267), now accompanied by a separate
[synthetic lookup/reference](SPEND_COST_EVIDENCE_REFERENCE.md) and manual local composition tests.
Neither slice adds a tokenizer, verified provider capability, configuration loader, durable store,
runtime reference-state integration, executor wiring or activation. Existing
[admission contracts](SPEND_ADMISSION_CONTRACTS.md), [local reference](SPEND_ADMISSION_REFERENCE.md)
and observed-spend/serving behavior are unchanged. Import these private modules directly, not as
public SDK/API/SSE contracts or facade exports.

## Declared version-one values

`domain/spend_cost_evidence.py` defines five frozen/slotted shapes, each requiring exact version
`1.0`, plain bounded scalar types and canonical lowercase SHA-256 provenance:

- `SpendPreparedTextBinding`: opaque gateway-local preparation handle, deployment/API family,
  exact policy epoch and policy/plan/registry/retry digests, positive output limit and closed shape.
  The issuer must bind the actual immutable native preparation/model/configuration. A handle is
  not a payload hash, caller request ID, public response ID or authorization token.
- `SpendTextCostModel`: declared pinned input/output USD-per-million rates for one API family.
  Plain finite nonnegative Decimals only; exponent `-12..18`, at most 31 coefficient digits and
  magnitude at most `2**63-1`. Unsupported representations are refused, not rounded/repriced.
  This bounded encoding is a deliberately restrictive internal model, not a new registry schema.
- `SpendTextCostBound`: binding/model, explicit nonnegative all-input token bound, estimator and
  usage-contract digests, and privately issued bound-evidence handle. The declared output bound
  is the binding's output limit; a future adapter must prove it caps **all charged output**.
- `SpendUsageFinalityRequest`: bound, exact reserved dispatch receipt and private report handle.
  Construction correlates policy/plan/registry/retry, deployment, price, evidence and amount.
  Report/receipt issuance and exact owner/attempt correlation are independent adapter obligations.
- `SpendTextUsageFinality`: mandatory final input/output counts, including explicit zero, and
  private usage-evidence handle under that request's same pinned cost/usage model. Missing or
  provisional usage has no instance of this value; there is no implicit zero default.

The only declared shape is `text_input_output_v1`. It excludes schemas, tools/tool results, media,
reasoning, provider cache tiers, server tools, flat fees and other charge dimensions. An API-family
name/shape enum does not approve a provider or verify its charge semantics. There is no approved
API/model combination in this slice; a future trusted capability must inspect the retained exact
native request and deny unsupported/missing dimensions before enabled-mode admission.

## Arithmetic and correlation, not admission

Rates are represented exactly as rational numbers. Because USD-per-million times token count is
already micro-USD, sum both dimensions and ceil once using integer arithmetic, independent of the
caller's Decimal precision/rounding/traps. Counts, amounts and allocation projections must fit
`0..2**63-1`; policy epochs/output limits/attempt numbers are positive. Legacy conversion is intact.

`bound.allocation(...)` projects the same amount, pricing digest and evidence into an existing
attempt value. It does not verify slot authorization, complete retry/fallback coverage or reserve
capacity. `finality.settlement()` preserves the exact dispatch/owner/slot and usage-evidence handle;
it neither validates provider finality nor acknowledges a journal write. Provider-reported total
cost is not an input. Reserve/dispatch/settle/close transitions remain in their existing ports.

Representable usage above token/cost bounds stays truthful, never clamped. Both token and cost
violations are exposed; a token-bound violation must invalidate the affected model even where
free pricing or micro rounding hides a monetary excess. The generic settlement alone cannot
carry that token-violation flag. Future integration must retain/check the finality value and signal
the model violation before new admissions/claims; no suspension integration is supplied here.
Unrepresentable truthful cost raises rather than manufacturing zero or releasing a hold.

## Consumer-owned capabilities

`application/spend_cost_evidence.py` supplies two synchronous no-I/O Protocols:

- `SpendCostBoundPort.bound(binding)` independently resolves trusted preparation and pinned
  configuration/tokenization/pricing/finality capabilities. Unsupported/unavailable/invalid or
  conflicting evidence raises a generic closed-category `SpendCostEvidenceError`, not a padded
  estimate, free default or provider-transient retry classification. Return binding must match.
- `SpendUsageFinalityPort.finalize(request)` validates privately retained exact-attempt report
  issuance/completeness under the same pinned versions. `None` means an inspected supported source
  cannot establish complete final usage: keep the entire hold unknown. Missing/corrupt/foreign
  handles, unavailable configuration, unsupported dimensions and conflicts raise, not `None` or
  zero. Return request must match. No implicit report conversion or fallback is implemented.

These ports acquire no budget, authorize nothing, perform no network/provider/storage/remote
tokenizer I/O, publish/reset/renew/recover no state and create no logs. A future caller must verify
returned correlation and evidence issuance; equality alone cannot do so. Public final usage,
normalized usage defaults, HTTP success/error, EOF, empty output or cancellation do not prove zero
or complete provider cost. Failed/partial attempts still need separately verified finality or
unknown retained exposure. Late unknown-to-known reports require future trusted reconciliation.

## Privacy, proof and follow-up

Default repr hides attribution/provenance/handles/fences, not encryption or ACLs. Do not serialize
these private values with `asdict` into public responses, logs/traces/Operations or metric labels.
Retained native requests/reports belong behind scoped adapter capabilities; payloads, prompts,
completions, credentials, headers and raw errors do not belong in these metadata values. Bound and
usage evidence must have explicit issuer/lifetime/retention rules before operational integration.

Synthetic tests prove shape, immutable correlation/projections, exact upward arithmetic, invalid
metadata/rates/overflow refusal, explicit unknown versus zero, excess visibility and port permission
signatures. Separate reference tests add finite synthetic lookup/manual composition evidence,
not real issuance or finality. They do not prove real tokenization, complete charged dimensions,
provider acceptance,
billing, finality/issuance, distributed admission, cancellation cleanup, durability or serving.
Next review a real bounded API/model capability with strict trusted configuration and retained
preparation/report provenance, including unsupported-shape tests. Durable storage/recovery and both
executor integrations remain separate prerequisites before any explicit opt-in rollout.
