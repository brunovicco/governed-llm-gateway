# Checkpoint Log

This is the detailed, dated, append-only history behind `docs/project/CURRENT_STATE.md`. Each section
below is a proof record: what was done, what evidence was captured, and what commit/CI run it landed at.
`CURRENT_STATE.md` states only what is true today; this file explains how each of those facts was
established. Entries are in chronological order and are never rewritten after the fact — a superseded
fact gets a new entry, not an edit to the old one.

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

## Operational readiness checkpoint — PC-51 certified

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
- PC-39 — repeated Console routing evidence must remain immutable across the normalized stream;
- PC-41 — `POST /v1/generate` SSE responses are explicitly non-storable;
- PC-42 — implicit OpenAPI/Swagger/ReDoc documentation surfaces are disabled by default;
- PC-43 — governed generation request bodies are bounded before parsing;
- PC-44 — `POST /v1/route/explain` responses are explicitly non-storable;
- PC-45 — route-explanation request bodies are bounded before parsing;
- PC-46 — the Uvicorn `Server` response header fingerprint is suppressed;
- PC-47 — non-storability is extended to every generation response, not only the streaming path;
- PC-48 — inbound requests require an explicit JSON media type before body parsing;
- PC-49 — implicit Uvicorn forwarded-header/proxy trust is disabled pending a reviewed reverse-proxy boundary;
- PC-50 — ambiguous duplicate `X-Gateway-API-Key` headers are rejected before credential resolution;
- PC-51 — the local Gateway Console sends bounded anti-framing/browser-hardening response headers.

Latest certified repository baseline:

`34d0e3fc5153022d2402808397ce93b3c19f2c7e` (PR #219 / PC-51).

Post-merge `main` evidence for PC-51:

- `quality` run `34303543270` — PASS;
- `console-quality` run `34303543250` — PASS;
- `local-demo-smoke` run `34303543251` — PASS.

OR-8 remains complete only at the bounded operations-only local-demo scope. OR-9 is now **IN PROGRESS** through bounded security increments PC-34 through PC-51; none of those increments completes production IAM/TLS/SSO, production browser identity/session handling, rate limiting, CSRF policy or future mutation authority. OR-10 remains pending.

Credential-free CI proves repository/configuration/protocol behavior only. It does not by itself prove a credential-backed provider/PDP request.

## First live-provider inference proof — PC-33 profile, executed 2026-09-08

An operator ran the PC-33 governed live-development profile end to end with real local processes and real provider credentials, from repository baseline `34d0e3fc5153022d2402808397ce93b3c19f2c7e`:

1. `policy-model-router` (sibling repository, commit `889b41b3276c453c31fff125cff0397c6c0a4de6`) served `POST /route` on loopback port 8001 with the reviewed `examples/policies/gateway-generic.yaml` policy;
2. the Gateway served `POST /v1/generate` on loopback port 8000 with the `config/profiles/live-development/` artifacts;
3. `scripts/live_development_smoke.py --live` executed one `rag.answer` / `low` / `public` request through the thin client using only `GOVERNED_LLM_GATEWAY_URL` and `GOVERNED_LLM_GATEWAY_API_KEY`.

The Policy Router accepted the request (`model_group: balanced`, `policy_id: gateway-generic-routing`, `policy_version: 1.0.0`) and the Gateway executed it against the native Gemini deployment. The harness printed exactly one metadata-only JSON object and no prompt/completion content:

```json
{"api_family":"gemini-generate-content","attempt_number":1,"authorized_model_group":"balanced","deployment":"google-gemini-3-8-flash-dev","fallback_index":0,"input_tokens":13,"latency_ms":1920,"model":"gemini-3.8-flash","output_tokens":6,"provider":"google","request_id":"66a3244a-463b-4088-9af5-894d6020c5ff","status":"succeeded"}
```

This satisfies README item 1 of "What remains before calling the application finished": an explicit opt-in real-provider proof has now been executed and recorded, independent of the required credential-free CI. It does not certify the OpenAI deployment in the same profile, and it is not a production TLS/IAM/SLA claim; both processes were stopped after the proof and no long-running live deployment was left active.

## Live-development profile extended to six providers — proofs executed 2026-09-09

The PC-33 profile was extended from two to six deployments in the same authorized `balanced` group: `google-gemini-3-8-flash-dev`, `openai-gpt-5-6-luna-dev`, `anthropic-claude-sonnet-5-dev` (native Anthropic Messages), `nvidia-nemotron-3-super-dev`, `groq-gpt-oss-120b-dev`, and `openrouter-llama-3-3-70b-dev` (all three via the existing `openai-compatible` adapter family). `scripts/live_development_smoke.py` was extended to recognize all six as reviewed identities.

Booting the full six-deployment profile at once requires all six provider credentials to resolve, because adapter construction happens eagerly for every enabled deployment at startup. To prove one provider at a time without requiring every credential simultaneously, each proof below used a reduced local `model_registry.yaml` (only the target deployment `enabled: true`, the other five `enabled: false`) and a matching `provider_runtime.json` containing only that provider's binding; `provider_runtime.json` validation requires an exact match against currently-enabled registry deployments, and disabled deployments naturally surfaced as `deployment_disabled` rejected candidates rather than being silently dropped.

Individually proven with real operator credentials against repository baseline `97cd0ce` (post PR #222):

- `google-gemini-3-8-flash-dev` — succeeded, `latency_ms: 1598`;
- `openai-gpt-5-6-luna-dev` — succeeded, `latency_ms: 3308`;
- `groq-gpt-oss-120b-dev` — succeeded, `latency_ms: 580` (model corrected during this proof from the originally wired `llama-3.3-70b-versatile`, no longer served by Groq's catalog, to `openai/gpt-oss-120b`, confirmed against the account's live `/v1/models` listing);
- `anthropic-claude-sonnet-5-dev` — initially reached the provider and failed closed with a sanitized `invalid_request` gateway error; direct diagnosis against the real Anthropic API confirmed the model/endpoint/version were correct and the cause was an account-level issue, not a configuration defect. Later individually re-proven successfully the same day, see below;
- `nvidia-nemotron-3-super-dev` (proven later the same day, see below) and `openrouter-llama-3-3-70b-dev` — wired identically but not yet proven at the time of this record; `NVIDIA_API_KEY` and `OPENROUTER_API_KEY` were not available in the operator's environment for this session.

NVIDIA/Groq/OpenRouter pricing in the registry is an approximate placeholder pending a separately reviewed catalog update; it does not affect authorization and only participates in cost-eligibility filtering within the already-authorized `balanced` group.

The originally wired NVIDIA model (`meta/llama-3.3-70b-instruct`) had reached end-of-life on NVIDIA's hosted catalog (`410 Gone`) and was corrected to `nvidia/nemotron-3-super-120b-a12b`, confirmed against the account's live `/v1/models` listing, in both this profile and `personal-default` below; the deployment id was renamed from `nvidia-llama-3-3-70b-dev` to `nvidia-nemotron-3-super-dev` to match.

`openrouter-llama-3-3-70b-dev` was individually proven later the same day, once `OPENROUTER_API_KEY` became available: succeeded through the full Policy Router + Gateway chain, `provider: openrouter`, `model: meta-llama/llama-3.3-70b-instruct`, `latency_ms: 11762`. (`openai-gpt-5-6-luna-dev` was also re-confirmed the same day: `latency_ms: 1718`, same deployment identity as the original proof above — a spot-check, not new information.)

The account-level issue above was resolved the same day. `anthropic-claude-sonnet-5-dev` was individually re-proven using the same isolation procedure: succeeded through the full Policy Router + Gateway chain, `provider: anthropic`, `model: claude-sonnet-5`, `finish_reason: end_turn`, `latency_ms: 2037`. **All six deployments in the PC-33 profile are now individually proven live**, closing README item 1 of "What remains before calling the application finished" completely.

## Personal default profile — NVIDIA cost-preferred routing, executed 2026-09-09

`config/profiles/personal-default/` is a new, distinct profile from `live-development`: it is the operator's actual day-to-day governed deployment rather than a reviewed demo. It wires the same six providers into the `balanced` group, but `nvidia-nemotron-3-super-dev` is given a real ranking preference — `cost: "1.00"` against `"0.50"` for the other five deployments, with registry `pricing` both `"0.00"` reflecting a genuine free tier — so it wins the deterministic ranking (total score `0.60` vs `0.50`) under normal conditions while automatic bounded fallback to the other five stays available if NVIDIA is disabled, missing its credential, unhealthy, or hits a retryable failure. All six deployments still sit in the single `balanced` group serving one workload, `rag.answer`; extending into the Policy Router's other model groups (`fast-small`, `reasoning-strong`, `agentic-strong`, `structured-fast`) is explicitly out of scope for this increment.

The NVIDIA model originally wired in this profile (`meta/llama-3.3-70b-instruct`) returned `410 Gone` — it had reached end of life on NVIDIA's hosted catalog on 2026-08-26. Corrected to `nvidia/nemotron-3-super-120b-a12b`, confirmed against the account's live `/v1/models` listing before wiring it.

Individually proven with real operator credentials:

- `nvidia-nemotron-3-super-dev` alone — succeeded through the full Policy Router + Gateway chain, `latency_ms: 3571`.
- `nvidia-nemotron-3-super-dev` competing against `google-gemini-3-8-flash-dev`, `openai-gpt-5-6-luna-dev`, `anthropic-claude-sonnet-5-dev`, and `groq-gpt-oss-120b-dev` simultaneously enabled (only `openrouter-llama-3-3-70b-dev` disabled, for lack of `OPENROUTER_API_KEY`) — NVIDIA won the deterministic ranking and was selected, confirming the `cost: "1.00"` preference actually decides routing rather than only working in isolation. `latency_ms: 1206`; `rejected_candidates` correctly showed only the disabled OpenRouter deployment, not the four healthy competing candidates.

A full six-deployment boot proving this against all five alternatives simultaneously, including OpenRouter, is recorded below once `OPENROUTER_API_KEY` became available.

## Personal-default profile extended to four additional model groups, executed 2026-09-09

`personal-default` was extended from one workload (`rag.answer`/`balanced`) to nine workloads across five model groups, reusing the same six existing provider bindings (no new credentials required): `classification.simple`/`fast-small` (Groq, NVIDIA), `extraction.structured`/`structured-fast` (OpenAI, Gemini), `reasoning.complex`, `security.analysis`, `code.generate`, `code.review`/`reasoning-strong` (Anthropic, OpenAI), and `agent.orchestration`, `agent.tool-use`/`agentic-strong` (OpenAI, Anthropic). `client_auth.json`'s `allowed_workloads` was extended to all nine.

`structured-fast`, `reasoning-strong` and `agentic-strong` only use OpenAI/Anthropic/Gemini deployments, because those are the three adapters with verified real native structured-output and tool-calling translation (`native_structured_output=True, native_tool_calling=True` in `openai_responses.py`, `anthropic.py`, `gemini.py`); Groq/NVIDIA/OpenRouter's `openai-compatible` bindings keep `supports_native_structured_output`/`supports_native_tool_calling` at `false` since that has not been verified for those specific APIs, so they remain scoped to `balanced`/`fast-small`.

Individually proven with real operator credentials, through the full Policy Router + Gateway chain (OpenRouter disabled for lack of `OPENROUTER_API_KEY`, matching the existing constraint):

- `classification.simple` — succeeded via Groq (`fast-small`), `latency_ms: 606`. A first attempt with a very small `max_output_tokens` failed because `openai/gpt-oss-120b` spends hidden reasoning tokens before visible content — a real model-behavior characteristic, not a wiring defect.
- `extraction.structured` — succeeded via Gemini (`structured-fast`), `latency_ms: 1712`.
- `reasoning.complex` and `agent.orchestration` — both initially routed to Anthropic (alphabetically first at equal neutral scores) and failed closed on the same pre-existing account-level issue recorded above (since resolved), with no fallback (a permanent, non-retryable failure never triggers cross-provider fallback by design). With Anthropic's two new deployments temporarily disabled to prove the group's other member, both succeeded via OpenAI: `reasoning.complex` `latency_ms: 3577`, `agent.orchestration` `latency_ms: 1748`.
- `security.analysis`, `code.generate`, `code.review` (sharing the same `reasoning-strong` deployments as `reasoning.complex`) were wired identically but not individually exercised with a live request at the time of this record — closed later the same day, see "personal-default profile — full Anthropic and reasoning-strong workload proof coverage" below. `agent.tool-use` was separately proven with a real tool call — see below.

This does not change the checked-in fail-closed default `config/` artifacts, and does not add or require any new provider credential beyond the six already in use.

The full six-deployment `personal-default` profile requires all six provider credentials to resolve at once (adapter construction is eager at startup); a full-profile boot proving the NVIDIA-wins-ranking behavior end to end is recorded below once `OPENROUTER_API_KEY` became available.

## Real structured-output and tool-calling proof, executed 2026-09-09

Both native capabilities registered on the `structured-fast`/`reasoning-strong`/`agentic-strong` deployments were exercised with genuinely real requests through the full Policy Router + Gateway chain (Anthropic's two `agentic-strong`/`reasoning-strong` deployments temporarily disabled locally to reach OpenAI past the recorded account-level issue; no committed config changed):

- **Structured output** — `extraction.structured` with a real JSON Schema (`{"type": "object", "properties": {"apples": {"type": "integer"}}, "required": ["apples"]}`) succeeded via `google-gemini-3-8-flash-structured-dev`, returning valid schema-conformant JSON (`{"apples": 5}`).
- **Tool calling** — `agent.tool-use` with a real `ToolDefinition` (`get_weather(city: string)`) succeeded via `openai-gpt-5-6-luna-agentic-dev`: the model correctly decided to call the tool, the gateway normalized `tool_call.started` → `tool_call.arguments.delta` → `tool_call.completed` with real provider correlation (`call_id`), and the terminal response carried the canonical `ToolCall` (`get_weather({"city": "Paris"})`).

Two real constraints surfaced while proving this, not gateway defects:

- `gemini-3.8-flash` spends a large, variable share of `max_output_tokens` on internal "thinking" before any visible/structured text, the same class of issue as `gpt-oss-120b` above. `max_output_tokens: 200` reliably left no budget for the actual JSON (`finishReason: MAX_TOKENS` after only a few visible tokens); `max_output_tokens: 2000` was reliable. Confirmed directly against the real Gemini API (both `generateContent` and `streamGenerateContent`), independent of the gateway.
- OpenAI's strict tool/structured-output mode requires `additionalProperties: false` on every object node and every property listed in `required`. The gateway's `openai_responses.py`/`openai_responses_streaming.py` already enforce this locally (`_require_openai_strict_schema`) and fail closed in ~2ms with a clear `invalid_request` message before any network call when a caller's schema is missing it — this is the gateway working as designed, not a bug; a first attempt without `additionalProperties: false` correctly failed this way.

## Full six-provider boot proven, executed 2026-09-09

Once `OPENROUTER_API_KEY` became available, the full `personal-default` profile — all six deployments in `balanced` enabled simultaneously, nothing disabled — was booted for the first time end to end using `scripts/personal_default_launcher.py` (proving the launcher itself against the complete profile, not just a reduced one): the Policy Model Router and Gateway both started, resolved all six provider credentials, and reached `/readyz` together.

A real `rag.answer` request through the launched services selected `nvidia-nemotron-3-super-dev` with `rejected_candidates: null` in the terminal routing provenance — all six candidates were eligible and ranked, none rejected, and NVIDIA won purely on its cost-preference score against the complete field rather than a partial one. `Ctrl+C` (SIGINT) cleanly stopped and tore down both owned processes afterward, confirmed with no orphaned processes left on ports 8000/8001.

This closes the last deferred item from the two increments above: the full-field ranking preference and the launcher are now both proven against all six providers together, not a reduced set.

## OR-10 reproducible end-to-end validation, executed 2026-09-09

The first OR-10 increment: literally following the checked-in README rather than relying on internalized shortcuts, to catch drift between documentation and reality.

- `uv run --frozen python scripts/local_demo.py --smoke-test` — first attempt failed closed with a clear message (`Cannot connect to the Docker daemon`) because Docker Desktop was not running; not a repository defect, but confirms the operations-only demo genuinely depends on a running Docker daemon beyond the "Docker with Docker Compose" prerequisite line. Once Docker was started, the same command succeeded end to end: Gateway, Console, OTel Collector, Tempo and Grafana all reached readiness, then all owned processes and the dedicated Compose project (containers, volumes, networks) were torn down cleanly.
- The exact `uv add "governed-llm-gateway-client @ git+https://github.com/brunovicco/governed-llm-gateway.git#subdirectory=packages/gateway-client"` install command from the README's own consumer quick start was run for the first time from a genuinely separate `uv init` project (not a workspace member), against the real GitHub remote, with `personal_default_launcher.py` running in parallel — it resolved and built both `governed-llm-gateway-client` and its `governed-llm-gateway-contracts` dependency correctly.
- Running the README's own literal Python example (`GatewayClient.from_env().generate(workload="rag.answer", ...)`) from that separate project surfaced a real, reproducible finding: at the example's original `max_output_tokens=128`, NVIDIA's `nemotron-3-super-120b-a12b` returned empty `response.content` in roughly 2 of 5 repeated real calls, and roughly half at `max_output_tokens=512`; `2000` succeeded in 4 consecutive calls. This is the same internal-"thinking"-token-budget class of issue already found with Gemini and Groq's `gpt-oss-120b`, now confirmed on NVIDIA too, and on the exact code path a real consumer would copy. The README's example and `config/profiles/personal-default/README.md`'s known-limitations note were both corrected to `max_output_tokens=2000` with an explicit warning, rather than leaving a copy-pasteable example that intermittently fails for a real user.

A second OR-10 increment followed the same day: a focused security review (using the repository's own `security-review` process) of every line of new code from this session's `personal-default` line — `scripts/personal_default_launcher.py` (the only substantial new script) and the one-line reviewed-deployment allowlist addition to `scripts/live_development_smoke.py`. No shell execution, no `eval`/`exec`, no unsafe deserialization; subprocess calls use fixed argument lists (no shell interpolation); HTTP probes are restricted to fixed `127.0.0.1:8000`/`8001` URLs with no externally-controlled host, path, query, or fragment; credentials are never logged or printed; no secret was found committed in any config file this session added. **No findings.** This is expected rather than notable on its own — the launcher reuses `scripts/local_demo.py`'s already-reviewed `DemoRuntime`/subprocess/cleanup pattern verbatim and introduces no new attack surface — but it is now an explicit, dated part of the record rather than an assumption.

A third OR-10 increment consolidated the non-claims that were previously scattered across `live-development`'s and `personal-default`'s own READMEs into a single `## Non-claims` section in the top-level README (and its `pt-BR` translation): not production infrastructure, not a provider SLA, not a production-traffic benchmark, not multi-tenant/remote, not a complete Phase 14 rollout, and not a finished OR-9 or OR-10.

A fourth OR-10 increment extended the security review beyond this session's own new code to the repository's existing HTTP surface and provider adapter layer: the FastAPI application in `apps/gateway-api` (client authentication, operations access, generation/route-explain/streaming request handling, header and content-type hardening) and the provider adapter/transport layer in `packages/gateway-core` (OpenAI Responses, Anthropic Messages, Gemini and generic OpenAI-compatible adapters, provider/PDP runtime binding, governance authorization verification), plus the `ImageInput` contract in `packages/gateway-contracts`. **No findings.** Confirmed: all YAML loading uses a safe loader with duplicate-key rejection and no `yaml.load`/`eval`/`exec`/`pickle`/`subprocess`/`os.system` usage anywhere in `apps/` or `packages/`; provider/PDP credentials are resolved only from validated environment-variable references, compared with `hmac.compare_digest`, and never appear in error messages, span attributes, or logs; every outbound endpoint (provider, PDP, the one loopback-only HTTP exception) is validated at config-load time to reject userinfo/query/fragment, and the one genuinely user-supplied URL (`ImageInput.url`) is HTTPS-validated the same way and is documented as forwarded to the provider without the Gateway itself fetching it; deployment-relative config paths are resolved and rejected if they escape the deployment root; provider JSON responses are walked with explicit type checks and rejected on mismatch rather than unsafely coerced; request bodies are size-bounded before parsing, content-type is enforced to a single JSON media type, duplicate credential headers are rejected, and generation/route-explain/ops responses carry `Cache-Control: no-store`. Separately, and specific to this repository's permanent invariant: both the non-streaming and streaming execution services independently re-validate that every ranking candidate's model group equals the PDP-authorized model group before building the bounded candidate list, raising a dedicated `RankingInvariantViolation` otherwise — so `Gateway allowed set ⊆ Policy Router authorized set` is enforced defensively at the resilience layer itself, not only trusted from upstream ranking; runtime health can only remove candidates, never add them; fallback only ever advances through already-ranked members of the same authorized group. This pass did not re-read the already-reviewed `scripts/local_demo.py`/`scripts/personal_default_launcher.py`, the streaming-adapter variants (presumed structurally parallel to their reviewed non-streaming counterparts), composition-root wiring, or domain-layer ranking logic beyond the resilience/streaming invariant checks — a further pass could still cover those.

A fifth OR-10 increment closed the remaining item: real screenshots of the operations-only local demo, captured with a headless Chromium (Playwright) driving an actual local run — not mockups. `docs/assets/screenshots/gateway-console-disconnected.png` and `gateway-console-connected.png` show the Console before and after connecting with the real `GATEWAY_LOCAL_DEMO_API_KEY`; the connected screenshot shows the demo's real checked-in fail-closed state honestly (`phase2-empty` registry, `0 deployments`, `0 healthy` process health), not a staged one. `docs/assets/screenshots/grafana-trace-dashboard.png` shows the provisioned local Grafana dashboard querying the real local Tempo instance, with an empty trace table — correctly empty, because the operations-only demo mode never exposes an inference route to generate a trace; this is documented in both READMEs as the demo behaving as designed, not a gap. Both READMEs now embed these three screenshots directly in the "Bounded local platform demo" section. The demo stack (Gateway, Console, OTel Collector, Tempo, Grafana) was fully torn down afterward (`docker compose ... down --volumes`, all owned processes terminated) with no leftover containers or processes. One operational note found along the way, not a repository defect: `scripts/local_demo.py`'s shutdown path relies on `KeyboardInterrupt` from an interactive `Ctrl+C`; sending `SIGINT` to the detached process directly (as this automation did, since it was launched without a controlling terminal to script the screenshot capture) did not trigger the same graceful shutdown, and manual `SIGTERM` plus a direct Compose teardown were used instead. The documented interactive `Ctrl+C` usage path is unaffected.

OR-10 is now complete: reproducible end-to-end validation, a security review of this session's new code, a security review of the existing HTTP/adapter surface, the consolidated non-claims section, and real demo screenshots.

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

## OR-9 bounded hardening — PC-34 through PC-51

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

PC-39 squash merge:

`99bbbf1f98605695935a89befc873b8c6a4296d4`

PC-41 through PC-51 (PRs #197, #199, #201, #203, #205, #207, #209, #211, #215, #217, #219) continued the same bounded OR-9 sequence over the owned HTTP surfaces: non-storable SSE/generation/route-explanation responses (PC-41, PC-44, PC-47), disabled implicit API-documentation surfaces (PC-42), bounded request bodies for generation and route-explanation (PC-43, PC-45), a suppressed server fingerprint header (PC-46), a required explicit JSON media type (PC-48), disabled implicit forwarded-header/proxy trust (PC-49), rejection of ambiguous duplicate credential headers (PC-50), and anti-framing/browser-hardening headers on the local Console (PC-51). Each increment is scoped to the already-owned HTTP boundary and does not touch authorization, ranking, retry/fallback or provider execution.

PC-51 squash merge / latest certified baseline:

`34d0e3fc5153022d2402808397ce93b3c19f2c7e`

These increments do not complete OR-9. Production browser identity/session handling, OAuth/OIDC/workload identity, TLS termination, rate limiting, CSRF policy and any future mutation authority remain separate reviewable concerns. None of the hardening increments may authorize or widen model execution.

## OR-9 minimum-hardening investigation, executed 2026-09-09

README item 3 of "What remains before calling the application finished" asked to "complete the minimum OR-9 security hardening appropriate to the demonstrated operational surfaces" — but, unlike OR-10, no document anywhere enumerated what that minimum actually consisted of beyond "PC-34 through PC-51 complete; production concerns pending". This increment investigated whether a concrete, still-open, non-production gap exists on the surfaces this repository actually exposes (the Operations API, the governed generation/route-explain HTTP boundary, and the local Console), rather than leaving the item permanently unclosable for lack of a defined scope.

Checked and confirmed already covered, with no further action needed: debug/reload is never enabled on the Uvicorn server (no stack-trace disclosure on unexpected exceptions); every `except Exception` handler in `apps/gateway-api` returns a sanitized message, never raw exception text (consistent with the OR-10 code security review); the Operations API (`/v1/ops/*`) exposes GET-only routes with no request body to bound; `/livez` and `/readyz` return fixed, minimal, non-informative payloads; there are no `TODO`/`FIXME` markers anywhere in `apps/gateway-api` or `packages/gateway-core` hinting at a known-but-deferred gap; the OTLP exporter's credential boundary is already explicitly documented as deferred in `docs/project/PROCESS_ENTRYPOINT.md`, not silently missing.

One genuine, previously undocumented finding: the Gateway API has no CORS middleware configured. This is correct, not a gap — the Console only ever reaches the Gateway through Vite's same-origin `/v1` dev proxy, so no genuinely cross-origin browser request is ever made, and the absence of CORS headers means a browser blocks any other origin from reading a response by default. The property was true but implicit; it is now explicitly documented in `docs/project/GATEWAY_CONSOLE.md` as a reviewed choice, specifically to prevent a future contributor from "fixing" a perceived CORS gap by adding permissive cross-origin headers without a separately reviewed consumer boundary.

**Conclusion: OR-9's minimum-appropriate hardening for the currently demonstrated operational surfaces is complete.** No further non-production gap was found. The remaining OR-9 scope — production browser identity/session handling, OAuth/OIDC/workload identity, TLS termination, rate limiting, CSRF policy, and any future mutation authority — is genuinely production-only work, correctly deferred rather than a silently missing "minimum," and remains explicitly open in both this document and the README's Non-claims section.

## PC-52 — Gateway Console per-request trace navigation, executed 2026-09-09

README item 2 of "What remains before calling the application finished" asked whether the Console should gain a bounded live-request/provenance view and per-trace navigation. The live-request/provenance view already existed (PC-38's "Run governed request" panel, already showing real provider/model/deployment identity). The genuinely open part was per-trace navigation: a real link from one completed request to that exact trace in Grafana, not just the general dashboard PC-28 already links to.

`ProviderExecution` gained an optional `trace_id` field (validated everywhere as an exact 32-character lowercase-hex string, or absent — never fabricated). `apps/gateway-api/stream_generate.py` reads the Gateway's own already-active OTel span's `SpanContext.trace_id` (via a new `current_trace_id` helper in `packages/gateway-core/application/telemetry.py`) only when building the terminal `RESPONSE_COMPLETED` SSE event, only when that span context is valid. The field threads through the SSE wire payload, the Python thin client's codec, and the Console's own SSE decoder, each independently closed-schema validating it. The Console renders a "View this request's trace in Grafana" link when present, built by a new `buildLocalGrafanaTraceUrl` alongside the existing `buildLocalGrafanaDashboardUrl`.

The per-trace link does not use Grafana's Explore view: this local demo's anonymous Viewer role does not have Explore access (confirmed directly — Grafana redirects `/explore` to `/?redirectTo=%2Fexplore` for that role). Instead, `deploy/observability/gateway-traces-dashboard.json` gained a second panel, `Selected request trace` (a Tempo `traces` panel querying `${traceId}`), fed by a new `traceId` textbox dashboard variable; the link sets that variable and jumps straight to the panel (`/d/<uid>/<slug>?var-traceId=<id>&viewPanel=2`). This reuses the same reviewed, `allowUiUpdates: false` dashboard the Console already links to.

Proving this end to end surfaced one real, previously undiscovered infrastructure bug: `otel-collector` in `compose.observability.yml` declared `127.0.0.1:4318:4318`, but its only Docker network was `observability`, which is `internal: true` — an internal network cannot have any of its containers' ports published to the host, so Docker silently dropped the mapping and the Collector was unreachable from any host process. This had never been caught because the credential-free `collector-receipt` CI proof uses an entirely separate, non-internal-networked compose file (`compose.collector-receipt.yml`), and nothing else sent a real span through this specific stack from a host process. Fixed by adding `otel-collector` to the `grafana-host-access` bridge alongside `grafana`; Tempo stays internal-only and unpublished, unchanged.

With the fix in place, this was proven completely live, twice:

1. **SDK-level proof** (`personal-default` profile, OTel enabled, real observability stack): a real governed request returned `trace_id: c4825b8223d1d5187b3a65ef6323dab3` (then `06aab379f1d4674df651e926f2d14882` after the network fix); Grafana's `Selected request trace` panel rendered the real waterfall for the second one — `governed-llm-gateway: llm.gateway.request` (273ms) → `policy.route` (234ms) and `llm.gateway.stream` (1.63s) → `provider.inference` (1.62s) — matching the Gateway's own span hierarchy exactly.
2. **Full browser proof** (Console UI, not just the SDK): connected to the live Gateway, ran a real governed request through the Console's own form, got back `provider: nvidia`, `deployment: nvidia-nemotron-3-super-dev`, and `Trace ID: 0d4f1d56a6af2f2a50fa1b1ae217b870` displayed in the evidence panel; clicked the Console's own "View this request's trace in Grafana" link; Grafana opened showing that exact same trace ID and the same waterfall shape. Screenshots: `docs/assets/screenshots/console-trace-evidence.png` and `docs/assets/screenshots/grafana-selected-trace-panel.png`.

All local processes and the observability Compose stack (including volumes) were torn down after the proof; `git status --short config/` was clean throughout since no committed config was edited for this profile run.

This closes README item 2 completely and closes OR-6's previously-deferred per-trace-correlation gap.

## personal-default profile — full Anthropic and reasoning-strong workload proof coverage, executed 2026-09-09

A full-repository gap analysis found two remaining proof gaps specific to `personal-default` (distinct
from `live-development`, where Anthropic in `balanced` was already proven): Anthropic's three deployments
in this profile (`anthropic-claude-sonnet-5-dev` in `balanced`, `-reasoning-dev` in `reasoning-strong`,
`-agentic-dev` in `agentic-strong`) had never been individually exercised here, and `security.analysis`,
`code.generate`, `code.review` (the three `reasoning-strong` siblings of the already-proven
`reasoning.complex`) had never been individually exercised at all. Both closed the same day, using the
account-level issue resolution already recorded above and the profile's own single-provider isolation
procedure where needed:

- `security.analysis`, `code.generate`, `code.review` — run with the full default profile (all 14
  deployments enabled, nothing disabled): all three succeeded via `anthropic-claude-sonnet-5-reasoning-dev`
  (alphabetically first at equal neutral scores, same tie-break behavior already documented for
  `reasoning.complex`), `latency_ms` 7206 / 2780 / 1824 respectively. This closes the workload gap and
  simultaneously proves Anthropic live in `reasoning-strong`.
- `rag.answer` isolated to `anthropic-claude-sonnet-5-dev` only (the other five `balanced` deployments
  temporarily disabled) — succeeded, `latency_ms: 2203`, proving Anthropic live in `balanced`.
- `agent.orchestration` isolated to `anthropic-claude-sonnet-5-agentic-dev` only (`openai-gpt-5-6-luna-agentic-dev`
  temporarily disabled) — succeeded, `latency_ms: 2448`, proving Anthropic live in `agentic-strong`.

Every deployment in every model group `personal-default` wires (`balanced`, `fast-small`,
`structured-fast`, `reasoning-strong`, `agentic-strong`) is now individually proven live in this profile
specifically. Both local processes were stopped after each proof and the temporary isolation edits were
reverted with no diff left behind (`git status --short config/profiles/personal-default/` clean before
committing).

## Documentation restructure, executed 2026-09-09

A full-repository gap analysis raised a structural concern: `docs/` had grown to 97 markdown files
(~13k lines) written progressively one file per PR/increment, and `CURRENT_STATE.md` itself had grown to
564 lines as an append-only log. That shape suits a long-lived team source of truth; it does not suit a
repository whose stated purpose is demonstrating engineering practice to a reader with minutes, not weeks.

- `docs/evaluation/` went from 30 files to 3 (`BENCHMARK_MATRIX.md`, `OPERATIONAL_EVIDENCE.md`,
  `OPERATIONAL_SAMPLE_BATCH.md`). The 27 removed were narrow one-per-workload or
  one-per-increment-attestation docs whose content was already condensed into `BENCHMARK_MATRIX.md`;
  verified no file outside `docs/evaluation/` linked to any of the removed paths before deleting.
- Removed `docs/project/PHASE0_ACCEPTANCE.md`, `PHASE14_TERMINAL_EXECUTION_EVIDENCE.md` and
  `PHASE14_PROVIDER_NEUTRAL_EXECUTION_PROVENANCE.md`: one-time phase-completion snapshots already
  condensed into this document's own historical entries above.
- Resolved a genuine duplicate: `docs/architecture/MODEL_REGISTRY.md` and the required
  `docs/project/MODEL_REGISTRY.md` covered overlapping ground under the same title. Merged the
  architecture copy's unique detail (YAML safety mechanics, exact digest canonicalization steps) into
  the required file and removed the duplicate.
- Split this file: `CURRENT_STATE.md` now states only what is true today; the full dated proof-by-proof
  narrative moved here, to `CHECKPOINT_LOG.md`, unchanged in content and chronological order.

Full quality gate passed throughout, including `scripts/phase0_gate.py`'s frozen `REQUIRED_FILES` check
and `scripts/architecture_check.py`. No code changes.
