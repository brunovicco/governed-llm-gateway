# ADR-0022 — Bounded provider cost-evidence acquisition

## Status

Proposed for implementation review — design approved by the user for private implementation.
The first slice implements pure native text count projection and strict count observations only;
remote acquisition, trusted issuance and expanded pricing are not implemented or qualified.
It does not supersede accepted ADR-0017, change private version-one cost contracts, approve a
provider/model, or authorize serving activation, paid calls or infrastructure provisioning.

## Date

2026-09-17

## Context

Baseline: `main@005b17ee6cd0f2575b5126e9d4bf05c64534bc12` (PR #268).
Proposed [ADR-0021](ADR-0021-conservative-spend-admission-and-settlement.md) requires complete verified
cost bounds before admission, exact-attempt final usage, retained unknown exposure and later durable
all-scope accounting. Its private values/ports and synthetic reference do not qualify a real provider.

The [dated Responses assessment](../project/SPEND_OPENAI_CAPABILITY_ASSESSMENT.md) records inspected
adapter/configuration paths and official sources. A documented remote exact-input counter is a
candidate, but cannot run inside synchronous pure preflight or cost-bound lookup. The current native
Luna configuration also has charge/usage dimensions outside the private two-rate text-only shape.
Current normalized usage cannot independently establish complete-zero or exact-attempt finality.

## Decision

### Proposed acquisition phase, separate from pure preparation

The approved design proposes a bounded **asynchronous acquisition phase** after fresh
authentication/PDP authorization, deterministic ranking and pure preparation of the existing bounded
candidate sequence, but before budget admission and before HTTP response commitment/generation I/O.
Pure preparation and existing synchronous bound/finality ports remain no-I/O.
This would introduce provider metadata I/O before HTTP response commitment, not generation during
preflight; that observable latency/failure change requires explicit review before implementation.

Acquisition may inspect only the exact retained native preparations of already-authorized candidates.
Use an adapter-owned immutable input-count projection derived from the same authoritative preparation
as dispatch, not a reconstructed canonical request or caller estimate. Define explicit issuer,
model/configuration/pricing/usage-contract provenance, correlation, finite validity and invalidation
rules. Return private issued evidence for pure lookup; do not change existing lookup into remote I/O.
No inference receipt is minted and no budget/authorization/replay authority is acquired by counting.

Preserve prompt-free PDP requests and existing prepared-request reuse. Do not put a tokenizer in
domain, add public count/receipt fields, enumerate global models or weaken deterministic preparation.
Do not prune defective/unqualified fallbacks silently. Every possible slot of the original bounded
plan must qualify and be reserved before generation; unsupported enabled-mode plans deny.

Any remote counting request needs its own reviewed charging and exposure semantics before dispatch.
If it can spend, an independently verified bound and accounting must precede it; lacking that proof,
deny instead of creating unbudgeted pre-admission spend. No assumption that a metadata API is free.
Define finite configuration-owned control deadlines, cancellation/resource closure and sanitized
errors. Do not derive a total deadline from policy `max_latency_ms` or silently reuse provider timeout.
Authorization single use/expiry/revocation remains authoritative; acquisition cannot refresh or cache
authorization. Review authorization lifetime at subsequent admission/dispatch boundaries.

### Proposed separate versioned cost model

Review a new private versioned shape for one explicit text-only API/model/configuration rather than
alter the meaning of `text_input_output_v1`. Its exact pricing schedule must distinguish every
supported input category, generated output, context threshold and processing/region profile.
Reasoning output cannot be added twice to an inclusive generated-token total. Every dimension needs
an independent bound and reviewed complete-final-usage interpretation; unsupported dimensions deny.
No specific rate, model snapshot identifier or production configuration is accepted by this ADR.

A possible conservative admission formula uses verified total input times the maximum applicable
input-category rate plus the enforced inclusive output limit times the applicable output rate,
with reviewed context/profile applicability and one upward conversion. This is not approved here:
prove full category coverage/partitioning and threshold/output-rate dependence first.
Settlement would use complete native category usage under that same pinned schedule, not substituted
registry projections, provider-reported money or retroactively fetched prices.
State precisely that settled figures are modeled estimates, not an invoice guarantee.

Keep native evidence parsing/issuance behind adapters, deterministic arithmetic/values in private
domain and acquisition coordination behind application ports. Existing synthetic fixtures and
version-one tests remain unchanged; new shapes require their own contracts and tests.
Retain truthful token/cost excess, including token violations hidden by zero pricing/rounding,
and require affected-model suspension/invalidation before new admission/claims.

### Preserve finality and later prerequisites

Do not use `ProviderUsage()`, HTTP status, terminal event names, EOF or cancellation as cost evidence.
Any supported complete report must independently bind its issued preparation and exact dispatch
execution/owner/slot/fences and validated raw usage/model/profile. Uncertain or unsupported usage
retains the full allocation; explicit zero requires complete evidence. Recovery must not replay
inference. Late reconciliation and durable storage remain separately reviewed work.

This design proposes neither a backend nor executor integration. Durable atomic admission/journal,
recovery/migration/retention, all-attempt accounting, acknowledged settlement before public completion,
HTTP abandonment cleanup and explicit opt-in rollout remain required under ADR-0021.

## Alternatives considered

- Local character/byte division, padded caller counts or assumed message overhead: not a verified
  native-input bound; rejected without independent proof.
- Call the remote counter inside `prepare`/`bound`: violates the no-I/O contract; rejected.
- Accept configured context capacity or two registry prices as capability proof: missing charged
  dimensions/correlation; rejected.
- Set the existing input rate to a worst-case number silently: changes version-one semantics and
  hides category/settlement obligations; rejected.
- Retain only observed-spend semantics: valid current behavior, but does not close the admission
  race. Serving remains unchanged until a separately verified opt-in implementation.
- Choose another API/model with a documented pure estimator and complete simpler charging:
  remains possible. No cross-provider feasibility comparison or live benchmark has been performed.

## Consequences

Remote acquisition could provide documented native-input evidence without corrupting pure preflight,
but adds provider dependency, latency and payload transmission even when later admission refuses.
It may consume rate limits and possibly money; both require explicit review. Binding server behavior
over count-to-dispatch time is a qualification obligation, not solved by a local SHA-256 digest.
The proposed pricing shape is more complex and intentionally narrow. Documentation or fixture
conformance alone does not prove a real bound, finality, durability or a hard billing ceiling.

## Security and privacy impact

Acquisition can only narrow the existing PDP-authorized sequence. It grants no model/group/tool,
retry/fallback or business-action authority. No new permanent-error or post-semantic replay.
Counting would transmit native input to a provider before generation; review classification,
endpoint/account retention and consent/exposure requirements before enabling it.
Prompts, completions, native payloads, credentials, headers and raw errors remain excluded from
budget journals, public receipts, logs/traces/Operations and default evidence under ADR-0008.
Private count/usage handles are neither authentication tokens nor encryption.

## Operational impact

No current runtime/configuration/dependency/ranking changes. A future implementation needs an
explicit closed opt-in profile and operational evidence for deadlines, capacity, error mapping,
payload retention, rate limits, evidence validity and provider drift. No silent local estimator,
legacy spend fallback, price refresh, cold balance or keyspace reset.
Both JSON and streaming paths must eventually share the same acquisition/admission protocol;
explain-only routes remain provider-free. Provider outages deny enabled-mode qualification rather
than manufacture zero, widen authorization or expose raw error details.

## Follow-up

The [first private projection/parser slice](../project/SPEND_OPENAI_INPUT_COUNT_PROJECTION.md)
retains actual native bytes without runtime integration. Its observations are not trusted evidence;
no remote request, admission or finality is authorized by constructing them.

1. Design approval permits focused private implementation/tests, not serving or live calls.
   Review the separate pricing shape and remote-use proof obligations before expanding this slice.
2. Resolve count charging/retention and model/configuration/version/finality proof obligations
   listed in the assessment; keep an unqualified combination unavailable.
3. Propose small implementation slices with files, controlled tests, risks and acceptance criteria:
   trusted native preparation/count issuance, expanded exact pricing, native complete-usage
   validation, then separately reviewed configuration and acquisition orchestration.
4. Run focused credential-free tests, standalone Phase 0 and the unchanged complete quality gate.
   Scope any live provider proof separately; no benchmark/ranking artifacts without authorization.
5. Keep durable backend, recovery and both executor integrations separate before explicit rollout.
