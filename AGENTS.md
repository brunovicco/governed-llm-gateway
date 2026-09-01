# governed-llm-gateway engineering contract

## Project

- Runtime: Python 3.13+
- Harness authority: `codex-python-engineering-harness`
- Harness profile: `workspace`
- Governance profile: `agentic`
- Root: virtual uv project (`package = false`)
- Primary builder: Codex
- Independent reviewer: Claude Code
- Current phase: Phase 5 — Deterministic Operational Ranking and Explainability
- Phase 1 dependency: completed in `policy-model-router` PR #20
- Phase 2: completed in `governed-llm-gateway` PR #1
- Phase 3: completed in `governed-llm-gateway` PR #2
- Phase 4: completed in `governed-llm-gateway` PR #3
- Phase 5: implemented on `feat/phase-5-deterministic-ranking`, pending independent review/merge

Read, in order:

1. `docs/project/PROJECT_INSTRUCTIONS.md`
2. `docs/project/CURRENT_STATE.md`
3. `docs/project/ARCHITECTURE.md`
4. `docs/project/ROADMAP.md`
5. relevant ADRs under `docs/adr/`, especially ADR-0006 for Phase 5
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
- `gateway-core/application`: provider-neutral execution/policy/ranking orchestration boundaries;
  no concrete provider or Policy Model Router HTTP implementation.
- `gateway-core/adapters`: provider/configuration/infrastructure implementations. Ranking-policy YAML
  parsing belongs here; ranking semantics remain in domain/application code.
- `gateway-client`: consumers receive a gateway credential only; no provider or PDP credentials.
- `gateway-api`: composition root. Phase 5 permits the authenticated, prompt-free
  `POST /v1/route/explain` surface here. FastAPI/Pydantic types must not leak inward.
- consumer repositories may depend on the gateway; the gateway must never depend on business
  projects such as OpsLens, RAGForge, Getnet, Controlled Autonomy Lab, or Multi-Agent Credit Desk.

## Trust and authorization boundary

Request fields such as `risk_level`, `data_classification`, `agent_identity`, limits, and environment
must not automatically become authoritative security facts. Authentication and policy establish the
effective context. Policy/identity failures fail closed.

The Phase 4 `AuthorizedCandidateSet` is the only candidate source for Phase 5. Ranking must never
re-enumerate the global registry to discover alternatives outside that set. Registry digest mismatch,
multiple authorized logical groups, or a candidate outside PDP authorization are ranking invariant
violations and fail closed.

The Policy Model Router receives only prompt-free `PolicyRequestMetadata`. `GatewayRequest.messages`
must never be sent to it. Conversely, PDP-only metadata must not be copied into provider requests.

Registry and ranking-policy YAML are untrusted configuration until strict safe parsing,
duplicate-key checks, closed-schema validation, semantic validation, and deterministic
canonicalization succeed.

## Phase 5 ranking rules

Phase 5 permits only deterministic static/versioned operational ranking:

- filter before score;
- only candidates already authorized by Phase 4 may be evaluated;
- deterministic `Decimal` arithmetic;
- workload-specific weights sum exactly to `1`;
- unknown pricing is not free;
- missing ranking input is not a neutral/default score;
- cost uses versioned registry pricing and the projected token estimates;
- expected latency is a versioned planning input, not live health;
- ties resolve by ascending `deployment_id`;
- selection provenance records PDP provenance, registry digest, ranking-policy version/digest,
  score snapshot ID, selected deployment, and rejection reasons;
- `benchmark_snapshot_id` remains unset because Phase 5 static score input is not empirical benchmark
  evidence.

The `POST /v1/route/explain` endpoint performs authentication-context resolution, PDP authorization,
eligibility, ranking, and explanation only. It performs no provider inference and rejects message or
prompt fields at its request boundary.

## Explicitly deferred

Do not pull forward:

- Phase 6 runtime health, retries, fallback, or circuit breakers;
- Phase 7 tool or structured-output normalization/execution behavior;
- Phase 8 streaming;
- Phase 9 OpenTelemetry runtime;
- Phase 10/11 benchmark-derived ranking evidence;
- Phase 13 signed Verifiable AI Governance runtime authorization.

`min_context_tokens` remains a capability requirement, not an input-token estimate. Policy Model
Router API 1.0 models required tool calling through the workload policy rule rather than a per-request
field; do not invent a wire field.

Do not change repository policy or architecture without an ADR.

Do not use `from __future__ import annotations`. Quote only individual forward references when needed.

## Privacy and evidence

Evidence is metadata-only by default. Never record prompts, completions, tool arguments/results,
provider API keys, PDP API keys, Authorization headers, arbitrary customer payloads, or raw malicious
provider/PDP error bodies in logs/traces/evidence.

## Quality gate

Run:

```bash
uv run python scripts/quality_gate.py
```

For the Architecture Gate regression specifically:

```bash
python scripts/phase0_gate.py
```

The Phase 0 regression gate is intentionally frozen to the five contract modules present at the
`phase-0-architecture-gate` tag. Future-phase contract tests belong to the repository-wide pytest
quality gate.

Phase 5 acceptance requires identical inputs to produce identical ranking, ineligible deployments to
be unable to win, deterministic tie resolution, the no-inference route-explain endpoint, preserved
PDP authorization boundaries, and the complete read-only repository quality gate to pass.
