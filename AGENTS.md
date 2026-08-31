# governed-llm-gateway engineering contract

## Project

- Runtime: Python 3.13+
- Harness authority: `codex-python-engineering-harness`
- Harness profile: `workspace`
- Governance profile: `agentic`
- Root: virtual uv project (`package = false`)
- Primary builder: Codex
- Independent reviewer: Claude Code
- Current phase: Phase 3 — Provider Execution Foundation
- Phase 1 dependency: completed in `policy-model-router` PR #20
- Phase 2: completed in `governed-llm-gateway` PR #1

Read, in order:

1. `docs/project/PROJECT_INSTRUCTIONS.md`
2. `docs/project/CURRENT_STATE.md`
3. `docs/project/ARCHITECTURE.md`
4. `docs/project/ROADMAP.md`
5. relevant ADRs under `docs/adr/`
6. the source roadmap at `docs/project/SOURCE_ROADMAP.txt` when a decision is unclear

## Non-negotiable invariant

The gateway is a Policy Enforcement Point and operational selector. It may restrict Policy Model
Router authorization but may never broaden it.

`Gateway allowed set ⊆ Policy Router authorized set`

Any code path that can select outside the PDP-authorized logical model group is a security defect.
Provider adapters have no authorization authority.

## Architecture boundaries

- `gateway-contracts`: provider-neutral immutable contracts only. No provider SDK, FastAPI,
  database, OpenTelemetry SDK, HTTP client, dynamic imports, or business-domain dependencies.
- `gateway-core/domain`: deterministic domain logic. No provider SDK, FastAPI, database, or
  OpenTelemetry SDK.
- `gateway-core/application`: provider-neutral execution/routing ports and orchestration boundaries;
  no concrete provider implementation.
- `gateway-core/adapters`: provider/configuration/infrastructure implementations. Phase 3 provider
  execution is permitted here only.
- `gateway-client`: consumers receive a gateway credential only; no provider credentials.
- `gateway-api`: composition root. Do not implement Phase 4+ authorization/routing endpoints early.
- consumer repositories may depend on the gateway; the gateway must never depend on business
  projects such as OpsLens, RAGForge, Getnet, Controlled Autonomy Lab, or Multi-Agent Credit Desk.

## Trust boundary

Request fields such as `risk_level`, `data_classification`, `agent_identity`, limits, and environment
must not automatically become authoritative security facts. Authentication and policy establish the
effective context. Policy/identity failures fail closed.

Registry YAML is untrusted configuration input until it passes strict parsing, duplicate-key checks,
closed-schema validation, semantic validation, and deterministic canonicalization.

Provider transport responses are untrusted external input. Non-2xx raw response bodies, credentials,
authorization headers, and arbitrary provider payloads must not escape into errors/evidence.

## Privacy and evidence

Evidence is metadata-only by default. Never record prompts, completions, tool arguments/results,
provider API keys, Authorization headers, arbitrary customer payloads, or raw malicious provider
error bodies in logs/traces/evidence.

## Provider rule

Provider API defines the adapter. Concrete model defines a registry entry. Do not create one adapter
per model family when a native or explicit OpenAI-compatible API adapter is sufficient.

OpenAI-compatible means API compatibility, not behavioral identity. Provider quirks must stay
explicit. Never fake an unsupported provider capability.

## Development rule

Phase 3 permits provider execution ports and API-family adapters for text generation, usage,
timeouts, and typed errors. Do not pull forward:

- PDP authorization integration;
- operational ranking;
- retries/fallback/circuit breakers;
- tool or structured-output normalization;
- streaming;
- OpenTelemetry runtime.

Do not change repository policy or architecture without an ADR.

Do not use `from __future__ import annotations`. Quote only individual forward references when needed.

## Quality gate

Run:

```bash
uv run python scripts/quality_gate.py
```

For the Architecture Gate regression specifically:

```bash
python scripts/phase0_gate.py
```

Phase 3 acceptance requires text-generation contract behavior for all four adapter families, usage
extraction, timeout/error normalization, no secret/raw-error leakage, adapter contract tests, and the
complete repository quality gate to pass.
