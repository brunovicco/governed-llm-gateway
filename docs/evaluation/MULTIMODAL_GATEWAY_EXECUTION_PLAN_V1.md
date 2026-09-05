# Multimodal Gateway Execution Plan v1

Status: provider-neutral materialization boundary after `multimodal-analysis-v1` stabilized.

## Purpose

The execution plan converts one validated multimodal benchmark case and one immutable fixture publication into the existing provider-neutral `GatewayRequest` contract.

It does not call a provider, perform network I/O, choose a model, or grant authorization.

## Inputs

Materialization requires four explicit inputs:

- a validated `multimodal-analysis-v1` benchmark case;
- its immutable `BenchmarkFixturePublication`;
- a caller-provided `request_id`;
- a caller-provided dotted `workload_identity`.

The workload identity is deliberately not inferred from the benchmark name. An execution environment must supply an identity that is already meaningful to its normal policy path.

This preserves the permanent invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Materialized request

The v1 plan produces a request with:

- `schema_version = 1.0`;
- caller-provided `request_id`;
- caller-provided `workload`;
- `risk_level = low`;
- `data_classification = public`;
- `requirements.vision = true`;
- one `user` message containing the benchmark prompt;
- one provider-neutral `ImageInput` using the case media type and commit-pinned publication URL.

The plan intentionally does not enable `structured_output`. The benchmark scorer evaluates the normalized JSON result, while model eligibility for this visual task remains isolated to the vision requirement.

## Fail-closed provenance checks

Before creating the request, the materializer requires the publication fixture ID and digest to match the benchmark case metadata exactly.

The dataset-loading boundary already validates the case against the local fixture catalog and publication catalog. The execution-plan boundary repeats the identity/digest comparison so direct use cannot silently substitute another published image.

The publication URL continues to be governed by the immutable-publication contract: HTTPS, credential-free, query-free, and commit-pinned.

## Authorization boundary

Creating an execution plan is not an authorization decision.

The returned `GatewayRequest` must still pass through the ordinary gateway policy, registry eligibility, ranking, resilience, and provider execution path. The plan cannot add an authorized model group, provider, model, or deployment.

Benchmark fixture identity, digest, score, and publication metadata are evaluation provenance only.

## CI boundary

Default CI only validates materialization behavior and contracts. It performs no provider call and does not fetch the published image.

A later live benchmark runner may submit the materialized request through an authorized gateway client and normalize the resulting response into `ProviderCall` evidence. That remains a separate reviewed increment.
