# Benchmark Workload Matrix

Status: **COMPLETE — all roadmap-listed benchmark classes are represented by reviewed deterministic contracts; the core 5/5 baseline and historical versions remain preserved**

The Phase 10 framework originally established a generic provider-neutral benchmark pipeline. PRs #19–#24 then added workload-specific deterministic contracts on top of that foundation without turning the benchmark layer into runtime authority. After core execution stabilized, PR #32 added the roadmap-authorized `multimodal_analysis` extension, PR #44 added `long_context`, PR #45 added `classification`, PR #47 added `reasoning`, PR #48 added `code_review`, PR #50 added `security_analysis`, PR #51 added `tool_selection`, PR #52 added `tool_argument_generation`, PR #55 added `multi_step_tool_use`, PR #58 added `rag_answer`, and PR #61 added the distinct `json_schema_compliance` class.

## Matrix

| Workload | Reviewed benchmark version | Scorer / semantics | PR |
|---|---|---|---|
| `structured_extraction` | `structured-extraction-v2` | bounded recursive schema validation + exact type-sensitive leaf-value accuracy | #19 established v1; #22 added v2 hardening |
| `json_schema_compliance` | `json-schema-compliance-v1` | binary Draft 2020-12 compliance over normalized `JsonValue`; schemas reuse the bounded Phase 7 acceptance boundary and exact extraction values are out of scope | #61 |
| `rag_ptbr` | `rag-ptbr-v1` | reviewed required-fact coverage with explicit forbidden-claim regression checks | #20 |
| `rag_answer` | `rag-answer-v1` | reviewed required-fact coverage plus citation set-F1 against checked-in synthetic source IDs; unknown citations and inconsistent reference grounding fail closed | #58 |
| `code_generation` | `code-generation-v1` | normalized Python AST exactness; candidate code is never executed | #21 |
| `tool_use` | `tool-use-v1` | tool-selection score + exact recursive type-sensitive argument score; tool execution disabled | #23 |
| `agent_orchestration` | `agent-orchestration-v1` | observable agent/action sequence + handoff accuracy; agent execution disabled | #24 |
| `multimodal_analysis` | `multimodal-analysis-v1` | actual fixture-bound image inspection + deterministic quadrant/color scoring | #32 |
| `long_context` | `long-context-v1` | tokenizer-neutral retrieval of one reviewed synthetic needle across early/middle/late positions in 8,192 generated records | #44 |
| `classification` | `classification-v1` | exact closed-set support-intent label from immutable `support-intents-v1`; no model-as-judge | #45 |
| `reasoning` | `reasoning-v1` | exact type-sensitive final-answer scoring across four reviewed reasoning families; no chain-of-thought collection | #47 |
| `code_review` | `code-review-v1` | structured non-security findings with deterministic set-F1 scoring; candidate code is never executed | #48 |
| `security_analysis` | `security-analysis-v1` | defensive structured security findings with deterministic set-F1 scoring; candidate code is never executed and exploitation is out of scope | #50 |
| `tool_selection` | `tool-selection-v1` | exact reviewed tool-or-no-tool selection from immutable `support-tools-v1`; arguments and execution are out of scope | #51 |
| `tool_argument_generation` | `tool-argument-generation-v1` | fixed reviewed tool plus recursive exact, type-sensitive argument matching; selection and execution are out of scope | #52 |
| `multi_step_tool_use` | `multi-step-tool-use-v1` | ordered 2–3 step reviewed tool proposals with positional selection and exact type-sensitive argument scoring; tool execution disabled | #55 |

`structured-extraction-v1` is preserved as historical benchmark semantics. The v2 contract is the current hardened structured-extraction reference; v1 evidence must not be silently rewritten.

The original generic `gateway-eval-v1` dataset remains the historical five-workload framework baseline. Post-core workloads were added as separate versioned contracts rather than mutating that dataset.

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

### json_schema_compliance

`json-schema-compliance-v1` isolates the roadmap-listed schema-compliance dimension from extraction correctness. It accepts any normalized provider-neutral `JsonValue` that satisfies the reviewed schema and returns binary quality evidence: valid is `1.0`, any schema violation is `0.0`.

Benchmark schema acceptance reuses the existing Phase 7 bounded Draft 2020-12 structured-output validator, including its depth/size controls and rejection of remote references and unsupported validation keywords. The checked-in `expected` value is only a satisfiable reference witness, not an exact-value target. Because `ProviderCall.output` is already normalized `JsonValue`, malformed raw JSON text, markdown fences, transport truncation and provider-native structured-output enforcement remain separate provider/execution/normalization facts rather than being fabricated by this scorer.

### rag_ptbr

The v1 scorer checks reviewed required facts inside a synthetic/public PT-BR context and forces a zero score when a reviewed conflicting/unsupported `forbidden_claim` appears.

It intentionally does not claim arbitrary factuality evaluation and does not call another model as judge.

### rag_answer

`rag-answer-v1` evaluates a model answer against checked-in public/synthetic source records whose reviewed source IDs are materialized into the prompt. It scores required-fact coverage and citation set-F1 separately, then combines them deterministically.

Unknown/invented citations fail closed. Reference ground truth also fails closed if its reviewed citations do not contain every required fact, so benchmark truth cannot silently drift into an unsupported answer/source pairing. The workload performs no retrieval, embedding, reranking, URL fetch, provider-specific grounding call or LLM-as-judge step; source records are evaluation ground truth only and never data-access authorization.

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

### long_context

`long-context-v1` deterministically materializes exactly 8,192 synthetic numbered records per case and places one reviewed needle at an early, middle or late record. The checked-in dataset stores the compact generator specification; the canonical dataset digest is computed over the fully materialized prompt.

The contract deliberately does not infer an exact token count or provider context-window capability from character length. Those are provider/runtime facts, not benchmark metadata. The scorer accepts only the exact reviewed `{"needle": "<value>"}` result.

### classification

`classification-v1` evaluates exact closed-set classification over six reviewed synthetic support-intent labels in `support-intents-v1`, with exactly two cases per label.

The scorer requires exactly `{"label": "<reviewed-label>"}`. Unknown labels, wrong types, extra/missing fields or the wrong reviewed label score zero. No embeddings, external data or model-as-judge path is used.

### security_analysis

`security-analysis-v1` evaluates defensive structured findings over checked-in synthetic Python. Its reviewed security vocabulary is separate from `code-review-v1`; exact finding validity and set-F1 scoring are deterministic, candidate code is never executed, and exploitation instructions are outside the contract.

### tool_selection

`tool-selection-v1` measures only exact reviewed tool choice or explicit no-tool choice from immutable `support-tools-v1`. Argument generation and tool execution are intentionally excluded so selection failures remain attributable.

### tool_argument_generation

`tool-argument-generation-v1` fixes the reviewed tool identity in the case and scores only the generated `arguments` object with recursive exact, type-sensitive comparison. Tool selection and execution remain separate boundaries; `selected_tool` is benchmark ground truth, not runtime authorization.

### multi_step_tool_use

`multi-step-tool-use-v1` evaluates an ordered proposal of two or three reviewed tool calls. Immutable synthetic intermediate-result context is supplied by each case; the benchmark never executes tools or MCP calls. Positional tool selection and exact recursive type-sensitive arguments are scored separately, and arguments on a step with the wrong tool are not rewarded. `execute_tools=false` is mandatory, and the expected trajectory remains benchmark ground truth rather than runtime authorization.

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

## Additional post-core deterministic workloads

PR #44 added `long-context-v1` without a provider tokenizer dependency or a fabricated token-count claim. PR #45 added `classification-v1` as an exact closed-set workload with immutable label vocabulary and strict dataset drift checks. PR #47 added `reasoning-v1` with answer-only, type-sensitive scoring and no chain-of-thought collection. PR #48 added `code-review-v1` with structured reviewed non-security findings, clean-case false-positive coverage and no candidate execution. PR #50 added `security-analysis-v1` with a separate defensive security vocabulary and no exploitation path. PR #51 added `tool-selection-v1` to isolate exact tool-choice quality. PR #52 added `tool-argument-generation-v1` to isolate argument quality after the reviewed tool identity is fixed. PR #55 added `multi-step-tool-use-v1` to measure short ordered tool-call proposals against immutable synthetic intermediate context without executing tools. PR #58 added `rag-answer-v1` to measure reviewed fact grounding plus explicit source-ID citation quality without performing retrieval. PR #61 added `json-schema-compliance-v1` to isolate normalized JSON Schema validity from extraction-value correctness while reusing the existing bounded Phase 7 schema acceptance boundary. PR #64 preserved reviewed offline quality components in observations, scorecards and snapshot schema 1.2 without changing promotion or ranking.

These are consumer-agnostic benchmark extensions. None adds a live executor, changes provider selection, or creates a benchmark-only authorization/routing path.

## Roadmap measurement evidence

PR #64 preserves the Roadmap quality dimensions already demonstrated by reviewed deterministic scorers instead of collapsing them into one scalar only:

- `schema_validity`;
- `tool_selection_accuracy`;
- `tool_argument_accuracy`;
- `trajectory_success`;
- `grounding`.

`quality_success_rate` remains the reviewed task-success aggregate. Latency p50/p95, TTFT, normalized input/output units, cost, provider/rate-limit errors and fallback frequency remain operational scorecard evidence and are not conflated with offline quality. Provider failures carry no component quality and do not dilute completed-call component means.

PT-BR quality remains an explicit gap: `rag-ptbr-v1` measures required-fact coverage with forbidden-claim checks in PT-BR, not independent Portuguese fluency/grammar/localization/style quality. The ledger therefore does not fabricate a `pt_br_quality` alias.

## Target matrices

The reviewed target catalog is versioned rather than rewritten:

- `targets-v1.json` / schema `1.0`: provider/model/API/configuration/source-date identity;
- `targets-v2.json` / schema `1.1`: explicit reviewed `api_family`;
- `targets-v3.json` / schema `1.2`: explicit reviewed `api_family` and positive `max_output_tokens`.

Schema 1.1/1.2 attestation compares declared target fields to observed terminal evidence before scoring. Historical schema 1.0 remains valid without those later requirements.

## Snapshot provenance

Historical benchmark snapshot schema `1.0` remains valid and content-addresses the benchmark version, runner version, run date, dataset digest, target payloads, observations and scorecards.

Schema `1.1` remains the historical target-matrix provenance extension: a normalized matrix version produces a canonical `target_matrix_digest`, and both provenance fields participate in `snapshot_id`.

PR #64 added snapshot schema `1.2` only when reviewed quality component evidence is present. Observation `quality_metrics` and scorecard `mean_quality_metrics` are serialized canonically and participate in `snapshot_id`; target-matrix provenance may coexist as a complete version/digest pair. Empty component mappings are omitted, so historical 1.0/1.1 payload semantics remain unchanged.

This proves which reviewed evidence was persisted. It does not attest arbitrary provider-specific configuration claims or make component metrics ranking authority.

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

Latest validated `main` baseline after PR #64:

- commit `ef1d83c8c82a63a3f5abc533d7dc75db51144690`;
- post-merge quality run `34048733993` — PASS;
- 714 tests passed;
- 82.21% aggregate coverage;
- strict mypy and Ruff passed across 172 source files;
- Bandit reported no issues across 15,972 LOC;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

## Next boundary

All roadmap-listed benchmark classes now have reviewed versioned contracts. That completion does **not** create a new Phase 14 consumer migration exception.

Issue #18 still defers OpsLens reconciliation and explicitly prevents starting RAGForge in parallel unless the normative integration order is revised.

Until that changes, further gateway work should be consumer-agnostic and independently justified. The Roadmap measurement audit is now explicit: all currently supportable deterministic component measures are preserved, while independent PT-BR quality remains the next concrete benchmark-measurement gap. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.
