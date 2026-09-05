# Terminal Max Output Provenance v1

Status: **IMPLEMENTED**

## Purpose

The gateway already constructs a concrete provider-neutral `ProviderRequest` for each authorized execution attempt. That request contains the effective `max_output_tokens` value forwarded to the selected adapter, but terminal execution evidence previously did not preserve it.

This increment adds bounded terminal provenance for that value.

## Evidence flow

```text
caller max_output_tokens
    ↓
PreparedStreamingExecution.max_output_tokens
    ↓
ProviderRequest.max_output_tokens
    ↓
ProviderExecution.max_output_tokens
    ↓
Gateway SSE execution payload
    ↓
gateway-client ProviderExecution
```

`ProviderExecution.max_output_tokens` means:

> the positive provider-neutral maximum-output-token limit carried by the concrete `ProviderRequest` for that execution attempt.

It does **not** mean that the provider produced that many tokens, reserved them, or guaranteed identical provider-native semantics beyond the reviewed adapter translation.

## Success and failure semantics

The field is preserved on terminal execution evidence for both:

- `ExecutionStatus.SUCCEEDED`; and
- `ExecutionStatus.FAILED` when a concrete provider request was attempted.

This makes a failed benchmark/provider attempt auditable without converting operational failure into quality evidence.

## Compatibility

The field is optional on the provider-neutral `ProviderExecution` contract.

Historical execution objects remain valid with:

```text
max_output_tokens = None
```

When absent, the SSE payload omits `max_output_tokens`. The client codec accepts both the historical shape and the new optional field.

When present, the value must be a positive integer.

## What is not included

This increment intentionally does not add or claim provenance for:

- temperature;
- top-p;
- reasoning/thinking mode;
- provider-specific sampling controls;
- access/tier labels;
- provider timeout;
- the opaque `BenchmarkTarget.configuration` string.

Those values are not currently represented as equivalent provider-neutral model-quality controls in `ProviderRequest`, or belong to a different operational boundary.

`provider_timeout_seconds` is deliberately excluded because it is an execution/resilience timeout rather than a model-generation quality parameter.

## Benchmark relationship

`BenchmarkTarget.configuration` remains declarative and unverified.

Terminal max-output provenance is only the runtime evidence foundation required before a future benchmark target schema can declare an explicit expected max-output setting and attest it fail-closed. No parser is introduced for the historical opaque configuration string.

## Authority boundary

Execution provenance is evidence, never authorization.

It cannot add deployments to the authorized set, mutate policy, change registry eligibility, affect ranking, expand fallback candidates, or promote benchmark results automatically.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## CI boundary

Contract tests remain deterministic and credential-free. They verify:

- the exact `ProviderRequest.max_output_tokens` value reaches the provider adapter;
- successful terminal execution preserves the value;
- failed terminal execution preserves the attempted value;
- SSE serialization and client decoding round-trip the field;
- historical payloads omit the absent optional field; and
- non-positive values fail closed.
