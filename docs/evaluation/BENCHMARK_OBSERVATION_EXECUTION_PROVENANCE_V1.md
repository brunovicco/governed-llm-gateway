# Benchmark Observation Execution Provenance v1

## Purpose

A benchmark snapshot must preserve the execution evidence needed to audit what actually produced a completed model output.

`ProviderCall` already carries optional terminal `provider`, `model`, and `deployment` identity. Before this increment, `BenchmarkRunner` validated provider/model consistency against the declared target but discarded that observed identity when creating `BenchmarkObservation`.

This boundary carries the observed terminal identity into observations and, when present, into canonical snapshots.

## Observation contract

`BenchmarkObservation` can carry:

- `provider`;
- `model`;
- `deployment`.

The fields are optional for backward compatibility with credential-free/replay evidence. When any one is present, all three must be present, normalized, and non-empty.

Completed calls copy the identity from `ProviderCall` after the existing target-integrity check succeeds.

Provider failures continue to use the existing availability evidence path. This increment does not invent terminal identity for failures when the executor did not supply it.

## Snapshot behavior

Canonical snapshot serialization includes observed execution identity only when it exists.

This has two deliberate consequences:

1. snapshots with terminal execution identity cover provider/model/deployment in `snapshot_id`;
2. legacy/replay observations without identity keep the previous canonical observation shape, avoiding unnecessary historical snapshot drift.

A change only in the observed deployment therefore changes the content-addressed snapshot ID even when the declared benchmark target remains the same.

## Target versus observed execution

The declared `BenchmarkTarget` and observed terminal execution are different evidence dimensions:

- target = the reviewed evaluation label;
- observed execution = what the execution boundary reports actually ran.

The runner still fails closed before scoring when observed provider/model contradict the target.

The current terminal execution contract still does not prove the target's full `api` or `configuration` fields. Persisting provider/model/deployment does not upgrade those dimensions to verified facts.

## Authority boundary

Execution provenance is evidence, never authorization.

This increment does not:

- force provider/model/deployment selection;
- expand an authorized model group;
- bypass registry eligibility or ranking;
- change fallback behavior;
- activate ranking evidence;
- promote a snapshot automatically;
- create provider credentials or network calls.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`.

## Next boundary

A gateway-backed live benchmark executor remains deferred until the repository has an explicit reviewed way to attest the remaining target dimensions it claims to evaluate, especially API family and effective configuration. The benchmark layer must not infer those values from provider/model names or from benchmark labels.
