# governed-llm-gateway engineering contract

## Project

- Runtime: Python 3.13+
- Harness authority: `codex-python-engineering-harness`
- Harness profile: `workspace`
- Governance profile: `agentic`
- Root: virtual uv project (`package = false`)
- Primary builder: Codex
- Independent reviewer: Claude Code
- Current phase: Phase 8 — Streaming, implemented / in review
- Phase 1: complete in `policy-model-router` PR #20
- Phase 2: complete in `governed-llm-gateway` PR #1
- Phase 3: complete in PR #2
- Phase 4: complete in PR #3
- Phase 5: complete in PR #4
- Phase 6: complete in PR #5
- Phase 7: complete in PR #6

Read, in order:

1. `docs/project/PROJECT_INSTRUCTIONS.md`
2. `docs/project/CURRENT_STATE.md`
3. `docs/project/ARCHITECTURE.md`
4. `docs/project/ROADMAP.md`
5. ADR-0007, ADR-0011, and ADR-0013
6. `docs/project/FALLBACK_AND_RETRY.md`
7. `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`
8. `docs/project/STREAMING.md`
9. `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`
10. `docs/project/SOURCE_ROADMAP.txt` when a decision is unclear

## Non-negotiable invariant

The gateway is a Policy Enforcement Point and operational selector. It may restrict Policy Model
Router authorization but may never broaden it.

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Any path that selects/retries/falls back/streams outside the PDP-authorized logical model group is a
security defect. Provider adapters have no authorization authority.

## Architecture boundaries

- `gateway-contracts`: provider-neutral immutable contracts only; no provider SDK, FastAPI, HTTP
  transport, OpenTelemetry SDK, JSON Schema engine, or business-domain dependencies.
- `gateway-core/domain`: deterministic domain logic, provider-neutral runtime state, local schema
  validation; no FastAPI/provider SDK/OpenTelemetry SDK.
- `gateway-core/application`: provider-neutral authorization/ranking/resilience/streaming orchestration;
  no concrete provider/PDP HTTP implementation.
- `gateway-core/adapters`: provider/configuration/infrastructure and JSON/SSE transports.
- `gateway-client`: consumers receive gateway credentials only.
- `gateway-api`: FastAPI/Pydantic composition root; framework types must not leak inward.
- consumer repositories may depend on the gateway; the gateway never depends on business projects.

## Trust and authorization boundary

Caller risk/classification/identity/environment claims are not authoritative until authenticated
reconciliation creates `EffectivePolicyContext`.

Phase 4 creates `AuthorizedCandidateSet`. Phase 5 filters/ranks only inside it. Phase 6 consumes only
`selected + alternatives`. Phase 7 translates only selected deployment/API-family features. Phase 8
streams only from the same bounded execution sequence. No later layer may re-enumerate the global
registry or reacquire broader authorization after provider failure.

Messages, structured-output schemas, and tool definitions never enter the Policy Model Router request.
PDP-only metadata must not be copied into provider payloads.

## Phase 5 ranking rules retained

- filter before score;
- evaluate only Phase 4 authorized candidates;
- deterministic `Decimal` arithmetic and ascending `deployment_id` tie-break;
- unknown pricing/missing score fail closed;
- expected latency is static planning evidence, not live health;
- static score evidence is distinct from benchmark evidence.

## Phase 6 resilience rules retained

- retry = same concrete deployment;
- fallback = another already-ranked authorized deployment;
- only retryable rate-limit/timeout/unavailable/transport failures replay;
- permanent policy/auth/config/semantic failures do not retry/fallback;
- attempts/fallback/backoff/jitter/Retry-After influence are bounded;
- runtime health can only narrow candidates and is not static ranking evidence;
- missing active health evidence fails closed;
- replay stops after observed output, external side effect, or opaque provider state;
- provider timeout is per attempt, not an implicit total `max_latency_ms` budget.

## Phase 7 structured-output/tool rules retained

- structured output means provider-native schema enforcement plus local validation, not prompted JSON;
- schema/tool requests still require normal registry capability eligibility;
- validate bounded Draft 2020-12 locally; no remote `$ref`/`$dynamicRef`;
- validate provider structured output again after native enforcement;
- normalize declared tools only and validate arguments locally;
- canonical `ToolCall` requires real provider correlation; do not fabricate IDs/state;
- gateway never executes business tools;
- OpenAI-compatible optional features require explicit verified configuration;
- invalid structured output/tool calls are permanent and do not retry/fallback.

## Phase 8 streaming rules

- streaming requests require registry `Capability.STREAMING`;
- adapter/API family must separately prove `native_streaming` and `streaming_usage`;
- OpenAI-compatible streaming/final usage remain explicit opt-ins;
- `/v1/generate` finishes authentication, PDP authorization, health snapshot, deterministic ranking,
  and eligible candidate selection before returning SSE;
- provider-native start is not semantic output;
- first content/tool-call event crosses the replay boundary;
- before semantic output, normal bounded Phase 6 retry/fallback may apply;
- after semantic output, never retry/fallback; emit terminal partial failure;
- successful normalized stream emits final usage exactly once before completion;
- invalid lifecycle/EOF fails closed;
- record provider success before exposing `response.completed`;
- cancellation/disconnect closes execution + upstream provider stream and is not provider failure;
- SSE transport is HTTPS-only, bounded to 1 MiB/event, header-sanitized, and explicitly closeable;
- incremental structured output/tool calls retain Phase 7 local validation;
- streaming adds no tool-execution, authorization, telemetry, or benchmark authority.

## Explicitly deferred

Do not pull forward:

- Phase 9 OpenTelemetry runtime;
- Phase 10/11 benchmark-derived ranking evidence;
- Phase 12 client transport completion;
- Phase 13 signed Verifiable AI Governance runtime authorization;
- provider-native tool-result continuation requiring a canonical transcript/state contract;
- shared/distributed circuit state;
- implicit total streaming deadline derived from policy latency.

Do not change repository policy or architecture without an ADR.
Do not use `from __future__ import annotations`.

## Privacy and evidence

Evidence is metadata-only by default. Never record prompts, completions, structured payloads, tool
arguments/results, provider/PDP credentials, Authorization headers, arbitrary provider headers, or raw
provider/PDP error bodies in logs/traces/evidence.

## Quality gate

Run:

```bash
uv run python scripts/quality_gate.py
```

The normal GitHub Actions workflow must remain `contents: read`.

Coverage is enforced at >=80% twice: pytest-cov and an independent
`coverage report --fail-under=80`. Do not lower the threshold or exclude Phase 8 code to pass CI.

`scripts/phase0_gate.py` remains frozen to the five Phase 0 baseline contract modules. New phase tests
belong to the repository-wide pytest gate.

Phase 8 acceptance requires normalized provider streaming, final usage, pre-output-only replay,
partial-output terminal failure, cancellation/upstream closure, preserved PDP authorization, no tool
execution authority, and the complete read-only quality gate to pass.
