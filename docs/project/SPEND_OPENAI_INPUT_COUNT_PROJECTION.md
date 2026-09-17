# Private Responses input-count projection

This first implementation slice follows the user-approved design in proposed
[ADR-0022](../adr/ADR-0022-bounded-provider-cost-evidence-acquisition.md), based on merged
`main@005b17ee`. It adds **pure wire preparation and parsing only**, not remote acquisition,
trusted evidence issuance, model approval or a cost bound. Existing version-one values/ports,
synthetic lookup, serving, configuration, dependencies and routing remain unchanged.

## Private adapter surface

`adapters/openai_responses_input_count.py` contains two frozen/slotted values:

- `OpenAIResponsesTextCountProjection` retains the exact supplied native generation bytes,
  hidden from repr, and derives its count body internally. It never retranslates canonical
  messages. Direct construction also accepts the same closed JSON-shaped body without
  `stream`; it does not prepare or integrate the current JSON executor.
- `OpenAIResponsesInputCountObservation` pairs an exact projection object with a mandatory
  plain integer count, including explicit zero. This is an observation, not an issued/authenticated
  receipt, independently verified input bound, dispatch permission or final usage.

`prepare_openai_responses_text_count` accepts only a plain `PreparedSseRequest` for the literal
native Responses route, with `stream=true`. It retains that object's body bytes and never reads
or copies its headers. The route check is not provider/account authentication. No count URL,
headers, transport, timeout, credentials or remote call is prepared. The serving adapter has not
been changed to expose or invoke this helper.

The supported native body requires `model`, `store=false`, a positive explicit output limit
and nonempty local user/assistant message lists containing only `input_text` blocks. Optional
instructions, message/content order, whitespace, Unicode and empty text blocks are preserved.
Known optional fields are accepted only as an actual Boolean `stream`, `reasoning.effort=none`,
`service_tier=default` or `truncation=disabled`. No omitted defaults are inserted or qualified.
Model spelling is bounded syntax, not a pinned snapshot or eligibility check. Even an accepted
body remains unqualified for pricing, caching, server defaults and provider behavior.

The count body contains the actual model/input and only present instructions/reasoning/truncation.
Generation-only store/stream/output-limit/service-tier fields stay in the retained generation body.
The separate count API documents these input parameters and a `response.input_tokens` object
with `input_tokens`; it supplies no internal issuance or dispatch rights.
[Official count reference](https://developers.openai.com/api/reference/typescript/resources/responses/subresources/input_tokens/methods/count).

Unknown fields are rejected even when empty, null or apparently disabled: no silent dropping of
schemas, tools/results, media, remote history, compaction, cache options or native metadata.
The count parser requires exactly the expected object marker and count field; missing/null/Boolean/
fractional/negative/overflow values never become zero or unknown. Both scalar counters and output
limits fit signed 64-bit nonnegative/positive ranges, respectively.

## Safety and proof boundary

JSON parsing rejects malformed UTF-8, duplicate members at any depth, nonfinite constants,
non-object roots and excessive nesting. Native bodies are limited to 8 MiB and reports to 64 KiB
before parsing. These are private parser-allocation ceilings, not token estimates, model context
capacity, policy limits or budget caps. Invalid representations raise sanitized closed-category
errors with suppressed exception chaining. No raw count report is retained in the observation.

Native/count bodies remain sensitive private adapter state. Do not serialize these objects into
public responses, budget metadata/journals, logs/traces/Operations or metric labels. Frozen Python
objects and repr hiding are not ACLs, encryption or protection against privileged process tampering.
Parser pairing does not establish that a provider returned this count for this preparation:
controlled response correlation, trusted issuance, finite validity and model/configuration drift
checks remain unimplemented.

`test_openai_responses_input_count.py` covers exact body retention, option omission/preservation,
local history/order, strict types and unsupported dimensions, malformed/duplicate/bounded JSON,
explicit zero versus absence, immutability and sanitized private surfaces. A controlled interop
test captures the actual SSE preparation produced by the unchanged native adapter, projects that
body and verifies dispatch receives the exact same object/bytes, with normal events and closure.
It does not perform network I/O or prove provider acceptance, exact tokenization, pricing/finality,
HTTP lifecycle integration, distributed durability, throughput or latency.

Before any remote use, resolve count charging/retention/rate limits, fresh authorization and finite
control deadlines. Separately implement and qualify trusted preparation/count issuance, complete
versioned pricing and native usage/finality. Current model charge dimensions remain outside
version one; this helper cannot implement its bound/finality ports or release a reserve.
Durable all-attempt accounting and both executor integrations remain later prerequisites.
No live call, credential read, model/ranking change or activation is included.

The [next private native usage-counter slice](SPEND_OPENAI_NATIVE_USAGE_COUNTERS.md)
preserves explicit input/cache/output/reasoning totals in a separate pure parser. It does
not change this projection, turn a count observation into trusted evidence, introduce
expanded pricing or qualify native finality. Legacy JSON/SSE normalization stays unchanged.
