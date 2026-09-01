# Phase 0 through Phase 5 Validation Record

Date: 2026-08-31

## Toolchain

- Python project runtime: 3.13+
- project pin: Python 3.13.12
- quality-tool execution pinned to Python 3.13
- uv workspace with locked dependencies

## Phase 0 baseline

The Architecture Gate baseline passed its quality, architecture, security, and contract checks. The
Phase 0 independent Claude Code review remains a separate historical review criterion recorded in
`docs/architecture/REVIEW.md`.

`scripts/phase0_gate.py` is now explicitly frozen to the five contract modules that existed at the
`phase-0-architecture-gate` tag:

- `test_authorization_invariant.py`;
- `test_contracts.py`;
- `test_phase0_boundaries.py`;
- `test_phase0_documents.py`;
- `test_workspace_smoke.py`.

Future-phase contract tests are exercised by the repository-wide pytest gate instead of being
silently absorbed into the Phase 0 regression gate. Durable provider-neutral contracts/domain
boundaries continue to be enforced by `scripts/architecture_check.py`.

## Phase 2 completed

Phase 2 — Contracts and Model Registry was merged through `governed-llm-gateway` PR #1. Its
acceptance evidence remains covered by the current regression suite: strict registry schema,
duplicate-key rejection, safe YAML, capability/modality consistency, explicit unknown pricing, and
deterministic SHA-256 registry provenance.

## Phase 3 completed

Phase 3 — Provider Execution Foundation was merged through `governed-llm-gateway` PR #2. Its
provider contract evidence remains covered by the current regression suite: native OpenAI, Anthropic,
Gemini and explicit OpenAI-compatible mapping; usage extraction; typed timeout/error normalization;
bounded `Retry-After`; no raw error/secret leakage; and no live provider credentials or requests
required by CI.

## Phase 4 completed

Phase 4 — Policy Router Integration was merged through `governed-llm-gateway` PR #3. The current
regression suite continues to prove prompt-free trusted policy projection, strict accepted/rejected
provenance binding, registry intersection with PDP authorization, zero provider calls after denial or
authorization-boundary failure, and no PDP-only metadata leakage into provider calls.

## Phase 5 implementation validation

Phase 5 — Deterministic Operational Ranking and Explainability was validated in the read-only GitHub
Actions quality workflow after the ranking acceptance and authority-boundary tests were complete.

Code-complete acceptance-test head: `090f7f250c23c69b87e1c71c34ca27f0ec67a770`

GitHub Actions push run: `33453828758`.

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff formatting — PASS;
- mypy — PASS across 49 source files;
- pytest — PASS, 94 tests;
- total coverage — 83.43% (minimum 80%);
- Bandit — PASS, no identified issues and no skipped files;
- pip-audit — PASS, no known vulnerabilities;
- architecture validation — PASS;
- secret scanning — PASS;
- Phase 0 regression gate — PASS.

The workflow executed with `contents: read` and no provider/PDP credentials.

## Phase 5 acceptance evidence

The normative roadmap acceptance criteria are covered directly:

- same inputs produce the same ranking and deterministic routing decision ID;
- eligibility is evaluated before score, so an ineligible deployment cannot win even with a higher
  configured score;
- equal scores resolve deterministically by ascending `deployment_id`;
- authenticated `POST /v1/route/explain` is implemented, deterministic for the same inputs, and
  performs no provider inference.

Contract tests additionally verify:

- ranking operates only on `AuthorizedCandidateSet` from Phase 4;
- registry digest drift after authorization fails closed before selection;
- a candidate outside the PDP-authorized logical model group fails closed;
- Phase 5 requires exactly one PDP-authorized logical model group and rejects ambiguous multi-group
  authorization;
- disabled deployments are rejected before scoring;
- missing tool/capability requirements, insufficient context, and disallowed environment reject the
  deployment;
- unknown pricing is not treated as free;
- missing ranking evidence is not treated as a neutral/default score;
- projected cost and versioned expected-latency ceilings can make a deployment ineligible;
- ranking policy YAML rejects duplicate keys, unknown fields, invalid weight sums, and unknown
  workloads;
- semantically equivalent decimal representations produce the same ranking-policy digest;
- selection provenance carries PDP provenance, model-registry digest, ranking-policy version/digest,
  static score snapshot ID, selected concrete identities, and machine-readable rejection reasons;
- `benchmark_snapshot_id` remains unset for Phase 5 static score evidence;
- explain requests reject prompt/message fields, unsupported schema versions, and invalid non-dotted
  workload identifiers;
- rejected gateway credentials are normalized without credential echo.

## Phase 5 scope boundaries

- Static score input is versioned configuration, not benchmark-derived empirical evidence.
- Expected latency is a planning input, not live runtime health.
- Runtime health, circuit breaker state, retry, and fallback remain Phase 6 concerns.
- Phase 5 does not add provider calls to the explain path.
- FastAPI/Pydantic remain in `gateway-api`; contracts/domain stay framework-neutral.

## Quality-gate execution model

Ruff, Bandit, and pip-audit remain isolated quality tools. mypy and pytest execute with `uv run
--all-packages` so tools importing workspace code see the actual locked project dependencies. mypy's
ephemeral environment includes pytest because current contract modules legitimately use pytest
markers/types.

The GitHub Actions workflow is read-only (`contents: read`) and invokes the canonical command:

```bash
uv run python scripts/quality_gate.py
```

One non-blocking `StarletteDeprecationWarning` is currently emitted by FastAPI's TestClient regarding
`httpx`. It does not affect Phase 5 acceptance and should be handled as a separate dependency
maintenance item unless a later phase naturally resolves it.

## Phase 5 status

Implementation quality gates: **PASS**

Deterministic ranking acceptance targets: **PASS**

Authorization/architecture/security regressions: **PASS**

Phase 5 independent review/merge: **PENDING**
