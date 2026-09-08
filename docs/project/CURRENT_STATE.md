# Current State

Last updated: 2026-09-08

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
- immediate process-local runtime health and versioned recent operational evidence remain distinct from ranking policy and from each other;
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

## Benchmark and multimodal program — ALL ROADMAP-LISTED BENCHMARK CLASSES REPRESENTED

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

Additional roadmap-listed post-core evaluation classes were then added without changing the historical five-workload baseline:

- PR #44 — `long-context-v1`, a tokenizer-neutral deterministic needle-retrieval benchmark over exactly 8,192 generated records, covering early/middle/late positions without fabricating provider token counts or context-window evidence;
- PR #45 — `classification-v1`, a deterministic closed-set public/synthetic classification benchmark over immutable `support-intents-v1`, with exact JSON scoring and no model-as-judge path;
- PR #47 — `reasoning-v1`, an answer-only deterministic reasoning benchmark over arithmetic, boolean logic, constraints and sequences without requesting or preserving chain-of-thought;
- PR #48 — `code-review-v1`, a non-executing structured-findings benchmark with six reviewed non-security rules, two clean cases and deterministic set-F1 scoring.
- PR #50 — `security-analysis-v1`, a defensive structured-findings benchmark over synthetic Python with six reviewed security rules, two clean cases, deterministic set-F1 scoring, and no candidate execution or exploitation path.
- PR #51 — `tool-selection-v1`, an exact reviewed tool-or-no-tool benchmark over immutable `support-tools-v1`, with no argument generation or tool execution.
- PR #52 — `tool-argument-generation-v1`, a fixed-reviewed-tool benchmark with recursive exact, type-sensitive argument scoring and no tool selection or execution.
- PR #55 — `multi-step-tool-use-v1`, a deterministic non-executing benchmark for reviewed two-to-three-step tool-call proposals using immutable synthetic intermediate-result context and separate positional selection/argument evidence.
- PR #58 — `rag-answer-v1`, a deterministic grounded-answer benchmark over checked-in public/synthetic source records with required-fact coverage, citation set-F1, fail-closed unknown citations and reference-source grounding validation, without retrieval or an LLM-as-judge.
- PR #61 — `json-schema-compliance-v1`, a binary normalized-JSON schema-compliance benchmark that reuses the bounded Phase 7 Draft 2020-12 schema acceptance boundary while keeping extraction-value correctness out of scope.
- PR #64 — immutable benchmark quality-component evidence for schema validity, tool selection, tool arguments, trajectory success and grounding, with snapshot schema 1.2 and no implicit promotion/ranking change.
- PR #67 — `rag-ptbr-v2`, preserving historical v1 while adding separate grounding and bounded reviewer-authored Brazilian Portuguese locale/terminology quality evidence as `pt_br_quality`, with no provider/model forcing or promotion/ranking change.
- PR #70 — strict schema `1.0` recent operational evidence with collector/time-window provenance, content-derived identity and explicit request/error/fallback/latency measurements; no collector, ranking-score normalization or routing-policy change.
- PR #73 — deterministic materialization from bounded timestamped metadata-only provider-attempt samples, including fail-closed process-local coverage/eviction semantics and canonical schema `1.0` snapshot creation; no executor recorder wiring, ranking or authorization change.
- PR #76 — optional process-local best-effort provider-attempt recording in non-streaming and streaming executors, with separate monotonic/UTC clocks and conservative completeness invalidation for cancellation, unrepresentable post-call failures or recorder failure; no ranking or authorization change.
- PR #79 — immutable content-addressed operational sample batch handoff with explicit `source_instance_id`, strict JSON/tamper validation, out-of-band export and batch-backed source coverage; no fleet-completeness, ranking or authorization change.

All roadmap-listed benchmark classes now have reviewed versioned contracts. The Roadmap measurement audit preserves every currently reviewed deterministic quality component separately from operational health, including bounded `pt_br_quality` from `rag-ptbr-v2`. Historical `rag-ptbr-v1` remains unchanged, and broader fluency/grammar/style/cultural-quality claims remain explicitly out of scope.

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

Latest validated gateway baseline after PR #79:

`51a9196f066a7ae4035322ccda7aefb147003b0c`

Post-merge quality run:

`34064435787` — PASS.

Validation:

- 782 tests passed;
- aggregate coverage 82.52%;
- strict mypy passed across 186 source files;
- Ruff lint/format passed across 186 files;
- Bandit reported no issues across 17,632 LOC;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

The detailed benchmark ledger is documented in `docs/evaluation/BENCHMARK_MATRIX.md`.

## Recent operational evidence — CONTRACT + MATERIALIZER + LOCAL RECORDER + BATCH HANDOFF COMPLETE, FLEET COMPLETENESS PENDING

PR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples, a canonical snapshot factory and a bounded process-local source with fail-closed coverage/eviction semantics. PR #76 adds optional process-local best-effort recording to both bounded executors. PR #79 adds a content-addressed batch handoff that preserves explicit source-instance/exporter/window provenance and can be loaded as an `OperationalSampleSource` outside provider execution.

This does not reinterpret `InMemoryHealthTracker` / `DeploymentHealthSnapshot` as historical evidence. Those objects remain immediate process-local resilience/eligibility state. The recorder/source is intentionally local to one process and does not claim distributed completeness. Cancellation, generator close, unrepresentable post-call failures and recorder failures conservatively invalidate completeness rather than fabricate provider errors or fail inference.

Shared ingestion, fleet/source-membership completeness, production backend adapters, online-score normalization and ranking-policy changes remain pending. Operational evidence cannot authorize or restore an otherwise ineligible candidate, and any future use in scoring requires a separate explicit versioned policy.

See `docs/evaluation/OPERATIONAL_EVIDENCE.md`.

## Operational readiness checkpoint — PC-39 certified

The consumer-independent operational-readiness track advanced without changing Phase 14 sequencing or the permanent authorization boundary. The currently certified sequence includes:

- PC-26 — real Collector → Tempo trace-by-ID + TraceQL queryability proof;
- PC-27 — first file-provisioned read-only Grafana Tempo dashboard;
- PC-28 — local-only Console navigation to that dashboard;
- PC-29 — operations-only local Gateway bootstrap with no provider/PDP materialization;
- PC-30 — deterministic one-command orchestration for the bounded operations-only local stack;
- PC-33 — explicit governed live-development repository profile with loopback-only PDP HTTP exception;
- PC-34 — `/v1/ops/*` responses are explicitly non-storable with `Cache-Control: no-store`;
- PC-35 — the thin Gateway client accepts plaintext HTTP only on literal loopback addresses;
- PC-36 — opt-in provider-neutral live-development smoke harness with metadata-only output;
- PC-37 — explicit secret-free Operations visibility grant for `gateway-demo/development` in the live-development profile;
- PC-38 — bounded provider-neutral governed inference in the Console through only relative `POST /v1/generate`, with fail-closed normalized SSE validation and in-memory state;
- PC-39 — repeated Console routing evidence must remain immutable across the normalized stream.

Latest certified repository baseline:

`99bbbf1f98605695935a89befc873b8c6a4296d4` (PR #191 / PC-39).

Post-merge `main` evidence for PC-39:

- `quality` run `34291142714` — PASS;
- `console-quality` run `34291142715` — PASS;
- `local-demo-smoke` run `34291142723` — PASS.

OR-8 remains complete only at the bounded operations-only local-demo scope. OR-9 is now **IN PROGRESS** through bounded security increments PC-34, PC-35, PC-37, PC-38 and PC-39; none of those increments completes production IAM/TLS/SSO, production browser identity/session handling, rate limiting, CSRF policy or future mutation authority. OR-10 remains pending.

Credential-free CI proves repository/configuration/protocol behavior only. It does not prove a credential-backed provider/PDP request. A real provider/PDP execution must still be run explicitly with local/server-side credentials before the live inference path is described as portfolio/demo-ready.

## Governed live-inference development profile — PC-33 certified repository profile

PR #179 introduced the first explicit opt-in development profile that composes the real governed serving path without changing the checked-in fail-closed defaults. The profile lives under `config/profiles/live-development/` and is bounded to one `development` / `public` / `rag.answer` client, an external Policy Model Router decision, the authorized logical group `balanced`, deterministic ranking, and native Gemini/OpenAI provider execution.

The profile does not contain raw credentials. Gateway-client, PDP and provider credentials remain separate server-side references, and default CI remains credential-free. Provider credentials alone still cannot activate inference because registry, provider runtime, trusted client identity and PDP configuration must materialize coherently.

PC-33 also adds a narrow local-development transport exception: plaintext Policy Router HTTP is accepted only for a literal loopback IP address and is revalidated immediately before the connection is opened. `localhost`, private-LAN and remote HTTP endpoints remain rejected; non-loopback PDP deployments continue to require HTTPS. This exception supplies connectivity only and cannot widen PDP authorization.

The two checked-in ranking entries intentionally use equal neutral static component inputs. They exercise the existing deterministic tie-break and are not represented as observed quality, reliability, availability, latency or benchmark evidence.

Squash merge / certified repository profile baseline:

`36890ab99f6524c9fe8fe04033cb669816569555` (PR #179).

Post-merge `main` evidence:

`34281851561` — PASS.

This is a credential-free repository/configuration proof, not a live-provider certification.

## OR-9 bounded hardening — PC-34 through PC-39

PC-34 / PR #181 was the first bounded OR-9 hardening increment after the minimum authenticated Operations access prerequisite. Every HTTP response under the owned `/v1/ops/` namespace is explicitly non-storable with `Cache-Control: no-store`, including success, sanitized failures and unknown Operations paths. The middleware does not buffer or alter inference/SSE responses.

PC-34 squash merge:

`ea6180c33374824bc99ab07d38402d3f0482fd0c`

Post-merge quality run `34282957304` — PASS.

PC-35 / PR #184 reconciled the canonical thin client with the live-development profile by allowing plaintext HTTP only on literal loopback IP addresses. `localhost`, private-LAN, link-local, DNS/public HTTP and non-loopback plaintext remain rejected. HTTPS behavior is unchanged.

PC-35 squash merge:

`aac737d8aa1a58c1364b4a89cfc60a1212fe5b09`

PC-36 / PR #185 added an explicit `--live` opt-in smoke harness over the canonical thin client. The consumer sees only `GOVERNED_LLM_GATEWAY_URL` and `GOVERNED_LLM_GATEWAY_API_KEY`; provider and Policy Router credentials remain server-side. The harness never forces provider/model/deployment and emits metadata-only execution provenance rather than prompt/completion content.

PC-36 squash merge:

`74f826f490fb51cf23a9bdbe4533783dc1baa952`

Post-merge quality run `34284584354` — PASS.

PC-37 / PR #187 added the explicit secret-free Operations visibility artifact for exactly `gateway-demo/development` to the live-development profile. Authentication is shared, but inference authorization and Operations visibility remain distinct policy decisions.

PC-37 squash merge:

`545153a25ac32589e34ca0d51827bb5caaacdbcd`

PC-38 / PR #189 added bounded governed inference to the Gateway Console. The browser can submit only the reviewed provider-neutral `rag.answer` request to relative `POST /v1/generate`; it has no provider/model/deployment/fallback selector. Credential, prompt, completion and evidence remain in memory only. The SSE consumer enforces request binding, contiguous sequence, reviewed event types, byte ceilings, normalized usage, terminal execution evidence and routing/execution consistency fail closed.

PC-38 squash merge:

`9c161841d9416f8631ebf71daaf133bb9361b044`

Post-merge `quality`, `console-quality` and `local-demo-smoke` all passed.

PC-39 / PR #191 hardened the Console consumer so repeated routing evidence must remain semantically identical across all decoded provenance fields, including evidence-bearing array ordering.

PC-39 squash merge / latest certified baseline:

`99bbbf1f98605695935a89befc873b8c6a4296d4`

These increments do not complete OR-9. Production browser identity/session handling, OAuth/OIDC/workload identity, TLS termination, rate limiting, CSRF policy and any future mutation authority remain separate reviewable concerns. None of the hardening increments may authorize or widen model execution.

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

Not started because Case 3 is deliberately deferred. The sequencing guard is versioned directly in `SOURCE_ROADMAP.txt`, `ROADMAP.md` and this checkpoint: do not start RAGForge in parallel unless the normative order is explicitly revised.

### Case 5 — Verifiable AI Governance — NOT STARTED

Remains after the preceding integration cases.

## Current working boundary

1. `main@99bbbf1f98605695935a89befc873b8c6a4296d4` is the latest certified repository baseline. Live-provider execution remains a separate opt-in proof and must not be inferred from credential-free CI.
2. OR-9 is in progress through bounded hardening PC-34..PC-39; it is not complete. Continue only with separately justified, consumer-independent security increments that preserve existing serving semantics.
3. Do not modify OpsLens until its independent development state is ready for reconciliation.
4. Do not begin RAGForge in parallel unless the normative roadmap order is explicitly revised.
5. Accept further upstream gateway changes only when they are consumer-agnostic, independently justified and preserve the permanent authorization invariant.
6. Do not create a model-forcing benchmark bypass: benchmark target identity must never become an authorization or routing override.
7. Treat `rag-ptbr-v2` `pt_br_quality` strictly as bounded reviewer-authored Brazilian Portuguese locale/terminology evidence; do not generalize it into arbitrary fluency, grammar, style or cultural-quality claims.
8. Keep benchmark quality components and recent operational evidence outside new ranking semantics until separate explicit versioned contracts review such use.
9. A future operational-evidence increment may add shared ingestion and an explicit fleet/source-membership completeness model over validated source-instance batches; it must not make remote evidence delivery part of inference availability or invent online score normalization/adaptive policy.
10. A future live gateway-backed benchmark executor must use an already-authorized gateway path, preserve target/effective-execution integrity checks, and remain outside credential-free default CI.
11. When OpsLens is resumed, reconcile against the then-current gateway commit and rerun the full OpsLens Python and Terraform gates before merge.

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
