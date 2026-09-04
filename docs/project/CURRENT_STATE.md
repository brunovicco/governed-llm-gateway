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
| Phase 11 — Evidence-Driven Ranking | CURRENT — REVIEW PREPARATION |
| Phase 12+ | NOT STARTED / BLOCKED ON PHASE 11 MERGE |

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

Phase 9 merged through PR #8 at merge commit
`be15c21ecfc76ef9bb727e5c4144c4929f028489` and added metadata-only OpenTelemetry through
`a2a-otel-kit==0.6.0` while preserving telemetry as evidence only.

Phase 10 merged through PR #9 at squash commit
`db30ffc481d1a3c02fb01f46524b5190290fb7ac` after independent architecture/security review returned
`APPROVE`. It established the offline `benchmarks/` source root, deterministic public/synthetic
workloads and scorers, quality-versus-availability separation, exact target provenance, and immutable
content-derived benchmark snapshots.

Final Phase 10 validation before merge:

- GitHub Actions run `33807237149` — PASS;
- pytest — 207 passed;
- aggregate branch coverage — 80.56%;
- Ruff, mypy, Bandit, pip-audit, architecture check, secret scan, and Phase 0 gate — PASS.

Coverage reporting remains fixed at precision 2. The existing FastAPI/Starlette TestClient `httpx` ->
`httpx2` deprecation warning remains non-blocking maintenance work.

## Phase 11 — Evidence-Driven Ranking

Active branch:

`feat/phase-11-evidence-driven-ranking`

The branch starts from the Phase 10 merge commit
`db30ffc481d1a3c02fb01f46524b5190290fb7ac`.

ADR-0009 — Benchmark-Derived Routing Scores — is accepted.

The authority boundary is:

`immutable benchmark snapshot -> explicit approval/promotion -> versioned ranking evidence -> runtime ranking`

Permanent rules:

- benchmark evidence may affect ordering only inside the PDP-authorized and otherwise-eligible set;
- unapproved benchmark snapshots have zero runtime authority;
- runtime never discovers or auto-loads the newest benchmark result;
- the Phase 10 benchmark runner remains off the runtime request path;
- provider failures remain availability evidence and never become quality score zeroes;
- missing evidence fails closed;
- manual override is explicit, versioned, attributable configuration and cannot broaden eligibility;
- rollback selects a previously approved immutable ranking artifact;
- benchmark runs, telemetry, and runtime outcomes never rewrite active ranking policy automatically.

## Phase 11 implementation

Implemented and validated:

1. deterministic benchmark target/workload -> runtime deployment/workload promotion;
2. promotion identity covering approval metadata, exact benchmark snapshot, dataset digest, and records;
3. immutable/idempotent promoted-evidence persistence;
4. runtime-side evidence validation without importing `benchmarks/`, including content-derived
   `evidence_id` verification and duplicate-key rejection;
5. schema `1.1` evidence-driven ranking policy and explicit `score_provenance_mode`;
6. deterministic `benchmark_hybrid` compilation that replaces only empirical `quality` and
   `availability`;
7. static/versioned reliability, latency score, cost score, weights, and `expected_latency_ms` retained
   until separately reviewed normalization semantics exist;
8. all-or-nothing hybrid compilation with fail-closed missing evidence;
9. exact benchmark/promotion identities included in ranking-policy digest;
10. exact `benchmark_snapshot_id` included in routing provenance and routing-decision identity;
11. authorization monotonicity regressions proving benchmark evidence cannot resurrect a PDP-excluded
    candidate or bypass `enabled=False`;
12. content-addressed, versioned, attributable `ManualOverrideBundle` configuration;
13. manual override limited to promoted `quality`/`availability`, unable to add candidates or stack
    implicitly;
14. exact `manual_override_id` and score-provenance mode included in ranking and routing provenance;
15. immutable `ApprovedRankingArtifact` identity and exact rollback selection with unknown/ambiguous
    targets failing closed;
16. runtime tests proving manual override also cannot bypass PDP authorization or deployment
    eligibility and that provenance-only changes alter deterministic decision identity.

## Final Phase 11 implementation baseline

Validated source/documentation checkpoint before final review synchronization:

`d076ced8a99fcf89afa7f0d62234913501413a4d`

GitHub Actions run `33814109995` — PASS:

- pytest — **251 passed**;
- aggregate branch coverage — **81.27%**;
- mypy — PASS across **97 source files**;
- Ruff lint/format — PASS, 97 files;
- Bandit — **0 identified issues**;
- pip-audit — **no known vulnerabilities**;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 regression gate — PASS;
- default CI remains credential-free and read-only with no live provider/PDP calls.

`EVALUATION.md`, `ROADMAP.md`, and `VALIDATION.md` are synchronized with the Phase 11 implementation and
accepted ADR-0009 semantics. The current documentation head requires one final PR-preparation quality
run before the branch is considered review-ready.

## Explicitly deferred

- automatic/adaptive policy optimization or self-modifying routing;
- normalized benchmark latency/cost ranking scores without separately reviewed normalization policy;
- uncontrolled online-learning logic;
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation requiring a canonical transcript/state contract;
- widening the supported JSON Schema subset without explicit safety/compatibility semantics;
- shared/distributed circuit-breaker state beyond Phase 6;
- treating policy `max_latency_ms` as an implicit total cross-retry streaming deadline;
- payload capture or prompt/completion logging as default telemetry.

## Next step

Run the final documentation-synchronized quality gate, open the Phase 11 PR, and require independent
architecture/security review. Do not start Phase 12 until PR-head CI is green, review returns `APPROVE`
with no justified BLOCKER/HIGH/MEDIUM findings, and Phase 11 is merged.
