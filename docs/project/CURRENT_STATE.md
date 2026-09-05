# Current State

Last updated: 2026-09-05

## Phase status

| Phase | Status |
|---|---|
| Phase 0 — Architecture Gate | COMPLETE BASELINE |
| Phase 1 — Policy Model Router generalization | COMPLETE (`policy-model-router` PR #20) |
| Phase 2 — Contracts and Model Registry | COMPLETE (`governed-llm-gateway` PR #1) |
| Phase 3 — Provider Execution Foundation | COMPLETE (`governed-llm-gateway` PR #2) |
| Phase 4 — Policy Router integration | COMPLETE (`governed-llm-gateway` PR #3) |
| Phase 5 — Deterministic Operational Ranking and Explainability | COMPLETE (`governed-llm-gateway` PR #4) |
| Phase 6 — Runtime Health, Retry and Safe Fallback | COMPLETE (`governed-llm-gateway` PR #5) |
| Phase 7 — Structured Output and Tool Normalization | COMPLETE (`governed-llm-gateway` PR #6) |
| Phase 8 — Streaming | COMPLETE (`governed-llm-gateway` PR #7) |
| Phase 9 — OpenTelemetry | COMPLETE (`governed-llm-gateway` PR #8) |
| Phase 10 — Evaluation Framework | COMPLETE (`governed-llm-gateway` PR #9) |
| Phase 11 — Evidence-Driven Ranking | COMPLETE (`governed-llm-gateway` PR #10) |
| Phase 12 — Thin Client SDK | COMPLETE (`governed-llm-gateway` PR #11) |
| Phase 13 — Governance Integration | COMPLETE (`governed-llm-gateway` PR #12) |
| Phase 14 — Real Project Integrations | IN PROGRESS — CASES 1/2 COMPLETE; CASE 3 DEFERRED |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api` boundaries;
- Verifiable AI Governance is an optional upstream governance authority;
- Policy Model Router remains the deterministic PDP;
- the gateway remains the PEP plus operational selector/executor;
- permanent invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- governance authorization may narrow that set further but may never expand it;
- provider-specific SDKs/credentials remain behind gateway adapters;
- metadata-only evidence remains the default;
- business-tool execution remains outside the gateway;
- benchmark, telemetry, SDK, client state and runtime evidence are never authorization sources.

## Phase 13 — complete

Governance Integration was merged through `governed-llm-gateway` PR #12 at:

`ec18ad8e95490fdeb6ee4c6b9e26ae7cd5b1b0b1`

Final validated Phase 13 baseline:

- 317 tests passed;
- aggregate coverage 81.10%;
- `governance_execution.py` coverage 88.57%;
- mypy/Ruff passed across 110 files;
- Bandit 0 issues across 11,525 lines of code;
- pip-audit no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

The authority chain remains:

`Verifiable AI Governance → Policy Model Router → Governed LLM Gateway → model provider`

Governance authorization is audience-, time-, request- and scope-bound. Governance/PDP intersection happens before operational selection, and later ranking/retry/fallback cannot resurrect excluded model groups.

## Upstream hardening discovered by real consumers

### Typed SDK packaging

PR #13 merged at:

`96b09956e933db50bf9ea900973f8a0b2145cb3c`

This adds the PEP 561 markers required for strict downstream type checking.

### Terminal execution evidence

PR #15 merged at:

`ba5661514f90aff96749789e3275ce5685e1aea4`

This preserves terminal `ProviderExecution` through the gateway SSE/API and thin SDK.

### Provider-neutral execution provenance

PR #16 merged at:

`e2f724d1339419207fbe89437fc5c590673dd33c`

The provider-neutral terminal evidence now supports:

- concrete provider/model/deployment identity;
- gateway correlation `request_id` distinct from optional provider response identity;
- optional `provider_request_id`;
- optional `finish_reason`;
- gateway-observed positive `attempt_number`;
- zero-based `fallback_index` among deployments actually attempted;
- measured provider-attempt `latency_ms`;
- normalized input/output token counts;
- optional `total_tokens` and cache read/write token details;
- optional cost.

Unknown optional evidence remains absent rather than being synthesized as zero. Contradictory provider response IDs and invalid retry/fallback provenance fail closed.

## Workload-specific benchmark matrix — COMPLETE 5/5

The generic Phase 10/11 benchmark and promotion framework is now exercised by all five initial roadmap workloads through PRs #19–#24:

1. `structured_extraction` — v1 established in PR #19; hardened `structured-extraction-v2` added in PR #22 without rewriting historical v1 semantics;
2. `rag_ptbr` — `rag-ptbr-v1`, PR #20;
3. `code_generation` — `code-generation-v1`, PR #21;
4. `tool_use` — `tool-use-v1`, PR #23;
5. `agent_orchestration` — `agent-orchestration-v1`, PR #24.

Shared properties remain:

- public/synthetic versioned fixtures;
- credential-free deterministic default CI;
- workload-specific fail-closed contracts;
- provider failures separated from completed model-quality failures;
- deterministic dataset digests and content-addressed snapshots;
- explicit promotion only;
- no live tool execution, generated-code execution or agent execution;
- no LLM-as-judge dependency in the default path;
- benchmark/promoted evidence can affect ranking only inside the already-authorized and eligible set.

The completed workload ledger is documented in `docs/evaluation/BENCHMARK_MATRIX.md`.

Latest benchmark-complete `main` baseline after PR #24:

`a8f2003663eb9ac713df6929a8c7b5bc79573e69`

Post-merge quality run:

`33968458431` — PASS.

Validation:

- 421 tests passed;
- aggregate coverage 81.32%;
- mypy passed across 132 source files;
- Ruff lint/format passed across 132 files;
- Bandit 0 issues across 12,883 LOC;
- pip-audit no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

## Phase 14 — Real Project Integrations

Normative order:

1. `controlled-autonomy-lab`
2. `getnet-multi-agent-support-v2`
3. `OpsLens`
4. `RAGForge`
5. `Verifiable AI Governance`

The roadmap says each migration is an integration case and consumers must not be migrated simultaneously.

### Case 1 — controlled-autonomy-lab — COMPLETE

Consumer squash merge:

`238e4b93284579b5c9ba0d650161febcdbf83a51`

The gateway path is opt-in and bounded to supported text generation. The consumer does not own provider credentials, provider/model/deployment selection or local retry/fallback. Unsupported provider-native continuation remains outside the gateway path and fails closed rather than faking tool results as user text.

Final consumer validation:

- 194 tests passed;
- coverage 86.19%;
- strict mypy and Ruff passed;
- Bandit 0 findings;
- architecture dependency check passed.

### Case 2 — getnet-multi-agent-support-v2 — COMPLETE

Consumer squash merge:

`6ee7f3db8f666e35f78f7df5524a1fc15e1ef0da`

The gateway owns generation provider/model selection and resilience. Gemini remains required only for the separate semantic-embedding path. Incomplete gateway configuration fails closed and never silently falls back to Gemini generation.

Final consumer validation:

- 259 tests passed, 14 skipped, 1 deselected;
- coverage 88.59%;
- strict mypy and Ruff passed;
- architecture/governance gates passed;
- Bandit 0 findings.

### Case 3 — OpsLens — VALIDATED CANDIDATE, DEFERRED

`brunovicco/opslens` PR #89 reached a green candidate integration for the bounded semantic-query planner.

Validated head:

`939c0e46110329c3bac046e05f5908ffb6c6e889`

Recorded validation:

- Python CI `33888638650` — PASS;
- 73 semantic-query tests passed;
- strict Pyright: 0 errors / 0 warnings;
- Ruff passed;
- Terraform CI `33888638704` — PASS;
- Checkov, Lambda package builds, Terraform validate and TFLint passed.

Authority boundary in that candidate remained correct: the model produces only a bounded structured proposal; deterministic OpsLens parser/domain validation remains mandatory; SQL compilation and Athena execution remain deterministic OpsLens responsibilities.

**Current decision:** do not change or merge OpsLens while that repository is under active independent development. Reconcile this integration only after the repository stabilizes.

### Case 4 — RAGForge — NOT STARTED

Not started because Case 3 is deliberately deferred. Issue #18 explicitly preserves the sequencing guard and prohibits starting RAGForge in parallel unless the normative order is revised.

### Case 5 — Verifiable AI Governance — NOT STARTED

Remains after the preceding integration cases.

## Current working boundary

1. Keep `governed-llm-gateway/main` stable at the benchmark-complete, provider-neutral baseline.
2. Do not modify OpsLens until its independent development state is ready for reconciliation.
3. Do not begin RAGForge in parallel unless the roadmap order is explicitly revised.
4. Accept upstream gateway changes only when they are consumer-agnostic and independently justified.
5. When OpsLens is resumed, reconcile against the then-current gateway commit and rerun the full OpsLens Python and Terraform gates before merge.

## Explicitly deferred

- OpsLens reconciliation/merge while its repository is actively evolving;
- RAGForge migration while Case 3 is deferred;
- client-side provider credentials or provider SDKs;
- client-side retry/fallback/circuit breaking/model selection;
- automatic/adaptive routing self-modification;
- arbitrary key discovery from governance token contents;
- using governance/runtime/benchmark evidence as a new authorization source;
- provider-native tool-result continuation without canonical provider state;
- payload/prompt/completion capture as default telemetry/evidence.
