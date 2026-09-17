# Spend cost evidence — OpenAI Responses candidate assessment

Date: 2026-09-17

Inspected baseline: `main@005b17ee6cd0f2575b5126e9d4bf05c64534bc12` (PR #268).

This is a documentation-only assessment, not an approved provider capability, live proof or
implementation. The subsequent [private projection/parser slice](SPEND_OPENAI_INPUT_COUNT_PROJECTION.md)
implements pure wire helpers only, not remote counting or model qualification.
OpenAI Responses is the first **candidate for further verification** because the
repository already implements its native JSON/SSE translations and an official input-count API
exists. This is not a comparative provider benchmark or a recommendation to change routing.
[ADR-0022](../adr/ADR-0022-bounded-provider-cost-evidence-acquisition.md) proposes the next design
boundary; its design is approved for private implementation, but the ADR remains proposed and
does not supersede any serving contract.

## Repository evidence

Paths below are relative to `packages/gateway-core/src/governed_llm_gateway_core/`:

- `adapters/openai_responses.py` builds `model`, `store=false`, `max_output_tokens`,
  `input` and optional `instructions`/schemas/tools. It does not set `service_tier`, explicit
  reasoning or prompt-cache options. System messages are joined into instructions; canonical
  message translation, not raw caller text, is therefore the input to count.
- `adapters/openai_responses_streaming.py::prepare_stream` freezes a serialized native request
  in an opaque `PreparedProviderStream`. It performs no network I/O. That object provides no
  separate cost-count projection or independently issued native-preparation evidence.
- JSON `_extract_usage` returns `ProviderUsage()` when usage is absent and defaults absent
  counters to zero. SSE requires a usage mapping on `response.completed`, but shared
  `adapters/streaming_common.py::provider_usage` also defaults absent counters to zero.
  Neither translator retains the native cache-write/cache-read breakdown or actual service tier.
  These are existing normalization facts, not allegations of a broken current spend admission
  control: the proposed control is not composed into serving.
- `application/provider.py::ProviderUsage` has optional cache-read/cache-write counts, but no
  evidence-issuance, native-request, attempt-owner/fence or finality binding. Its default values
  cannot be used as independently verified complete-zero reports.
- `domain/spend_cost_evidence.py` deliberately limits version one to two-rate text with no
  reasoning/cache dimensions. `application/spend_cost_evidence.py` ports are synchronous,
  no-I/O lookups. The synthetic adapter accepts only `synthetic_text_v1`, not real API families.
- `config/profiles/personal-default/model_registry.yaml` declares `gpt-5.6-luna` and only
  input/output price metadata. The active ranking remains `rag.answer` in `balanced`.
  Context capacity, configured price labels and historical live runs do not qualify a cost bound.

## Official documentation checked

These are dated observations from current official documentation, not an immutable provider
agreement or confirmation of the local account/project settings.

The token-counting guide describes an exact count for the model's input, including request-formatting
tokens, when the corresponding native input is supplied. This makes remote counting a stronger
candidate than character division or a locally guessed message overhead. It does not remove our
obligation to preserve request/model/configuration correlation between counting and dispatch.
[Official token-counting guide](https://developers.openai.com/api/docs/guides/token-counting).

The count endpoint is `POST /v1/responses/input_tokens`. Its response has `input_tokens` and
`object=response.input_tokens`; it does not return a request digest, model snapshot, expiry or
versioned count-to-dispatch receipt. Gateway-owned issuance/provenance would therefore be needed;
the numeric response alone is not our internal bound evidence.
[Official count reference](https://developers.openai.com/api/reference/typescript/resources/responses/subresources/input_tokens/methods/count).

Responses documents `max_output_tokens` as including visible output and reasoning tokens.
An omitted `service_tier` defaults to `auto`; the actual response tier may differ from the
requested tier. The response usage schema has input/output totals and cache/read-write and
reasoning details. These facts support a candidate output cap and native usage parser, not a
complete cost/finality proof for every status.
[Official Responses reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

Prompt caching is enabled by default on supported models. Input can use uncached, cached or
cache-write pricing; cache-write pricing replaces the corresponding input rate rather than being
an additive charge. Full rendered input can include provider-supplied instructions.
Consequently, `store=false` must not be treated as proof that prompt caching is disabled.
[Official prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching).

For the locally configured Luna model, the model page documents default `reasoning.effort=medium`,
cache-write pricing at 1.25 times uncached input, and whole-request long-context multipliers above
272K input tokens. Its snapshot section does not provide a distinct dated identifier we can
silently invent or pin. These properties are outside the current two-rate text-only evidence model.
[Official Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

The current standard pricing table separately lists short/long-context input, cached input,
cache-write and output rates, plus processing/residency qualifications. The two registry rates
are not a complete capability-approved pricing schedule. No prices, approved ranking artifacts
or runtime configuration are changed by this assessment.
[Official pricing](https://developers.openai.com/api/docs/pricing).

## Qualification result

| Obligation | Evidence found | Result for present private version one |
| --- | --- | --- |
| Exact native input including formatting | Official remote count; private projection only, no acquisition/issuance | No verified bound or qualification |
| All generated output bounded | Documented inclusive output limit | Candidate guarantee; model/shape still unqualified |
| Complete pinned charge dimensions | Cache, reasoning, context and processing distinctions | Not representable by current scope |
| Exact-attempt complete final usage | Native usage fields; current defaults lose absence/detail | No trusted finality capability |
| Pure preflight and lookup | Current synchronous no-I/O boundaries | Preserve; remote calls do not belong inside them |
| Durable all-attempt accounting | No durable journal/backend/coordinator wiring | Still a separate later prerequisite |

Engineering conclusion: **do not approve any real API/model through version one** and do not
activate spend admission. The candidate merits a separately reviewed acquisition/pricing design,
not another synthetic fixture presented as production evidence. This does not imply that existing
inference must stop, or that every supported provider has the same limitations.

## Proposed verification scope

Start with one explicitly pinned Responses model/configuration and immutable text-only native
input. Exclude schemas, tools/results, media, hosted tools, remote files, provider-managed
conversation history, previous-response state, compaction, background processing and caller-selected
native options. Explicit local text-message history remains part of the exact counted input.
Pin an explicitly reviewed processing/region/pricing profile, output limit and reasoning setting.
These are proposed cost-capability restrictions, not changes to current registry eligibility.
Even a non-reasoning setting must account for all non-visible generated tokens.

Before acquisition/pricing code or activation, review the proposed asynchronous boundary and a separate
versioned pricing shape. Keep current version-one values/ports unchanged. A conservative maximum
rate for admission and detailed same-schedule settlement are a design option, not an implicit
reinterpretation of version-one input/output rates. Counts must cover the entire charged input;
discounts, zero prices or upward rounding never excuse a violated token bound.

Required proof and tests beyond the pure projection/parser slice:

1. One authoritative immutable native preparation supplies both count projection and dispatch.
   Verify instructions, role/order, input content, model and every input-affecting option.
   Changed preparation/pricing/model/tier or expired/foreign/missing evidence denies without
   admission or generation. No payload hash exposed publicly or stored in the budget journal.
2. Document count endpoint charging, retention, rate limits and failure semantics before remote
   use. If counting itself can spend, bound/account for it before dispatch or deny the capability;
   do not exempt it by naming it preflight. Apply fresh authorization and gateway-owned finite
   timeout/cancellation limits before any count call. No global-model enumeration or permanent-error
   fallback. Count controls never replay generation.
3. Bind trusted configuration, pricing/context threshold, API/model provenance and evidence lifetime.
   Verify count-to-execution drift conditions rather than assuming a price digest pins the server.
   A live comparison can falsify a bound but cannot alone prove it for every supported input.
4. Validate mandatory raw usage fields and input-category partition rules under the reviewed native
   contract. Missing/null/provisional counters are never zero. Avoid counting reasoning twice.
   Correlate model, actual processing tier, response identity and exact issued dispatch slot.
   Complete-zero evidence must be explicit. Failed/incomplete/cancelled/invalid semantic output
   needs separate finality review; unsupported or uncertain reports keep the entire allocation.
5. Price every supported dimension exactly once with one pinned schedule and upward arithmetic.
   Test cache-category ambiguity, long-context threshold boundaries, free-price token excess,
   actual-tier/configuration conflicts and overflow. Preserve truthful token/cost violations and
   suspend affected future admissions/claims; never clamp or release uncertain exposure.
6. Use credential-free controlled JSON/SSE/count fixtures first, then unchanged Phase 0 and full
   repository gates. Separately authorized governed live proof must retain normal PDP/ranking,
   configured credentials, metadata-only evidence and no new benchmark/ranking artifacts.

No count or inference request, benchmark, latency measurement, provider credential read, storage
provisioning or rollout was performed for this assessment. Approval of its design is not approval
of live calls, backend selection or serving activation.
