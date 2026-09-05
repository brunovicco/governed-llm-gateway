# Benchmark Target Max Output Attestation v1

Status: **IMPLEMENTED**

## Purpose

Terminal gateway execution evidence now preserves the concrete provider-neutral `max_output_tokens` value carried by the `ProviderRequest`. Benchmark targets can therefore declare that value explicitly and require exact terminal evidence before quality scoring.

This contract does not parse or reinterpret the historical opaque `BenchmarkTarget.configuration` string.

## Target schema evolution

### Schema `1.0` — historical

Schema `1.0` remains unchanged and accepts only the original benchmark target fields.

It rejects both `api_family` and `max_output_tokens` extensions.

### Schema `1.1` — API-family-attested

Schema `1.1` requires explicit `api_family` and remains closed to `max_output_tokens`.

`benchmarks/runners/targets-v2.json` remains unchanged.

### Schema `1.2` — API-family and max-output-attested

Schema `1.2` requires:

- explicit normalized `api_family`; and
- explicit positive-integer `max_output_tokens`.

The reviewed matrix is `benchmarks/runners/targets-v3.json`.

| Provider | `api_family` | `max_output_tokens` |
|---|---|---:|
| NVIDIA | `openai-compatible` | 16384 |
| Groq | `openai-compatible` | 4096 |
| OpenRouter | `openai-compatible` | 4096 |
| Google | `gemini` | 4096 |
| OpenAI | `openai-responses` | 4096 |
| Anthropic | `anthropic` | 4096 |

These values are reviewed typed target declarations. Their current correspondence with text inside the legacy `configuration` field is informational only; no parser or equality rule is derived from that string.

## Attestation semantics

For a completed benchmark call, target identity is checked before the deterministic scorer runs.

When `target.max_output_tokens` is present:

```text
require terminal execution identity
require observed ProviderCall.max_output_tokens
require observed max_output_tokens == target.max_output_tokens
```

Missing or mismatched evidence raises `BenchmarkTargetMismatchError` before quality scoring.

A target without explicit `max_output_tokens` does not infer one from `configuration`, even if that string contains a token such as `max_output=4096`.

## Runtime evidence chain

The attested value follows this reviewed path:

```text
ProviderRequest.max_output_tokens
    ↓
ProviderExecution.max_output_tokens
    ↓
GatewayResponse.execution.max_output_tokens
    ↓
normalize_multimodal_gateway_response(...)
    ↓
ProviderCall.max_output_tokens
    ↓
BenchmarkRunner target attestation
    ↓
BenchmarkObservation.max_output_tokens
```

The field represents the concrete provider-neutral maximum-output limit forwarded for the execution attempt. It does not represent produced output tokens or a provider guarantee beyond adapter translation.

## Provider failures

Provider failures remain availability evidence.

When the executor raises `BenchmarkProviderFailure`, the runner records `ObservationStatus.PROVIDER_FAILURE` and does not manufacture a max-output quality mismatch. A completed call that returns contradictory target evidence fails closed before scoring.

## Snapshot provenance

Canonical snapshots include `max_output_tokens` when present in:

- the typed benchmark target declaration; and
- the completed benchmark observation.

Therefore `snapshot_id` changes when either declared or observed max-output evidence changes.

Historical targets with `max_output_tokens=None` preserve their previous target serialization shape.

## What remains unattested

This contract does not attest:

- temperature;
- top-p;
- reasoning/thinking mode;
- provider-specific sampling options;
- access or provider-tier labels;
- provider timeout; or
- the opaque `BenchmarkTarget.configuration` string as a whole.

Those controls require their own explicit provider-neutral runtime evidence before they can become benchmark attestations.

`provider_timeout_seconds` remains outside this contract because it is an operational/resilience timeout rather than a model-generation quality control.

## Authority boundary

Benchmark target attestation is evidence, never authorization.

It cannot add models/deployments to the authorized set, mutate policy, alter registry eligibility, change ranking, expand fallback candidates, or automatically promote benchmark results.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## CI boundary

The default test suite remains deterministic and credential-free. It covers:

- strict schema `1.2` loading;
- schema `1.1` closure against the new field;
- positive-integer validation including boolean rejection;
- exact attestation success;
- missing and mismatched evidence failure;
- no inference from the historical configuration string;
- gateway-response-to-`ProviderCall` evidence propagation; and
- canonical snapshot provenance.
