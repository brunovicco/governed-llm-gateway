# Structured Extraction Benchmark

`structured_extraction` is the reference workload for the gateway benchmark pipeline:

`dataset -> runner -> deterministic scorer -> scorecard -> immutable snapshot -> explicit promotion`

The benchmark remains offline-first. It does not call another LLM, does not use network access in the scorer, and does not receive runtime routing or authorization authority.

## Versioning

`structured-extraction-v1` and scorer `structured_extraction_v1` remain frozen compatibility evidence. They are not rewritten in place because changing a versioned dataset or scorer would change historical benchmark meaning.

`structured-extraction-v2` and scorer `structured_extraction_v2` are the reviewed reusable contract for new structured-extraction runs.

## Dataset boundary

The v2 dataset is public, synthetic, credential-free, and intentionally small. It covers strings, integers and decimals, booleans, nullable values, enums, nested objects, arrays of scalars and objects, optional absent fields, irrelevant source fields that must not become outputs, and values that can be schema-valid while still semantically wrong.

Every case carries a bounded output schema. Object schemas must set `additionalProperties` to `false`; nested objects repeat the same rule and arrays require an explicit item schema. Unknown schema or metadata fields fail closed.

The scorer consumes normalized `JsonValue` output only. A string containing JSON is not parsed as JSON; it is an incompatible output and scores zero. This prevents permissive parsing from hiding model contract failures.

## Deterministic scoring

The v2 assessment exposes two independent components:

- `schema_score`: `1` only when the complete output satisfies the reviewed schema, otherwise `0`;
- `value_score`: exact, type-sensitive leaf-value accuracy against the reviewed expected output, including nested paths and array positions.

The scalar score consumed by `BenchmarkRunner` is `score = (schema_score + value_score) / 2`.

Exact output therefore scores `1`. Partial output remains measurable, but any schema violation is visible independently from semantic value accuracy. No fuzzy matching, embeddings, model-as-judge, or network lookup is used.

## Explainability

`assess_structured_extraction_v2()` returns stable issue codes with JSON-pointer-like paths. Current reason codes include `missing_required_field`, `missing_expected_field`, `unexpected_field`, `unexpected_extracted_field`, `wrong_type`, `wrong_value`, `enum_violation`, and `array_length_mismatch`.

The generic benchmark observation and snapshot contracts continue to persist the scalar quality score. The workload-specific assessment is additive so later workload scorers are not forced into a new framework or snapshot schema migration.

## Quality versus availability

A completed provider call is assessed by the v2 scorer and is either `succeeded` or `quality_failure` under the existing `BenchmarkRunner` threshold. Provider timeouts, rate limits, outages, and other provider failures remain `provider_failure` with `quality_score = None`.

Scorecards, content-addressed snapshots, and Phase 11 promotion therefore preserve the existing separation between model quality and provider availability.

## Promotion boundary

Promotion remains explicit through `PromotionMapping`. A promoted benchmark artifact has no authority to widen policy authorization, enable a deployment, or mutate runtime routing by itself. Missing or inconsistent quality evidence fails closed before promotion.
