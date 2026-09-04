# Phase 0 through Phase 11 Validation Record

Date: 2026-09-03

## Toolchain

- Python project runtime: 3.13+
- project pin: Python 3.13.12
- quality-tool execution pinned to Python 3.13
- uv workspace with locked dependencies
- default GitHub Actions permissions: `contents: read`, `metadata: read`

## Historical architecture baseline

`scripts/phase0_gate.py` remains frozen to the contract baseline that existed at the
`phase-0-architecture-gate` tag. Current/future phase tests are exercised by the complete pytest gate.
Package boundaries remain enforced separately by `scripts/architecture_check.py`.

The core authorization invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Completed phases

- Phase 2 — Contracts and Model Registry: PR #1.
- Phase 3 — Provider Execution Foundation: PR #2.
- Phase 4 — Policy Router Integration: PR #3.
- Phase 5 — Deterministic Operational Ranking and Explainability: PR #4.
- Phase 6 — Runtime Health, Retry and Safe Fallback: PR #5.
- Phase 7 — Structured Output and Tool Normalization: PR #6, merge commit
  `6c53d5586b6c6f9fbafcfda642f2b9e7af0cbca0`.
- Phase 8 — Streaming: PR #7, merge commit
  `ed429a6554fb987cd4ab991d330b2005d8cfd0d7`.
- Phase 9 — OpenTelemetry: PR #8, merge commit
  `be15c21ecfc76ef9bb727e5c4144c4929f028489`.
- Phase 10 — Evaluation Framework: PR #9, squash merge
  `db30ffc481d1a3c02fb01f46524b5190290fb7ac`.

## Phase 8 validation checkpoint

Phase 8 code-validation head:

`a8b9fdcd6d69b94a2ab6ed942e67409df50d0092`

GitHub Actions run `33790152650`:

- Ruff/mypy/pytest/security/architecture/secret gates — PASS;
- pytest — 183 tests;
- coverage — 80.61%;
- bounded incremental SSE parsing enforced the 1 MiB event limit before an unterminated provider line
  could grow without bound inside HTTPX;
- run was credential-free and made no live provider/PDP calls.

## Phase 9 validation checkpoint

Final Phase 9 source head after lifecycle hardening:

`5177f6b71c6ba2b3c5e17762d9cec0b39a3013b3`

Read-only revalidation run `33803564689`:

- Ruff lint/format — PASS;
- mypy — PASS across 75 source files;
- pytest — 192 tests;
- coverage — 80.07%;
- Bandit — no identified issues;
- pip-audit — no known vulnerabilities;
- architecture/secret/Phase 0 gates — PASS.

Phase 9 findings resolved before merge included restoring backward-compatible optional telemetry
parameters, preserving the shared deny-by-default sanitizer, adding error-path coverage, and closing
provider-attempt spans before retry backoff.

## Phase 10 implementation and validation

Phase 10 introduced the repository-level offline `benchmarks/` source root without making it a runtime
dependency of the gateway packages.

Validated behavior includes:

- schema `1.0` / benchmark `gateway-eval-v1` public/synthetic dataset;
- ten cases across `structured_extraction`, `rag_ptbr`, `code_generation`, `tool_use`, and
  `agent_orchestration`;
- strict dataset validation before provider execution;
- deterministic scorer registry: `exact_json`, `contains_all`, `mapping_fields`, `ordered_sequence`;
- provider-neutral executor/runner;
- explicit `succeeded`, `quality_failure`, and `provider_failure` observations;
- provider failures retain `quality_score = None`;
- scorecards separately aggregate quality, availability, latency, TTFT, usage, cost, rate limits,
  fallback frequency, and provider errors;
- exact provider/model/API/configuration/source-date target provenance;
- canonical dataset digest and content-addressed immutable benchmark snapshot identity;
- immutable/idempotent result persistence without raw provider responses.

Phase 10 quality hardening also resolved a coverage-report precision issue. The threshold was not
lowered and benchmark code was not excluded; meaningful scorer tests raised actual coverage above 80%,
and coverage precision is fixed at 2 decimals.

Final Phase 10 validated baseline before merge:

- GitHub Actions run `33807237149` — PASS;
- pytest — 207 passed;
- aggregate branch coverage — 80.56%;
- Ruff lint/format — PASS;
- mypy — PASS;
- Bandit — no identified issues;
- pip-audit — no known vulnerabilities;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 regression gate — PASS;
- credential-free default CI with no live provider/PDP calls.

Independent architecture/security review returned `APPROVE` before PR #9 merged.

## Phase 11 — Evidence-Driven Ranking

Active implementation branch:

`feat/phase-11-evidence-driven-ranking`

ADR-0009 — Benchmark-Derived Routing Scores — is accepted.

### Promotion and evidence boundary

Phase 11 implements:

```text
immutable benchmark snapshot
  -> explicit approval/promotion
  -> content-addressed ranking evidence
  -> evidence-driven ranking policy
  -> runtime ordering inside the PDP-authorized/eligible set
```

`benchmarks/promotion.py` explicitly maps benchmark target/workload evidence to exact runtime
workload/deployment identities. Promotion identity covers approval metadata, source benchmark snapshot,
dataset digest, and promoted records. Provider-only failures cannot become false zero-quality evidence:
promotion requires completed quality evidence and fails closed when it is absent.

`benchmarks/promotion_store.py` persists promoted evidence immutably/idempotently and rejects
same-identity/different-content collisions.

Runtime code does not import the repository-level benchmark runner. `ranking_evidence.py` and the
strict JSON adapter validate promoted evidence on the runtime side and verify the content-derived
`evidence_id`, including duplicate-key rejection.

### Benchmark-hybrid compilation

`evidence_ranking.py` introduces schema `1.1` evidence-driven policies with exact benchmark/promotion
provenance. The initial compiler replaces only:

- `quality` with promoted mean quality;
- `availability` with promoted availability rate.

It deliberately does not invent normalization for benchmark latency/cost. Reliability, normalized
latency score, normalized cost score, weights, and hard `expected_latency_ms` remain explicit static
Phase 5 inputs until separately reviewed normalization semantics exist.

Compilation is all-or-nothing for deployments represented by the approved base ranking policy.
Missing promoted evidence fails closed. Exact benchmark snapshot and promotion identities participate
in the ranking-policy digest.

### Runtime provenance and authority monotonicity

`RoutingProvenance` records Phase 11 reconstruction evidence:

- exact `benchmark_snapshot_id`;
- `score_provenance_mode`;
- `manual_override_id` when present.

These identities also participate in deterministic `routing_decision_id` calculation. Static policies
leave Phase 11 provenance unset.

Contract tests prove benchmark-derived ranking cannot:

- resurrect a deployment outside the PDP-provided candidate set;
- bypass `enabled=False` eligibility;
- create authorization independently of Policy Model Router.

### Manual override

`ranking_override.py` implements explicit, versioned, attributable manual override configuration.
A bundle records approval version/date/operator/reason and exact target/value changes, and its complete
canonical form produces a content-derived `manual_override_id`.

The first override contract is intentionally narrow: it may replace only benchmark-promoted `quality`
and/or `availability`. It cannot add deployments, change policy authorization, alter reliability,
latency/cost scores, weights, or hard expected latency. Unknown targets fail closed.

Overrides cannot stack implicitly. A replacement override must be applied from the approved
benchmark-hybrid baseline, ensuring each active override has one explicit provenance identity.

Runtime regression tests prove manual override cannot resurrect an excluded PDP candidate or bypass a
disabled deployment. Changing only override attribution/reason changes the manual override identity and
routing decision identity even when effective numeric score/selection remains unchanged.

### Rollback

`ApprovedRankingArtifact` binds approval metadata to an immutable ranking-policy digest and exact
benchmark/manual-override provenance. `select_rollback_policy` requires an exact content-derived
artifact identity and returns the previously approved immutable policy. Unknown or ambiguous rollback
targets fail closed.

Rollback therefore selects known configuration; it does not mutate the active policy in place and does
not derive policy from live telemetry/runtime outcomes.

## Phase 11 final implementation baseline before documentation synchronization

Validated head:

`d076ced8a99fcf89afa7f0d62234913501413a4d`

GitHub Actions run:

`33814109995`

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff format — PASS, **97 files**;
- mypy — PASS across **97 source files**;
- pytest — **251 passed**;
- aggregate branch coverage — **81.27%**;
- `ranking_override.py` — **91.78%** coverage;
- `evidence_ranking.py` — **89.38%** coverage;
- Bandit — PASS, **0 identified issues** across 9,564 lines scanned;
- pip-audit — PASS, **no known vulnerabilities**;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 regression gate — PASS;
- default workflow token remains read-only;
- credential-free and no live provider/PDP calls.

The only warning remains the existing FastAPI/Starlette TestClient `httpx` -> `httpx2` deprecation
notice; it is non-blocking and unrelated to Phase 11.

## Phase 11 review boundary

Implementation validation: **PASS**

Authorization monotonicity regression coverage: **PASS**

Benchmark quality-versus-availability separation: **PASS**

Explicit promotion / content-addressed evidence: **PASS**

Manual override / rollback behavior: **PASS**

Documentation synchronization: **IN PROGRESS**

Independent architecture/security review: **PENDING**

Phase 11 merge: **PENDING**

Phase 12 remains blocked until Phase 11 documentation is synchronized, PR-head CI is green,
independent architecture/security review returns `APPROVE` with no justified BLOCKER/HIGH/MEDIUM
findings, and the Phase 11 PR is merged.
