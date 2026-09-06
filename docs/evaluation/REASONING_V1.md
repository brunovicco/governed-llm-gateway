# Reasoning Benchmark v1

Status: COMPLETE — merged in PR #47.

## Purpose

`reasoning-v1` adds the roadmap-listed `reasoning` benchmark class as a bounded, deterministic, credential-free workload.

The benchmark evaluates only observable final answers. It deliberately does **not** request, preserve, score, or expose chain-of-thought or other hidden reasoning state.

## Reviewed families

The v1 dataset contains exactly three public/synthetic cases for each reviewed family:

- `arithmetic`
- `boolean_logic`
- `constraint`
- `sequence`

This produces 12 total cases.

The families are intentionally small and auditable. They establish a deterministic reasoning baseline without claiming broad reasoning coverage or requiring a model-as-judge.

## Answer-only contract

Every prompt uses the reviewed instruction to return only:

```json
{"answer": "<reviewed-final-answer>"}
```

The `answer` value may be a bounded normalized string token, integer, or boolean depending on the case. Floating-point, object, array, and null expected answers are outside v1.

The scorer is exact and type-sensitive. In particular, JSON/Python boolean values are not accepted as integer substitutes.

Stable failure codes are:

- `invalid_output_shape`
- `wrong_answer_type`
- `wrong_answer`

An exact type-sensitive final answer scores `1`; any failure above scores `0`.

Extra fields, including an `explanation` or reasoning trace, violate the v1 output shape and score zero. This keeps the benchmark evidence focused on the externally observable answer rather than hidden reasoning content.

## Dataset contract

`load_reasoning_dataset(...)` fails closed when:

- `benchmark_version` is not `reasoning-v1`;
- case IDs are duplicated;
- a case uses a different workload or scorer;
- the reviewed answer-only prompt instruction drifts;
- metadata contains unknown fields;
- `contract_version`, `family`, `response_format`, `synthetic`, or `answer_only` drift;
- expected output is not exactly one `answer` field with a reviewed v1 scalar type;
- any reviewed family does not contain exactly three cases.

The checked-in dataset remains schema `1.0` and `data_classification: public`.

## Determinism and privacy boundary

The benchmark uses only checked-in synthetic prompts and exact deterministic scoring. The canonical dataset digest covers the prompt, expected final answer, metadata, scorer ID, case ID, and workload identity.

No provider credentials, network access, external data, embeddings, code execution, tool execution, agent execution, or LLM-as-judge call is required.

No chain-of-thought field exists in the benchmark contract. Raw provider payloads are not part of the benchmark snapshot contract.

## Relationship to tool-use workloads

The roadmap separately lists `tool selection`, `tool argument generation`, and `multi-step tool use`. `tool-use-v1` already produces separate deterministic `selection_score` and `arguments_score` for a single proposed call, so this reasoning increment does not duplicate those semantics.

A future multi-step tool-use workload would require a separately reviewed trajectory contract and must still keep actual tool execution disabled unless a distinct execution-security boundary is approved.

## Authorization boundary

Reasoning benchmark evidence is evaluation evidence, not authorization.

A benchmark target naming a provider/model/API/configuration cannot force that provider or model through the gateway. Any future gateway-backed execution must use ordinary policy authorization, model-registry eligibility, operational ranking, resilience, and terminal provenance checks.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`

This increment does not change runtime policy, ranking, promotion, registry data, provider adapters, retries/fallback, API contracts, SDK behavior, or Phase 14 consumer sequencing.

Issue #18 continues to defer OpsLens reconciliation and blocks starting RAGForge in parallel unless the normative integration order is explicitly revised.
