# Benchmark Quality Component Evidence

Status: **COMPLETE — merged in PR #64.**

## Purpose

The Roadmap requires offline model-quality dimensions to remain separate from online
operational health. The benchmark framework already preserves operational evidence such as
latency, TTFT, usage, cost, provider errors and fallback frequency, but historically reduced
workload-specific quality assessments to one scalar `quality_score` before observations and
scorecards were persisted.

This increment preserves reviewed quality components that are already deterministically
produced by existing workload semantics. It does not add a new model judge, provider call,
runtime authority source, or ranking rule.

## Canonical component vocabulary

The bounded `BenchmarkQualityMetric` vocabulary contains only dimensions the current
reviewed scorers can actually demonstrate:

| Metric | Reviewed source workloads |
|---|---|
| `schema_validity` | `structured-extraction-v2`, `json-schema-compliance-v1` |
| `tool_selection_accuracy` | `tool-use-v1`, `tool-selection-v1`, `multi-step-tool-use-v1` |
| `tool_argument_accuracy` | `tool-use-v1`, `tool-argument-generation-v1`, `multi-step-tool-use-v1` |
| `trajectory_success` | `multi-step-tool-use-v1`, `agent-orchestration-v1` |
| `grounding` | `rag-answer-v1`, `rag-ptbr-v2` |
| `pt_br_quality` | `rag-ptbr-v2` |

The historical scalar scorer callable contract remains unchanged. Existing code can still
call a scorer and receive one `Decimal` from 0 through 1. Component-aware scorers expose an
additional deterministic measurement used by `BenchmarkRunner`.

## Roadmap measurement coverage

| Roadmap measure | Evidence status |
|---|---|
| task success | `quality_success_rate` over completed calls under the configured reviewed quality threshold |
| schema validity | preserved as `schema_validity` component evidence |
| tool-selection accuracy | preserved as `tool_selection_accuracy` component evidence |
| tool-argument accuracy | preserved as `tool_argument_accuracy` component evidence |
| trajectory success | preserved as `trajectory_success` component evidence |
| grounding | preserved as `grounding` component evidence from `rag-answer-v1` |
| PT-BR quality | bounded reviewer-authored locale/terminology conformance preserved as `pt_br_quality` by `rag-ptbr-v2`; not a universal fluency/grammar claim |
| latency p50 / p95 | existing scorecard evidence |
| TTFT | existing scorecard evidence |
| input / output tokens or normalized units | existing scorecard evidence |
| cost | existing scorecard evidence |
| provider errors | existing scorecard evidence |
| rate-limit errors | existing scorecard evidence |
| fallback frequency | existing scorecard evidence |

### PT-BR quality is bounded and explicit

`rag-ptbr-v1` remains the historical required-fact/forbidden-claim contract and still exposes no
language-quality component. PR #67 adds `rag-ptbr-v2`, which keeps `grounding` separate from
`pt_br_quality`. The new component measures only conformance to case-local reviewer-authored
Brazilian Portuguese locale/terminology rules using explicit preferred and rejected terms.

This closes the Roadmap measurement gap only at that bounded level. It does not claim arbitrary
Portuguese fluency, complete grammar correctness, unrestricted semantic equivalence, style/tone,
cultural appropriateness or quality across every Portuguese variety. Those would require separate
reviewed contracts.

## Observation and aggregation semantics

For a completed provider call:

- `quality_score` remains the workload's historical scalar score;
- `quality_metrics` may contain reviewed component values, each bounded from `0` through `1`;
- component mappings are immutable;
- unknown component keys fail closed.

Provider failures carry neither scalar quality nor component quality. They remain
availability evidence and are never imputed as zero model quality.

For one target/workload scorecard, every completed observation must expose the same set of
component keys. Partial component coverage fails closed instead of averaging a convenient
subset. `mean_quality_metrics` is computed only across completed calls.

## Snapshot schema evolution

Historical snapshot semantics remain preserved:

- schema `1.0` — historical snapshot without target-matrix provenance or component metrics;
- schema `1.1` — historical target-matrix provenance extension without component metrics;
- schema `1.2` — quality component evidence is present and participates in the canonical
  content-addressed `snapshot_id`; target-matrix provenance may also be present as a complete
  version/digest pair.

Empty component mappings are omitted from canonical JSON, so existing schema 1.0/1.1
payloads are not silently rewritten. Manually placing component evidence into schema 1.0 or
1.1 fails closed.

## Promotion and ranking boundary

Phase 11 promotion remains schema `1.0` and continues to consume the reviewed scalar
`mean_quality_score` plus its existing operational fields. This increment deliberately does
not copy component metrics into promoted ranking evidence.

Making a component metric eligible for promotion would require a separate explicit,
versioned promotion-contract change with its own review, tests and rollback semantics.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Component metrics cannot:

- authorize a model, provider or deployment;
- force a benchmark target into routing;
- bypass gateway eligibility;
- widen governance scope;
- mutate policy;
- self-promote;
- automatically change ranking weights.

## CI boundary

The component evidence path is credential-free and deterministic. It reuses existing
checked-in public/synthetic benchmark cases and does not add network access, provider
credentials, tool execution, generated-code execution or LLM-as-judge behavior to default
CI.

## Phase 14 sequencing

This is consumer-agnostic benchmark evidence hardening. Issue #18 remains authoritative:
OpsLens stays deferred, and RAGForge must not start in parallel unless the normative
integration order is explicitly revised.
