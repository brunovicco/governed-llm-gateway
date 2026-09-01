# Phase 0 through Phase 7 Validation Record

Date: 2026-09-01

## Toolchain

- Python project runtime: 3.13+
- project pin: Python 3.13.12
- quality-tool execution pinned to Python 3.13
- uv workspace with locked dependencies

## Phase 0 baseline

The Architecture Gate baseline passed its quality, architecture, security, and contract checks.
`scripts/phase0_gate.py` remains explicitly frozen to the five contract modules from the
`phase-0-architecture-gate` tag. Current/future phase contract tests are exercised by the complete
pytest gate. Durable package boundaries remain enforced by `scripts/architecture_check.py`.

## Completed phases

- Phase 2 — Contracts and Model Registry: merged through PR #1; strict registry schema, safe YAML,
  duplicate-key rejection, pricing metadata, capability/modality validation, deterministic digest.
- Phase 3 — Provider Execution Foundation: merged through PR #2; provider-neutral execution contract,
  native/compatible adapters, usage extraction, typed timeout/error normalization and secret-safe
  transport.
- Phase 4 — Policy Router Integration: merged through PR #3; trusted prompt-free PDP projection,
  strict accepted/rejected provenance binding, registry/PDP intersection and zero provider calls after
  policy denial/boundary failure.
- Phase 5 — Deterministic Operational Ranking and Explainability: merged through PR #4; deterministic
  eligibility/ranking, ranking-policy provenance, authority-boundary hardening and authenticated
  no-inference `POST /v1/route/explain`.
- Phase 6 — Runtime Health, Retry and Safe Fallback: merged through PR #5; ADR-0007, bounded retry,
  bounded authorized fallback, circuit breaker/runtime health, replay-safety boundary, and
  metadata-only attempt evidence.

Phase 6 PR #5 merged at commit `8a5559edc1282494cb023e50f3898882fd0aa8e0`.

## Phase 7 implementation validation

Phase 7 — Structured Output and Tool Normalization was validated in the normal read-only GitHub
Actions workflow after canonical contracts, provider mappings, resilience interaction, schema
hardening, and acceptance tests were implemented.

Hardened validation head: `79a79051fa2f631580cd39ca3ad88494d210e8b8`

GitHub Actions run: `33521577607`.

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff formatting — PASS;
- mypy — PASS across 58 source files;
- pytest — PASS, 132 tests;
- total coverage — 82.62% (minimum 80%);
- Bandit — PASS, no identified issues and no skipped files;
- pip-audit — PASS, no known vulnerabilities;
- architecture validation — PASS;
- secret scanning — PASS;
- Phase 0 regression gate — PASS.

The workflow executed with `contents: read` and no provider/PDP credentials or live provider calls.

`jsonschema==4.26.0` is the Phase 7 runtime schema-validation dependency in `gateway-core`.
`types-jsonschema==4.26.0.20260518` is injected only into the ephemeral mypy environment by
`scripts/quality_gate.py`; it is not a runtime dependency.

## Phase 7 acceptance evidence

The normative roadmap acceptance criteria are covered directly:

- provider-native structured-output support is represented explicitly rather than inferred from
  prompting;
- malformed JSON and schema-invalid structured output are rejected;
- model-produced tool-call arguments are validated against the declared tool schema;
- the gateway exposes no business-tool execution authority.

Additional contract/boundary tests verify:

- `StructuredOutputSchema`, `ToolDefinition`, `ToolCall`, and `ToolResult` identity/shape constraints;
- structured output can be requested only together with the corresponding workload capability;
- tool definitions can be supplied only together with the tool-calling capability;
- duplicate tool definitions fail before provider execution;
- JSON Schema syntax is validated as Draft 2020-12 before provider execution;
- oversized/deep/externally referenced schemas fail closed;
- remote `$ref` and `$dynamicRef` resolution is not allowed;
- `pattern` and `patternProperties` are rejected instead of evaluating caller-controlled regex;
- `format` is rejected instead of being silently accepted without explicit local enforcement;
- ordinary object properties named `pattern` remain valid;
- tool schemas receive the same bounded schema-subset checks as structured output;
- provider output is parsed and revalidated locally after native schema enforcement;
- OpenAI Responses native structured-output payload mapping;
- OpenAI Responses function-tool mapping and normalized function-call extraction;
- Anthropic Messages structured-output/tool mapping and normalized `tool_use` extraction;
- Gemini `generateContent` response-schema/function-declaration mapping and normalized
  `functionCall` extraction;
- missing provider tool-call correlation fails closed rather than synthesizing an ID;
- generic OpenAI-compatible structured-output/tool support is disabled by default and requires
  explicit endpoint opt-in;
- structured-output/tool contracts survive the Phase 6 resilience boundary unchanged;
- `invalid_structured_output` and `invalid_tool_call` are permanent and produce zero automatic retry
  and zero automatic fallback.

## Phase 7 architecture/security boundaries

- structured output means provider-native schema enforcement, not prompted JSON;
- provider-native enforcement never replaces gateway-side post-response validation;
- Phase 7 implements a documented bounded Draft 2020-12 subset rather than unrestricted schema
  semantics;
- schema evaluation is local and performs no remote retrieval;
- caller-controlled regex keywords are excluded until a bounded evaluation strategy exists;
- `format` is excluded until explicit local checker semantics are adopted;
- provider feature support is separate from registry deployment capability and from PDP authorization;
- provider adapters translate features but have zero model-authorization authority;
- `ToolCall` is data, not permission to execute an external action;
- application/agent/MCP runtime owns business-tool authorization, execution, side effects, and
  `ToolResult` creation;
- provider correlation IDs are never fabricated;
- provider-native continuation/reasoning state is not reconstructed from guesses;
- semantic structured/tool validation failures are not converted into availability fallback;
- prompts, completions, structured payloads, tool arguments/results, provider/PDP secrets, and raw
  provider error bodies remain excluded from default evidence.

## Quality-gate execution model

Ruff, Bandit, and pip-audit remain isolated quality tools. mypy and pytest execute with `uv run
--all-packages` so tools importing workspace code see the locked project dependencies.

`types-jsonschema` is installed through the mypy command's ephemeral `--with` dependency only. This
allows strict typing of `jsonschema` without adding a stub-only package to production/runtime
requirements.

The GitHub Actions workflow is read-only (`contents: read`) and invokes:

```bash
uv run python scripts/quality_gate.py
```

One non-blocking `StarletteDeprecationWarning` remains from FastAPI TestClient regarding `httpx` versus
`httpx2`. It is unrelated to Phase 7 functionality/security and remains separate maintenance work.

## Phase 7 status

Implementation quality gates: **PASS**

Structured-output/tool acceptance targets: **PASS**

Authorization/resilience/architecture/security regressions: **PASS**

Phase 7 independent review/merge: **PENDING**
