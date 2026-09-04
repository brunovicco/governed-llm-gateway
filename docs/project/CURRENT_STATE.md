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
| Phase 8 — Streaming | COMPLETE (`governed-llm-gateway` PR #7) |
| Phase 9 — OpenTelemetry | COMPLETE (`governed-llm-gateway` PR #8) |
| Phase 10 — Evaluation Framework | COMPLETE (`governed-llm-gateway` PR #9) |
| Phase 11 — Evidence-Driven Ranking | COMPLETE (`governed-llm-gateway` PR #10) |
| Phase 12 — Client SDK | CURRENT — VALIDATED / REVIEW READY |
| Phase 13+ | NOT STARTED |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api`
  boundaries;
- Policy Model Router remains the PDP; the gateway remains the PEP plus operational selector;
- permanent invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- provider-specific SDKs/credentials remain behind gateway adapters;
- metadata-only evidence remains the default;
- business-tool execution remains outside the gateway;
- no benchmark, telemetry, SDK, or client state becomes an authorization source.

## Completed through Phase 11

Phase 10 merged through PR #9 at squash commit
`db30ffc481d1a3c02fb01f46524b5190290fb7ac` after independent architecture/security review. It added
the offline benchmark framework and immutable evaluation evidence.

Phase 11 merged through PR #10 at squash commit
`5888376da798d55b9f4139e943514dca0e573dea` after review approval. It added explicit benchmark
promotion, content-addressed ranking evidence, benchmark-hybrid ranking, manual override, immutable
rollback artifacts, and Phase 11 routing provenance while preserving authorization monotonicity.

Final PR-head Phase 11 validation before merge:

- head `444a386183233dcded5c367b391f7db713b79360`;
- pull-request run `33814795729` — PASS;
- pytest — 252 passed;
- aggregate coverage — 81.28%;
- mypy — PASS across 97 source files;
- Ruff, Bandit, pip-audit, architecture, secret scan, and Phase 0 gate — PASS.

Post-merge `main` validation:

- merge commit `5888376da798d55b9f4139e943514dca0e573dea`;
- GitHub Actions run `33821014717` — PASS.

## Phase 12 — Client SDK

Active branch:

`feat/phase-12-client-sdk`

The branch starts from the Phase 11 squash merge commit
`5888376da798d55b9f4139e943514dca0e573dea`.

ADR-0010 — Client SDK Boundary — is accepted.

Normative acceptance remains:

- consumer needs no provider SDK;
- consumer needs no provider API key;
- consumer does not implement retry/fallback;
- consumer can inspect routing provenance.

The accepted SDK boundary is intentionally thin:

- dependencies limited to `gateway-contracts`, HTTPX, and the standard library;
- `GatewayClient.from_env()` reads only gateway URL/API-key configuration;
- HTTPS-only base URL, no URL userinfo/query/fragment, redirects disabled;
- gateway credential sent only through `X-Gateway-API-Key`;
- no client-side model selection, ranking, retry, fallback, circuit breaking, or policy decisions;
- `stream()` performs one `POST /v1/generate` request and yields validated `GatewayStreamEvent` values;
- bounded incremental SSE parsing with strict UTF-8/JSON/sequence/terminal validation;
- every SSE event is bound to the exact `request_id` sent by the client;
- `generate()` aggregates that same single stream into `GatewayResponse` without a second execution;
- risk level and data classification remain explicit caller inputs rather than unsafe implicit defaults;
- raw gateway error bodies and credentials are excluded from client exception text;
- Phase 11 provenance is reconstructed for inspection but never interpreted as authorization.

## Phase 12 validated slice

Implemented and full-gate validated on the branch:

1. accepted ADR-0010 and moved it out of the deferred ADR backlog;
2. added sanitized client error classes for configuration/request/transport/HTTP/protocol failures;
3. added bounded strict SSE/JSON decoding into provider-neutral immutable contracts;
4. implemented reusable async `GatewayClient`, `from_env()`, `stream()`, `generate()`, lifecycle, and
   credential-safe representation;
5. added contract tests for one-attempt transport behavior, gateway-only request payloads, HTTP-error
   sanitization, SSE bounds/sequence/terminal failures, request correlation, redirects, and Phase 11
   provenance;
6. closed the SSE compatibility gap by serializing `score_provenance_mode` and `manual_override_id`
   alongside `benchmark_snapshot_id`, preserving Phase 11 provenance for SDK consumers;
7. updated `gateway-client` to `0.2.0`, added direct HTTPX transport dependency, and refreshed the
   workspace lock;
8. made the client dependency boundary executable in both `architecture_check.py` and the engineering
   harness configuration: stdlib + `gateway-contracts` + HTTPX only, with no core/API/benchmark/PDP or
   provider-SDK imports;
9. bounded HTTP/SSE reads, disabled redirects, disabled environment-derived proxy/client settings, and
   fail closed when stream request identity or protocol sequencing is inconsistent;
10. removed all temporary Phase 12 bootstrap/hardening workflows from the final branch diff.

Final validated Phase 12 head before PR preparation:

- head `d83075713503227780a979f399bf6bf8b891e1b5`;
- GitHub Actions run `33829884632` — PASS;
- pytest — 271 passed, 1 known nonblocking Starlette/httpx TestClient deprecation warning;
- aggregate coverage — 80.93%;
- mypy — PASS across 101 source files;
- Ruff check/format — PASS across 101 files;
- Bandit — PASS, 0 issues across 10,348 lines of code;
- pip-audit — no known vulnerabilities;
- architecture check, secret scan, and Phase 0 gate — PASS.

## Next step

Open the Phase 12 pull request, verify pull-request CI, and perform independent architecture/security
review against ADR-0010 and the roadmap acceptance criteria. Phase 12 remains CURRENT until review is
approved and the PR is merged. Do not start Phase 13 before that merge.

## Explicitly deferred

- provider SDKs or provider API keys in consumers;
- client-side retry/fallback/circuit breaking/model selection;
- OpenAI compatibility surface in the client;
- unsafe defaulting of omitted data classification to `public`;
- automatic/adaptive routing self-modification;
- signed Verifiable AI Governance runtime authorization (Phase 13);
- provider-native tool-result continuation without canonical provider state;
- payload/prompt/completion capture as default telemetry.
