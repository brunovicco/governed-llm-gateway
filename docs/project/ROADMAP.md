# Roadmap

The normative detailed roadmap is preserved verbatim at `SOURCE_ROADMAP.txt`.

Current execution sequence:

0. Architecture Gate — COMPLETE BASELINE.
1. Generalize `policy-model-router` contract/vocabulary — COMPLETE (`policy-model-router` PR #20).
2. Contracts and deterministic model registry/digest — COMPLETE (`governed-llm-gateway` PR #1).
3. Provider execution foundation and first adapters — COMPLETE (`governed-llm-gateway` PR #2).
4. Policy Model Router authorization — COMPLETE (`governed-llm-gateway` PR #3).
5. Deterministic operational ranking and explainability — COMPLETE (`governed-llm-gateway` PR #4).
6. Runtime health, bounded retry, safe fallback, circuit breaker — COMPLETE (`governed-llm-gateway` PR #5).
7. Structured output and tool normalization — COMPLETE (`governed-llm-gateway` PR #6).
8. Streaming — COMPLETE (`governed-llm-gateway` PR #7).
9. OpenTelemetry via `a2a-otel-kit` — COMPLETE (`governed-llm-gateway` PR #8).
10. Evaluation framework — COMPLETE (`governed-llm-gateway` PR #9, squash merge
    `db30ffc481d1a3c02fb01f46524b5190290fb7ac`).
11. Evidence-driven ranking — COMPLETE (`governed-llm-gateway` PR #10, squash merge
    `5888376da798d55b9f4139e943514dca0e573dea`).
12. Thin client SDK transport — CURRENT; ADR-0010 accepted, implementation validated and review ready.
13. Optional Verifiable AI Governance integration, including signed runtime authorization when used.
14. Incremental real-project integrations.

## Permanent authority sequence

Phase 4 establishes the authorized candidate set. Later ranking, health, retry/fallback, benchmark
promotion, SDK transport, and telemetry may only narrow or execute inside that authority boundary:

`Gateway allowed set ⊆ Policy Router authorized set`

No client, benchmark result, telemetry signal, provider result, or runtime observation may broaden the
PDP authorization set.

## Completed runtime foundations

Phase 6 owns replay safety: retry/fallback stays server-side and stops after observed semantic output,
external side effects, or opaque continuation state unless a later explicit continuation contract says
otherwise.

Phase 7 normalizes structured output and tool calls but never executes business tools. Phase 8 adds the
normalized SSE lifecycle and cancellation/partial-output semantics. Phase 9 adds metadata-only tracing
without creating a new authority source.

Phase 10 creates offline benchmark evidence. Phase 11 consumes only explicitly promoted immutable
evidence and preserves manual override/rollback as attributable operator configuration. Runtime never
auto-discovers the newest benchmark snapshot or self-modifies ranking policy.

Phase 11 completed after PR-head validation and review approval. Post-merge `main` commit
`5888376da798d55b9f4139e943514dca0e573dea` passed GitHub Actions run `33821014717`.

## Phase 12 — Thin Client SDK

Normative target experience:

```python
gateway = GatewayClient.from_env()
result = await gateway.generate(
    workload="rag.answer",
    messages=messages,
)
```

Initial implementation keeps security context explicit even though the conceptual target above omits
it: `risk_level` and `data_classification` are required caller inputs until a separately reviewed safe
defaulting contract exists.

Acceptance:

- consumer needs no provider SDK;
- consumer needs no provider API key;
- consumer does not implement retry/fallback;
- consumer can inspect routing provenance.

ADR-0010 defines the implementation boundary:

- `gateway-client` depends only on `gateway-contracts`, HTTPX, and stdlib;
- `GatewayClient.from_env()` uses gateway URL/API-key environment configuration only;
- HTTPS-only base URL; no userinfo/query/fragment; redirects disabled and environment-derived HTTP
  settings disabled;
- `stream()` performs one request to the governed `/v1/generate` SSE endpoint;
- bounded strict SSE parsing reconstructs `GatewayStreamEvent` and full `RoutingProvenance`;
- every received event must match the exact `request_id` emitted in that client request;
- `generate()` aggregates that same stream into `GatewayResponse` with no second execution;
- the SDK performs no retry, fallback, provider/model selection, circuit breaking, ranking, or policy
  decision;
- transport/HTTP/protocol failures are sanitized and never expose the gateway credential or raw error
  body;
- Phase 11 benchmark/override provenance remains inspection evidence only;
- the architecture gate restricts the client to stdlib, `gateway-contracts`, and HTTPX and rejects
  imports from runtime core/API/benchmark/PDP/provider-specific boundaries.

The Phase 12 implementation closes the SSE compatibility gap required by the acceptance criterion:
`score_provenance_mode` and `manual_override_id` are serialized alongside
`benchmark_snapshot_id`, so a consumer can reconstruct the same Phase 11 routing evidence visible in
the server domain contract.

Validated pre-review baseline:

- branch `feat/phase-12-client-sdk`;
- validated head `d83075713503227780a979f399bf6bf8b891e1b5`;
- GitHub Actions run `33829884632` — PASS;
- 271 tests passed;
- aggregate coverage 80.93%;
- mypy and Ruff passed across 101 source/files;
- Bandit reported 0 issues across 10,348 lines of code;
- pip-audit reported no known vulnerabilities;
- architecture check, secret scan, and Phase 0 gate passed.

Phase 12 remains CURRENT until pull-request CI and independent review are approved and the PR is
merged. Phase 13 must not begin before that merge.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
