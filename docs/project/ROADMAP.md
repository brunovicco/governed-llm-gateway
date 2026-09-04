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
12. Thin client SDK transport — COMPLETE (`governed-llm-gateway` PR #11, squash merge
    `1b9b3ef01f0efac49d1f2a92056473ec4b45c375`).
13. Optional Verifiable AI Governance integration — COMPLETE (`governed-llm-gateway` PR #12,
    squash merge `ec18ad8e95490fdeb6ee4c6b9e26ae7cd5b1b0b1`).
14. Incremental real-project integrations — CURRENT.

## Permanent authority sequence

The portfolio authority chain is:

`Verifiable AI Governance → Policy Model Router → Governed LLM Gateway → model provider`

Phase 4 establishes the Policy Router-authorized candidate set. Later governance intersection,
ranking, health, retry/fallback, benchmark promotion, SDK transport and telemetry may only narrow or
execute inside that authority boundary:

`Gateway allowed set ⊆ Policy Router authorized set`

Governance authorization may narrow the set further but may not expand the Policy Router result.
No client, benchmark result, telemetry signal, provider result, runtime observation or evidence record
may broaden the authorization set.

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

Phase 12 adds the thin provider-neutral SDK. Consumers need only gateway URL/credential and do not own
provider SDKs, provider keys, ranking, retry or fallback. The SDK preserves routing provenance and
strictly bounds/validates its SSE transport.

Phase 13 integrates optional signed Verifiable AI Governance authorization without turning the gateway
into a second PDP. Governance scope can only narrow the Policy Router-authorized set, and denial/runtime
execution evidence remains metadata-only and non-authoritative.

## Phase 14 — Real project integrations

Normative recommended order:

1. `controlled-autonomy-lab`
2. `getnet-multi-agent-support-v2`
3. `OpsLens`
4. `RAGForge`
5. `Verifiable AI Governance`

Each migration is an integration case. Consumers depend on the gateway; the gateway never depends on a
business project. Migrations remain incremental rather than moving all consumers simultaneously.

### Integration case 1 — controlled-autonomy-lab — COMPLETE

Consumer PR #24 was squash-merged as:

`238e4b93284579b5c9ba0d650161febcdbf83a51`

The consumer now has an opt-in `LLM_PROVIDER=gateway` path for bounded text generation:

- exact gateway SDK/contracts dependency pin;
- explicit dotted workload identity;
- no provider credentials, provider model selection, retry or fallback in the consumer path;
- normalized gateway SSE text/usage mapped into the existing consumer model port;
- direct provider adapters retained only for benchmark comparability and unsupported continuation cases;
- bounded-agent tool-result continuation fails closed because no canonical provider-neutral continuation
  contract exists yet.

The first consumer also exposed a real SDK packaging defect: installed `gateway-client` and
`gateway-contracts` were not PEP 561-discoverable. Gateway PR #13 added `py.typed` markers and was
squash-merged as `96b09956e933db50bf9ea900973f8a0b2145cb3c` before the consumer integration was finalized.

Consumer validation before merge:

- GitHub Actions run `33883274493` — PASS;
- 194 tests passed;
- aggregate coverage 86.19%;
- strict mypy PASS across 85 source files;
- Ruff lint/format PASS across 88 files;
- Bandit 0 issues across 6,281 lines of code;
- pip-audit reported no known vulnerabilities in auditable registry dependencies.

### Integration case 2 — getnet-multi-agent-support-v2 — COMPLETE

Consumer PR #3 was squash-merged as:

`6ee7f3db8f666e35f78f7df5524a1fc15e1ef0da`

The migration adds an opt-in gateway implementation of the existing one-shot `LLMPort` while keeping
customer scope, market isolation, support-agent routing, evidence gates, web search and business-tool
authority inside the consumer. The gateway path owns neither direct provider credentials nor concrete
model selection/retry/fallback. Gemini semantic embeddings remain a separate direct capability because
the gateway does not expose an embeddings service.

A pre-review contract check found that a failed gateway terminal response may carry partial generated
content. The consumer now requires `ExecutionStatus.SUCCEEDED` before returning any generated answer;
failed partial output is rejected fail closed.

Final consumer validation before merge:

- GitHub Actions run `33886194928` — PASS;
- 259 tests passed, 14 skipped and 1 deselected;
- aggregate coverage 88.59%;
- strict mypy PASS across 55 source files;
- Ruff lint/format PASS across 118 files;
- Bandit 0 issues across 2,022 lines of code;
- pip-audit reported no known vulnerabilities in auditable registry dependencies;
- architecture, MCP configuration, governance and vendored loop-schema gates passed.

### Integration case 3 — OpsLens — CURRENT

OpsLens already freezes a bounded semantic-query planner contract before model invocation. Its accepted
ADR 0021 deliberately separates the model proposal from deterministic query construction, validation,
SQL compilation and read-only Athena execution. The integration should preserve that narrower authority
while moving provider/model selection and provider retry/fallback behind the gateway.

The existing offline Bedrock request contract remains useful as a benchmark/reference artifact; the
consumer migration must not turn a model response into SQL authority or broaden the supported semantic
surface.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
