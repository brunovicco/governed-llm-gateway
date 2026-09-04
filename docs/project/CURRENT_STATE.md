# Current State

Last updated: 2026-09-04

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
| Phase 14 — Incremental Real-Project Integrations | CURRENT — CASE 1 COMPLETE, CASE 2 IN PROGRESS |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api`
  boundaries;
- Verifiable AI Governance is an optional upstream governance authority;
- Policy Model Router remains the deterministic PDP;
- the gateway remains the PEP plus operational selector/executor;
- permanent invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- governance authorization may narrow that set further but may never expand it;
- provider-specific SDKs/credentials remain behind gateway adapters;
- metadata-only evidence remains the default;
- business-tool execution remains outside the gateway;
- benchmark, telemetry, SDK, client state and evidence are never authorization sources.

## Phase 13 — completed

PR #12 was squash-merged into `main` as:

`ec18ad8e95490fdeb6ee4c6b9e26ae7cd5b1b0b1`

Phase 13 established the optional signed Verifiable AI Governance boundary without turning the gateway
into a second PDP. Governance authorization can only narrow Policy Router authorization. The gateway
continues to own operational eligibility, ranking and provider execution inside the authorized set.

The public SDK packaging was subsequently hardened for strict external consumers in PR #13. The
`gateway-client` and `gateway-contracts` distributions now include PEP 561 `py.typed` markers. PR #13
was squash-merged as:

`96b09956e933db50bf9ea900973f8a0b2145cb3c`

## Phase 14 — incremental real-project integrations

Recommended integration order remains:

1. `controlled-autonomy-lab`
2. `getnet-multi-agent-support-v2`
3. `OpsLens`
4. `RAGForge`
5. `Verifiable AI Governance`

Each consumer migration is treated as its own integration case. Dependency direction remains strictly
consumer → gateway; the gateway does not import business-project code.

### Case 1 — controlled-autonomy-lab — COMPLETE

Consumer PR #24 was squash-merged as:

`238e4b93284579b5c9ba0d650161febcdbf83a51`

The migration adds an opt-in gateway path for bounded text generation while keeping unsupported
provider-neutral agent continuation fail-closed. Provider credentials, concrete model selection, retry
and fallback are not owned by the gateway consumer path.

Final consumer validation before merge:

- GitHub Actions run `33883274493` — PASS;
- 194 tests passed;
- aggregate coverage 86.19%;
- strict mypy PASS across 85 source files;
- Ruff lint/format PASS across 88 files;
- Bandit 0 issues across 6,281 lines of code;
- pip-audit reported no known vulnerabilities in auditable registry dependencies.

### Case 2 — getnet-multi-agent-support-v2 — IN PROGRESS

Consumer PR #3:

`https://github.com/brunovicco/getnet-multi-agent-support-v2/pull/3`

Current migration boundary:

- opt-in `LLM_PROVIDER=gateway` implementation of the consumer-owned one-shot `LLMPort`;
- gateway SDK/contracts pinned to exact merged commit
  `96b09956e933db50bf9ea900973f8a0b2145cb3c`;
- no provider model/key selection, retry or fallback in the gateway generation path;
- customer scope, market isolation, agent routing, evidence gates, web search and business-tool
  authority remain in the Getnet application;
- Gemini direct generation remains an explicit comparison path;
- Gemini semantic embeddings remain a separate capability and still require `GOOGLE_API_KEY` because
  the gateway does not expose an embeddings service;
- incomplete gateway credentials fail closed rather than falling back silently to Gemini.

The deterministic dependency-lock/format normalization completed successfully. Full PR-head quality
validation is the current gate before review.

## Explicitly deferred

- client-side provider credentials or provider SDKs in gateway consumer paths;
- client-side retry/fallback/circuit breaking/model selection in gateway consumer paths;
- automatic/adaptive routing self-modification;
- arbitrary key discovery from governance token contents;
- using governance evidence/telemetry as a new authorization source;
- provider-native tool-result continuation without canonical provider state;
- treating the generation gateway as an embeddings service;
- payload/prompt/completion capture as default telemetry/evidence;
- migrating multiple Phase 14 consumers in one integration case.
