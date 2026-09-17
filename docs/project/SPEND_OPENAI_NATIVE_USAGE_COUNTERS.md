# Private native Responses usage counters

This second pure slice follows the user-approved private implementation of proposed
[ADR-0022](../adr/ADR-0022-bounded-provider-cost-evidence-acquisition.md), based on merged
`main@0ac0193` (PR #269). It parses a native **usage fragment only**, not a full Response,
HTTP exchange or SSE lifecycle. It does not acquire or issue trusted cost evidence.
The [input-count projection](SPEND_OPENAI_INPUT_COUNT_PROJECTION.md), private version-one
contracts, legacy JSON/SSE normalization, serving, dependencies, configuration and routing
remain unchanged. No public contract or expanded pricing model is introduced.

## Closed native counter subset

The Responses usage schema inspected on 2026-09-17 contains input/output/total counters,
input details for cache reads and writes, and output details for reasoning.
[Official Responses reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

`adapters/openai_responses_usage.py` requires exactly these native members:

- `input_tokens`, `output_tokens`, `total_tokens`;
- `input_tokens_details` with `cached_tokens` and `cache_write_tokens`;
- `output_tokens_details` with `reasoning_tokens`.

`parse_openai_responses_usage_counters` accepts bounded plain bytes containing that JSON
object. Its frozen/slotted `OpenAIResponsesUsageCounters` preserves six mandatory plain
nonnegative integers, including explicit zero, each within signed 64-bit range. There are
no defaults for absent categories. Direct construction independently enforces these rules.
Totals must equal input plus inclusive output; reasoning cannot exceed output and is not
added a second time. Each cache counter must not exceed input.

Combined cache reads/writes exceeding input are **unsupported** by this conservative
closed subset, even if each individually fits. This restriction is not a provider-wide
partition guarantee or evidence about billing semantics. No uncached category is derived,
no price/formula is applied and no count is clamped to a request, context or budget cap.
Truthful representable excess remains visible for a future independently qualified issuer.

Missing/null/malformed members or inconsistent counters raise sanitized `INVALID_STATE`;
additional unknown dimensions in otherwise complete objects raise `UNSUPPORTED`, even
when zero, empty or disabled. Full response/event objects, count-endpoint observations and
legacy normalized usage are not this native fragment and cannot substitute for it.

## Privacy and authority boundary

The parser shares the existing strict JSON loader: duplicate members at any depth,
nonfinite constants, invalid UTF-8, non-object roots and excessive nesting are rejected.
A 64 KiB ceiling bounds parser input allocation; it is not a token estimate or cost bound.
Failures suppress exception chaining and contain neither report values nor raw errors.
No raw body, prompt, completion, identifier, credential, header or transport is retained.
Counter fields are hidden from repr; freezing and repr hiding are not ACLs or encryption.
Do not serialize private counters into public responses, journals, logs/traces/Operations
or metric labels. There is no production caller, export or runtime hook in this slice.

Parsing does not validate response identity/model/service tier, preparation/dispatch
correlation, execution/slot/owner/fences, authorization, incomplete details, terminal
semantics or report provenance. An entirely explicit zero object still does not prove
complete zero usage, remote finality or permission to release a reserve. These values
cannot implement version-one bound/finality ports or create admission/replay authority.

## Controlled verification and next boundary

Contract tests cover exact integers, zero versus absence, inclusive reasoning, cache
restrictions, truthful excess, invalid/unknown/duplicate/bounded JSON, direct constructor
validation, immutability and sanitized surfaces. Local fake JSON/SSE transports exercise
the unchanged native adapters: public usage/events and SSE closure stay unchanged while
the separate fixture fragment preserves native details. Fixture extraction is not trusted
production ingestion and proves neither provider acceptance nor authenticated finality.
Concurrent pure parsing tests do not establish throughput or latency guarantees.

Trusted preparation/count issuance, complete versioned pricing and exact-attempt native
finality qualification remain unimplemented. Before remote use, independently review
count charging/retention/rate limits, fresh authorization and finite control deadlines.
Durable all-attempt accounting, recovery and both executor integrations remain later
prerequisites. No live call, credential read, model/ranking change or activation is included.

The next boundary is proposed [ADR-0023](../adr/ADR-0023-versioned-cache-category-cost-evidence.md)
and its [private v2 implementation plan](SPEND_COST_EVIDENCE_V2_PLAN.md). The continued
[v2 contract slice](SPEND_COST_EVIDENCE_V2_CONTRACTS.md) implements declarations/arithmetic/
ports/tests only, not real pricing, issuance or native finality. This parser acquires no
evidence authority and its code remains unchanged.
