# Code Review Benchmark v1

Status: COMPLETE — merged in PR #48.

## Purpose

`code-review-v1` adds the roadmap-listed `code review` benchmark class as a bounded, deterministic, credential-free workload.

The benchmark evaluates structured review findings over checked-in synthetic Python snippets. It does not execute the reviewed code and does not use another model as a judge.

This workload is deliberately separate from `security analysis`. The reviewed v1 rules cover correctness, maintainability, performance, and robustness only; security-specific findings remain a separate benchmark boundary.

## Reviewed rules

The immutable v1 rule vocabulary is:

| Rule | Severity | Review dimension |
|---|---|---|
| `mutable_default_argument` | `medium` | correctness |
| `missing_return_path` | `high` | correctness |
| `off_by_one_range` | `medium` | correctness |
| `repeated_membership_scan` | `low` | performance |
| `duplicate_branch_logic` | `low` | maintainability |
| `broad_exception_catch` | `medium` | robustness |

The dataset contains exactly one reviewed case for every rule plus exactly two reviewed clean cases. Clean cases are important because false-positive findings must reduce quality rather than being silently ignored.

## Response contract

Every case requires exactly one JSON object:

```json
{
  "findings": [
    {
      "rule_id": "mutable_default_argument",
      "severity": "medium",
      "line": 1
    }
  ]
}
```

Line numbers are 1-based and relative to the Python snippet inside the prompt, not the surrounding benchmark instruction.

A finding is valid only when:

- `rule_id` belongs to the reviewed v1 rule vocabulary;
- `severity` exactly matches the versioned severity assigned to that rule;
- `line` is a positive integer;
- the finding contains exactly `rule_id`, `severity`, and `line`.

Observed findings are order-independent and duplicates fail closed.

## Deterministic scoring

The scorer compares the reviewed finding set with the observed finding set without executing code.

For valid finding sets, the scalar score is deterministic set F1:

`2 * matched / (expected + observed)`

When both sets are empty, the score is `1`.

This means:

- exact reviewed findings score `1`;
- omitted findings reduce recall;
- extra findings reduce precision;
- a false positive on a reviewed clean case scores `0`.

Stable scoring issue codes are:

- `invalid_output_shape`
- `invalid_findings`
- `invalid_finding`
- `duplicate_finding`
- `missing_finding`
- `unexpected_finding`

The scorer does not infer new findings from AST analysis and does not reinterpret the reviewed ground truth. Dataset content is the reviewed benchmark evidence.

## Dataset contract

`load_code_review_dataset(...)` fails closed when:

- `benchmark_version` is not `code-review-v1`;
- case IDs are duplicated;
- a case uses another workload or scorer;
- the reviewed non-executing prompt instruction drifts;
- metadata contains unknown fields;
- `contract_version`, `language`, `response_format`, `synthetic`, or `execute_candidate` drift;
- an expected finding contains an unknown rule, wrong severity, invalid line, or unexpected field;
- any reviewed rule is not represented exactly once;
- there are not exactly two reviewed clean cases.

The checked-in dataset remains schema `1.0` and `data_classification: public`.

## Execution and security boundary

`execute_candidate` is fixed to `false`. Neither expected nor observed code is imported, evaluated, compiled, or executed by this benchmark.

The snippets are synthetic and checked in. No provider credentials, network access, external repository, package installation, sandbox, tool execution, agent execution, or model-as-judge call is required.

Security analysis is intentionally out of scope. A future `security-analysis-v1` must define its own reviewed rule vocabulary and evidence semantics rather than silently extending this workload.

## Authorization boundary

Code-review evidence is evaluation evidence, never authorization.

A benchmark target naming a provider/model/API/configuration cannot force that provider or model through the gateway. Any future gateway-backed execution must continue through normal policy authorization, model-registry eligibility, operational ranking, resilience, and terminal provenance validation.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`

This increment does not change runtime policy, registry data, ranking, promotion, provider adapters, retries/fallback, API contracts, SDK behavior, or consumer repositories.

Issue #18 continues to defer OpsLens reconciliation and blocks starting RAGForge in parallel unless the normative integration order is explicitly revised.
