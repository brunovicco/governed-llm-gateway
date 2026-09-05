# Benchmark Execution Identity v1

## Purpose

Benchmark scorecards are meaningful only when completed-call evidence can be associated with the provider/model target that the run claims to evaluate.

The governed gateway deliberately owns provider/model selection through authorization, registry eligibility, ranking, and resilience. A benchmark executor must therefore never assume that a requested or labeled target was the deployment that actually executed.

This boundary preserves observed terminal execution identity when it is available and fails closed before scoring when that identity contradicts the declared benchmark target.

## ProviderCall identity

`ProviderCall` may now carry the terminal execution identity:

- `provider`;
- `model`;
- `deployment`.

The three fields are optional for backward compatibility with existing credential-free/replay executors, but they are all-or-none when present. Every supplied identity value must be normalized and non-empty.

Gateway response normalization populates all three values from provider-neutral `ProviderExecution` evidence.

## Runner integrity check

Before deterministic scoring, `BenchmarkRunner` compares observed `provider` and `model` against the declared `BenchmarkTarget` when execution identity is present.

A mismatch raises `BenchmarkTargetMismatchError` and aborts the affected run path. It is intentionally not converted into:

- `PROVIDER_FAILURE`, because the provider may have executed successfully;
- `QUALITY_FAILURE`, because output quality is not the integrity problem.

The problem is mislabeled benchmark evidence.

## What v1 does not attest

`BenchmarkTarget` also contains `api` and `configuration`. The current provider-neutral terminal execution contract does not prove those dimensions.

Therefore v1 does **not** claim that observing a matching provider/model proves:

- the benchmark target API family;
- temperature/reasoning/max-output configuration;
- access tier or other target configuration metadata.

A future gateway-backed benchmark executor must introduce an explicit reviewed binding or stronger execution provenance before it may claim those dimensions. It must not infer them from provider/model names.

## Governance boundary

Execution identity is evidence, never authorization.

This increment does not:

- force a provider, model, or deployment;
- expand the Policy Router authorized set;
- bypass model-registry eligibility;
- change ranking or fallback behavior;
- promote benchmark evidence automatically;
- create provider credentials or network calls in default CI.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`.

## Consequence for the next executor increment

A gateway-backed `BenchmarkExecutor` is still intentionally deferred until target labeling can cover the full evidence contract safely. The executor must call the gateway boundary, preserve actual terminal execution identity, and must not use `BenchmarkTarget` as authority to force routing.
