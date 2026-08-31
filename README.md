# Governed LLM Gateway

Reusable provider-neutral LLM execution gateway whose responsibility is **governed model resolution
and execution**.

Status: **Phase 3 — Provider Execution Foundation implemented; under review**.

The project separates authorization from operational selection:

```text
Application / Agent
       │ workload + requirements + policy metadata
       ▼
Policy Model Router (PDP)
       │ authorized logical model group + provenance
       ▼
Governed LLM Gateway (PEP + operational selection)
       │ concrete eligible deployment
       ▼
LLM Provider
```

Core invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may make authorization narrower due to capability, health, environment, cost, latency,
or other operational constraints. It must never make authorization broader.

## Current implementation

Phase 0 established the uv workspace, architecture/security boundaries, provider-neutral contract
baseline, ADR-0001 through ADR-0005, and fail-closed authorization invariant.

Phase 1 was completed in `policy-model-router`, generalizing workload and logical model-group
identifiers while preserving deterministic policy decisions and provenance.

Phase 2 completed the strict model registry with safe YAML parsing, closed-schema/semantic validation,
versioned pricing metadata, and deterministic SHA-256 registry provenance.

Phase 3 adds the first provider execution foundation:

- provider-neutral `ProviderPort`, request/response/usage/error types;
- native OpenAI Responses adapter;
- native Anthropic Messages adapter;
- native Google Gemini `generateContent` adapter;
- explicitly configured OpenAI-compatible chat-completions adapter;
- bounded stdlib HTTPS/JSON transport with injectable test transport;
- text generation and token-usage normalization;
- explicit request timeouts and typed retryability/error classification;
- no raw non-2xx provider body, API key, or authorization header in normalized errors;
- contract tests for native payload mapping, usage, malformed responses, 401/429/5xx, timeout,
  transport failure, and secret-leakage boundaries.

Provider adapters execute a concrete model only. They do not authorize workloads, select providers,
perform retries/fallback, execute tools, or broaden policy decisions.

## Gemini API note

Google recommends its Interactions API for new projects as of June 2026, while `generateContent`
remains fully supported. The initial Gemini adapter deliberately uses `generateContent` because the
current provider-neutral request carries canonical conversation messages but not the exact
model-generated Interaction steps required for lossless stateless Interactions history. The gateway
will not fabricate provider reasoning/state merely to translate between APIs.

## Repository layout

```text
apps/gateway-api/          future HTTP composition root
packages/gateway-contracts provider-neutral contracts
packages/gateway-core/     domain/application/adapters boundary
packages/gateway-client/   thin consumer SDK boundary
config/                    model/ranking/provider configuration
benchmarks/                future benchmark framework
examples/                  future consumers/examples
tests/                     contract/integration/e2e suites
docs/                      durable project sources and ADRs
```

## Validate

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

The quality gate includes Ruff, mypy, pytest/coverage, Bandit, pip-audit, architecture validation,
secret scanning, and the Phase 0 architecture regression gate.

Current Phase 3 branch validation: 51 tests, 85.58% total coverage, all quality/security gates PASS.
No live provider credential is required by CI.

## Source of truth

Start with `docs/project/CURRENT_STATE.md` for continuation and
`docs/project/SOURCE_ROADMAP.txt` for the original project specification.
