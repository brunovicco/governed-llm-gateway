# Evaluation

Gateway routing is treated as empirical optimization. Runtime code must not encode personal model preferences such as "model X is always best for agents".

## Phase 5 static ranking evidence

Phase 5 introduced deterministic ranking before the benchmark framework existed. Its `score_snapshot_id` identifies **static, versioned ranking input configuration** only.

It is not benchmark evidence and must not be represented as `benchmark_snapshot_id`.

Static Phase 5 inputs provide a reproducible bridge to later empirical routing while preserving:

- workload-specific versioned weights;
- deterministic score calculation;
- ranking-policy digest provenance;
- explicit rollback/replay of configuration;
- no hard-coded model preference in application logic.

## Phase 10 evaluation boundary

Phase 10 implements an offline-first, provider-neutral evaluation framework under `benchmarks/`. It is deliberately outside the gateway runtime packages: benchmark code and result artifacts do not become an execution dependency of `gateway-core`, `gateway-api`, or provider-neutral contracts.

The framework provides:

- strict versioned public/synthetic datasets;
- a strict, fully identified provider/model/API/configuration target matrix;
- deterministic local scorers with no model-as-judge or network dependency;
- a provider-neutral `BenchmarkExecutor` port and `BenchmarkRunner`;
- distinct quality and provider-availability observation states;
- deterministic scorecard aggregation;
- canonical dataset digests and immutable content-derived snapshot identifiers;
- versioned snapshot persistence suitable for review and Phase 11 promotion;
- benchmark code included in Ruff, mypy, Bandit, architecture validation and repository coverage.

## Generic Phase 10 baseline

`benchmarks/datasets/gateway-eval-v1.json` remains the original schema `1.0` generic benchmark baseline, explicitly classified `public`. It contains two public/synthetic cases for each original roadmap workload and uses the original generic deterministic scorers:

- `exact_json`;
- `contains_all`;
- `mapping_fields`;
- `ordered_sequence`.

That dataset is preserved as the initial framework evidence. It is not silently rewritten when workload-specific contracts evolve or when post-core multimodal evaluation is added.

## Workload-specific matrix — CORE 5/5 COMPLETE; MULTIMODAL EXTENSION COMPLETE

PRs #19–#24 added the initial five explicit versioned workload contracts on top of the Phase 10/11 foundation. PR #32 later added the roadmap-authorized multimodal extension after core execution and image-input foundations stabilized.

| Workload | Current reviewed contract | Core deterministic semantics |
|---|---|---|
| `structured_extraction` | `structured-extraction-v2` | bounded schema validity + exact type-sensitive leaf values |
| `rag_ptbr` | `rag-ptbr-v1` | reviewed required-fact coverage + explicit forbidden-claim regression checks |
| `code_generation` | `code-generation-v1` | normalized Python AST exactness; candidate code is never executed |
| `tool_use` | `tool-use-v1` | tool selection + exact recursive type-sensitive arguments; tool execution disabled |
| `agent_orchestration` | `agent-orchestration-v1` | observable agent/action sequence + handoff accuracy; step execution disabled |
| `multimodal_analysis` | `multimodal-analysis-v1` | actual fixture-bound image inspection with deterministic quadrant/color scoring |

`structured-extraction-v1` from PR #19 remains a historical contract. PR #22 added v2 rather than rewriting already-versioned semantics. The original `gateway-eval-v1` dataset also remains the historical five-workload generic baseline; multimodal was added as a new workload contract instead of mutating that dataset.

All workload contracts reuse the same non-authoritative evidence path:

```text
versioned dataset / fixture provenance
  -> contract validation
  -> BenchmarkRunner
  -> deterministic scorer
  -> observations + Scorecard
  -> content-addressed snapshot
  -> explicit promotion
```

The detailed workload ledger is `docs/evaluation/BENCHMARK_MATRIX.md`.

## Deterministic scorer boundary

Scorer references are validated for the complete dataset before the first provider call. Unknown scorers or contract drift therefore fail before a partial benchmark run can masquerade as valid evidence.

Workload-specific scorers are intentionally bounded and auditable. They do not create a general LLM-as-judge layer:

- RAG v1 uses reviewed facts/conflicting claims instead of arbitrary factuality judging;
- code-generation v1 compares safe normalized AST structure and does not execute candidate code;
- tool-use v1 scores proposed calls/arguments and never executes business tools;
- agent-orchestration v1 scores an observable trajectory and never executes agents or inspects hidden reasoning;
- structured-extraction v2 separates schema validity from exact reviewed value accuracy;
- multimodal-analysis v1 scores four exact visual quadrant labels against a deterministic real image fixture.

More permissive, behavioral or execution-based evaluators require separately reviewed contracts and security boundaries.

## Versioned target matrices and execution attestation

Benchmark targets remain reviewed configuration data rather than application-code preferences.

The repository preserves three target-matrix generations:

- `benchmarks/runners/targets-v1.json`, schema `1.0`: historical provider/model/API/configuration identity;
- `benchmarks/runners/targets-v2.json`, schema `1.1`: adds explicit reviewed `api_family`;
- `benchmarks/runners/targets-v3.json`, schema `1.2`: additionally requires positive `max_output_tokens`.

Every target still records provider, exact model identifier, API surface, benchmark configuration and source date. Later schemas add explicit fields rather than parsing the opaque `configuration` string.

Gateway-backed terminal evidence can preserve:

- concrete provider/model/deployment identity;
- selected `api_family`;
- concrete provider-neutral `max_output_tokens` carried by the attempted request;
- latency, fallback position, normalized usage and optional cost.

The benchmark runner fails closed before scoring when an attested completed call contradicts the declared provider/model target, declared API family, or declared max-output value. Missing required terminal attestation evidence also fails closed. Provider failures remain availability evidence and are not converted into false configuration mismatches.

This does **not** attest arbitrary values inside `BenchmarkTarget.configuration`. Temperature, top-p, reasoning/thinking mode, access/tier labels and provider-specific controls remain declarative unless a future provider-neutral runtime contract can prove them explicitly.

Free-tier or developer-access endpoints are benchmark/development targets only. They must not receive confidential/private evaluation fixtures by default.

A result must not be described as a "best model" result unless provider, exact model, API/configuration provenance, run date and benchmark version are stated together.

## Quality versus availability

Offline quality evidence and provider availability are intentionally distinct.

A completed provider call is scored deterministically and becomes either:

- `succeeded`; or
- `quality_failure`.

A timeout, rate limit, provider outage or other failed provider call becomes `provider_failure` and has `quality_score = None`.

Therefore a 429 or timeout cannot silently become a zero-quality model result. Provider failures contribute to availability/error evidence instead.

Scorecards aggregate independently:

- availability rate;
- quality success rate among completed calls;
- mean quality score among completed calls;
- latency p50/p95;
- TTFT p50/p95 where present;
- normalized input/output usage;
- total benchmark cost;
- rate-limit error count;
- fallback frequency;
- stable provider error counts.

Online gateway runtime health and circuit-breaker state remain separate mutable operational evidence.

## Snapshot reproducibility

A dataset digest is derived from canonical JSON over the complete ordered benchmark case content.

Historical snapshot schema `1.0` remains valid. Its snapshot identifier covers:

- snapshot schema version;
- benchmark version;
- runner version;
- run date;
- dataset digest;
- exact benchmark targets and configurations;
- normalized observations;
- aggregated scorecards.

New snapshots may opt into schema `1.1` by supplying an explicit `target_matrix_version`. Schema 1.1 additionally stores a canonical `target_matrix_digest` over the matrix version plus the complete effective ordered target payload. Both matrix provenance fields participate in `snapshot_id`.

This makes reviewed matrix origin directly auditable while preserving historical schema 1.0 artifact shape. The matrix digest proves which target declaration was used; it does not turn every opaque configuration claim into runtime attestation.

Observed provider/model/deployment identity, `api_family` and `max_output_tokens` are serialized into benchmark observations only when present. Their presence therefore affects immutable snapshot identity without fabricating values for historical/replay evidence.

Persisted artifacts are stored under:

```text
benchmarks/results/<benchmark-version>/<snapshot-sha256>.json
```

Persistence is immutable/idempotent: an existing snapshot ID with different content fails closed. Raw provider responses are not part of the score snapshot contract.

## CI and live-provider boundary

Default CI is credential-free and deterministic. It validates loaders, workload contracts, multimodal fixture integrity/publication metadata, scorers, aggregation, response normalization, attestation, reproducibility, failure classification, privacy-oriented result structure and architecture rules without live PDP/provider calls.

The repository now has provider-neutral building blocks for a future gateway-backed multimodal execution path:

1. validated `multimodal-analysis-v1` case + immutable fixture publication;
2. provider-neutral `GatewayRequest` materialization with `requirements.vision = true`;
3. ordinary gateway authorization/routing/resilience/provider execution;
4. terminal `GatewayResponse` normalization into `ProviderCall`;
5. execution-identity/API-family/max-output integrity checks before deterministic scoring.

There is still no benchmark-side model-forcing bypass and no required live-provider executor in default CI. A future live execution adapter must call an already-authorized gateway composition and fail closed if observed terminal execution does not match the reviewed benchmark target requirements.

Credentials must remain outside the default quality gate. Public/synthetic workload fixtures do not create a policy exception for confidential/private provider use.

## Phase 11 promotion boundary

ADR-0009 is accepted. Phase 11 converts selected benchmark evidence into runtime ranking inputs only through an explicit, attributable promotion boundary:

```text
immutable benchmark snapshot
  -> explicit approval/promotion
  -> content-addressed ranking evidence
  -> evidence-driven ranking policy
  -> runtime ranking inside the existing authorized/eligible set
```

Runtime code does not import the offline `benchmarks/` source root and does not discover or load the newest benchmark snapshot automatically. `ranking_evidence.py` validates a promoted artifact through a runtime-side contract and verifies its content-derived `evidence_id` before it can be compiled into a ranking policy.

Promotion explicitly maps benchmark target/workload identities to runtime deployment/workload identities. It fails closed when completed quality evidence is absent, so provider-only failures cannot be converted into false quality-zero evidence.

## Benchmark-hybrid ranking semantics

The initial Phase 11 compiler is deliberately hybrid rather than inventing undocumented normalization. It replaces only the two benchmark dimensions that already have bounded, directly consumable meaning:

- `quality` <- promoted mean benchmark quality;
- `availability` <- promoted benchmark availability rate.

The following remain explicit Phase 5 static/versioned inputs:

- reliability;
- normalized latency score;
- normalized cost score;
- workload weights;
- `expected_latency_ms` used by the hard latency eligibility gate.

Raw benchmark p95 latency and cost evidence are retained in promoted evidence but are **not** silently converted to `[0,1]` ranking scores. A future normalization rule requires its own explicit reviewed semantics.

Hybrid compilation is all-or-nothing for deployments already represented by the approved base ranking policy. Missing promoted evidence fails closed rather than silently mixing provenance.

## Runtime activation boundary

The current repository does not contain an executable bootstrap that discovers ranking configuration from `config/`. Gateway composition receives an immutable `RankingPolicy` object explicitly. Therefore Phase 11 activation is an explicit composition action: validated promoted evidence is compiled into a schema `1.1` `EvidenceDrivenRankingPolicy`, and that exact object is injected into the coordinator or runtime service.

The legacy `ranking_policy_yaml.py` adapter remains a strict Phase 5/schema `1.0` loader and must not be interpreted as an automatic Phase 11 activation mechanism. Runtime must not scan `benchmarks/results/`, choose a newest promotion or infer an active evidence-driven policy from files.

If a future executable bootstrap persists/loads schema `1.1` policies, it must require an explicitly pinned approved artifact identity and preserve the same fail-closed provenance checks.

## Runtime provenance and explainability

Static Phase 5 routing keeps Phase 11 provenance unset. Evidence-driven routing records:

- ranking policy version and digest;
- `score_snapshot_id`;
- exact `benchmark_snapshot_id`;
- `score_provenance_mode`;
- `manual_override_id` when an override is active.

The benchmark snapshot and manual override identities participate in deterministic routing-decision identity. Changing provenance therefore changes `routing_decision_id` even when the selected deployment or effective numeric score is unchanged.

`POST /v1/route/explain` serializes the same Phase 11 reconstruction fields under its ranking evidence. Static policies return those optional fields as null; evidence-driven and manual-override policies return the exact active identities. This keeps the external explanation surface aligned with internal routing provenance without exposing prompts, provider payloads or credentials.

This is reconstruction evidence only. It does not become a source of authorization.

## Manual override and rollback

Manual override is explicit, versioned, attributable configuration rather than mutable in-memory state. A `ManualOverrideBundle` records:

- schema/version;
- approval date;
- approving operator identity;
- reason;
- exact workload/deployment targets;
- replacement quality and/or availability values.

The complete canonical bundle is content-addressed as `manual_override_id`. The initial override contract may replace only `quality` and `availability`, matching the dimensions promoted by the current benchmark compiler. It cannot add deployments, modify policy authorization, bypass eligibility or implicitly stack on another active override.

Replacing an override requires returning to the approved benchmark-hybrid baseline and applying a newly approved bundle.

Rollback selects an explicitly identified previously approved immutable ranking artifact. The approval artifact identity binds approval metadata to the exact ranking-policy digest and benchmark/override provenance. Unknown or ambiguous rollback targets fail closed.

## Authorization invariant

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Benchmark evidence and manual overrides may only change ordering among candidates already returned by the PDP and still passing gateway eligibility gates. Regression tests cover both candidate-set monotonicity and disabled-deployment rejection for benchmark-hybrid and manual-override modes.

No benchmark run, telemetry signal, provider outcome or runtime observation automatically rewrites the active ranking policy.
