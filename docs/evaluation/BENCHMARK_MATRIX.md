# Benchmark Workload Matrix

Status: **COMPLETE — 5/5 core roadmap workloads plus post-core multimodal extension implemented**

The Phase 10 framework originally established a generic provider-neutral benchmark pipeline. PRs #19–#24 then added workload-specific deterministic contracts on top of that foundation without turning the benchmark layer into runtime authority. After core execution stabilized, PR #32 added the roadmap-authorized `multimodal_analysis` extension.

## Matrix

| Workload | Reviewed benchmark version | Scorer / semantics | PR |
|---|---|---|---|
| `structured_extraction` | `structured-extraction-v2` | bounded recursive schema validation + exact type-sensitive leaf-value accuracy | #19 established v1; #22 added v2 hardening |
| `rag_ptbr` | `rag-ptbr-v1` | reviewed required-fact coverage with explicit forbidden-claim regression checks | #20 |
| `code_generation` | `code-generation-v1` | normalized Python AST exactness; candidate code is never executed | #21 |
| `tool_use` | `tool-use-v1` | tool-selection score + exact recursive type-sensitive argument score; tool execution disabled | #23 |
| `agent_orchestration` | `agent-orchestration-v1` | observable agent/action sequence + handoff accuracy; agent execution disabled | #24 |
| `multimodal_analysis` | `multimodal-analysis-v1` | actual fixture-bound image inspection + deterministic quadrant/color scoring | #32 |

`structured-extraction-v1` is preserved as historical benchmark semantics. The v2 contract is the current hardened structured-extraction reference; v1 evidence must not be silently rewritten.

The original generic `gateway-eval-v1` dataset remains the historical five-workload framework baseline. `multimodal_analysis` was added as a separate post-core workload contract rather than mutating that dataset.

## Shared evidence pipeline

Every workload reuses the provider-neutral Phase 10/11 path:

```text
versioned public/synthetic dataset or fixture provenance
  -> contract validation
  -> BenchmarkRunner
  -> deterministic workload scorer
  -> observations + Scorecard
  -> content-addressed snapshot
  -> explicit attributable promotion
  -> ranking evidence
```

The benchmark framework continues to distinguish provider availability from completed model quality:

- provider timeout/rate-limit/outage -> `provider_failure`, `quality_score = None`;
- completed but insufficient output -> `quality_failure`;
- completed output meeting the reviewed quality threshold -> `succeeded`.

A provider outage therefore does not become a false zero-quality result.

## Workload boundaries

### structured_extraction

The hardened v2 contract evaluates schema validity separately from exact extracted values. Validation is bounded and fail-closed, with explicit object/array/scalar semantics and stable issue paths/codes.

It does not use permissive JSON-text repair and it does not convert benchmark evidence into runtime structured-output authorization.

### rag_ptbr

The v1 scorer checks reviewed required facts inside a synthetic/public PT-BR context and forces a zero score when a reviewed conflicting/unsupported `forbidden_claim` appears.

It intentionally does not claim arbitrary factuality evaluation and does not call another model as judge.

### code_generation

The v1 contract parses expected and candidate Python into ASTs and compares normalized structure. Unsafe primitives are rejected and model-generated candidate code is never executed, imported, eval'd or launched in a subprocess.

Behavioral/sandboxed code execution would require a separate explicit security contract.

### tool_use

The v1 contract scores the model's proposed tool decision and arguments only. It can represent explicit abstention and rejects undeclared tools/invalid arguments fail-closed.

`execute_tool=false` is mandatory. Business-tool authorization, execution and `ToolResult` ownership remain outside the gateway benchmark and runtime normalization layers.

### agent_orchestration

The v1 contract scores an observable proposed trajectory:

```json
{
  "steps": [
    {"agent": "router", "action": "classify_request", "handoff_to": "knowledge"},
    {"agent": "knowledge", "action": "answer_public_knowledge", "handoff_to": null}
  ]
}
```

It evaluates sequence and handoffs without hidden reasoning. `execute_steps=false` is mandatory. It does not execute agents, tools, human escalations or side effects and it is not a multi-agent runtime.

### multimodal_analysis

`multimodal-analysis-v1` evaluates a real deterministic 16 × 16 RGB PNG fixture with four solid-color quadrants. The case is bound to a reviewed fixture ID, media type and SHA-256 digest.

The deterministic scorer requires exactly `top_left`, `top_right`, `bottom_left` and `bottom_right`. Each exact color match contributes `0.25`. Invalid top-level shape scores zero. No model-as-judge is used.

## Post-core multimodal and evidence hardening

The roadmap allows multimodal only after core execution is stable. The completed sequence is:

```text
bounded provider-neutral image input
  -> reviewed native provider translations
  -> local fixture integrity
  -> immutable public fixture publication
  -> multimodal-analysis-v1 dataset/scorer
  -> provider-neutral GatewayRequest materialization
  -> ordinary authorized gateway execution boundary
  -> GatewayResponse -> ProviderCall normalization
  -> terminal execution identity / API family / max-output attestation
  -> immutable snapshot + target-matrix provenance
```

### Runtime image input

PRs #26–#28 established HTTPS URL image input for user messages with explicit `requirements.vision = true`. Native reviewed translations exist for OpenAI Responses, Anthropic Messages and Gemini. Generic OpenAI-compatible image input remains fail closed unless its exact endpoint behavior is separately reviewed.

### Fixture and workload evidence

PRs #29–#31 added a credential-free fixture integrity/publication path. PR #32 added `multimodal-analysis-v1`, backed by the real deterministic `multimodal.quadrants_rgb_001` PNG.

Default CI does not fetch the published fixture or call a provider.

### Gateway execution composition boundary

PR #33 materializes a validated multimodal case into the existing provider-neutral `GatewayRequest`; PR #34 normalizes a terminal `GatewayResponse` into benchmark `ProviderCall` evidence.

Materialization never chooses or authorizes a provider/model. The request must still pass through normal PDP authorization, gateway eligibility, ranking, resilience and execution.

### Evidence integrity and attestation

PRs #35–#42 progressively preserve and verify execution facts the runtime can actually prove:

- observed provider/model/deployment identity;
- terminal `api_family`;
- terminal provider-neutral `max_output_tokens`;
- explicit target schema evolution (`1.0` -> `1.1` -> `1.2`);
- optional snapshot target-matrix version/digest provenance.

Completed calls that contradict an attested target fail closed before deterministic scoring. Provider failures remain availability evidence.

Opaque configuration strings are still declarative. The benchmark does not infer temperature, top-p, reasoning/thinking mode, access tier or provider-specific controls from those strings.

## Target matrices

The reviewed target catalog is versioned rather than rewritten:

- `targets-v1.json` / schema `1.0`: provider/model/API/configuration/source-date identity;
- `targets-v2.json` / schema `1.1`: explicit reviewed `api_family`;
- `targets-v3.json` / schema `1.2`: explicit reviewed `api_family` and positive `max_output_tokens`.

Schema 1.1/1.2 attestation compares declared target fields to observed terminal evidence before scoring. Historical schema 1.0 remains valid without those later requirements.

## Snapshot provenance

Historical benchmark snapshot schema `1.0` remains valid and content-addresses the benchmark version, runner version, run date, dataset digest, target payloads, observations and scorecards.

New snapshots may opt into schema `1.1` target-matrix provenance by supplying a normalized matrix version. The snapshot then records a canonical `target_matrix_digest` over matrix version plus the complete ordered target payload. Both provenance fields participate in `snapshot_id`.

This proves which reviewed matrix declaration produced the snapshot. It does not attest arbitrary provider-specific configuration claims.

## Authority boundary

The permanent project invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Benchmark data, observations, scorecards, snapshots and promoted evidence cannot:

- add an unauthorized model group or deployment;
- bypass gateway eligibility or governance scope;
- authorize a business tool or side effect;
- execute generated code;
- execute an agent trajectory;
- force a provider/model solely because it is named by a benchmark target;
- self-promote;
- automatically activate a new ranking policy;
- mutate policy or routing from online telemetry.

Promotion is an explicit reviewed conversion from immutable benchmark evidence into ranking inputs. Ranking can only reorder candidates already inside the authorized and eligible set.

## CI boundary

Default CI remains credential-free and deterministic:

- no live provider/network dependency is required by workload contract tests;
- no LLM-as-judge path is required;
- public/synthetic fixtures are used;
- workload/target/attestation contract drift fails closed;
- snapshot/digest behavior is replayable;
- architecture/security/secret gates cover benchmark code.

Latest validated `main` baseline after PR #42:

- commit `cb0fbac9c278df3e20bf9b26b20cb06f697f4d71`;
- post-merge quality run `33993826048` — PASS;
- 546 tests passed;
- 82.08% aggregate coverage;
- strict mypy and Ruff passed across 151 source files;
- Bandit reported no issues across 13,905 LOC;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

## Next boundary

Completion of the core 5/5 matrix, multimodal extension and execution-evidence hardening does **not** create a new Phase 14 consumer migration exception.

Issue #18 still defers OpsLens reconciliation and explicitly prevents starting RAGForge in parallel unless the normative integration order is revised.

Until that changes, further gateway work should be consumer-agnostic and independently justified. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.
