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
| Phase 10 — Evaluation Framework | COMPLETE (`governed-llm-gateway` PR #9) |
| Phase 11 — Evidence-Driven Ranking | CURRENT — PROMOTION / HYBRID COMPILATION IN PROGRESS |
| Phase 12+ | NOT STARTED |

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

## Completed through Phase 10

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

Phase 10 merged through PR #9 at squash commit
`db30ffc481d1a3c02fb01f46524b5190290fb7ac` after independent architecture/security review returned
`APPROVE`.

Phase 10 delivered:

- repository-level offline `benchmarks/` source root, intentionally outside runtime package authority;
- five initial workloads: `structured_extraction`, `rag_ptbr`, `code_generation`, `tool_use`, and
  `agent_orchestration`;
- ten explicitly public/synthetic benchmark cases;
- deterministic local scorers with whole-dataset fail-closed preflight;
- provider-neutral benchmark executor/runner;
- explicit `succeeded`, `quality_failure`, and `provider_failure` observation states;
- scorecards that keep quality and availability evidence separate;
- exact provider/model/API/configuration/source-date target provenance;
- canonical dataset digest and immutable content-derived benchmark snapshot identity;
- idempotent snapshot persistence without raw provider-response persistence;
- `benchmarks/` included in lint, typing, security, architecture, and coverage gates.

Final Phase 10 validation evidence recorded before merge:

- GitHub Actions run `33807237149` — PASS;
- pytest — 207 passed;
- aggregate branch coverage — 80.56%;
- Ruff, mypy, Bandit, pip-audit, architecture check, secret scan, and Phase 0 gate — PASS;
- default CI credential-free with no live provider/PDP calls.

Coverage reporting uses precision 2 so a real sub-80% result cannot be hidden by zero-decimal display
rounding.

The known FastAPI/Starlette TestClient `httpx` -> `httpx2` deprecation warning remains non-blocking and
is separate maintenance work.

## Phase 11 — Evidence-Driven Ranking

Active branch:

`feat/phase-11-evidence-driven-ranking`

The branch starts from the Phase 10 merge commit
`db30ffc481d1a3c02fb01f46524b5190290fb7ac`.

ADR-0009 — Benchmark-Derived Routing Scores — is accepted.

The Phase 11 authority boundary is:

`immutable benchmark snapshot -> explicit approval/promotion -> versioned ranking evidence -> runtime ranking`

Permanent Phase 11 rules:

- benchmark evidence may affect ordering only inside the PDP-authorized and otherwise-eligible candidate
  set;
- an unapproved benchmark snapshot has zero runtime routing authority;
- runtime must not discover or automatically load the newest benchmark result;
- the Phase 10 benchmark runner remains off the runtime request path;
- promoted routing evidence records the exact immutable `benchmark_snapshot_id`;
- provider failures remain availability evidence and must not become quality score zeroes;
- missing sufficient benchmark quality evidence fails closed instead of inventing neutral/default scores;
- manual override is explicit, versioned, attributable configuration and cannot broaden eligibility;
- rollback selects a previously approved immutable ranking artifact/snapshot combination;
- benchmark runs, telemetry, or runtime outcomes never rewrite active ranking policy automatically.

## Current Phase 11 implementation checkpoint

Completed in the current branch:

1. Phase 10 merged and Phase 11 unblocked.
2. ADR-0009 accepted and ADR backlog/roadmap synchronized.
3. `benchmarks/promotion.py` adds deterministic, explicit target/workload -> runtime
   deployment/workload promotion. Promotion identity covers approval metadata, exact Phase 10 snapshot,
   dataset digest, and promoted records.
4. Provider-only failures cannot become quality score zero: promotion requires completed quality
   evidence and fails closed when it is absent.
5. `benchmarks/promotion_store.py` persists promoted evidence immutably/idempotently and rejects
   same-ID/different-content collisions.
6. `ranking_evidence.py` adds a runtime-side strict contract that does not import `benchmarks/` and
   verifies the content-derived promotion `evidence_id` before accepting evidence.
7. `ranking_evidence_json.py` adds strict JSON loading, including duplicate-key rejection.
8. `evidence_ranking.py` adds a schema `1.1` evidence-driven ranking subtype and a deterministic
   `benchmark_hybrid` compiler.
9. Hybrid compilation replaces only empirical `quality` and `availability` dimensions. Phase 5
   `reliability`, normalized latency score, normalized cost score, weights, and `expected_latency_ms`
   remain explicit static inputs until a separate normalization rule is reviewed and approved.
10. Hybrid compilation is all-or-nothing for deployments already present in the base ranking policy;
    missing promoted evidence fails closed.
11. Benchmark snapshot ID and promotion evidence ID participate in the compiled ranking-policy digest.
12. The temporary scoped Ruff fixer self-removed after normalizing Phase 11 imports/formatting.

Earlier Phase 11 semantic baseline before the runtime-evidence/compiler additions:

- GitHub Actions run `33810104964` — PASS;
- pytest — 215 passed;
- aggregate coverage — 80.72%;
- mypy — PASS across 86 source files;
- Ruff, Bandit, pip-audit, architecture check, secret scan, and Phase 0 gate — PASS.

A full quality run for the current semantic checkpoint is required before runtime routing is connected
to the compiled policy.

## Next implementation slice

- validate the current promoted-evidence / JSON-loader / hybrid-compiler checkpoint through the full
  quality gate;
- connect compiled benchmark provenance to `RoutingProvenance.benchmark_snapshot_id` without changing
  the authorization or eligibility sequence;
- include benchmark provenance in deterministic routing decision identity/explain output;
- add regression tests proving benchmark evidence cannot resurrect an unauthorized or ineligible
  deployment;
- add explicit rollback/manual-override behavior only after benchmark-driven runtime provenance is
  stable.

## Explicitly deferred

- automatic/adaptive policy optimization or self-modifying routing;
- deriving normalized latency/cost ranking scores from benchmark p95/cost without an explicit reviewed
  normalization policy;
- combining benchmark ranking with uncontrolled online-learning logic;
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation requiring a canonical transcript/state contract;
- widening the supported JSON Schema subset until safety/compatibility semantics are explicit;
- shared/distributed circuit-breaker state beyond the Phase 6 per-process implementation;
- treating policy `max_latency_ms` as an implicit total cross-retry streaming deadline;
- payload capture or prompt/completion logging as part of default telemetry.

## Next step

Complete the current Phase 11 quality checkpoint. Only after it is green, wire approved benchmark
provenance into runtime ranking/explainability while preserving the existing PDP authorization and
eligibility ordering.