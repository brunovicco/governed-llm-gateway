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
| Phase 13 — Governance Integration | CURRENT — IMPLEMENTATION GREEN, REVIEW PREPARATION |
| Phase 14 | NOT STARTED |

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

## Phase 12 — completed

PR #11 was independently reviewed and squash-merged into `main` at:

`1b9b3ef01f0efac49d1f2a92056473ec4b45c375`

Final PR validation before merge:

- 277 tests passed;
- aggregate coverage 80.98%;
- mypy/Ruff passed across 102 files;
- Bandit reported 0 issues across 10,418 lines of code;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate passed.

Local post-merge validation on macOS/Python 3.13.12 reproduced the same baseline exactly.
The stale remote `tmp-ignore` branch was deleted after the Phase 12 merge.

The only known warning remains the nonblocking FastAPI/Starlette TestClient deprecation for the
current `httpx` integration in favor of `httpx2`.

## Phase 13 — Governance Integration

Active branch:

`feat/phase-13-governance-integration`

The branch starts from the Phase 12 squash merge commit:

`1b9b3ef01f0efac49d1f2a92056473ec4b45c375`

Normative roadmap scope:

- authorization context;
- scope validation;
- governance event sink;
- runtime evidence.

Acceptance:

- gateway enforces authorized model group;
- unauthorized expansion fails closed;
- denial produces evidence;
- execution evidence correlates to authorization.

## ADR-0012 — accepted

The authority chain is:

`Verifiable AI Governance → Policy Model Router → Governed LLM Gateway → model provider`

Phase 13 consumes the existing Verifiable AI Governance `SignedRuntimeAuthorization` v1.0 semantics
rather than inventing a parallel token. The external contract is Ed25519-signed, short-lived (maximum
600 seconds), audience-bound, request-bound and scope-bound, and carries governance policy/control
provenance.

Important decisions:

- governance integration remains optional at deployment/configuration level;
- when required, missing/invalid/expired/wrong-audience/request-mismatched authorization fails closed;
- signature verification stays behind an adapter/port boundary with explicitly configured trusted keys;
- no token-controlled key discovery is allowed;
- governance may only narrow Policy Router authorization;
- ranking/health/retry/fallback operate only after governance/PDP intersection;
- governance evidence is not a same-request authorization source;
- prompts/completions/raw provider payloads are excluded from default evidence.

## Phase 13 implementation state

Implemented and validated:

1. immutable `VerifiedGovernanceAuthorization` domain projection;
2. exact trusted runtime binding for workload, risk, data classification, token estimates,
   structured-output requirement, latency ceiling and cost ceiling;
3. stable fail-closed denial reason codes;
4. audience and authorization-window enforcement;
5. governance/PDP model-group intersection that only narrows Policy Router authorization;
6. final selected-model-group revalidation immediately before provider execution;
7. strict VAIG v1 JSON envelope parsing with duplicate-key and exact-schema validation;
8. canonical Ed25519 signing-byte reconstruction and verification against explicit trusted `kid` keys;
9. no network or token-controlled signing-key discovery;
10. metadata-only governance evidence correlated to authorization, PDP decision, routing decision and
    actual provider/deployment;
11. local-first evidence journal plus explicit `BEST_EFFORT` and `REQUIRED` remote-delivery modes;
12. `GovernanceExecutionService` wrapper around existing bounded resilience execution;
13. provider-attempt accounting that excludes circuit-open skips;
14. adversarial signature and runtime tests covering unknown keys, algorithm substitution, tampering,
    request mismatch, authorization expansion, fallback evidence and no-provider-attempt paths.

The temporary crypto bootstrap exposed known advisories in `cryptography==46.0.3`. The dependency was
remediated to `cryptography==50.0.0`, the lock regenerated, and the final gate reports no known
vulnerabilities. No audit waiver was introduced.

Latest validated implementation baseline:

- head `244eb7f6fdd46a8dc7375d4c76eee98d01c8868c`;
- GitHub Actions run `33881234729` — PASS;
- pytest — 317 passed;
- aggregate coverage — 81.10%;
- `governance_execution.py` — 88.57% coverage;
- mypy — PASS across 110 source files;
- Ruff check/format — PASS across 110 files;
- Bandit — 0 issues across 11,525 lines of code;
- pip-audit — no known vulnerabilities;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 gate — PASS.

## Phase 13 review boundary

Implementation validation: **PASS**

Authorization monotonicity and scope enforcement: **PASS**

Signed authorization verification: **PASS**

Denial/execution evidence correlation: **PASS**

Governed provider-execution boundary: **PASS**

Documentation synchronization: **IN PROGRESS**

Independent architecture/security review: **PENDING**

Phase 13 merge: **PENDING**

Phase 14 remains blocked until Phase 13 documentation is synchronized, PR-head CI is green,
independent architecture/security review returns `APPROVE` with no justified BLOCKER/HIGH/MEDIUM
findings, and the Phase 13 PR is merged.

## Explicitly deferred

- client-side provider credentials or provider SDKs;
- client-side retry/fallback/circuit breaking/model selection;
- automatic/adaptive routing self-modification;
- arbitrary key discovery from governance token contents;
- using governance evidence/telemetry as a new authorization source;
- provider-native tool-result continuation without canonical provider state;
- payload/prompt/completion capture as default telemetry/evidence;
- Phase 14 consumer migrations.
