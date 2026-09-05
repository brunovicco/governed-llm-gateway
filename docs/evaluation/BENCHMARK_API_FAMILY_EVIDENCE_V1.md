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

This increment does **not** compare `api_family` against `BenchmarkTarget.api`.

`BenchmarkTarget.api` is historical target metadata whose string vocabulary predates terminal `ModelDeployment.api_family` evidence. Existing targets may use API labels that are more specific, differently namespaced, or otherwise not textually identical to the registry API-family vocabulary.

Therefore the following would be unsafe:

```text
BenchmarkTarget.api == ProviderExecution.api_family
```

unless a reviewed versioned equivalence contract defines that relationship.

The snapshot deliberately preserves both facts independently:

```text
target.api                     # declared target metadata
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

A gateway-backed benchmark executor must not claim a fully identified benchmark target until effective configuration evidence has an explicit reviewed representation.

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

## Next boundary

The next safe benchmark step is a reviewed **target API-family attestation contract** that defines when a declared `BenchmarkTarget.api` can be compared to observed `api_family`, while preserving historical target vocabulary.

`BenchmarkTarget.configuration` remains a separate blocker before any gateway-backed executor can claim full target identity.
