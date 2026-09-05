# Roadmap

The normative detailed roadmap is preserved verbatim at `SOURCE_ROADMAP.txt`.

Current execution sequence:

0. Architecture Gate — COMPLETE BASELINE.
1. Generalize `policy-model-router` contract/vocabulary — COMPLETE (`policy-model-router` PR #20).
2. Contracts and deterministic model registry/digest — COMPLETE (`governed-llm-gateway` PR #1).
3. Provider execution foundation and first adapters — COMPLETE (`governed-llm-gateway` PR #2).
4. Policy Model Router authorization — COMPLETE (`governed-llm-gateway` PR #3).
5. Deterministic operational ranking and explainability — COMPLETE (`governed-llm-gateway` PR #4).
6. Runtime health, bounded retry, safe fallback, circuit breaker — COMPLETE (`governed-llm-gateway` PR #5).
7. Structured output and tool normalization — COMPLETE (`governed-llm-gateway` PR #6).
8. Streaming — COMPLETE (`governed-llm-gateway` PR #7).
9. OpenTelemetry via `a2a-otel-kit` — COMPLETE (`governed-llm-gateway` PR #8).
10. Evaluation framework — COMPLETE (`governed-llm-gateway` PR #9, squash merge `db30ffc481d1a3c02fb01f46524b5190290fb7ac`).
11. Evidence-driven ranking — COMPLETE (`governed-llm-gateway` PR #10, squash merge `5888376da798d55b9f4139e943514dca0e573dea`).
12. Thin client SDK — COMPLETE (`governed-llm-gateway` PR #11, squash merge `1b9b3ef01f0efac49d1f2a92056473ec4b45c375`).
13. Governance integration — COMPLETE (`governed-llm-gateway` PR #12, squash merge `ec18ad8e95490fdeb6ee4c6b9e26ae7cd5b1b0b1`).
14. Incremental real-project integrations — IN PROGRESS.

## Permanent authority sequence

The portfolio authority chain is:

`Verifiable AI Governance → Policy Model Router → Governed LLM Gateway → model provider`

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`

Governance authorization may narrow that set further but may never expand it. Ranking, health, retry/fallback, benchmark promotion, SDK transport, telemetry and runtime evidence are never independent authorization sources.

## Completed gateway foundations after Phase 13

Consumer-driven, provider-neutral hardening completed before the workload benchmark expansion:

- PR #13, squash merge `96b09956e933db50bf9ea900973f8a0b2145cb3c`: PEP 561 typed SDK packages;
- PR #15, squash merge `ba5661514f90aff96749789e3275ce5685e1aea4`: terminal `ProviderExecution` evidence through SSE and `GatewayClient.generate()`;
- PR #16, squash merge `e2f724d1339419207fbe89437fc5c590673dd33c`: provider-neutral execution provenance including provider response identity, finish reason, retry/fallback position and optional detailed usage.

Later post-core hardening extends the same provider-neutral evidence with:

- PR #37: terminal selected-deployment `api_family`;
- PR #40: terminal concrete positive `max_output_tokens` carried by the attempted request.

The runtime evidence chain is:

`normalized provider events → StreamingExecutionService → terminal SSE → API payload → SDK codec → GatewayResponse.execution`

Runtime evidence is descriptive only. It cannot authorize a retry, fallback, model/provider choice, tool execution, SQL execution or business action.

## Benchmark program — CORE 5/5 COMPLETE; POST-CORE MULTIMODAL/EVIDENCE HARDENING COMPLETE

The roadmap says to start with five workloads. The generic Phase 10/11 framework is exercised by all five through separate semantic increments:

1. `structured_extraction` — PR #19 established v1; PR #22 added hardened `structured-extraction-v2` while preserving historical v1 evidence;
2. `rag_ptbr` — PR #20, `rag-ptbr-v1`;
3. `code_generation` — PR #21, `code-generation-v1`;
4. `tool_use` — PR #23, `tool-use-v1`;
5. `agent_orchestration` — PR #24, `agent-orchestration-v1`.

The roadmap also says to add multimodal only after core execution is stable. That condition was satisfied before the post-core sequence:

- PRs #26–#28 established bounded provider-neutral image input and reviewed native translations for OpenAI Responses, Anthropic Messages and Gemini;
- PRs #29–#31 established deterministic local fixture integrity and immutable public publication;
- PR #32 added `multimodal-analysis-v1` using actual visual input and deterministic scoring;
- PRs #33–#34 added provider-neutral gateway request materialization and terminal response normalization without a benchmark-side model-forcing path;
- PRs #35–#36 preserved observed terminal provider/model/deployment identity in benchmark evidence;
- PRs #37–#39 added terminal API-family provenance and explicit benchmark target API-family attestation;
- PRs #40–#41 added terminal max-output provenance and explicit benchmark target max-output attestation;
- PR #42 added optional target-matrix version/digest provenance to immutable benchmark snapshots.

The completed benchmark path remains public/synthetic, deterministic and credential-free by default. Provider failures remain availability evidence rather than false quality-zero results. Promotion remains explicit and non-authoritative.

Target declarations are versioned rather than rewritten:

- schema `1.0` / `targets-v1.json` — historical provider/model/API/configuration identity;
- schema `1.1` / `targets-v2.json` — explicit reviewed `api_family`;
- schema `1.2` / `targets-v3.json` — explicit reviewed `api_family` + positive `max_output_tokens`.

Snapshots may remain historical schema `1.0`, or opt into schema `1.1` target-matrix version/digest provenance. Declarative provider configuration is not treated as runtime attestation unless the provider-neutral execution contract actually carries the corresponding evidence.

Completion of these gateway-internal increments does not alter the Phase 14 consumer order. See `docs/evaluation/BENCHMARK_MATRIX.md`.

## Phase 14 — Real project integrations

Normative order from `SOURCE_ROADMAP.txt`:

1. `controlled-autonomy-lab`
2. `getnet-multi-agent-support-v2`
3. `OpsLens`
4. `RAGForge`
5. `Verifiable AI Governance`

The roadmap explicitly requires incremental migration and says not to migrate all consumers simultaneously.

### Case 1 — controlled-autonomy-lab — COMPLETE

Consumer merge:

`238e4b93284579b5c9ba0d650161febcdbf83a51`

Validated bounded text-generation integration:

- opt-in gateway path;
- consumer supplies gateway URL/credential plus workload/risk/data classification;
- gateway owns provider/model/deployment selection and retry/fallback;
- direct adapters remain only for benchmark comparability and unsupported provider-native continuation;
- tool-result continuation fails closed instead of fabricating a user message when canonical continuation state is unavailable.

Final consumer CI baseline:

- 194 tests passed;
- coverage 86.19%;
- strict mypy passed;
- Ruff passed;
- Bandit 0 findings;
- registry-auditable dependencies clean;
- architecture dependency check passed.

### Case 2 — getnet-multi-agent-support-v2 — COMPLETE

Consumer merge:

`6ee7f3db8f666e35f78f7df5524a1fc15e1ef0da`

Validated generation integration:

- provider-neutral gateway request;
- no local retry/fallback;
- gateway credentials are independent of Gemini credentials;
- semantic embeddings remain a separate Gemini-specific concern;
- incomplete gateway credentials fail closed with no Gemini fallback;
- failed gateway responses remain failures even when partial content exists.

Final consumer CI baseline:

- 259 tests passed, 14 skipped, 1 deselected;
- coverage 88.59%;
- strict mypy passed;
- Ruff/architecture/governance gates passed;
- Bandit 0 findings;
- auditable dependency set clean.

### Case 3 — OpsLens — VALIDATED CANDIDATE, DEFERRED

PR `brunovicco/opslens#89` reached a green integration candidate with the bounded semantic-query planner routed through the gateway. The candidate preserved the correct authority split: model output remains a structured proposal, deterministic OpsLens parsing/domain validation remains mandatory, and SQL/Athena execution stays outside the gateway.

Validated candidate head:

`939c0e46110329c3bac046e05f5908ffb6c6e889`

Validation recorded before deferral:

- Python CI `33888638650` — PASS;
- 73 semantic-query tests passed;
- strict Pyright: 0 errors / 0 warnings;
- Ruff passed;
- Terraform CI `33888638704` — PASS;
- Checkov, Lambda package builds, Terraform validate and TFLint passed.

**Current sequencing decision:** do not modify or merge OpsLens while that repository is undergoing active independent development. Reconcile the consumer only after its development state stabilizes. This is an intentional deferral, not a gateway blocker.

### Case 4 — RAGForge — NOT STARTED

Do not start Case 4 while Case 3 is intentionally deferred unless the integration order is explicitly revised. Issue #18 records this sequencing guard.

### Case 5 — Verifiable AI Governance — NOT STARTED

Remains after the preceding consumer cases.

## Current gateway baseline

Latest merged and validated baseline:

`cb0fbac9c278df3e20bf9b26b20cb06f697f4d71` (PR #42)

Post-merge `main` quality run:

`33993826048` — PASS.

Validation:

- 546 tests passed;
- aggregate coverage 82.08%;
- strict mypy passed across 151 source files;
- Ruff lint/format passed across 151 files;
- Bandit reported no issues across 13,905 LOC;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

## Next boundary

Until OpsLens is ready for reconciliation:

1. keep the gateway `main` baseline stable;
2. do not start a second consumer migration in parallel;
3. perform only upstream gateway hardening that is independently justified and consumer-agnostic;
4. do not create benchmark-only routing/model-selection bypasses to force a nominal target;
5. keep live-provider benchmark execution explicitly separated from credential-free default CI and normal authorization semantics;
6. do not treat benchmark completion or runtime provenance as permission to bypass the Phase 14 order;
7. when OpsLens stabilizes, rebase/reconcile its integration against the then-current gateway commit and rerun its full native Python and Terraform CI before merge.

Do not pull work forward when doing so weakens an authority boundary, creates parallel consumer migrations or depends on an unstable consumer contract.
