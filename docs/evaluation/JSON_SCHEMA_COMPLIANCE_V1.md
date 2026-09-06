# JSON Schema Compliance Benchmark v1

Status: **COMPLETE — merged in PR #61.**

## Purpose

`json-schema-compliance-v1` measures whether normalized model output satisfies a reviewed
JSON Schema. It is the roadmap-listed `JSON/schema compliance` class and is intentionally
separate from `structured-extraction-v2`.

`structured-extraction-v2` evaluates two dimensions: schema validity and exact extracted
values. This workload evaluates only schema compliance. A different value can score 1.0
when it remains valid under the reviewed schema.

## Versioned contract

- workload: `json_schema_compliance`
- benchmark version: `json-schema-compliance-v1`
- contract version: `1.0`
- scorer: `json_schema_compliance_v1`
- data classification: `public`
- cases: six synthetic cases
- reviewed language: `en`
- scoring: binary schema compliance
- LLM-as-judge: none

The six cases cover:

- flat object shape and required fields;
- nested objects and typed properties;
- bounded arrays with enum and uniqueness constraints;
- enum compliance;
- nullable values;
- integer/number bounds.

## Reused Phase 7 schema boundary

Benchmark schemas are validated through the existing provider-neutral Phase 7 structured
output boundary before they can become benchmark ground truth. That boundary uses Draft
2020-12 validation with the gateway's existing safety constraints, including bounded schema
size/depth and rejection of remote references, `pattern`, `patternProperties`, and `format`.

The benchmark does not introduce a second JSON Schema dialect and does not expand runtime
schema support for evaluation convenience.

## Prompt materialization

Each canonical prompt includes the exact reviewed schema in deterministic compact JSON
with sorted object keys. Dataset validation recomputes that representation and fails closed
on prompt/schema drift.

The model is asked to return any JSON value permitted by the schema. The checked-in
`expected` value is only a reviewed satisfiable reference example used to validate the
benchmark case; it is not an exact-value scoring target.

## Deterministic scoring

For normalized `JsonValue` output:

- schema valid -> `1.0`;
- one or more schema violations -> `0.0`.

The assessment also exposes stable validator-derived issue codes and JSON-pointer-like
paths, for example:

- `schema_type` at `/profile/seats`;
- `schema_required` at `/`;
- `schema_enum` at `/status`;
- `schema_additionalProperties` at `/`;
- `schema_uniqueItems` at `/`;
- `schema_maximum` at `/ratio`.

No semantic correctness or extraction accuracy is mixed into this score.

## Normalization boundary

`BenchmarkRunner` consumes `ProviderCall.output` as provider-neutral `JsonValue`. By the
time this scorer runs, raw provider text has already crossed the provider/normalization
boundary.

Therefore this benchmark does **not** claim to observe malformed raw JSON text, markdown
fences, truncated transport bytes, or provider-native structured-output enforcement. Those
are execution/normalization facts and require provider/runtime evidence. This scorer only
measures whether the normalized JSON value satisfies the reviewed schema.

## Fail-closed validation

Dataset/case validation rejects, among other things:

- the wrong benchmark version;
- duplicate case IDs;
- a case count other than exactly six;
- workloads or scorers outside the reviewed v1 contract;
- unknown metadata;
- non-public/non-synthetic drift;
- malformed or empty schemas;
- schemas rejected by the existing Phase 7 bounded validator;
- reference examples that do not satisfy their schemas;
- prompt/schema drift.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Benchmark schemas, validation results, issue codes, observations and scores are quality
evidence only. They cannot:

- authorize structured output for a deployment;
- claim provider-native schema capability;
- add an unauthorized model/provider/deployment;
- force a benchmark target into routing;
- bypass ordinary gateway eligibility or policy;
- self-promote or mutate policy.

A deployment's runtime structured-output capability remains registry/policy/provider
execution data, not something this benchmark can grant.

## CI boundary

Default CI remains credential-free and deterministic:

- no live provider or network request is required;
- no external schema resolution is permitted;
- no LLM-as-judge path exists;
- checked-in public/synthetic cases are sufficient for replay;
- schema definitions and reference examples are validated before scoring.

## Non-goals

Version 1 does not introduce:

- extraction correctness scoring;
- raw JSON-text parsing benchmarks;
- provider-native schema feature tests;
- new JSON Schema runtime features;
- remote references or network resolution;
- benchmark-side model/provider forcing;
- automatic promotion or self-modifying policy.
