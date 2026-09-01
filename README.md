# Governed LLM Gateway

**English** | [Português (Brasil)](README.pt-BR.md)

Reusable provider-neutral LLM execution gateway for **governed model resolution and execution**.

Status: **Phase 8 — Streaming implemented; under review**.

The project separates authorization, deterministic operational selection, runtime resilience,
provider feature normalization, and streaming transport:

```text
Application / Agent
       │ workload + requirements + policy metadata
       │ messages + optional schema/tool definitions
       ▼
Policy Model Router (PDP)
       │ authorized logical model group + provenance
       ▼
Governed LLM Gateway (PEP + operational selection)
       │ authorized candidates
       ├─ eligibility + deterministic ranking
       ├─ runtime health / circuit breaker
       ├─ bounded retry / safe fallback
       ├─ structured output / tool-call normalization
       └─ normalized streaming / cancellation
       ▼
LLM Provider
       │ text / structured output / ToolCall / streaming events
       ▼
Application / Agent / MCP runtime
       └─ authorizes and executes business tools
```

Core invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may narrow authorization because of capability, environment/data policy, cost, latency,
health, circuit state, or other operational constraints. It must never broaden PDP authorization,
including during retry, fallback, provider translation, or streaming.

## Current implementation

Phases 0–4 established the workspace and architecture gates, strict model registry, provider execution
foundation, and deterministic Policy Model Router authorization boundary. Phase 5 added deterministic
eligibility/ranking and authenticated `POST /v1/route/explain`. Phase 6 added per-deployment runtime
health, circuit breaking, bounded retry, safe fallback, and replay-safety rules. Phase 7 added bounded
structured-output validation and provider-neutral tool-call normalization while keeping business-tool
execution outside the gateway.

Phase 8 adds normalized streaming:

- ADR-0011 defines streaming lifecycle, replay, cancellation, usage, and transport semantics;
- `Capability.STREAMING` participates in deterministic eligibility;
- provider adapters must separately prove `native_streaming` and final `streaming_usage` support;
- native streaming adapters exist for OpenAI Responses, Anthropic Messages, and Gemini
  `streamGenerateContent`;
- generic OpenAI-compatible streaming remains explicit opt-in rather than inferred compatibility;
- a dedicated asynchronous SSE-over-HTTPS transport provides bounded parsing and explicit upstream
  closure;
- `POST /v1/generate` authenticates, calls the PDP, snapshots runtime health, and ranks before the SSE
  response begins;
- retry/fallback is allowed only before semantic output becomes visible;
- after content/tool-call output becomes visible, a provider failure ends as
  `response.failed(partial=true, retryable=false)` and is never replayed across providers;
- normalized successful streams finalize usage exactly once before completion;
- client disconnect/cancellation closes the execution generator and upstream provider stream;
- structured-output and tool-call streaming preserve the Phase 7 local validation boundary;
- the gateway never executes business tools or fabricates missing provider continuation/correlation
  state.

## Canonical streaming events

`POST /v1/generate` emits only:

```text
response.started
content.delta
tool_call.started
tool_call.arguments.delta
tool_call.completed
usage.completed
response.completed
response.failed
```

Sequence numbers are positive and monotonic. `response.started` is public only when semantic model
output is about to become visible, so a provider-native start alone does not cross the retry/fallback
boundary.

Example SSE frame:

```text
event: content.delta
id: 2
data: {"delta":"hello","event_type":"content.delta","request_id":"...","sequence_number":2}

```

See `docs/project/STREAMING.md` and `docs/adr/ADR-0011-streaming-normalization.md`.

## Structured output and tools

Structured output is treated as a **native model/API capability**, not a prompt convention. The Phase
7 schema boundary uses a bounded Draft 2020-12 subset with a 64 KiB serialized limit, bounded depth,
no remote `$ref`/`$dynamicRef`, no caller-controlled regex keywords, and no silently unenforced
`format`. Provider output is locally revalidated after native enforcement.

Business-tool authority remains outside the gateway:

```text
Gateway → normalizes ToolCall
Application / Agent / MCP runtime → authorizes + executes tool → owns ToolResult
```

The gateway never converts model output into permission to perform an external action.

## Safe retry and fallback

Phase 6 resilience remains bounded to the Phase 5 ranked authorized sequence:

- retry targets the same concrete deployment;
- fallback can only move to an already-ranked authorized alternative;
- transient classes are rate limit, timeout, unavailable/5xx, and transport failure;
- permanent validation/authentication/authorization/configuration failures do not automatically
  fallback;
- open circuits and unhealthy deployments narrow eligibility;
- provider output, external side effects, or opaque continuation state stop automatic replay.

Phase 8 strengthens that boundary for streaming: once semantic stream output is visible, retry/fallback
is terminally disabled for that request.

## Deterministic route explanation

`POST /v1/route/explain` is metadata-only and performs no provider inference. It resolves trusted client
context, obtains the PDP decision, evaluates only authorized registry candidates, and returns selected
deployment, alternatives, rejection reasons, and provenance.

The endpoint intentionally does not accept `messages`.

## Streaming transport security

`HttpxSseTransport` is separate from the non-streaming JSON transport and enforces:

- absolute HTTPS endpoint;
- no URL userinfo or fragments;
- positive bounded timeout;
- maximum 1 MiB per SSE event;
- normalized open/read timeout and network failures;
- response-header allowlist limited to `content-type` and `retry-after`;
- explicit/idempotent upstream close.

Provider credentials, arbitrary provider response headers, and raw provider error bodies are not
surfaced in the normalized stream.

## Policy Router contract notes

`GatewayRequest.requirements.min_context_tokens` is a model-capability requirement, not an input-token
estimate, so it is not silently translated into Policy Model Router `context_tokens_estimated`.

Policy Model Router API 1.0 has no per-request `tool_calling_required` field. The gateway does not
invent one.

Deployments requiring signed governance runtime authorization fail closed until the later Verifiable AI
Governance integration.

## Repository layout

```text
apps/gateway-api/           HTTP composition root
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

Current Phase 8 validation baseline: **181 tests PASS, 80.40% total coverage, mypy across 71 source
files, Ruff/Bandit/pip-audit/architecture/secret/Phase 0 gates PASS**. CI is credential-free and the
normal workflow uses `contents: read`.

Coverage is enforced twice: pytest-cov uses `--cov-fail-under=80`, followed by an independent
`coverage report --fail-under=80` command.

The known Starlette TestClient `httpx`/`httpx2` deprecation warning remains non-blocking.

## Source of truth

Start with:

- `docs/project/CURRENT_STATE.md` — current checkpoint;
- `docs/project/STREAMING.md` and `docs/adr/ADR-0011-streaming-normalization.md` — Phase 8;
- `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` and ADR-0013 — Phase 7;
- `docs/project/FALLBACK_AND_RETRY.md` and ADR-0007 — Phase 6;
- ADR-0006 — deterministic Phase 5 ranking;
- `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` — Phase 4 authorization binding;
- `docs/project/SOURCE_ROADMAP.txt` — original project specification.
