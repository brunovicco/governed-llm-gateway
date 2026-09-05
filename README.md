# Governed LLM Gateway

**English** | [Português (Brasil)](README.pt-BR.md)

Reusable provider-neutral LLM execution gateway for **governed model resolution and execution**.

Status: **Phases 0–13 complete; Phase 14 in progress — Cases 1/2 complete, Case 3 deferred. Initial benchmark workload matrix 5/5 complete.**

The gateway is the operational Policy Enforcement Point (PEP) between an application's declared workload and the concrete LLM deployment selected for execution.

```text
Application / Agent
       │ workload + requirements + policy metadata
       ▼
Policy Model Router (PDP)
       │ authorized logical model group + provenance
       ▼
Governed LLM Gateway (PEP + operational selector)
       │ authorized candidates only
       ├─ capability / environment eligibility
       ├─ deterministic ranking
       ├─ runtime health / circuit breaker
       ├─ bounded retry / safe fallback
       ├─ structured-output / tool-call normalization
       ├─ streaming / cancellation
       ├─ approved benchmark evidence
       └─ provider-neutral execution provenance
       ▼
LLM Provider
       │ normalized model output + metadata-only evidence
       ▼
Application / Agent / MCP runtime
       └─ authorizes and executes business tools / side effects
```

Permanent invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may narrow authorization because of capability, data/environment policy, governance scope, cost, latency, health or other operational constraints. It may never broaden PDP authorization. Ranking, retry/fallback, benchmark evidence, telemetry, SDK state and runtime provenance are not authorization sources.

## Current implementation

Phases 0–13 are complete and establish:

- strict provider-neutral contracts and deterministic model registry;
- Policy Model Router integration with fail-closed authorization;
- deterministic eligibility, ranking and `POST /v1/route/explain`;
- runtime health, circuit breaking, bounded retry and safe fallback;
- structured-output validation and provider-neutral tool-call normalization;
- normalized streaming, cancellation and replay-safety boundaries;
- OpenTelemetry integration with metadata-only defaults;
- offline deterministic benchmark infrastructure and explicit evidence promotion;
- evidence-driven ranking with manual override and rollback boundaries;
- a thin typed client SDK with no provider SDK/API-key requirement for consumers;
- optional Verifiable AI Governance authorization and runtime evidence;
- provider-neutral terminal execution provenance preserved through SSE/API/SDK.

Phase 14 is migrating real consumers incrementally in the normative order:

1. `controlled-autonomy-lab` — **COMPLETE**;
2. `getnet-multi-agent-support-v2` — **COMPLETE**;
3. `OpsLens` — **VALIDATED CANDIDATE, DEFERRED** while that repository evolves independently;
4. `RAGForge` — **NOT STARTED** because the sequencing guard remains active;
5. `Verifiable AI Governance` — **NOT STARTED** as a Phase 14 consumer case.

See `docs/project/CURRENT_STATE.md` for the authoritative checkpoint and issue #18 for the active OpsLens/RAGForge sequencing guard.

## Benchmark workload matrix — 5/5 complete

The roadmap's first five workload-specific benchmark contracts are implemented:

| Workload | Current reviewed contract | Merge |
|---|---|---|
| `structured_extraction` | `structured-extraction-v2` (v1 preserved historically) | PRs #19 and #22 |
| `rag_ptbr` | `rag-ptbr-v1` | PR #20 |
| `code_generation` | `code-generation-v1` | PR #21 |
| `tool_use` | `tool-use-v1` | PR #23 |
| `agent_orchestration` | `agent-orchestration-v1` | PR #24 |

The workload-specific suites remain:

- public/synthetic and credential-free by default;
- deterministic and replayable;
- explicit about provider/model/API/configuration/date provenance;
- separate from live provider availability evidence;
- free of LLM-as-judge scoring in the default CI path;
- unable to execute business tools, generated code, agents or side effects;
- unable to self-promote or mutate active runtime routing.

The evidence path remains:

```text
versioned dataset
  -> BenchmarkRunner
  -> deterministic scorer
  -> Scorecard
  -> content-addressed snapshot
  -> explicit promotion
  -> ranking evidence inside the already-authorized candidate set
```

See `docs/evaluation/BENCHMARK_MATRIX.md` and `docs/project/EVALUATION.md`.

## Structured output and tools

Structured output is a model/API capability, not a prompt convention. Provider-native schema enforcement is followed by local bounded validation.

Business-tool authority remains outside the gateway:

```text
Gateway → normalizes ToolCall
Application / Agent / MCP runtime → authorizes + executes tool → owns ToolResult
```

The `tool_use` benchmark evaluates only the proposed tool decision and arguments. It never executes the tool.

## Agent orchestration boundary

The `agent_orchestration` benchmark evaluates only an observable proposed trajectory (`agent`, `action`, `handoff_to`). It does not inspect chain-of-thought and does not execute agents, tools, business operations or human handoffs.

Framework-specific orchestration remains a consumer/runtime responsibility. Frameworks are adapters, not owners of gateway policy or authorization.

## Safe retry and fallback

Retry and fallback remain bounded to the authorized, eligible and ranked sequence:

- retry targets the same concrete deployment;
- fallback can only advance to an already-authorized alternative;
- permanent validation/authentication/authorization/configuration failures do not automatically fallback;
- circuit-open/unhealthy state only narrows eligibility;
- visible semantic output, side effects or opaque continuation state stop automatic replay.

## Runtime evidence

Successful aggregate SDK responses preserve terminal provider-neutral execution evidence including provider/model/deployment identity, gateway request identity, optional provider request identity, finish reason, retry/fallback position, measured provider-attempt latency, normalized token usage and optional cost when actually known.

Unknown optional evidence remains absent instead of being synthesized. Runtime evidence is descriptive only and never becomes authorization.

## Repository layout

```text
apps/gateway-api/           HTTP composition root
packages/gateway-contracts provider-neutral contracts
packages/gateway-core/     domain/application/adapters boundary
packages/gateway-client/   thin typed consumer SDK
config/                    model/ranking/provider configuration
benchmarks/                offline datasets, scorers, runner, snapshots and promotion
examples/                  bounded examples
 tests/                    contract/integration/e2e suites
 docs/                     durable project sources, evaluation docs and ADRs
```

## Validate

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Current validated `main` baseline after PR #24 (`a8f2003663eb9ac713df6929a8c7b5bc79573e69`):

- **421 tests passed**;
- **81.32% aggregate coverage** (threshold 80%);
- mypy passed across **132 source files**;
- Ruff lint/format passed across **132 files**;
- Bandit reported **0 issues** across 12,883 LOC;
- pip-audit reported **no known vulnerabilities**;
- architecture check, secret scan and Phase 0 gate passed;
- post-merge `main` quality run `33968458431` — **PASS**.

The known Starlette TestClient `httpx`/`httpx2` deprecation warning remains non-blocking.

## Source of truth

Start with:

- `docs/project/CURRENT_STATE.md` — current project checkpoint;
- `docs/project/ROADMAP.md` and `docs/project/SOURCE_ROADMAP.txt` — execution ledger and normative source;
- `docs/project/EVALUATION.md` — benchmark/evidence architecture;
- `docs/evaluation/BENCHMARK_MATRIX.md` — completed initial workload matrix;
- `docs/project/PHASE14_PROVIDER_NEUTRAL_EXECUTION_PROVENANCE.md` — terminal runtime evidence;
- `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` — Phase 7 capability/authority boundary;
- `docs/project/STREAMING.md` — Phase 8 streaming lifecycle;
- `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` — authorization boundary.
