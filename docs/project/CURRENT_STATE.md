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
| Phase 9 — OpenTelemetry | IMPLEMENTED — READY FOR INDEPENDENT REVIEW |
| Phase 10+ | NOT STARTED |

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

## Completed through Phase 8

Phase 1 generalized Policy Model Router workload/model-group identifiers. Phase 2 established the
strict model registry and deterministic registry digest. Phase 3 added provider execution ports and
OpenAI Responses, OpenAI-compatible, Gemini `generateContent`, and Anthropic Messages adapters.
Phase 4 bound the gateway to Policy Model Router `POST /route` schema `1.0`, validated prompt-free
policy provenance, and built the authorized registry candidate set. Phase 5 added deterministic
eligibility/ranking, ADR-0006, ranking-policy provenance, and authenticated `POST /v1/route/explain`
without provider inference.

Phase 6 added ADR-0007, per-deployment runtime health, circuit-breaker state, bounded retry against the
same deployment, bounded fallback through already-ranked authorized alternatives, deterministic
backoff/jitter, replay-safety boundaries, and metadata-only attempt evidence.

Phase 7 added ADR-0013, bounded Draft 2020-12 structured-output validation, normalized tool
definitions/calls/results, native OpenAI/Anthropic/Gemini translations, explicit OpenAI-compatible
opt-in, local post-provider validation, and permanent fail-closed semantic errors. The gateway still
never executes business tools or fabricates provider-native continuation state.

Phase 8 merged through PR #7 at merge commit
`ed429a6554fb987cd4ab991d330b2005d8cfd0d7`. It added ADR-0011, provider-neutral streaming,
provider-native streaming adapters, authenticated `POST /v1/generate`, bounded replay-safe
retry/fallback before visible semantic output, cancellation-safe upstream closure, final normalized
usage, and the incremental 1 MiB SSE event bound hardened against unterminated provider lines.

Phase 5 static score inputs remain configuration evidence, not benchmark evidence.
`benchmark_snapshot_id` stays unset until later evaluation/evidence-driven ranking phases.

## Phase 9 — OpenTelemetry

Branch `feat/phase-9-opentelemetry` implements the roadmap OpenTelemetry boundary using
`a2a-otel-kit==0.6.0` as the runtime integration dependency while keeping telemetry out of
`gateway-contracts` and `gateway-core/domain`.

Delivered implementation:

- ADR-0008 defines metadata-only telemetry and the deny-by-default payload boundary;
- optional `Observability` injection keeps existing execution behavior valid when telemetry is not
  configured;
- `llm.gateway.request`, `llm.gateway.stream`, `policy.route`, and per-attempt
  `provider.inference` spans are instrumented without automatic exception recording;
- retry and fallback decisions are represented as metadata-only `llm.gateway.retry` and
  `llm.gateway.fallback` span events;
- provider inference attributes include bounded operational metadata such as provider/model/deployment,
  latency, TTFT where applicable, and normalized usage counts;
- provider usage is exported as `llm.usage.input_count` / `llm.usage.output_count` because the shared
  deny-by-default sanitizer intentionally rejects credential-like key names containing `token` even
  when allowlisted; the sanitizer was not weakened or bypassed;
- W3C `traceparent` / `tracestate` propagation is injected by the shared JSON and SSE transports and
  incoming trace context can be continued at the gateway API boundary;
- remote prompts, completions, tool arguments/results, credentials, arbitrary headers, raw provider
  bodies, and raw exception messages are excluded from default exported telemetry;
- architecture checks forbid both direct OpenTelemetry and `a2a_otel_kit` imports in contracts and
  domain layers;
- contract tests use an in-memory OpenTelemetry exporter to verify trace continuity, request/stream
  parent relationships, retry/fallback correlation, transport propagation, success/failure evidence,
  and metadata-only privacy behavior;
- `uv.lock` and the runtime audit input include the Phase 9 dependency chain.

The Phase 8 internal `_sse_body()` helper remains backward compatible: Phase 9 telemetry arguments are
optional and default to `None`.

## Final Phase 9 code validation

Code-validation head:

`f7f955703a25d28c68851ce5229165a136ee7d7a`

GitHub Actions run:

`33802472000`

Results:

- `uv lock --check` — PASS;
- Ruff lint/format — PASS;
- mypy — PASS across 75 source files;
- pytest — **192 passed**;
- aggregate coverage — **80.12%**, above the 80% minimum without relying on rounding;
- Bandit — no identified issues;
- pip-audit — no known vulnerabilities;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 regression gate — PASS.

Resolved during Phase 9 validation:

- regenerated and verified the Phase 9 dependency lock;
- restored optional `_sse_body()` telemetry defaults after mypy exposed a Phase 8 compatibility
  regression;
- replaced credential-ambiguous token-named telemetry keys with privacy-safe usage-count keys while
  preserving normalized token-count values;
- added telemetry error-path tests after an intermediate 79.82% result exposed reliance on rounded
  coverage display; final actual coverage is 80.12%;
- removed all temporary maintenance workflows after use.

The known FastAPI/Starlette TestClient `httpx` → `httpx2` deprecation warning remains non-blocking and
is separate maintenance work.

## Explicitly deferred

- benchmark/evaluation framework (Phase 10);
- benchmark-derived ranking evidence (Phase 11);
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation requiring a canonical transcript/state contract;
- widening the supported JSON Schema subset until safety/compatibility semantics are explicit;
- shared/distributed circuit-breaker state beyond the Phase 6 per-process implementation;
- treating policy `max_latency_ms` as an implicit total cross-retry streaming deadline;
- payload capture or prompt/completion logging as part of default telemetry.

## Next step

Open the Phase 9 pull request and run the required independent architecture/security review against the
complete `main...feat/phase-9-opentelemetry` diff. Resolve any justified BLOCKER/HIGH/MEDIUM finding,
rerun the normal read-only quality gate, and merge only after an explicit approval verdict.

Phase 10 must not start until Phase 9 is independently reviewed and merged.
