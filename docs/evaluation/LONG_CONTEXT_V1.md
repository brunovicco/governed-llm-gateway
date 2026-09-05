# Long Context Benchmark v1

## Purpose

`long-context-v1` adds the roadmap-listed `long context` evaluation class after the core benchmark and multimodal foundations stabilized.

It measures deterministic retrieval of a reviewed synthetic needle from different positions inside a large generated record stream. It is benchmark evidence only and does not authorize a model, expand a Policy Router decision, or force a gateway route.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Tokenizer-neutral design

The v1 contract deliberately does **not** claim an exact provider token count.

Provider tokenizers differ, and the benchmark layer must not manufacture token-level provenance that the runtime did not measure. Instead, each case deterministically materializes exactly:

```text
8192 synthetic numbered records
```

The resulting prompt is more than 300,000 characters with the current reviewed generator. The record count and generator version are stable contract facts; an exact provider-token count is not.

A future authorized live execution adapter may combine this workload with normal gateway `min_context_tokens` requirements, but that capability constraint remains a separate gateway authorization/eligibility input rather than a fact inferred from benchmark text length.

## Compact checked-in dataset

`benchmarks/datasets/long-context-v1.json` stores only the reviewed generation specification and expected result. The large prompt is generated deterministically at load time instead of committing megabytes of repeated filler text.

The dataset contains exactly three public/synthetic cases:

| Position | Needle record | Purpose |
|---|---:|---|
| `early` | 128 | retain an early fact across a long suffix |
| `middle` | 4096 | recover a fact near the center |
| `late` | 8064 | recover a fact near the end |

Every case uses the same fixed generator:

```text
numbered-records-v1
```

Non-needle records contain deterministic filler derived only from their record number. Exactly one record contains:

```text
needle=<reviewed-value>
```

The prompt asks for only:

```json
{"needle": "<exact-value>"}
```

The expected value is public synthetic benchmark data and is not sent separately to the provider.

## Fail-closed contract

The v1 loader requires:

- benchmark version `long-context-v1`;
- workload `long_context`;
- scorer `long_context_v1`;
- contract version `1.0`;
- generator version `numbered-records-v1`;
- `synthetic = true`;
- response format `needle_value_v1`;
- exactly 8,192 records;
- exactly one early, one middle and one late case;
- reviewed needle-record mapping for each position;
- normalized lowercase ASCII needle values containing only letters, digits and hyphens;
- the exact reviewed prompt instruction before materialization.

The fixed record count prevents malformed benchmark metadata from becoming an unbounded memory-allocation request.

## Deterministic scoring

The scorer accepts only an object with exactly one top-level field:

```text
needle
```

Scoring is binary:

- exact string match: `1.0`;
- wrong needle: `0`;
- wrong value type: `0`;
- missing/extra top-level fields: `0`.

Stable issue codes include:

- `invalid_output_shape`;
- `wrong_value_type`;
- `wrong_needle`.

No LLM-as-judge, fuzzy semantic similarity, network access, generated-code execution, tool execution or agent execution is used.

## Reproducibility

`load_long_context_dataset(...)` returns the **materialized** benchmark cases. Therefore the existing canonical dataset digest covers the complete generated prompt content, not only the compact generator specification.

Replaying the same reviewed dataset and generator yields the same prompt and dataset digest. Changing the generator contract, record placement, expected needle or instruction changes the effective benchmark evidence.

## Runtime and authorization boundary

This increment does not add a live provider executor.

A future gateway-backed execution path must still use ordinary authorization, registry eligibility, operational ranking, retry/fallback and terminal execution evidence. A benchmark target name must never become a model-forcing override.

Provider failures remain availability evidence under the existing `BenchmarkRunner`; completed wrong answers remain quality failures.

## CI boundary

Default CI remains credential-free and deterministic. It materializes the synthetic prompts locally, validates position/determinism/drift behavior and exercises the scorer without provider/network calls or secrets.

## Non-goals

This v1 increment does not:

- define an exact provider-token count;
- prove a provider/model context-window size;
- add or alter `min_context_tokens` authorization semantics;
- force a provider/model/deployment for benchmarking;
- call a provider in default CI;
- promote benchmark evidence automatically;
- change ranking policy or model-registry data;
- change Phase 14 consumer sequencing.

Issue #18 continues to defer OpsLens reconciliation and blocks starting RAGForge in parallel unless the normative integration order is explicitly revised.
