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
| Phase 7 — Structured Output and Tool Normalization | COMPLETE (`governed-llm-gateway` PR #6) |
| Phase 8 — Streaming | IMPLEMENTED — IN REVIEW |
| Phase 9+ | NOT STARTED |

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

## Completed through Phase 7

Phase 1 generalized Policy Model Router workload/model-group identifiers. Phase 2 established the
strict model registry and deterministic registry digest. Phase 3 added provider execution ports and
OpenAI Responses, OpenAI-compatible, Gemini `generateContent`, and Anthropic Messages adapters.
Phase 4 bound the gateway to Policy Model Router `POST /route` schema `1.0`, validated prompt-free
policy provenance, and built the authorized registry candidate set. Phase 5, merged through PR #4,
added deterministic eligibility/ranking, ADR-0006, ranking-policy provenance, and authenticated
`POST /v1/route/explain` without provider inference.

Phase 6, merged through PR #5, added ADR-0007, per-deployment runtime health, circuit-breaker state,
bounded retry against the same deployment, bounded fallback through already-ranked authorized
alternatives, deterministic backoff/jitter, replay-safety boundaries, and metadata-only attempt
evidence.

Phase 7, merged through PR #6 at merge commit
`6c53d5586b6c6f9fbafcfda642f2b9e7af0cbca0`, added ADR-0013, bounded Draft 2020-12 structured-output
validation, normalized tool definitions/calls/results, native OpenAI/Anthropic/Gemini translations,
explicit OpenAI-compatible opt-in, local post-provider validation, and permanent fail-closed semantic
errors. The gateway still never executes business tools or fabricates provider-native continuation
state.

Phase 5 static score inputs remain configuration evidence, not benchmark evidence.
`benchmark_snapshot_id` stays unset until later evaluation/evidence-driven ranking phases.

## Phase 8 implemented

Phase 8 adds provider-neutral streaming while preserving the Phase 4 authorization boundary and the
Phase 6 replay-safety rules.

Delivered:

- ADR-0011 defines streaming normalization, replay, cancellation, usage, and transport semantics;
- `Capability.STREAMING` participates in deterministic eligibility;
- canonical public stream events:
  - `response.started`;
  - `content.delta`;
  - `tool_call.started`;
  - `tool_call.arguments.delta`;
  - `tool_call.completed`;
  - `usage.completed`;
  - `response.completed`;
  - `response.failed`;
- `ProviderStreamingPort` and provider-neutral internal streaming events;
- dedicated asynchronous `HttpxSseTransport`, separate from the bounded synchronous JSON transport;
- native streaming adapters for OpenAI Responses, Anthropic Messages, and Gemini
  `streamGenerateContent`;
- OpenAI-compatible streaming remains explicit opt-in, with final usage support as a separate opt-in;
- bounded retry/fallback remains possible only before semantic output is visible;
- once content or tool-call output becomes visible, failures terminate with
  `response.failed(partial=true, retryable=false)` and never replay across providers;
- final normalized usage must be emitted exactly once before successful completion;
- successful provider health is recorded before `response.completed` is exposed;
- cancellation/client disconnect closes the gateway execution generator and upstream provider stream;
- client cancellation is not recorded as a provider failure;
- SSE framing/transport validation includes HTTPS-only endpoints, no URL userinfo/fragments, positive
  timeout, 1 MiB per-event bound, timeout/network normalization, and safe response-header allowlisting;
- `POST /v1/generate` performs credential resolution, PDP authorization, runtime-health snapshot, and
  deterministic ranking before returning `text/event-stream`;
- invalid request/schema/tool contracts, policy denial, ranking failures/invariant violations, and no
  eligible authorized streaming deployment remain pre-stream HTTP failures;
- deterministic SSE JSON framing includes bounded routing/fallback provenance and no credentials/raw
  provider bodies;
- quality gate now performs an independent `coverage report --fail-under=80` after pytest-cov so a
  coverage regression cannot be masked by plugin exit-code behavior.

See `docs/project/STREAMING.md` and ADR-0011.

## Phase 8 acceptance evidence

Contract and integration tests prove:

- deterministic normalized successful stream lifecycle and sequence numbers;
- same-deployment/cross-deployment resilience only before semantic output;
- zero automatic replay after partial content;
- upstream provider generator closure on consumer cancellation;
- provider/API-family streaming capability checks fail closed;
- missing/invalid streaming candidates fail before provider invocation;
- OpenAI, Anthropic, Gemini, and explicitly opted-in OpenAI-compatible event translation;
- tool-call and structured-output streaming preserve Phase 7 local validation semantics;
- final usage/completion lifecycle validation;
- bounded SSE parsing, EOF dispatch, comment handling, safe headers, open/read timeout/network
  normalization, 1 MiB event limit, and idempotent close;
- `/v1/generate` starts SSE only after successful pre-stream governance/ranking;
- API authentication/policy/ranking/no-eligible failures retain ordinary HTTP semantics;
- direct SSE body closure propagates to the execution generator.

## Current validation

The latest complete pre-documentation quality run on the Phase 8 implementation passed lint, format,
mypy, functional tests, security/audit, architecture, secret scan, and Phase 0 regression checks. At
that checkpoint the suite had 175 passing tests. The API expansion temporarily reduced aggregate
coverage below 80%, which exposed inconsistent pytest-cov exit behavior; the branch now contains an
independent coverage CLI enforcement step plus additional API boundary tests. A final read-only quality
run will be recorded after documentation is complete and before squash/PR.

The known Starlette TestClient `httpx`/`httpx2` deprecation warning remains non-blocking and unrelated
to Phase 8 behavior.

## Explicitly deferred

- OpenTelemetry runtime via `a2a-otel-kit` (Phase 9);
- benchmark/evaluation framework (Phase 10);
- benchmark-derived ranking evidence (Phase 11);
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation requiring a new canonical transcript/state contract;
- widening the supported JSON Schema subset until safety/compatibility semantics are explicit;
- shared/distributed circuit-breaker state beyond the Phase 6 per-process implementation;
- treating policy `max_latency_ms` as an implicit total cross-retry streaming deadline.

## Next step

Complete the Phase 8 documentation/security reconciliation, run the full read-only quality gate with
the independent coverage enforcement, review the complete diff, squash the branch into one Phase 8
commit on top of the Phase 7 merge, validate that clean SHA, and open PR #7 for independent
architecture/security review. Phase 9 must not start before Phase 8 is reviewed and merged.
