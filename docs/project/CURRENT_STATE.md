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

The provider-neutral terminal evidence supports concrete provider/model/deployment identity, request correlation, optional provider response identity, finish reason, attempt/fallback position, latency, normalized usage and optional cost.

Later provider-neutral hardening extends the same terminal evidence with:

- PR #37 — selected deployment `api_family`;
- PR #40 — concrete positive `max_output_tokens` carried by the attempted provider-neutral request.

Unknown optional evidence remains absent rather than being synthesized. Contradictory or malformed provenance fails closed. Runtime evidence remains descriptive only and is never authorization.

## Benchmark and multimodal program — CORE 5/5 COMPLETE; POST-CORE EXTENSION COMPLETE

The five initial roadmap workloads remain complete and historically versioned:

1. `structured_extraction` — v1 established in PR #19; hardened `structured-extraction-v2` added in PR #22 without rewriting v1 evidence;
2. `rag_ptbr` — `rag-ptbr-v1`, PR #20;
3. `code_generation` — `code-generation-v1`, PR #21;
4. `tool_use` — `tool-use-v1`, PR #23;
5. `agent_orchestration` — `agent-orchestration-v1`, PR #24.

After the core execution and five-workload baseline stabilized, the roadmap-authorized multimodal extension was implemented incrementally:

- PR #26 — bounded provider-neutral HTTPS image-input contract plus native OpenAI Responses translation;
- PR #27 — native Anthropic Messages image-input translation;
- PR #28 — native Gemini `generateContent` / `streamGenerateContent` image-input translation;
- PR #29 — credential-free content-addressed multimodal fixture foundation;
- PR #30 — first deterministic checked-in visual fixture catalog;
- PR #31 — immutable commit-pinned public fixture publication;
- PR #32 — `multimodal-analysis-v1` deterministic visual benchmark and scorer;
- PR #33 — provider-neutral multimodal `GatewayRequest` execution-plan materialization;
- PR #34 — terminal `GatewayResponse` → benchmark `ProviderCall` normalization;
- PRs #35–#36 — observed provider/model/deployment execution identity carried into benchmark observations and snapshots;
- PRs #37–#39 — terminal `api_family` provenance plus explicit schema-1.1 benchmark target attestation;
- PRs #40–#41 — terminal `max_output_tokens` provenance plus explicit schema-1.2 benchmark target attestation;
- PR #42 — opt-in snapshot schema 1.1 with canonical target-matrix version/digest provenance.

The benchmark target catalog is intentionally versioned rather than rewritten:

- `targets-v1.json` / schema `1.0` — historical provider/model/API/configuration identity;
- `targets-v2.json` / schema `1.1` — explicit reviewed `api_family` attestation;
- `targets-v3.json` / schema `1.2` — explicit reviewed `api_family` plus positive `max_output_tokens` attestation.

Observed terminal evidence and declared target claims remain separate. Provider/model identity, `api_family`, and `max_output_tokens` can be checked against runtime evidence where the reviewed contract supports it. Opaque configuration claims such as temperature, top-p, reasoning/thinking mode and access tier remain declarative and are not silently promoted to runtime facts.

Shared benchmark properties remain:

- public/synthetic versioned fixtures;
- credential-free deterministic default CI;
- workload-specific fail-closed contracts;
- provider failures separated from completed model-quality failures;
- deterministic dataset digests and content-addressed snapshots;
- explicit promotion only;
- no live tool execution, generated-code execution or agent execution;
- no LLM-as-judge dependency in the default path;
- benchmark/runtime evidence can affect ranking only inside the already-authorized and eligible set.

Latest validated gateway baseline after PR #42:

`cb0fbac9c278df3e20bf9b26b20cb06f697f4d71`

Post-merge quality run:

`33993826048` — PASS.

Validation:

- 546 tests passed;
- aggregate coverage 82.08%;
- strict mypy passed across 151 source files;
- Ruff lint/format passed across 151 files;
- Bandit reported no issues across 13,905 LOC;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

The detailed benchmark ledger is documented in `docs/evaluation/BENCHMARK_MATRIX.md`.

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

1. Keep `governed-llm-gateway/main` stable at the validated post-core benchmark/provenance baseline.
2. Do not modify OpsLens until its independent development state is ready for reconciliation.
3. Do not begin RAGForge in parallel unless the roadmap order is explicitly revised.
4. Accept further upstream gateway changes only when they are consumer-agnostic, independently justified and preserve the permanent authorization invariant.
5. Do not create a model-forcing benchmark bypass: benchmark target identity must never become an authorization or routing override.
6. A future live gateway-backed benchmark executor must use an already-authorized gateway path, preserve target/effective-execution integrity checks, and remain outside credential-free default CI.
7. When OpsLens is resumed, reconcile against the then-current gateway commit and rerun the full OpsLens Python and Terraform gates before merge.

## Explicitly deferred

- OpsLens reconciliation/merge while its repository is actively evolving;
- RAGForge migration while Case 3 is deferred;
- client-side provider credentials or provider SDKs;
- client-side retry/fallback/circuit breaking/model selection;
- automatic/adaptive routing self-modification;
- arbitrary key discovery from governance token contents;
- using governance/runtime/benchmark evidence as a new authorization source;
- provider-native tool-result continuation without canonical provider state;
- benchmark-side provider/model forcing;
- credential-bearing live-provider benchmark execution in default CI;
- payload/prompt/completion capture as default telemetry/evidence.
