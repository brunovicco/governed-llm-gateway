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
| Phase 13 — Governance Integration | CURRENT — FIRST ENFORCEMENT SLICE GREEN |
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

Local post-merge validation on macOS/Python 3.13.12 reproduced the same baseline exactly:

- 277 tests passed;
- aggregate coverage 80.98%;
- mypy/Ruff PASS across 102 files;
- Bandit 0 issues;
- pip-audit no known vulnerabilities;
- architecture check PASS;
- secret scan PASS;
- Phase 0 gate PASS.

The only known warning remains the nonblocking FastAPI/Starlette TestClient deprecation for the
current `httpx` integration in favor of `httpx2`.

The stale remote `tmp-ignore` branch was also deleted after the Phase 12 merge.

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

ADR-0012 now defines the Phase 13 boundary.

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

## Phase 13 first validated slice

Implemented:

1. `VerifiedGovernanceAuthorization` immutable domain projection for already-verified signed facts;
2. exact trusted runtime request binding for workload, risk, data classification, token estimates,
   structured-output requirement, latency ceiling and cost ceiling;
3. audience and authorization-window enforcement;
4. governance/PDP model-group intersection that can only narrow the Policy Router candidate set;
5. fail-closed behavior when governance and Policy Router have no executable intersection;
6. preservation of signed `workflow_id`/`task_id` for later evidence without inventing gateway values;
7. contract tests proving request mismatches and attempted authorization expansion fail closed.

First Phase 13 full gate:

- head `6e296fe45d22e8062f0634ecda33c9f8ff6d06ec`;
- GitHub Actions run `33877364977` — PASS;
- pytest — 290 passed;
- aggregate coverage — 81.05%;
- mypy — PASS across 104 source files;
- Ruff check/format — PASS across 104 files;
- Bandit — 0 issues across 10,571 lines of code;
- pip-audit — no known vulnerabilities;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 gate — PASS.

## Next Phase 13 slice

Implement the wire adapter for Verifiable AI Governance runtime authorization while keeping the domain
free of the external package:

1. strict v1 JSON envelope parsing;
2. canonical signing bytes compatible with the upstream contract;
3. Ed25519 verification against an explicit `kid`-key allowlist/resolver;
4. projection into `VerifiedGovernanceAuthorization`;
5. adversarial tests for unknown keys, algorithm substitution, malformed canonical fields, signature
   failure and schema drift;
6. then integrate governance evidence/event-sink semantics into the governed execution path.

Do not start Phase 14 before Phase 13 is reviewed, approved and merged.

## Explicitly deferred

- client-side provider credentials or provider SDKs;
- client-side retry/fallback/circuit breaking/model selection;
- automatic/adaptive routing self-modification;
- arbitrary key discovery from governance token contents;
- using governance evidence/telemetry as a new authorization source;
- provider-native tool-result continuation without canonical provider state;
- payload/prompt/completion capture as default telemetry/evidence;
- Phase 14 consumer migrations.
