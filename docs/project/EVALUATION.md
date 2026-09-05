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

`benchmarks/datasets/gateway-eval-v1.json` remains the original schema `1.0` generic benchmark baseline, explicitly classified `public`. It contains two public/synthetic cases for each roadmap workload and uses the original generic deterministic scorers:

- `exact_json`;
- `contains_all`;
- `mapping_fields`;
- `ordered_sequence`.

That dataset is preserved as the initial framework evidence. It is not silently rewritten when workload-specific contracts evolve.

## Workload-specific matrix — COMPLETE 5/5

PRs #19–#24 added explicit versioned workload contracts on top of the Phase 10/11 foundation:

| Workload | Current reviewed contract | Core deterministic semantics |
|---|---|---|
| `structured_extraction` | `structured-extraction-v2` | bounded schema validity + exact type-sensitive leaf values |
| `rag_ptbr` | `rag-ptbr-v1` | reviewed required-fact coverage + explicit forbidden-claim regression checks |
| `code_generation` | `code-generation-v1` | normalized Python AST exactness; candidate code is never executed |
| `tool_use` | `tool-use-v1` | tool selection + exact recursive type-sensitive arguments; tool execution disabled |
| `agent_orchestration` | `agent-orchestration-v1` | observable agent/action sequence + handoff accuracy; step execution disabled |

`structured-extraction-v1` from PR #19 remains a historical contract. PR #22 added v2 rather than rewriting already-versioned semantics.

All five workload contracts reuse:

```text
versioned dataset
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
- structured-extraction v2 separates schema validity from exact reviewed value accuracy.

More permissive, behavioral or execution-based evaluators require separately reviewed contracts and security boundaries.

## Initial target matrix

`benchmarks/runners/targets-v1.json` records matrix version `phase10-targets-v1`. Every target records:

- provider;
- exact model identifier;
- API family/surface;
- benchmark configuration;
- source date.

The initial matrix contains development/benchmark targets for NVIDIA, Groq, OpenRouter and Google Gemini, plus paid/control targets for OpenAI Responses and Anthropic Messages.

Free-tier or developer-access endpoints are benchmark/development targets only. They must not receive confidential/private evaluation fixtures by default.

A result must not be described as a "best model" result unless provider, exact model, API, configuration, run date and benchmark version are stated together.

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

A dataset digest is derived from canonical JSON over the complete ordered benchmark case content. A benchmark snapshot identifier is a `sha256:` digest over:

- snapshot schema version;
- benchmark version;
- runner version;
- run date;
- dataset digest;
- exact benchmark targets and configurations;
- normalized observations;
- aggregated scorecards.

Changing a target configuration changes the snapshot ID. Rebuilding the same evidence produces the same ID and canonical JSON.

Persisted artifacts are stored under:

```text
benchmarks/results/<benchmark-version>/<snapshot-sha256>.json
```

Persistence is immutable/idempotent: an existing snapshot ID with different content fails closed. Raw provider responses are not part of the score snapshot contract.

## CI and live-provider boundary

Default CI is credential-free and deterministic. It validates loaders, workload contracts, scorers, aggregation, reproducibility, failure classification, privacy-oriented result structure and architecture rules without live PDP/provider calls.

Live-provider benchmark execution must remain explicitly separated under the existing `live_provider` pytest marker or an equally explicit manual benchmark workflow. Credentials must not be required by the default quality gate.

Public/synthetic workload fixtures do not create a policy exception for confidential/private provider use.

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
