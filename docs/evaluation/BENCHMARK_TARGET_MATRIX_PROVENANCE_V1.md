# Benchmark Target Matrix Provenance v1

Status: **IMPLEMENTED — pending branch/PR validation**

## Purpose

Phase 10 requires reproducible benchmark evidence with explicit provider, model, API, configuration, date, and benchmark version provenance.

Benchmark snapshots already content-address the serialized target list as part of `snapshot_id`. That makes target drift detectable, but it does not explicitly identify the reviewed target-matrix version from which the list was loaded.

This boundary makes that origin directly reviewable without turning target metadata into runtime authority.

## Contract

`build_snapshot(...)` now accepts an optional:

```text
target_matrix_version
```

When it is omitted, historical behavior is preserved:

```text
snapshot schema_version = 1.0
no target_matrix_version
a no target_matrix_digest
```

When it is provided, the builder emits snapshot schema `1.1` with:

```text
target_matrix_version
target_matrix_digest
```

The matrix digest is SHA-256 over canonical JSON containing:

```text
matrix_version
all effective BenchmarkTarget entries in stable input order
```

Each target payload includes the existing target provenance fields:

```text
target_id
provider
model
api
configuration
source_date
api_family          # when present
max_output_tokens   # when present
```

The digest is therefore formatting-independent. Whitespace or JSON object-key order in the source file does not change it, while semantic target-matrix changes do.

## Snapshot identity

For schema `1.1`, both matrix provenance fields are part of the canonical base payload used to compute `snapshot_id`.

Consequences:

- changing `target_matrix_version` changes the matrix digest and snapshot ID;
- changing a target configuration claim changes the matrix digest and snapshot ID;
- changing reviewed `api_family`, `max_output_tokens`, provider/model/API, or source date changes the matrix digest and snapshot ID;
- replay can state exactly which reviewed matrix version was used without reconstructing provenance from target content alone.

## Compatibility

Snapshot schema `1.0` remains the historical format.

A call to `build_snapshot(...)` that does not provide `target_matrix_version`:

- still emits schema `1.0`;
- omits both matrix-provenance fields;
- keeps the historical target serialization path;
- does not retroactively relabel existing artifacts.

Snapshot schema `1.1` requires both a normalized matrix version and a canonical `sha256:<64 lowercase hex>` matrix digest. Partial provenance fails closed.

## Configuration semantics

This boundary does not upgrade declarative target configuration claims into runtime attestation.

The target matrix may still describe reviewed configuration such as access tier, temperature, thinking/reasoning mode, or provider-specific settings even when those values are not observable through the current provider-neutral runtime contract.

Existing explicit attestations remain separate:

- `api_family` — terminal execution evidence;
- `max_output_tokens` — terminal provider-neutral request-limit evidence.

The matrix digest proves **which reviewed target configuration was declared**, not that every declared provider-specific setting was observed at runtime.

## Authority boundary

Target-matrix provenance is benchmark evidence only.

It cannot:

- authorize a model, model group, deployment, tool, or side effect;
- expand the Policy Router decision;
- bypass gateway eligibility;
- mutate ranking policy;
- self-promote benchmark evidence;
- convert declarative configuration claims into authorization facts.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## CI boundary

The implementation is deterministic and credential-free:

- no provider calls;
- no network dependency;
- no secret-bearing inputs;
- digest behavior is tested against the checked-in `targets-v3.json` matrix;
- semantic drift is exercised by changing versioned target fields in memory;
- historical schema behavior is covered explicitly.

## Non-goals

This increment does not:

- parse the opaque `BenchmarkTarget.configuration` string into runtime controls;
- attest temperature, top-p, reasoning/thinking, or access/tier labels;
- attest `provider_timeout_seconds`;
- change provider adapters;
- change model-registry data;
- change ranking or promotion semantics;
- change Phase 14 consumer sequencing.

Issue #18 continues to defer OpsLens reconciliation and blocks starting RAGForge in parallel unless the normative integration order is explicitly revised.
