# Initial Benchmark Workload Matrix

Status: **COMPLETE — 5/5 initial roadmap workloads implemented**

The Phase 10 framework originally established a generic provider-neutral benchmark pipeline. PRs #19–#24 then added workload-specific deterministic contracts on top of that foundation without turning the benchmark layer into runtime authority.

## Matrix

| Workload | Reviewed benchmark version | Scorer / semantics | PR |
|---|---|---|---|
| `structured_extraction` | `structured-extraction-v2` | bounded recursive schema validation + exact type-sensitive leaf-value accuracy | #19 established v1; #22 added v2 hardening |
| `rag_ptbr` | `rag-ptbr-v1` | reviewed required-fact coverage with explicit forbidden-claim regression checks | #20 |
| `code_generation` | `code-generation-v1` | normalized Python AST exactness; candidate code is never executed | #21 |
| `tool_use` | `tool-use-v1` | tool-selection score + exact recursive type-sensitive argument score; tool execution disabled | #23 |
| `agent_orchestration` | `agent-orchestration-v1` | observable agent/action sequence + handoff accuracy; agent execution disabled | #24 |

`structured-extraction-v1` is preserved as historical benchmark semantics. The v2 contract is the current hardened structured-extraction reference; v1 evidence must not be silently rewritten.

## Shared evidence pipeline

Every workload reuses the existing provider-neutral Phase 10/11 path:

```text
versioned public/synthetic dataset
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

## Post-core multimodal extension

The roadmap also names `multimodal analysis` as a future benchmark class after core execution is stable. The gateway now has a reviewed provider-neutral image-input contract plus native translations for OpenAI Responses, Anthropic Messages and Google Gemini.

A multimodal benchmark must still evaluate **actual visual input**. Text-only prompts describing an imagined image are not accepted as a multimodal benchmark substitute.

The first post-core benchmark increment therefore establishes a credential-free local fixture boundary before defining `multimodal_analysis-v1`:

```text
strict public fixture manifest
  -> normalized relative path + media type + SHA-256
  -> root-containment / size / digest validation
  -> verified fixture bytes
  -> future multimodal BenchmarkExecutor
```

This foundation does not add a new `BenchmarkWorkload`, scorer, scorecard semantics, snapshot promotion, or ranking evidence. A later reviewed increment must bind cases to verified fixture IDs and define deterministic visual-task scoring.

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
- self-promote;
- automatically activate a new ranking policy;
- mutate policy or routing from online telemetry.

Promotion is an explicit reviewed conversion from immutable benchmark evidence into ranking inputs. Ranking can only reorder candidates already inside the authorized and eligible set.

## CI boundary

Default CI remains credential-free and deterministic:

- no live provider/network dependency is required by the workload contract tests;
- no LLM-as-judge path is required;
- public/synthetic fixtures are used;
- workload contract drift fails closed;
- snapshot/digest behavior is replayable;
- architecture/security/secret gates cover benchmark code.

Before the multimodal benchmark-fixture foundation branch, the validated `main` baseline after PR #28 is:

- 448 tests passed;
- 81.64% aggregate coverage;
- mypy and Ruff passed across 133 source files;
- Bandit reported no issues;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed;
- `main` commit `3428d7776cda5ab9374f1c5cae1ee4b66f27525c` passed the post-merge quality workflow.

## Next boundary

Completing the initial 5/5 matrix and adding consumer-agnostic multimodal foundations do **not** create a new Phase 14 consumer migration exception.

Issue #18 still defers OpsLens reconciliation and explicitly prevents starting RAGForge in parallel unless the normative integration order is revised. Until that changes, additional gateway work should remain consumer-agnostic and independently justified.
