# Synthetic spend cost-evidence reference

This continues the private [cost contracts](SPEND_COST_EVIDENCE_CONTRACTS.md) under proposed
[ADR-0021](../adr/ADR-0021-conservative-spend-admission-and-settlement.md). It adds finite read-only
fixtures and manual local composition tests, **not a verified cost estimator or provider finality
capability**. No provider family/model is approved. Serving/bootstrap, executors, public contracts,
configuration, dependencies, legacy SpendGuard and admission-state transitions are unchanged/off.

## Independent synthetic fixtures

`adapters/spend_cost_evidence_synthetic.py` contains four frozen/slotted private values:

- `SyntheticSpendPreparedText` retains one exact canonical `ProviderRequest` and declared cost
  bound. Only plain immutable system/user/assistant text is accepted, with the same explicit
  output limit. Legacy images, nontext blocks, tool transcripts/results, schemas, tools, mutable
  containers, subclass substitutions and invalid timeout/representation inputs are refused.
  This is not the provider-native payload, full configuration, input expansion or tokenizer.
- `SyntheticSpendCostBounds` freezes a nonempty finite preparation inventory. Lookup accepts
  only its exact registered binding; unknown handles raise, changed bindings conflict. It does
  not register caller input, infer token counts or mint new evidence/dispatch rights on a read.
- `SyntheticSpendUsageReport` explicitly pairs an exact request with either complete counts or
  `None` for an inspected incomplete synthetic source. Both fields are mandatory. Normalized
  `ProviderUsage` defaults are not a source or evidence; absent reports never become zero/None.
- `SyntheticSpendUsageFinality` independently freezes declared bounds, preapproved dispatches and
  reports. A report must belong to both inventories and its exact execution/owner/slot/fences.
  Bound/report/evidence identities and dispatch slots cannot be ambiguously reused; a pricing
  digest cannot name conflicting rates. No update, reset, publication, recovery or replay exists.

The only accepted API-family marker is `synthetic_text_v1`; real provider-family markers are
explicitly rejected. These wrappers structurally match the private port signatures **for synthetic
tests only**. They do not meet the ports' production tokenization/issuance/finality obligations.
Fixture construction is a test controller assumption, not authentication, trusted configuration,
receipt issuance, exact native preparation or cryptographic evidence validation. Reconstructing a
wrapper does not recover old authority or history. Identical value clones can resolve the same
fact without creating new dispatch permission; equality is not external evidence authentication.

## Unknown, zero, excess and manual composition

Successful reads return the exact retained bound/finality object without mutation or I/O. An
explicit registered incomplete source returns `None`. Missing/foreign handles raise `unavailable`,
changed registered facts raise `conflict`, real API families raise `unsupported`, and invalid
values or modeled invalid fixture state raise `invalid_state`. All capability errors have generic
closed-category messages with suppressed exception chaining, not raw payloads/provider errors.

Complete zero counts are distinct from unknown. Exact pinned rational pricing and truthful
representable excess remain in the finality value; lookup does not clamp them or release holds.
Token violations remain visible even at free prices. Projection to generic `SpendSettlement`
still loses the token-violation flag: future integration must invalidate/suspend affected models
before further admissions/claims, including nonmonetary violations. This reference adds no such
signal to the worker and must not be used as an activation shortcut.

`test_spend_cost_evidence_synthetic.py` manually composes the finite lookup with the existing local
admission reference. Under explicit synthetic opening state/intents/usage validation, it reserves
all slots, claims one, applies known usage once or retains unknown exposure, and closes only unused
slots across daily/monthly client/workload buckets. Exact duplicate settlement/close does not
double-charge. Truthful monetary excess uses the existing deployment suspension. There are no real
executor/coordinator calls, provider requests, HTTP/SSE completion or cancellation-cleanup claims.

## Privacy and proof boundary

Retained text remains only in the private canonical preparation fixture, never in budget metadata,
journals or usage reports. Every fixture/capability field is hidden from default repr. No logs,
traces, credentials, remote reads, payload serialization or public/facade exports are added. Repr
hiding and frozen Python objects are neither encryption/ACLs nor protection against privileged
in-process tampering. Validation detects modeled invalid shape/state, not arbitrary replacement of
all internally consistent facts or whole-process loss. Keep private objects out of `asdict`, public
responses, Operations and metric labels, as required by ADR-0008.

Synthetic tests cover strict text shapes, independent registration, changed provenance/price/bound,
cross-execution/report/owner/slot reuse, unknown versus zero, excess flags, ambiguous bootstrap,
frozen/private surfaces, concurrent pure reads, invalid-state sanitization and manual conservation.
They do not prove real tokenization, enforceable charged-output limits, complete charge dimensions,
provider finality/acceptance, billing, strict production loading, durable/distributed admission,
recovery/retention, cancellation closure or serving enforcement. No throughput/latency is measured.

For example, Anthropic documents its token-counting result as an estimate that may differ from
actual input usage. That alone is not the verified upper bound required by this proposal; no
padding or inference from context capacity is introduced. See the
[official token-counting documentation](https://platform.claude.com/docs/en/build-with-claude/token-counting).

Next require a separately reviewed real bounded API/model capability with trusted pinned
configuration and verified complete input/output/finality semantics. A durable backend and both
executor integrations remain later prerequisites before explicit opt-in activation.

The [Responses candidate assessment](SPEND_OPENAI_CAPABILITY_ASSESSMENT.md) records the next
feasibility review and links the user-approved private acquisition/pricing design.
The subsequent [pure projection/parser slice](SPEND_OPENAI_INPUT_COUNT_PROJECTION.md) does not
perform acquisition or issue a verified bound.
It is not provider approval or a relaxation of these synthetic proof boundaries.
