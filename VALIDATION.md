# Phase 0 through Phase 9 Validation Record

Date: 2026-09-03

## Toolchain

- Python project runtime: 3.13+
- project pin: Python 3.13.12
- quality-tool execution pinned to Python 3.13
- uv workspace with locked dependencies

## Historical architecture baseline

`scripts/phase0_gate.py` remains frozen to the five contract modules that existed at the
`phase-0-architecture-gate` tag. Current/future phase tests are exercised by the complete pytest gate.
Package boundaries remain enforced separately by `scripts/architecture_check.py`.

## Completed phases

- Phase 2 — Contracts and Model Registry: PR #1.
- Phase 3 — Provider Execution Foundation: PR #2.
- Phase 4 — Policy Router Integration: PR #3.
- Phase 5 — Deterministic Operational Ranking and Explainability: PR #4.
- Phase 6 — Runtime Health, Retry and Safe Fallback: PR #5.
- Phase 7 — Structured Output and Tool Normalization: PR #6, merge commit
  `6c53d5586b6c6f9fbafcfda642f2b9e7af0cbca0`.
- Phase 8 — Streaming: PR #7, merge commit
  `ed429a6554fb987cd4ab991d330b2005d8cfd0d7`.

## Phase 8 implementation validation

Phase 8 code-validation head:

`a8b9fdcd6d69b94a2ab6ed942e67409df50d0092`

GitHub Actions run:

`33790152650`

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff formatting — PASS;
- mypy — PASS across 71 source files;
- pytest — PASS, 183 tests;
- total coverage — 80.61% (minimum 80%);
- independent `coverage report --fail-under=80` — PASS;
- Bandit — PASS, no identified issues;
- pip-audit — PASS, no known vulnerabilities;
- architecture validation — PASS;
- secret scanning — PASS;
- Phase 0 regression gate — PASS;
- normal GitHub Actions token permissions — `contents: read` and `metadata: read`.

The run was credential-free and performed no live provider/PDP calls.

## Phase 8 SSE memory-bound review hardening

A builder-side architecture/security review found that the first Phase 8 implementation checked the
1 MiB SSE event limit after `httpx.aiter_lines()` had already produced a complete line. An unterminated
provider line could therefore grow inside HTTPX before the gateway enforced its own event bound.

Commit `a8b9fdcd6d69b94a2ab6ed942e67409df50d0092` replaced that framing path with incremental bounded
parsing:

- response bytes are consumed through `aiter_bytes(chunk_size=64 * 1024)`;
- LF, CRLF, and CR SSE boundaries are parsed by the gateway transport;
- complete lines count toward the same 1 MiB event budget;
- incomplete/unterminated lines are checked incrementally before another provider chunk is accepted;
- invalid UTF-8 fails closed as `invalid_response` transport evidence;
- upstream response/client closure semantics remain idempotent and cancellation-safe.

The hardening was transport-local and did not change PDP authorization, operational ranking, runtime
health, retry/fallback candidate authority, tool execution authority, or telemetry scope.

## Phase 9 implementation validation

Phase 9 — OpenTelemetry is implemented on `feat/phase-9-opentelemetry`.

Final Phase 9 source head after builder-side lifecycle hardening and its regression assertion:

`5177f6b71c6ba2b3c5e17762d9cec0b39a3013b3`

The normal read-only quality gate revalidated that source at documentation checkpoint
`810b9016c3db070093ea8fd8df3610859fef8822` in GitHub Actions run:

`33803564689`

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff formatting — PASS, 75 files formatted;
- mypy — PASS across 75 source files;
- pytest — PASS, **192 tests**;
- total coverage — **80.07%**, above the 80% minimum without relying on display rounding;
- independent `coverage report --fail-under=80` — PASS;
- Bandit — PASS, 7,901 lines scanned, no identified issues;
- pip-audit — PASS, no known vulnerabilities;
- architecture validation — PASS;
- secret scanning — PASS;
- Phase 0 regression gate — PASS;
- normal GitHub Actions token permissions remain read-only: `contents: read` and `metadata: read`.

The only test warning remains the known FastAPI/Starlette TestClient deprecation notice recommending
`httpx2`; it is non-blocking and separate maintenance work.

The validation run was credential-free and performed no live provider/PDP calls.

## Phase 9 acceptance evidence

Phase 9 now provides the roadmap observability boundary through `a2a-otel-kit==0.6.0`:

- `llm.gateway.request`, `llm.gateway.stream`, `policy.route`, and per-attempt
  `provider.inference` spans;
- W3C `traceparent` / `tracestate` continuation and propagation through shared JSON/SSE transports;
- metadata-only `llm.gateway.retry` and `llm.gateway.fallback` span events;
- provider/deployment, routing-policy provenance, latency, TTFT, normalized usage counts,
  retry/fallback counts, HTTP status, stable error category, and partial/cancellation outcomes;
- `record_exception=False` at gateway/PDP/provider boundaries so remote exception text is not copied
  automatically into exported spans;
- deny-by-default exclusion of prompts, completions, tool arguments/results, structured payloads,
  credentials, arbitrary headers, provider bodies, and raw remote error messages;
- telemetry remains optional and cannot become a routing, ranking, health, retry, fallback, or
  authorization authority;
- `gateway-contracts` and `gateway-core/domain` remain free of both `a2a_otel_kit` and direct
  OpenTelemetry imports.

Contract tests with an in-memory OpenTelemetry exporter verify trace continuity, request/stream parent
relationships, provider retry/fallback correlation, policy/provider transport propagation, successful
and failed streaming lifecycle, pre-stream HTTP failure evidence, unexpected stream failure evidence,
provider-span closure before retry backoff, and absence of payload/error sentinels from exported
telemetry.

## Phase 9 validation findings resolved

### Backward-compatible streaming helper

Initial Phase 9 integration made the new `_sse_body()` telemetry parameters mandatory. Existing Phase 8
contract tests call that helper directly, so mypy correctly identified a compatibility regression.
Both `observability` and `trace_carrier` were restored to optional `None` defaults without changing
tracing semantics.

### Privacy-safe usage metric keys

The gateway initially proposed telemetry keys `llm.input_tokens` and `llm.output_tokens`. The shared
`a2a-otel-kit` sanitizer intentionally rejects sensitive-looking key names containing `token` even when
a caller explicitly allowlists them. Therefore those attributes could never be exported without
weakening the shared privacy boundary.

The gateway preserved the sanitizer and renamed exported usage attributes to:

```text
llm.usage.input_count
llm.usage.output_count
```

The values remain normalized provider input/output token counts. ADR-0008 records this compatibility
constraint so future changes do not bypass the deny-by-default sanitizer.

### Coverage threshold made unambiguous

One intermediate run reported 79.82% actual coverage while the standalone coverage command accepted
the displayed rounded 80%. The threshold was not lowered and no source was excluded. Phase 9 added
meaningful tests for telemetry-enabled pre-stream HTTP failures and unexpected SSE failures. After the
final provider-span lifecycle hardening, actual aggregate coverage is **80.07%**. The final gate
therefore satisfies the threshold without relying on display rounding.

### Provider span lifetime excludes retry backoff

A final builder-side lifecycle review found that both non-streaming and streaming retry paths awaited
the retry sleeper while still inside the `provider.inference` span context. The explicit
`llm.latency_ms` attribute already represented only provider-attempt latency, but the actual span wall
clock duration incorrectly included operational retry backoff.

The execution loops now store the computed retry delay, close the concrete provider-attempt span, and
only then await the sleeper. Retry/fallback eligibility, health accounting, authorized candidate
boundaries, event metadata, replay safety, and provider request semantics are unchanged.

The existing retry/fallback telemetry test now uses a sleeper that inspects the in-memory exporter and
asserts that the first `provider.inference` span is already finished before the one retry backoff begins.
This regression protects the intended one-span-per-concrete-inference-attempt topology.

## Architecture/security boundaries

- Policy Model Router remains the PDP and the gateway remains the PEP plus operational selector;
- `Gateway allowed set ⊆ Policy Router authorized set` remains unchanged;
- telemetry consumes decision/execution evidence but cannot authorize or select a deployment;
- W3C propagation is limited to trace context and does not forward arbitrary inbound headers;
- provider/PDP credentials stay in transport configuration and are never telemetry attributes;
- provider error strings and traceback payload context are not auto-recorded;
- business-tool execution remains outside the gateway;
- streaming replay/fallback semantics from Phase 8 are unchanged;
- retry backoff is operational wait time outside the concrete `provider.inference` span;
- OpenTelemetry integration remains in application/adapter/composition boundaries rather than domain
  or provider-neutral contracts.

## Quality-gate execution model

Ruff, Bandit, pip-audit, and coverage CLI remain isolated quality tools. mypy and pytest execute with
`uv run --all-packages` so tools importing workspace code see locked project dependencies.

`types-jsonschema==4.26.0.20260518` remains an ephemeral mypy-only dependency.

The normal GitHub Actions workflow stays read-only and invokes:

```bash
uv run python scripts/quality_gate.py
```

## Phase 9 status

Implementation quality gates: **PASS**

Provider-span lifecycle finding: **RESOLVED AND REVALIDATED**

OpenTelemetry acceptance targets: **PASS**

Metadata-only privacy/W3C propagation tests: **PASS**

Authorization/resilience/streaming/architecture/security regression gate: **PASS**

Builder-side integration findings: **RESOLVED**

Independent architecture/security review and merge: **PENDING**

Phase 10 remains blocked until Phase 9 is independently reviewed and merged.
