# Phase 0, Phase 2, and Phase 3 Validation Record

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

## Phase 3 implementation validation

Phase 3 — Provider Execution Foundation was validated in the read-only GitHub Actions quality
workflow on 2026-08-31.

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff formatting — PASS;
- mypy — PASS across 36 source files;
- pytest — PASS, 52 tests;
- total coverage — 85.59% (minimum 80%);
- Bandit — PASS, no identified issues and no skipped files;
- pip-audit — PASS, no known vulnerabilities;
- architecture validation — PASS;
- secret scanning — PASS;
- Phase 0 regression gate — PASS.

GitHub Actions push run: `33410777455`.

## Phase 3 acceptance evidence

Contract tests verify:

- native OpenAI Responses text and usage extraction;
- OpenAI Responses system-instruction mapping and incomplete finish reason;
- explicit OpenAI-compatible chat-completions mapping;
- compatible-provider `max_tokens` / `max_completion_tokens` quirk configuration;
- native Gemini message/system mapping and token-usage extraction;
- native Anthropic system/message mapping, version header, text, and usage extraction;
- malformed successful provider responses fail as typed `INVALID_RESPONSE` errors;
- 401/403 authentication failures are non-retryable;
- 429 rate limits are retryable and expose only bounded numeric `Retry-After` metadata;
- 5xx failures are typed as retryable unavailable errors;
- transport timeouts and network errors are normalized;
- raw non-2xx provider response bodies are not parsed into normalized errors;
- arbitrary provider response headers are discarded except allowlisted `Retry-After` metadata;
- API keys and transport-internal error details do not appear in `ProviderError` messages;
- insecure HTTP endpoints are rejected by the stdlib transport;
- tool-result messages remain rejected because tool normalization is deferred to Phase 7.

All provider contract tests use an injected fake transport. CI does not require provider credentials
and makes no live inference calls.

## Quality-gate execution model

Ruff, Bandit, and pip-audit remain isolated quality tools. mypy and pytest execute with `uv run
--all-packages` so tools importing workspace code see the actual locked project dependencies.

The GitHub Actions workflow is read-only (`contents: read`) and invokes the canonical command:

```bash
uv run python scripts/quality_gate.py
```

## Phase 3 status

Implementation quality gates: **PASS**

Provider contract acceptance targets: **PASS**

Architecture/security regressions: **PASS**

Phase 3 independent review/merge: **PENDING**
