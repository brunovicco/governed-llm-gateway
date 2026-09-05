# Classification Benchmark v1

Status: IMPLEMENTED — pending branch/PR validation.

## Purpose

`classification-v1` adds the roadmap-listed `classification` benchmark class as a bounded, deterministic, credential-free workload.

The benchmark measures exact closed-set intent classification. It does not use an LLM judge and it does not grant authority to benchmark targets, datasets, observations, or scorecards.

## Reviewed label set

The immutable v1 label set is `support-intents-v1`:

- `account_access`
- `billing`
- `general_information`
- `sales`
- `security`
- `technical_support`

The checked-in public/synthetic dataset contains exactly two cases per reviewed label, for 12 total cases.

## Response contract

Every case requires exactly this JSON shape:

```json
{"label": "<reviewed-label>"}
```

Extra fields, missing fields, non-string labels, labels outside the reviewed set, or an incorrect reviewed label score zero.

The scorer emits stable evidence codes:

- `invalid_output_shape`
- `wrong_label_type`
- `unknown_label`
- `wrong_label`

A successful exact match scores `1`; every failure above scores `0`.

## Dataset contract

`load_classification_dataset(...)` fails closed when:

- `benchmark_version` is not `classification-v1`;
- case IDs are duplicated;
- a case uses a different workload or scorer;
- the reviewed prompt instruction drifts or carries surrounding whitespace;
- metadata includes unknown fields;
- `contract_version`, `label_set`, `response_format`, or `synthetic` drift;
- expected output is not exactly `{"label": "<reviewed-label>"}`;
- any reviewed label does not have exactly two cases.

Dataset schema remains the existing benchmark dataset schema `1.0`, with `data_classification: public`.

## Determinism and provenance

The benchmark uses only checked-in synthetic prompts and exact deterministic scoring. The existing canonical dataset digest therefore covers the prompt text, expected labels, metadata, scorer ID, case ID, and workload identity.

No provider credentials, network access, embeddings, external datasets, or model-as-judge calls are required to validate or score `classification-v1`.

## Authorization boundary

Classification evidence is evaluation evidence, not authorization.

A benchmark target naming a provider/model/API/configuration does not force that provider or model through the gateway. Any future gateway-backed execution must still pass the ordinary policy, registry, ranking, resilience, and terminal provenance paths.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`

This workload does not change policy, registry, ranking, promotion, provider adapters, retries/fallback, API contracts, or SDK behavior.

## Phase 14 sequencing

This benchmark is consumer-agnostic evaluation work. It does not modify Phase 14 integration sequencing.

OpsLens remains deferred while issue #18 is open, and RAGForge must not begin in parallel unless the normative integration order is explicitly revised.
