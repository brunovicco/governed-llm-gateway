# governed-llm-gateway engineering contract

## Project

- Runtime: Python 3.13+
- Harness authority: `codex-python-engineering-harness`
- Harness profile: `workspace`
- Governance profile: `agentic`
- Root: virtual uv project (`package = false`)
- Primary builder: Codex
- Independent reviewer: Claude Code
- Current phase: Phase 4 — Policy Router integration
- Phase 1 dependency: completed in `policy-model-router` PR #20
- Phase 2: completed in `governed-llm-gateway` PR #1
- Phase 3: completed in `governed-llm-gateway` PR #2
- Phase 4: implemented on `feat/phase-4-pdp-authorization`, pending review/merge

Read, in order:

1. `docs/project/PROJECT_INSTRUCTIONS.md`
2. `docs/project/CURRENT_STATE.md`
3. `docs/project/ARCHITECTURE.md`
4. `docs/project/ROADMAP.md`
5. relevant ADRs under `docs/adr/`
6. `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` for the bound Phase 4 PDP/PEP contract
7. the source roadmap at `docs/project/SOURCE_ROADMAP.txt` when a decision is unclear

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
- `gateway-core/application`: provider-neutral execution/policy ports and orchestration boundaries;
  no concrete provider or Policy Model Router HTTP implementation.
- `gateway-core/adapters`: provider/configuration/infrastructure implementations. Phase 4 permits
  the Policy Model Router HTTP adapter here in addition to Phase 3 provider adapters.
- `gateway-client`: consumers receive a gateway credential only; no provider or PDP credentials.
- `gateway-api`: composition root. Do not pull Phase 5+ ranking/explainability endpoints forward.
- consumer repositories may depend on the gateway; the gateway must never depend on business
  projects such as OpsLens, RAGForge, Getnet, Controlled Autonomy Lab, or Multi-Agent Credit Desk.

## Trust boundary

Request fields such as `risk_level`, `data_classification`, `agent_identity`, limits, and environment
must not automatically become authoritative security facts. Authentication and policy establish the
effective context. Policy/identity failures fail closed.

Phase 4 projects only prompt-free `PolicyRequestMetadata` to the Policy Model Router. Trusted
`client_id`, workload, risk, classification, and environment come from `EffectivePolicyContext`.
Caller-supplied `agent_identity`, risk, or classification cannot override that context.

Policy Model Router responses are untrusted external input. Success and denial provenance must be
strictly validated and correlated to the original request/trusted environment before authorization is
accepted. Unknown schema, malformed provenance, timeouts, transport failures, denials, or
misconfiguration fail closed before provider execution.

Registry YAML is untrusted configuration input until it passes strict parsing, duplicate-key checks,
closed-schema validation, semantic validation, and deterministic canonicalization.

Provider transport responses are untrusted external input. Non-2xx raw response bodies, credentials,
authorization headers, and arbitrary provider payloads must not escape into errors/evidence.

## Privacy and evidence

Evidence is metadata-only by default. Never record prompts, completions, tool arguments/results,
provider API keys, PDP API keys, Authorization headers, arbitrary customer payloads, or raw malicious
provider/PDP error bodies in logs/traces/evidence.

The Policy Model Router receives policy metadata only. `GatewayRequest.messages` must never be sent to
it. Conversely, policy-only metadata must not be copied into provider request payloads.

## Provider rule

Provider API defines the adapter. Concrete model defines a registry entry. Do not create one adapter
per model family when a native or explicit OpenAI-compatible API adapter is sufficient.

OpenAI-compatible means API compatibility, not behavioral identity. Provider quirks must stay
explicit. Never fake an unsupported provider capability.

## Development rule

Phase 4 permits:

- deterministic Policy Model Router `POST /route` integration using wire schema `1.0`;
- trusted, prompt-free policy metadata projection;
- strict accepted/rejected decision and provenance validation;
- fail-closed PDP error normalization;
- registry intersection with the PDP-authorized logical model group;
- explicit proof that provider execution cannot occur after PDP denial or outside authorization;
- enforcement of an externally selected deployment only as a Phase 4 boundary test/use case.

Do not pull forward:

- Phase 5 operational ranking or route explainability;
- Phase 6 retries, fallback runtime, or circuit breakers;
- Phase 7 tool or structured-output normalization;
- Phase 8 streaming;
- Phase 9 OpenTelemetry runtime;
- Phase 13 signed Verifiable AI Governance runtime authorization.

`min_context_tokens` is a capability requirement, not an input-token estimate; do not silently map it
to the Policy Model Router's `context_tokens_estimated`. Policy Model Router API 1.0 also models
required tool calling through the workload policy rule rather than a per-request field; do not invent
a wire field.

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

Phase 4 acceptance requires prompt-free/trusted PDP projection, strict provenance binding,
PDP-authorized registry intersection, zero provider calls after denial or authorization-boundary
failure, no policy metadata leakage into provider calls, and the complete repository quality gate to
pass.
