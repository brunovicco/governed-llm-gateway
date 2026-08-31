# Phase 0 through Phase 4 Validation Record

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

`scripts/phase0_gate.py` remains a regression gate. When Phase 3 activated provider adapters, its
obsolete repository-wide provider-import substring ban was retired. Durable Phase 0 provider-neutral
contracts/domain boundaries continue to be enforced by exact AST import checks in
`scripts/architecture_check.py`.

## Phase 2 completed

Phase 2 — Contracts and Model Registry was merged through `governed-llm-gateway` PR #1.

Its acceptance evidence remains covered by the current regression suite: strict registry schema,
duplicate-key rejection, safe YAML, capability/modality consistency, explicit unknown pricing, and
deterministic SHA-256 registry provenance.

## Phase 3 completed

Phase 3 — Provider Execution Foundation was merged through `governed-llm-gateway` PR #2 on
2026-08-31.

Its provider contract evidence remains covered by the current regression suite: native OpenAI,
Anthropic, Gemini and explicit OpenAI-compatible mapping; usage extraction; typed timeout/error
normalization; bounded `Retry-After`; no raw error/secret leakage; and no live provider credentials or
requests required by CI.

## Phase 4 implementation validation

Phase 4 — Policy Router integration was validated in the read-only GitHub Actions quality workflow on
2026-08-31 after the implementation and rejection-provenance hardening were complete.

Code-complete head: `22ac613f68e834757dd593557d8f5b93d35cb0ad`

GitHub Actions push run: `33416554085`.

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff formatting — PASS;
- mypy — PASS across 41 source files;
- pytest — PASS, 73 tests;
- total coverage — 83.38% (minimum 80%);
- Bandit — PASS, no identified issues and no skipped files;
- pip-audit — PASS, no known vulnerabilities;
- architecture validation — PASS;
- secret scanning — PASS;
- Phase 0 regression gate — PASS.

The workflow executed with `contents: read`.

## Phase 4 acceptance evidence

Contract tests verify:

- policy projection uses trusted `EffectivePolicyContext` identity/risk/classification rather than
  caller-spoofable security claims;
- `GatewayRequest.messages`/prompt content does not enter the Policy Model Router payload;
- the trusted client identity selects the PDP credential and maps to router `agent_name`;
- request latency/cost limits can narrow but not broaden gateway-owned projection defaults;
- successful Policy Model Router responses require exact schema, request-ID correlation, trusted
  environment, valid logical group, UTC decision time, and SHA-256 policy provenance;
- `422 no_viable_model_group` carries validated rejection provenance and is additionally bound to
  the original request ID, workload, and trusted environment;
- unknown/malformed 422 responses do not become authorization;
- 401/403 are non-retryable authorization/authentication failures;
- 429 and eligible unavailable/transport/timeout conditions are classified retryable but Phase 4
  does not retry them;
- non-200/non-422 PDP raw response bodies are not parsed into normalized errors;
- PDP API keys do not appear in normalized failure metadata;
- registry candidates are limited to deployments in the PDP-authorized logical group;
- a PDP rejection causes zero provider calls;
- an out-of-authorization or absent selected deployment causes zero provider calls;
- the final provider request contains execution data and message content but no PDP-only policy
  metadata;
- Policy Model Router and provider transports remain separate infrastructure boundaries.

CI uses fake transports. No live Policy Model Router or provider credential is required.

## Deliberate Phase 4 non-translations

- `GatewayRequest.requirements.min_context_tokens` is a model-capability requirement and is not used
  as `context_tokens_estimated`.
- Policy Model Router API 1.0 has no per-request tool-calling field; tool calling remains a workload
  policy rule upstream.
- Signed runtime governance authorization is deferred to the later optional Verifiable AI Governance
  integration; a router that requires it returns 403 and the gateway fails closed.

## Quality-gate execution model

Ruff, Bandit, and pip-audit remain isolated quality tools. mypy and pytest execute with `uv run
--all-packages` so tools importing workspace code see the actual locked project dependencies.

The GitHub Actions workflow is read-only (`contents: read`) and invokes the canonical command:

```bash
uv run python scripts/quality_gate.py
```

## Phase 4 status

Implementation quality gates: **PASS**

PDP/PEP contract acceptance targets: **PASS**

Architecture/security regressions: **PASS**

Phase 4 independent review/merge: **PENDING**
