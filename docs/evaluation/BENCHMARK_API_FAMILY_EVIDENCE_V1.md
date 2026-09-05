# Benchmark API Family Evidence v1

Status: **IMPLEMENTED**

## Purpose

Terminal gateway execution now preserves the selected `ModelDeployment.api_family` in `ProviderExecution`. The benchmark normalization layer previously retained provider, model, and deployment but would still discard this newly available terminal fact.

This increment carries API-family evidence through the benchmark evidence pipeline without redefining historical benchmark target semantics.

## Evidence path

```text
ProviderExecution.api_family
  -> ProviderCall.api_family
  -> BenchmarkObservation.api_family
  -> canonical benchmark snapshot
  -> snapshot_id
```

`normalize_multimodal_gateway_response` copies the API family exactly when the terminal gateway execution provides it. `BenchmarkRunner` then preserves it on completed observations. Canonical snapshot serialization includes it only when present, so the content-addressed snapshot ID covers the observed API family.

## Compatibility

Provider/model/deployment evidence existed before API-family provenance. Historical replay executors and snapshots may therefore contain complete provider/model/deployment identity without an API family.

For that reason:

- `ProviderCall.api_family` is optional;
- `BenchmarkObservation.api_family` is optional;
- historical provider/model/deployment evidence remains valid without it;
- when `api_family` is present, provider/model/deployment identity must also be present and the API family must be normalized;
- canonical serialization omits `api_family` when it is absent, preserving the historical snapshot payload shape.

This is an intentional compatibility boundary, not a claim that missing API-family evidence is equivalent to any particular API family.

## Target-attestation boundary

This evidence increment does **not** compare `api_family` against the historical `BenchmarkTarget.api` field.

`BenchmarkTarget.api` is historical target metadata whose string vocabulary predates terminal `ModelDeployment.api_family` evidence. Existing targets may use API labels that are more specific, differently namespaced, or otherwise not textually identical to the registry API-family vocabulary.

Therefore the following remains unsafe:

```text
BenchmarkTarget.api == ProviderExecution.api_family
```

The successor contract, `BENCHMARK_TARGET_API_FAMILY_ATTESTATION_V1.md`, adds a separate explicit `BenchmarkTarget.api_family` declaration under target-matrix schema `1.1`. Only that explicit field is eligible for exact terminal attestation. Historical schema `1.0` targets remain unattested.

The snapshot therefore keeps the concepts separate:

```text
target.api                     # declared API family/surface metadata
target.api_family              # optional explicit adapter-family expectation
observation.api_family         # observed terminal execution evidence
```

This prevents an observed API family from silently rewriting or validating historical target metadata.

## Configuration boundary

`BenchmarkTarget.configuration` remains unverified.

This increment does not infer or attest:

- temperature;
- reasoning effort/mode;
- max output configuration beyond existing measured/request contracts;
- provider-specific options;
- sampling parameters;
- arbitrary adapter configuration.

A gateway-backed benchmark executor must not claim a fully attested benchmark target until effective configuration evidence has an explicit reviewed representation.

## Authority boundary

API-family evidence is never authorization.

It cannot:

- add a provider/model/deployment to the allowed set;
- change registry eligibility;
- change ranking or fallback order;
- bypass the Policy Router decision;
- promote itself into ranking evidence;
- mutate policy or configuration.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## CI boundary

All tests remain credential-free and deterministic. No provider call, fixture hosting, secret, or external network dependency is added by this increment.

## Successor boundary

Explicit target API-family attestation is implemented by `BENCHMARK_TARGET_API_FAMILY_ATTESTATION_V1.md` and `benchmarks/runners/targets-v2.json`.

The next unresolved target-identity boundary is effective `BenchmarkTarget.configuration` provenance.
