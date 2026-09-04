# Roadmap

The normative detailed roadmap is preserved verbatim at `SOURCE_ROADMAP.txt`.

Current execution sequence:

0. Architecture Gate — COMPLETE BASELINE.
1. Generalize `policy-model-router` contract/vocabulary — COMPLETE (`policy-model-router` PR #20).
2. Contracts and deterministic model registry/digest — COMPLETE (`governed-llm-gateway` PR #1).
3. Provider execution foundation and first adapters — COMPLETE (`governed-llm-gateway` PR #2).
4. Policy Model Router authorization — COMPLETE (`governed-llm-gateway` PR #3).
5. Deterministic operational ranking and explainability — COMPLETE (`governed-llm-gateway` PR #4).
6. Runtime health, bounded retry, safe fallback, circuit breaker — COMPLETE (`governed-llm-gateway` PR #5).
7. Structured output and tool normalization — COMPLETE (`governed-llm-gateway` PR #6).
8. Streaming — COMPLETE (`governed-llm-gateway` PR #7).
9. OpenTelemetry via `a2a-otel-kit` — COMPLETE (`governed-llm-gateway` PR #8).
10. Evaluation framework — COMPLETE (`governed-llm-gateway` PR #9, squash merge
    `db30ffc481d1a3c02fb01f46524b5190290fb7ac`).
11. Evidence-driven ranking — COMPLETE (`governed-llm-gateway` PR #10, squash merge
    `5888376da798d55b9f4139e943514dca0e573dea`).
12. Thin client SDK transport — COMPLETE (`governed-llm-gateway` PR #11, squash merge
    `1b9b3ef01f0efac49d1f2a92056473ec4b45c375`).
13. Optional Verifiable AI Governance integration — CURRENT; signed authorization verification,
    monotonic enforcement, runtime evidence and governed execution boundary are full-gate green.
14. Incremental real-project integrations — NOT STARTED.

## Permanent authority sequence

The portfolio authority chain is:

`Verifiable AI Governance → Policy Model Router → Governed LLM Gateway → model provider`

Phase 4 establishes the Policy Router-authorized candidate set. Later governance intersection,
ranking, health, retry/fallback, benchmark promotion, SDK transport and telemetry may only narrow or
execute inside that authority boundary:

`Gateway allowed set ⊆ Policy Router authorized set`

Governance authorization may narrow the set further but may not expand the Policy Router result.
No client, benchmark result, telemetry signal, provider result, runtime observation or evidence record
may broaden the authorization set.

## Completed runtime foundations

Phase 6 owns replay safety: retry/fallback stays server-side and stops after observed semantic output,
external side effects, or opaque continuation state unless a later explicit continuation contract says
otherwise.

Phase 7 normalizes structured output and tool calls but never executes business tools. Phase 8 adds the
normalized SSE lifecycle and cancellation/partial-output semantics. Phase 9 adds metadata-only tracing
without creating a new authority source.

Phase 10 creates offline benchmark evidence. Phase 11 consumes only explicitly promoted immutable
evidence and preserves manual override/rollback as attributable operator configuration. Runtime never
auto-discovers the newest benchmark snapshot or self-modifies ranking policy.

Phase 12 adds the thin provider-neutral SDK. Consumers need only gateway URL/credential and do not own
provider SDKs, provider keys, ranking, retry or fallback. The SDK preserves routing provenance and
strictly bounds/validates its SSE transport.

## Phase 12 completion

PR #11 was reviewed and squash-merged at:

`1b9b3ef01f0efac49d1f2a92056473ec4b45c375`

Final validated baseline reproduced in CI and locally on macOS/Python 3.13.12:

- 277 tests passed;
- aggregate coverage 80.98%;
- mypy/Ruff PASS across 102 files;
- Bandit 0 issues;
- pip-audit no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate PASS.

## Phase 13 — Governance Integration

Normative source scope:

- authorization context;
- scope validation;
- governance event sink;
- runtime evidence.

Acceptance:

- gateway enforces authorized model group;
- unauthorized expansion fails closed;
- denial produces evidence;
- execution evidence correlates to authorization.

ADR-0012 defines the Phase 13 boundary:

- integrate with the existing Verifiable AI Governance `SignedRuntimeAuthorization` v1.0 semantics;
- keep the gateway as PEP/operational selector, not a second governance system or PDP;
- signature verification remains behind an adapter/port boundary with explicit trusted keys;
- no arbitrary key discovery from token-controlled URLs;
- governance authorization is audience-, time-, request- and scope-bound;
- governance/PDP authorization is intersected before registry eligibility/ranking/health;
- ranking, retry, fallback and manual ranking override cannot resurrect governance-excluded groups;
- denials and executions emit minimized correlated runtime evidence;
- evidence is not a same-request authorization source;
- prompts/completions/raw provider payloads remain excluded from default evidence.

Validated Phase 13 implementation now includes:

- strict v1 JSON envelope parsing with duplicate-key and schema-drift rejection;
- canonical signing bytes and Ed25519 verification against an explicit `kid` allowlist;
- `cryptography==50.0.0`, remediating the vulnerable 46.0.3 bootstrap without audit waiver;
- immutable verified-governance facts and exact runtime request binding;
- audience/time/scope enforcement with stable denial reason codes;
- governance/Policy Router model-group intersection that only narrows authorization;
- final selected-model-group revalidation immediately before provider execution;
- metadata-only denial and execution evidence correlated across governance authorization, Policy Router
  decision, gateway routing decision, and actual provider/deployment;
- local-first evidence journal with explicit `BEST_EFFORT` and `REQUIRED` remote-delivery modes;
- governed execution wrapper around the existing resilience service, without duplicating retry/fallback;
- real-provider attempt counting that excludes circuit-open skips;
- tests proving governance denial blocks provider execution, fallback evidence names the actual final
  deployment, and circuit-only paths do not fabricate provider-execution evidence.

Latest validated Phase 13 baseline:

- branch `feat/phase-13-governance-integration`;
- head `244eb7f6fdd46a8dc7375d4c76eee98d01c8868c`;
- GitHub Actions run `33881234729` — PASS;
- 317 tests passed;
- aggregate coverage 81.10%;
- `governance_execution.py` coverage 88.57%;
- mypy/Ruff PASS across 110 files;
- Bandit 0 issues across 11,525 lines of code;
- pip-audit reports no known vulnerabilities;
- architecture check, secret scan and Phase 0 gate PASS.

Next boundary: synchronize review documentation, open the Phase 13 PR, then obtain independent
architecture/security review. Phase 14 remains blocked until Phase 13 review approval and merge.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
