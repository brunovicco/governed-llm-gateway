# Current State

Last updated: 2026-09-03

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
| Phase 10 — Evaluation Framework | IMPLEMENTED — VALIDATION / REVIEW PREPARATION |
| Phase 11+ | NOT STARTED |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api`
  boundaries;
- provider-neutral contracts/domain and provider-specific infrastructure isolated in adapters;
- Policy Model Router remains the PDP; the gateway remains the PEP plus operational selector;
- core invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- metadata-only evidence by default and fail-closed handling of untrusted configuration/external
  responses;
- provider-native feature support never grants model authorization by itself;
- business-tool execution remains outside the gateway.

## Completed through Phase 9

Phase 1 generalized Policy Model Router workload/model-group identifiers. Phase 2 established the
strict model registry and deterministic registry digest. Phase 3 added provider execution ports and
OpenAI Responses, OpenAI-compatible, Gemini `generateContent`, and Anthropic Messages adapters.
Phase 4 bound the gateway to Policy Model Router authorization and built the authorized registry
candidate set. Phase 5 added deterministic eligibility/ranking and explainability while preserving the
authorized set. Phase 6 added bounded retry/fallback and per-deployment health. Phase 7 added
structured-output and tool normalization without business-tool execution. Phase 8 added normalized
streaming and replay-safe fallback semantics.

Phase 9 merged through PR #8 at merge commit
`be15c21ecfc76ef9bb727e5c4144c4929f028489`. It added metadata-only OpenTelemetry through
`a2a-otel-kit==0.6.0`, W3C propagation, gateway/policy/provider spans, retry/fallback events, streaming
trace handoff, and privacy tests. Provider-attempt spans close before retry backoff. Telemetry remains
evidence only and has no authorization/ranking/health authority.

## Phase 10 — Evaluation Framework

Branch `feat/phase-10-evaluation-framework` implements the offline-first evaluation framework under a
repository-level `benchmarks/` source root. It deliberately does not become a runtime dependency of
the gateway packages.

Delivered implementation:

- strict provider-neutral benchmark contracts for cases, targets, observations, scorecards, and
  immutable snapshots;
- five roadmap workload identifiers: `structured_extraction`, `rag_ptbr`, `code_generation`,
  `tool_use`, and `agent_orchestration`;
- `benchmarks/datasets/gateway-eval-v1.json`: schema `1.0`, explicitly `public`, ten
  public/synthetic cases (two per initial workload);
- strict dataset loader rejecting unknown fields, malformed values, unsupported workload values, and
  non-public Phase 10 classification;
- deterministic local scorers: `exact_json`, `contains_all`, `mapping_fields`, and
  `ordered_sequence`;
- scorer preflight before any executor call so unknown scorer identifiers fail closed without partial
  provider execution;
- provider-neutral `BenchmarkExecutor` port and `BenchmarkRunner`;
- explicit `succeeded`, `quality_failure`, and `provider_failure` observation states;
- provider failures carry no quality score, preventing rate limits/timeouts/outages from becoming
  false zero-quality model results;
- scorecards that independently aggregate availability, quality, latency p50/p95, TTFT p50/p95,
  usage, cost, rate-limit count, fallback frequency, and stable provider-error counts;
- strict provider/model target matrix in `benchmarks/runners/targets-v1.json`, with exact model ID,
  API surface, configuration, and source date for NVIDIA, Groq, OpenRouter, Google Gemini, OpenAI, and
  Anthropic benchmark/control targets;
- canonical dataset digest and content-derived `sha256:` snapshot identity covering benchmark version,
  runner version, run date, exact targets/configuration, observations, and scorecards;
- immutable/idempotent snapshot persistence under
  `benchmarks/results/<benchmark-version>/<snapshot-sha256>.json`;
- raw provider responses are outside the score-snapshot contract;
- `benchmarks/` is included in Ruff, mypy, Bandit, architecture validation, and aggregate coverage.

## Phase 10 validation baseline

Validated code head before documentation synchronization:

`9a7b49407b0a040c976eac88fb29201ecf102a28`

GitHub Actions run:

`33806876880`

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff format — PASS, 84 files;
- mypy — PASS across **84 source files**;
- pytest — **207 passed**;
- aggregate branch coverage — **80.56%**, above the 80% threshold using the actual value;
- Phase 10 deterministic scorer module — 100% coverage;
- Bandit — no identified issues;
- pip-audit — no known vulnerabilities;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 regression gate — PASS;
- default workflow token permissions remain read-only (`contents: read`, `metadata: read`);
- no live provider/PDP calls and no provider credentials required.

A Phase 10 validation finding exposed that coverage tooling with default precision could display an
actual 79.63% result as rounded 80% and allow the workflow to continue. The threshold was not lowered
and benchmark code was not excluded. Additional meaningful scorer tests raised actual coverage to
80.56%, and `[tool.coverage.report] precision = 2` is now configured so future sub-80 results cannot be
hidden by zero-decimal display rounding.

The known FastAPI/Starlette TestClient `httpx` -> `httpx2` deprecation warning remains non-blocking and
is separate maintenance work.

## Phase boundary

Phase 10 produces benchmark evidence only. Runtime routing does not import or consume `benchmarks/`,
and `benchmark_snapshot_id` remains unset in routing provenance.

ADR-0009 — Benchmark-derived routing scores — remains deferred to Phase 11. When Phase 11 begins,
approved benchmark evidence may affect ordering only inside the already-authorized candidate set. It
must never broaden authorization.

Free/developer provider endpoints remain benchmark/development-only for public/synthetic datasets by
default. Confidential/private benchmark fixtures must not be sent to those endpoints.

## Explicitly deferred

- benchmark-derived ranking evidence/runtime snapshot consumption (Phase 11);
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation requiring a canonical transcript/state contract;
- widening the supported JSON Schema subset until safety/compatibility semantics are explicit;
- shared/distributed circuit-breaker state beyond the Phase 6 per-process implementation;
- treating policy `max_latency_ms` as an implicit total cross-retry streaming deadline;
- payload capture or prompt/completion logging as part of default telemetry.

## Next step

Complete final Phase 10 documentation/quality validation, open the Phase 10 pull request, then run the
required independent architecture/security review against the complete `main...feat/phase-10-evaluation-framework`
diff. Resolve every justified BLOCKER/HIGH/MEDIUM finding before merge.

Phase 11 must not start until Phase 10 is independently reviewed and merged.
