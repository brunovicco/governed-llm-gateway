# Current State

Last updated: 2026-09-01

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
| Phase 7 — Structured Output and Tool Normalization | IMPLEMENTED — IN REVIEW |
| Phase 8+ | NOT STARTED |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api`
  boundaries;
- provider-neutral contracts/domain and provider-specific infrastructure isolated in adapters;
- Policy Model Router remains the PDP; the gateway remains the PEP plus operational selector;
- core invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- metadata-only evidence by default and fail-closed handling of untrusted configuration/external
  responses;
- provider-native feature support never grants model authorization by itself;
- business-tool execution remains outside the gateway.

## Completed through Phase 6

Phase 1 generalized Policy Model Router workload/model-group identifiers. Phase 2 established the
strict model registry and deterministic registry digest. Phase 3 added provider execution ports and
OpenAI Responses, OpenAI-compatible, Gemini `generateContent`, and Anthropic Messages adapters.
Phase 4 bound the gateway to Policy Model Router `POST /route` schema `1.0`, validated prompt-free
policy provenance, and built the authorized registry candidate set. Phase 5, merged through PR #4,
added deterministic eligibility/ranking, ADR-0006, ranking-policy provenance, and authenticated
`POST /v1/route/explain` without provider inference.

Phase 6, merged through PR #5 at merge commit
`8a5559edc1282494cb023e50f3898882fd0aa8e0`, added ADR-0007, per-deployment runtime health,
circuit-breaker state, bounded retry against the same deployment, bounded fallback through already
ranked authorized alternatives, deterministic backoff/jitter, replay-safety boundaries, and
metadata-only execution-attempt evidence.

Phase 5 static score inputs remain configuration evidence, not benchmark evidence.
`benchmark_snapshot_id` stays unset until later evaluation/evidence-driven ranking phases.

## Phase 7 implemented

Phase 7 adds provider-neutral structured-output and client-side business-tool normalization without
moving business-tool execution authority into the gateway.

Delivered:

- ADR-0013 defines structured-output/tool normalization and authority boundaries;
- `StructuredOutputSchema` is the canonical named JSON Schema request contract;
- `ToolDefinition`, `ToolCall`, and `ToolResult` are hardened provider-neutral contracts;
- `GatewayRequest` carries optional tool definitions and structured-output schema only when the
  corresponding workload capability is required;
- `GatewayResponse` and `ProviderResponse` can carry normalized structured output and tool calls;
- Phase 7 validates a bounded Draft 2020-12 subset with `jsonschema` inside `gateway-core`;
- schema evaluation is local: 64 KiB serialized limit, bounded schema depth, remote `$ref` and
  `$dynamicRef` rejected;
- `pattern`, `patternProperties`, and `format` are rejected in Phase 7 rather than evaluated or
  silently accepted without a bounded enforcement contract;
- provider output is parsed and validated locally even after provider-native schema enforcement;
- tool calls require a declared tool and schema-valid object arguments;
- provider correlation IDs are required for canonical `ToolCall`; missing IDs fail closed instead of
  being synthesized;
- `ProviderFeatureSupport` separates adapter/API-family translation from registry capability and PDP
  authorization;
- OpenAI Responses, Anthropic Messages, and Gemini `generateContent` translate native structured-output
  and tool-call features;
- generic OpenAI-compatible endpoints assume neither feature and require explicit opt-in;
- `invalid_structured_output` and `invalid_tool_call` are permanent failures and therefore produce zero
  automatic retry and zero automatic fallback;
- Phase 6 resilience forwards schema/tools unchanged to provider attempts;
- the gateway never executes business tools.

## Phase 7 deliberate boundaries

- structured output means provider-native schema enforcement; prompted JSON is not treated as the same
  capability;
- local validation remains mandatory after provider-native enforcement;
- the supported schema subset intentionally excludes regex keywords until bounded regex evaluation is
  explicitly designed and excludes `format` until local enforcement semantics are explicit;
- automatic repair of invalid structured output is not implemented;
- `ToolResult` represents a result owned by the application/agent/MCP runtime;
- provider-native continuation after a tool executes is not fabricated when exact provider-generated
  continuation/reasoning state is absent from the canonical request;
- Gemini calls that omit a correlation ID fail closed even though older API/model variants may treat
  the field as optional;
- streaming structured output/tool deltas remain Phase 8.

See `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` and ADR-0013.

## Phase 7 acceptance evidence

Contract and integration tests prove:

- native structured-output translation for the supported API families;
- invalid JSON and schema mismatch are rejected;
- unsafe external schema references fail before provider execution;
- unsafe/unbounded regex keywords and unenforced `format` semantics fail closed;
- a normal property named `pattern` is not confused with the JSON Schema keyword;
- tool schemas use the same bounded schema policy as structured output;
- tool calls are normalized only for declared tools and arguments are schema-validated;
- missing required provider correlation fails closed;
- OpenAI-compatible optional features stay disabled without explicit endpoint opt-in;
- schema/tool contracts survive the resilience boundary unchanged;
- structured-output/tool semantic failures do not retry or fall back;
- no gateway contract exposes a business-tool execution hook.

## Current validation

Read-only GitHub Actions run `33521577607` passed on hardened Phase 7 head
`79a79051fa2f631580cd39ca3ad88494d210e8b8`:

- 132 tests PASS;
- 82.62% total coverage (minimum 80%);
- Ruff lint/format PASS;
- mypy PASS across 58 source files;
- Bandit PASS with no identified issues;
- pip-audit PASS with no known vulnerabilities;
- architecture check PASS;
- secret scan PASS;
- Phase 0 regression gate PASS;
- GitHub Actions permissions: `contents: read`.

`types-jsonschema==4.26.0.20260518` is used only in the ephemeral mypy environment. It is not a runtime
dependency. `jsonschema==4.26.0` is the Phase 7 runtime validation dependency in `gateway-core`.

The known Starlette TestClient `httpx`/`httpx2` deprecation warning remains non-blocking and unrelated
to Phase 7 behavior.

## Explicitly deferred

- streaming, partial-output/tool-call deltas, cancellation, and streaming replay semantics (Phase 8);
- OpenTelemetry runtime via `a2a-otel-kit` (Phase 9);
- benchmark/evaluation framework (Phase 10);
- benchmark-derived ranking evidence (Phase 11);
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation requiring a new canonical transcript/state contract;
- widening the supported JSON Schema subset until safety/compatibility semantics are explicit.

## Next step

Complete the Phase 7 builder-side diff review, clean the branch history into one Phase 7 commit on top
of the Phase 6 merge, verify the complete read-only quality gate on that clean SHA, and open the Phase
7 pull request for independent architecture/security review. Phase 8 must not start before Phase 7 is
reviewed and merged.
