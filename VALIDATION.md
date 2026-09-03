# Phase 0 through Phase 10 Validation Record

Date: 2026-09-03

## Toolchain

- Python project runtime: 3.13+
- project pin: Python 3.13.12
- quality-tool execution pinned to Python 3.13
- uv workspace with locked dependencies
- default GitHub Actions permissions: `contents: read`, `metadata: read`

## Historical architecture baseline

`scripts/phase0_gate.py` remains frozen to the contract baseline that existed at the
`phase-0-architecture-gate` tag. Current/future phase tests are exercised by the complete pytest gate.
Package boundaries remain enforced separately by `scripts/architecture_check.py`.

The core authorization invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

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
- Phase 9 — OpenTelemetry: PR #8, merge commit
  `be15c21ecfc76ef9bb727e5c4144c4929f028489`.

## Phase 8 validation checkpoint

Phase 8 code-validation head:

`a8b9fdcd6d69b94a2ab6ed942e67409df50d0092`

GitHub Actions run `33790152650`:

- Ruff/mypy/pytest/security/architecture/secret gates — PASS;
- pytest — 183 tests;
- coverage — 80.61%;
- bounded incremental SSE parsing enforced the 1 MiB event limit before an unterminated provider line
  could grow without bound inside HTTPX;
- run was credential-free and made no live provider/PDP calls.

## Phase 9 validation checkpoint

Final Phase 9 source head after lifecycle hardening:

`5177f6b71c6ba2b3c5e17762d9cec0b39a3013b3`

Read-only revalidation run `33803564689`:

- Ruff lint/format — PASS;
- mypy — PASS across 75 source files;
- pytest — 192 tests;
- coverage — 80.07%;
- Bandit — no identified issues;
- pip-audit — no known vulnerabilities;
- architecture/secret/Phase 0 gates — PASS.

Phase 9 findings resolved before merge included:

- restoring backward-compatible optional `_sse_body()` telemetry parameters;
- retaining the shared `a2a-otel-kit` deny-by-default sanitizer and exporting usage counts under
  `llm.usage.input_count` / `llm.usage.output_count` rather than weakening credential-like-key
  filtering;
- adding telemetry error-path coverage after an intermediate rounded-coverage ambiguity;
- closing `provider.inference` spans before retry backoff in both non-streaming and streaming paths;
- adding a regression assertion proving that the provider span is finished before the retry sleeper
  starts.

## Phase 10 implementation

Phase 10 is implemented on `feat/phase-10-evaluation-framework` as an offline-first evaluation source
root under `benchmarks/`. It does not become a runtime dependency of the gateway packages.

### Dataset and workload evidence

`benchmarks/datasets/gateway-eval-v1.json`:

- schema version `1.0`;
- benchmark version `gateway-eval-v1`;
- explicit data classification `public`;
- ten public/synthetic cases;
- two cases for each initial roadmap workload:
  `structured_extraction`, `rag_ptbr`, `code_generation`, `tool_use`, and
  `agent_orchestration`.

The strict loader rejects unknown fields, malformed JSON-compatible values, unsupported workload
identifiers, and non-public Phase 10 datasets before provider execution.

### Deterministic scorer evidence

The bounded scorer registry contains:

- `exact_json`;
- `contains_all`;
- `mapping_fields`;
- `ordered_sequence`.

Scorers are deterministic/local and do not require another model or network call. The entire dataset
is preflighted for known scorer identifiers before any benchmark executor call.

### Provider/model target evidence

`benchmarks/runners/targets-v1.json`, matrix version `phase10-targets-v1`, identifies every target by:

- provider;
- exact model identifier;
- API family/surface;
- benchmark configuration;
- source date.

The initial matrix contains development/benchmark targets for NVIDIA, Groq, OpenRouter, and Google
Gemini plus paid/control targets for OpenAI Responses and Anthropic Messages.

Free/developer endpoints are public/synthetic benchmark/development targets only by default.

### Quality versus provider availability

The provider-neutral runner represents observations as:

- `succeeded`;
- `quality_failure`;
- `provider_failure`.

Provider failures have `quality_score = None`; rate limits, timeouts, and outages therefore remain
availability/error evidence rather than becoming false zero-quality model results.

Scorecards separately aggregate availability, quality success among completed calls, mean quality,
latency p50/p95, TTFT p50/p95, usage, cost, rate-limit count, fallback frequency, and provider error
counts.

### Snapshot reproducibility

Dataset digests and benchmark snapshot identifiers are canonical `sha256:` values. Snapshot identity
covers:

- benchmark and runner versions;
- run date;
- full dataset digest;
- exact benchmark targets/configurations;
- normalized observations;
- aggregate scorecards.

Equivalent evidence produces identical canonical JSON and snapshot ID. Changing target configuration
changes the snapshot ID. Persisted snapshots are immutable/idempotent under:

```text
benchmarks/results/<benchmark-version>/<snapshot-sha256>.json
```

Raw provider responses are outside the persisted score-snapshot contract.

## Phase 10 validation findings resolved

### Repository source-root importability

`benchmarks/` is intentionally not a runtime workspace package. mypy already treated the repository
root as a source root; pytest initially did not when invoked as an installed console script.
`pythonpath = ["."]` now makes this repository-level evaluation source boundary explicit without
adding benchmark code to gateway runtime dependencies.

### Strict scorer typing

Initial mypy validation exposed five scorer-registry/narrowing errors. The string-list scorer now
performs explicit element narrowing and the scorer registry is typed directly as
`dict[str, DeterministicScorer]`. No scorer semantics were relaxed.

### Coverage threshold precision

After the first Phase 10 tests, all 199 tests passed but actual aggregate coverage was 79.63%. Default
coverage display precision rounded the report to 80%, which allowed the workflow to continue despite
the sub-threshold actual value.

The threshold was not lowered and `benchmarks/` was not excluded. Meaningful deterministic scorer
branch tests increased actual coverage to **80.56%**, and `[tool.coverage.report] precision = 2` now
makes future threshold evaluation/display unambiguous.

## Phase 10 current validated baseline

Validated source head before documentation-only synchronization:

`9a7b49407b0a040c976eac88fb29201ecf102a28`

GitHub Actions run:

`33806876880`

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff format — PASS, **84 files**;
- mypy — PASS across **84 source files**;
- pytest — **207 passed**;
- aggregate branch coverage — **80.56%**;
- `benchmarks/scoring.py` — **100%** coverage;
- Bandit — PASS, no identified issues;
- pip-audit — PASS, no known vulnerabilities;
- architecture check — PASS;
- secret scan — PASS;
- Phase 0 regression gate — PASS;
- default workflow token remains read-only;
- credential-free and no live provider/PDP calls.

The only test warning remains the existing FastAPI/Starlette TestClient `httpx` -> `httpx2`
deprecation notice; it is non-blocking and unrelated to Phase 10.

A final quality run is required after the documentation and coverage-precision checkpoint before the
Phase 10 PR is considered review-ready.

## Phase boundary

Phase 10 benchmark evidence is **not** consumed by production ranking. Runtime code does not import the
benchmark source root and `benchmark_snapshot_id` remains unset in routing provenance.

ADR-0009 — Benchmark-derived routing scores — remains deferred to Phase 11. Future benchmark-derived
ranking may order only candidates already inside the PDP-authorized set and must never widen
authorization.

## Phase 10 status

Evaluation framework implementation: **IMPLEMENTED**

Deterministic dataset/scorer/runner/snapshot tests: **PASS**

Quality-versus-availability separation: **PASS**

Credential-free default CI: **PASS**

Coverage precision hardening: **IMPLEMENTED; FINAL REVALIDATION PENDING**

Independent architecture/security review and merge: **PENDING**

Phase 11 remains blocked until Phase 10 is independently reviewed and merged.
