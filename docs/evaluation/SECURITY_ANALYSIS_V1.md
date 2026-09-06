# Security Analysis Benchmark v1

Status: IMPLEMENTED — pending branch/PR validation.

## Purpose

`security-analysis-v1` adds the roadmap-listed `security analysis` benchmark class as a bounded, deterministic, credential-free workload.

The benchmark evaluates defensive structured findings over checked-in synthetic Python snippets. It does not execute reviewed code, generate exploit payloads, provide exploitation instructions, or use another model as a judge.

This workload is deliberately separate from `code-review-v1`. Code review covers correctness, maintainability, performance, and robustness; this contract owns the reviewed security-specific vocabulary and evidence semantics.

## Reviewed defensive rules

The immutable v1 rule vocabulary is:

| Rule | Severity | Defensive concern |
|---|---|---|
| `hardcoded_credential` | `high` | credential material embedded in source |
| `path_traversal_join` | `high` | untrusted path joined directly to a trusted base path |
| `tls_verification_disabled` | `high` | TLS certificate verification explicitly disabled |
| `unsafe_pickle_load` | `high` | untrusted serialized data loaded through pickle |
| `unsafe_shell_construction` | `high` | user-controlled text concatenated into a shell command |
| `weak_password_hash` | `medium` | fast legacy digest used for password hashing |

The dataset contains exactly one reviewed case for every rule plus exactly two reviewed clean cases. Clean cases ensure false-positive security findings reduce quality rather than being silently ignored.

## Response contract

Every case requires exactly one JSON object:

```json
{
  "findings": [
    {
      "rule_id": "tls_verification_disabled",
      "severity": "high",
      "line": 3
    }
  ]
}
```

Line numbers are 1-based and relative to the Python snippet inside the prompt.

A finding is valid only when `rule_id` is reviewed, `severity` matches the versioned rule severity, `line` is a positive integer, and the object contains exactly those three fields. Observed findings are order-independent and duplicates fail closed.

## Deterministic scoring

For valid finding sets the scalar score is deterministic set F1:

`2 * matched / (expected + observed)`

When both sets are empty, the score is `1`.

This makes omissions reduce recall and false positives reduce precision. A false positive on a clean case scores `0`.

Stable issue codes are:

- `invalid_output_shape`
- `invalid_findings`
- `invalid_finding`
- `duplicate_finding`
- `missing_finding`
- `unexpected_finding`

The scorer does not scan code or replace reviewed ground truth with inferred findings. The checked-in dataset is the versioned evidence contract.

## Dataset and execution boundary

`load_security_analysis_dataset(...)` fails closed on benchmark-version drift, duplicate case IDs, prompt drift, unknown metadata, unsupported language/response format, execution enablement, malformed expected findings, incomplete reviewed-rule coverage, or a wrong number of clean cases.

`execute_candidate` is fixed to `false`. The snippets are synthetic data; they are not imported, compiled, evaluated, executed, sent to a shell, deserialized, or used for network access by the benchmark.

The reviewed prompts explicitly request defensive analysis only and prohibit exploitation instructions. No exploit payload generation or operational offensive-security procedure is part of this benchmark.

Default CI needs no provider credential, external network call, sandbox, package installation, tool execution, agent execution, or model-as-judge call.

## Authorization boundary

Security-analysis evidence is evaluation evidence, never authorization.

A benchmark target cannot force provider/model/deployment selection. Any future gateway-backed execution must continue through normal policy authorization, model-registry eligibility, operational ranking, resilience, and terminal provenance validation.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`

This increment does not change runtime policy, registry data, ranking, promotion, provider adapters, retries/fallback, API contracts, SDK behavior, or consumer repositories.

Issue #18 continues to defer OpsLens reconciliation and blocks starting RAGForge in parallel unless the normative integration order is explicitly revised.
