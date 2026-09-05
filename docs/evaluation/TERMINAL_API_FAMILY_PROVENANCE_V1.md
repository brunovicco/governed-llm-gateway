# Terminal API Family Provenance v1

Status: **IMPLEMENTED**

## Purpose

The gateway already selects a concrete `ModelDeployment` before provider execution. That deployment includes a reviewed `api_family`, and `StaticProviderResolver` uses the exact `(provider, api_family)` pair to resolve the adapter that performs the call.

Before this increment, terminal `ProviderExecution` evidence preserved provider, model, and deployment but dropped the API-family dimension even though it was known at execution time.

This increment preserves that fact end to end.

## Contract

`ProviderExecution` now has an optional `api_family` field.

The field is appended after the existing optional execution fields so positional construction of the previous contract remains compatible. When present, it must be a normalized non-empty string.

The field is optional for protocol compatibility with historical/replayed terminal events. New gateway runtime execution populates it from the selected `ModelDeployment.api_family` for both successful and failed provider executions.

```text
selected ModelDeployment.api_family
  -> ProviderExecution.api_family
  -> terminal SSE execution payload
  -> gateway client codec
  -> GatewayResponse.execution
```

The API serializer omits `api_family` when it is absent, preserving the historical wire shape for legacy evidence. The SDK accepts both shapes and preserves the field exactly when present.

## Evidence boundary

`api_family` is terminal execution evidence. It is not authorization and it does not select an adapter after the fact.

The authoritative sequence remains:

```text
PDP-authorized logical model group
  -> eligible registry deployments
  -> deterministic ranking
  -> selected ModelDeployment
  -> ProviderResolver(provider, api_family)
  -> provider execution
  -> terminal execution evidence
```

The evidence therefore reports the API family already used by the selected deployment; it cannot broaden the candidate set or mutate routing.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Benchmark boundary

This increment deliberately does **not** claim that `BenchmarkTarget.api` is now attested.

The benchmark target contract predates this terminal field and its `api` vocabulary is not yet formally bound to the model-registry `api_family` vocabulary. Treating arbitrary historical target strings as equivalent would create false evidence.

A later reviewed benchmark-attestation increment may define the exact equivalence or mapping rules and then fail closed on API-family mismatch.

`BenchmarkTarget.configuration` also remains unverified. No temperature, reasoning mode, provider-specific option, or other effective configuration is inferred from the API family.

## Compatibility

- existing `ProviderExecution` constructors remain valid without `api_family`;
- existing terminal SSE payloads without `api_family` remain decodable;
- new runtime terminal evidence includes the selected deployment API family;
- no `RoutingProvenance` field is added in v1;
- no benchmark snapshot, scorecard, ranking policy, model registry, or authorization contract is mutated by this increment.

## Security and privacy

`api_family` is bounded metadata sourced from the validated model registry. It contains no prompt/completion content, provider credential, arbitrary provider header, or raw provider response.

No new provider network call or credential is required by default CI.

## Next boundary

Before a gateway-backed benchmark executor can claim a fully identified `BenchmarkTarget`, the benchmark layer still needs an explicit reviewed attestation contract for:

1. how `BenchmarkTarget.api` maps to observed terminal `api_family`; and
2. how effective benchmark `configuration` is represented and proven.

Until those dimensions are explicit, benchmark evidence must not imply that a routed gateway execution proves the complete target declaration.
