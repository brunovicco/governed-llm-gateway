# Current State

Last updated: 2026-09-03

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
| Phase 8 — Streaming | IMPLEMENTED — PR #7 IN REVIEW |
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
policy provenance, and built the authorized registry candidate set. Phase 5 added deterministic
eligibility/ranking, ADR-0006, ranking-policy provenance, and authenticated `POST /v1/route/explain`
without provider inference.

Phase 6 added ADR-0007, per-deployment runtime health, circuit-breaker state, bounded retry against the
same deployment, bounded fallback through already-ranked authorized alternatives, deterministic
backoff/jitter, replay-safety boundaries, and metadata-only attempt evidence.

Phase 7, merged through PR #6 at merge commit
`6c53d5586b6c6f9fbafcfda642f2b9e7af0cbca0`, added ADR-0013, bounded Draft 2020-12 structured-output
validation, normalized tool definitions/calls/results, native OpenAI/Anthropic/Gemini translations,
explicit OpenAI-compatible opt-in, local post-provider validation, and permanent fail-closed semantic
errors. The gateway still never executes business tools or fabricates provider-native continuation
state.

Phase 5 static score inputs remain configuration evidence, not benchmark evidence.
`benchmark_snapshot_id` stays unset until later evaluation/evidence-driven ranking phases.

## Phase 8 — PR #7

PR #7 (`feat/phase-8-streaming`) implements provider-neutral streaming while preserving the Phase 4
authorization boundary and Phase 6 replay-safety rules.

Delivered:

- ADR-0011 defines streaming normalization, replay, cancellation, usage, and transport semantics;
- `Capability.STREAMING` participates in deterministic eligibility;
- canonical public stream events: `response.started`, `content.delta`, `tool_call.started`,
  `tool_call.arguments.delta`, `tool_call.completed`, `usage.completed`, `response.completed`, and
  `response.failed`;
- `ProviderStreamingPort` and provider-neutral internal streaming events;
- native streaming adapters for OpenAI Responses, Anthropic Messages, and Gemini
  `streamGenerateContent`;
- OpenAI-compatible streaming and final usage remain separate explicit opt-ins;
- bounded retry/fallback is allowed only before semantic output becomes visible;
- after content or tool-call output becomes visible, failure terminates with
  `response.failed(partial=true, retryable=false)` and cannot replay across providers;
- final normalized usage must be emitted exactly once before successful completion;
- cancellation/client disconnect closes the gateway generator and upstream provider stream;
- client cancellation is not recorded as a provider failure;
- authenticated `POST /v1/generate` completes trusted context, PDP authorization, runtime-health
  snapshot, and deterministic ranking before returning `text/event-stream`;
- invalid request/schema/tool contracts, policy denial, ranking failures/invariant violations, and no
  eligible authorized streaming deployment remain pre-stream HTTP failures;
- provider credentials, raw provider error bodies, prompt/completion payloads, tool arguments/results,
  and arbitrary response headers remain excluded from public/default evidence.

See `docs/project/STREAMING.md` and ADR-0011.

## Phase 8 review hardening

A builder-side architecture/security review of PR #7 found that the original 1 MiB SSE event bound was
applied after `httpx.aiter_lines()` produced a complete line. An unterminated provider line could
therefore accumulate inside HTTPX before the gateway checked the event-size limit, weakening the
memory-exhaustion control described by the threat model.

The issue was fixed in commit `a8b9fdcd6d69b94a2ab6ed942e67409df50d0092`:

- the transport no longer relies on `aiter_lines()` for framing;
- decoded response bytes are consumed in bounded 64 KiB chunks;
- SSE LF, CRLF, and CR line boundaries are parsed locally;
- the 1 MiB event bound is enforced incrementally, including an unterminated line;
- invalid UTF-8 fails closed as an invalid provider response;
- a regression test proves an oversized unterminated event is rejected before the source stream is
  exhausted;
- CRLF/CR framing has dedicated regression coverage.

This hardening changes only the transport implementation. It does not widen authorization, alter the
ranked candidate sequence, change replay semantics, or add Phase 9 telemetry behavior.

## Current validation

GitHub Actions run `33790152650` passed for code head
`a8b9fdcd6d69b94a2ab6ed942e67409df50d0092`.

Validated baseline:

- `uv lock --check` PASS;
- Ruff lint/format PASS;
- mypy PASS across 71 source files;
- 183 tests PASS;
- aggregate coverage 80.61% (minimum 80%);
- independent Coverage.py threshold PASS;
- Bandit PASS with no identified issues;
- pip-audit PASS with no known vulnerabilities;
- architecture validation PASS;
- secret scan PASS;
- frozen Phase 0 regression gate PASS;
- workflow permissions remain `contents: read` and `metadata: read`.

The known FastAPI/Starlette TestClient `httpx` → `httpx2` deprecation warning remains non-blocking and
unrelated to Phase 8 behavior.

## Explicitly deferred

- OpenTelemetry runtime via `a2a-otel-kit` (Phase 9);
- benchmark/evaluation framework (Phase 10);
- benchmark-derived ranking evidence (Phase 11);
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation requiring a canonical transcript/state contract;
- widening the supported JSON Schema subset until safety/compatibility semantics are explicit;
- shared/distributed circuit-breaker state beyond the Phase 6 per-process implementation;
- treating policy `max_latency_ms` as an implicit total cross-retry streaming deadline.

## Next step

Run the required independent Claude Code architecture/security review against the current PR #7 head,
with special focus on authorization monotonicity, replay boundaries, provider stream lifecycle,
structured-output/tool streaming validation, cancellation/resource ownership, SSE bounds/error
sanitization, and OpenAI-compatible opt-in behavior. Resolve any justified BLOCKER/HIGH/MEDIUM findings
and rerun the full quality gate before merge.

Phase 9 must not start until Phase 8 is independently reviewed and merged.
