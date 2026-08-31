# governed-llm-gateway engineering contract

## Project

- Runtime: Python 3.13+
- Harness authority: `codex-python-engineering-harness`
- Harness profile: `workspace`
- Governance profile: `agentic`
- Root: virtual uv project (`package = false`)
- Primary builder: Codex
- Independent reviewer: Claude Code
- Current phase: Phase 0 — Architecture Gate

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

## Architecture boundaries

- `gateway-contracts`: provider-neutral immutable contracts only. No provider SDK, FastAPI,
  database, OpenTelemetry SDK, HTTP client, dynamic imports, or business-domain dependencies.
- `gateway-core/domain`: deterministic domain logic. No provider SDK, FastAPI, database, or
  OpenTelemetry SDK.
- `gateway-core/adapters`: concrete provider/infrastructure integrations begin in later phases.
- `gateway-client`: consumers receive a gateway credential only; no provider credentials.
- `gateway-api`: composition root. No provider API call exists in Phase 0.
- consumer repositories may depend on the gateway; the gateway must never depend on business
  projects such as OpsLens, RAGForge, Getnet, Controlled Autonomy Lab, or Multi-Agent Credit Desk.

## Trust boundary

Request fields such as `risk_level`, `data_classification`, `agent_identity`, limits, and environment
must not automatically become authoritative security facts. Authentication and policy establish the
effective context. Policy/identity failures fail closed.

## Privacy and evidence

Evidence is metadata-only by default. Never record prompts, completions, tool arguments/results,
provider API keys, Authorization headers, arbitrary customer payloads, or raw malicious provider
error bodies in logs/traces/evidence.

## Provider rule

Provider API defines the adapter. Concrete model defines a registry entry. Do not create one adapter
per model family when a native or explicit OpenAI-compatible API adapter is sufficient.

## Development rule

Phase 0 permits no provider API calls. Do not add OpenAI, Anthropic, Google, Groq, NVIDIA,
OpenRouter, or other inference SDK/runtime dependency before the relevant ADR/phase is active.
Do not change repository policy or architecture without an ADR.

Do not use `from __future__ import annotations`. Quote only individual forward references when needed.

## Quality gate

Run:

```bash
uv run python scripts/quality_gate.py
```

For the Architecture Gate specifically:

```bash
python scripts/phase0_gate.py
```

The phase is complete only when architecture boundaries, required documents, ADRs 0001–0005,
contract tests, and source provenance pass.
