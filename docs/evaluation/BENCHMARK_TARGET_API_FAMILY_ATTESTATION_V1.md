# Benchmark Target API Family Attestation v1

Status: **IMPLEMENTED**

## Purpose

Gateway terminal execution now exposes the selected registry `api_family`, and benchmark observations preserve that evidence. Historical benchmark targets, however, identify an API **family/surface** through labels such as:

- `openai-compatible/chat-completions`;
- `gemini/generateContent`;
- `openai/responses`;
- `anthropic/messages`.

Those labels are intentionally more specific than the model-registry adapter-family vocabulary. Runtime code must therefore not derive or guess an adapter family from the historical `BenchmarkTarget.api` string.

This increment introduces an explicit, versioned target-side `api_family` declaration that can be attested against terminal execution evidence.

## Target schema versions

### Schema `1.0` — historical

`benchmarks/runners/targets-v1.json` remains unchanged.

Schema `1.0` accepts only the original target fields and rejects `api_family` as an unknown field. Loaded targets therefore have:

```text
BenchmarkTarget.api_family = None
```

No API-family attestation is performed for those targets.

### Schema `1.1` — API-family-attested

`benchmarks/runners/targets-v2.json` uses schema `1.1` and requires an explicit normalized `api_family` for every target.

The reviewed declarations are:

| Provider target | API surface | Declared `api_family` |
|---|---|---|
| NVIDIA | `openai-compatible/chat-completions` | `openai-compatible` |
| Groq | `openai-compatible/chat-completions` | `openai-compatible` |
| OpenRouter | `openai-compatible/chat-completions` | `openai-compatible` |
| Google | `gemini/generateContent` | `gemini` |
| OpenAI | `openai/responses` | `openai-responses` |
| Anthropic | `anthropic/messages` | `anthropic` |

This mapping is reviewed configuration data. It is not a runtime parsing rule.

## Attestation semantics

For a completed benchmark call:

```text
if target.api_family is None:
    preserve historical provider/model matching only
else:
    require terminal execution identity
    require observed ProviderCall.api_family
    require observed api_family == target.api_family
```

A missing or mismatched observed API family raises `BenchmarkTargetMismatchError` before quality scoring.

Provider failures remain availability evidence. A provider call that never completed does not become a false API-family quality mismatch.

## Snapshot provenance

When a target declares `api_family`, canonical snapshot serialization includes it in the target payload. The content-addressed `snapshot_id` therefore covers both:

- the declared target API family; and
- the observed terminal API family preserved in completed observations.

Historical targets omit the field and preserve their prior canonical target shape.

## What this does not attest

`BenchmarkTarget.configuration` remains declarative target metadata. This increment does not prove the effective runtime values of:

- temperature;
- top-p;
- reasoning or thinking mode;
- max output configuration;
- provider-specific options;
- access/tier labels;
- any other serialized configuration token.

A future gateway-backed benchmark executor must not claim complete configuration attestation until those effective settings have their own reviewed execution-evidence contract.

The first bounded runtime foundation now exists for max-output evidence through `ProviderExecution.max_output_tokens`; see `TERMINAL_MAX_OUTPUT_PROVENANCE_V1.md`. That evidence does not parse, reinterpret, or attest the opaque historical `BenchmarkTarget.configuration` field.

## Authority boundary

Target API-family attestation is benchmark evidence, not authorization.

It cannot add a model or deployment to the allowed set, change policy, alter registry eligibility, reorder fallback candidates, mutate ranking configuration, or self-promote benchmark evidence.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## CI boundary

The contract is deterministic and credential-free. Tests exercise strict target loading, legacy compatibility, exact matching, missing/mismatch failure, and snapshot provenance without provider or network calls.

## Next boundary

Effective configuration provenance remains intentionally incremental. The runtime now preserves the concrete max-output limit sent to the adapter, but benchmark targets still need an explicit future schema field before max-output can be attested fail-closed. Temperature, top-p, reasoning/thinking controls, and provider-specific settings remain outside the current provider-neutral execution contract.
