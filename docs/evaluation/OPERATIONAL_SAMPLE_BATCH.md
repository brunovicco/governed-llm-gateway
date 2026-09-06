# Operational Sample Batch Handoff

Status: **IN DEVELOPMENT through issue #78.**

## Purpose

PR #76 records metadata-only provider-attempt samples into an optional process-local recorder without making evidence collection an inference-availability dependency. The next boundary is moving a complete local sample window out of that process without putting remote I/O back into `ResilientExecutionService` or `StreamingExecutionService`.

Issue #78 defines a durable handoff artifact for that purpose.

## Artifact scope

`OperationalSampleBatch` is an immutable schema `1.0` batch containing exactly one complete exported window for one declared `source_instance_id`.

It preserves:

- `schema_version`;
- explicit `batch_version`;
- `source_instance_id`;
- `exporter_id` and `exporter_version`;
- UTC `window_start` / `window_end`;
- UTC `exported_at`;
- content-derived `sha256:` `batch_id`;
- canonically ordered metadata-only `OperationalAttemptSample` records.

The `batch_id` covers the complete canonical payload except the identifier itself. Any change in provenance, window boundaries or samples therefore changes the identity.

## Completeness claim

The batch makes a deliberately narrow completeness claim:

```text
complete for source_instance_id + [window_start, window_end)
```

It does **not** claim:

- fleet-wide completeness;
- distributed replica discovery;
- exactly-once delivery across processes;
- cross-region completeness;
- backend ingestion success;
- completeness outside the declared window.

A later shared/production aggregator must know which source instances are expected before it can claim fleet-level completeness.

## Export boundary

`OperationalSampleBatchExporter` reads an already-complete window through `OperationalSampleSource` and creates the content-addressed batch.

The exporter is intentionally outside provider execution. It has no provider/model call path and is not injected into the runtime recorder.

If the source cannot prove window completeness, or if the requested window has no attempts, export fails closed. Export failure does not alter any provider execution because export is not part of the inference path.

## Load/source boundary

The strict JSON adapter rejects:

- malformed JSON;
- duplicate JSON object keys;
- unknown or missing fields;
- malformed timestamps/identifiers;
- unsupported outcome/error-kind values;
- non-canonical sample ordering;
- samples outside the declared window;
- duplicate provider-attempt identities;
- tampered content where `batch_id` no longer matches the canonical payload.

`OperationalSampleBatchSource` exposes a validated batch through the existing `OperationalSampleSource` port. It may serve complete subwindows only inside the batch coverage and fails closed outside that range.

The existing `OperationalEvidenceMaterializer` can therefore consume a loaded batch without adding a new ranking or authorization path.

## Privacy boundary

The artifact remains metadata-only. It contains no prompt, completion, message body, tool payload, business payload, credential, API key, Authorization header or provider secret.

## Authority boundary

Permanent invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operational sample batches cannot:

- authorize a model, provider, deployment or model group;
- restore an ineligible candidate;
- force a benchmark/provider target;
- modify ranking weights;
- modify `StaticDeploymentScore` or `OperationalRankingService`;
- self-promote;
- rewrite active policy;
- create adaptive routing.

They are evidence-transport artifacts only.

## Explicitly not implemented by issue #78

- no remote/network exporter in provider execution;
- no production/shared backend;
- no fleet membership/discovery contract;
- no multi-replica merge semantics;
- no metrics/OTel query adapter;
- no online score normalization;
- no ranking-policy activation from operational evidence;
- no OpsLens or RAGForge work.

## Next boundary

After a validated batch handoff exists, a later consumer-agnostic increment may define a shared ingestion/source contract or fleet-level completeness model. Remote transport must remain decoupled from inference availability, and any operational-score use still requires a separate explicit versioned ranking policy.

Issue #18 remains OPEN and authoritative for Phase 14 sequencing.
