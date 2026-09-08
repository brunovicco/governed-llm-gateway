# Governed LLM Gateway

**English** | [Português (Brasil)](README.pt-BR.md)

**A provider-neutral LLM execution gateway for governed AI platforms.**

It centralizes model authorization, selection, resilience, provider adaptation and runtime evidence so applications and agents do not need to own provider credentials, model choice, retry/fallback or routing policy.

## Why this project exists

LLM execution becomes harder to govern as applications add more models, providers and agent workflows. This project separates **business/application logic** from **model execution policy** and keeps authorization ahead of optimization.

The gateway is designed to provide one reusable boundary for:

- provider-neutral model execution;
- deterministic and explainable routing;
- policy enforcement and fail-closed authorization;
- runtime resilience and safe fallback;
- structured output, tool-call normalization and streaming;
- observability, provenance and auditable evidence;
- benchmark-driven model evaluation without automatic policy mutation.

## Core capabilities

| Area | What the gateway provides |
|---|---|
| **Governance** | PDP/PEP separation, fail-closed authorization and optional governance integration |
| **Routing** | Deterministic model registry, eligibility filters, ranking and route explainability |
| **Resilience** | Runtime health, circuit breaking, bounded retry and safe fallback |
| **Provider abstraction** | Provider-neutral contracts, request translation and normalized execution results |
| **Model I/O** | Structured-output validation, tool-call normalization, streaming and cancellation |
| **Observability** | OpenTelemetry integration, metadata-only defaults and terminal execution provenance |
| **Evaluation** | Deterministic benchmark framework, immutable evidence, explicit promotion and rollback boundaries |
| **Consumer integration** | Thin typed SDK without requiring provider SDKs or provider API keys in consumers |

## Architecture

```text
Application / Agent
       │ workload + requirements + policy metadata
       ▼
Policy Model Router (PDP)
       │ authorized logical model groups
       ▼
Governed LLM Gateway (PEP)
       ├─ eligibility
       ├─ deterministic ranking
       ├─ health / circuit breaker
       ├─ retry / safe fallback
       ├─ provider translation
       └─ provenance / telemetry
       ▼
LLM Provider
```

Business-tool execution and side effects remain outside the gateway. The gateway may normalize a tool call, but the application/agent runtime owns tool authorization and execution.

### Permanent authorization invariant

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may narrow the authorized set because of capability, environment, governance, cost, latency or runtime health. It may never broaden upstream authorization. Ranking, telemetry, benchmark evidence and runtime provenance are not authorization sources.

## Design principles

- **Authorization before optimization.** Ranking only operates inside the already-authorized and eligible candidate set.
- **Fail closed on ambiguity.** Invalid policy, provenance, capability or evidence state does not silently degrade into permissive behavior.
- **Evidence is descriptive, not authority.** Runtime and benchmark evidence cannot self-authorize or rewrite active policy.
- **Provider failures are not model-quality failures.** Availability and quality evidence remain separate.
- **Business side effects stay outside the gateway.** Tools and application actions remain owned by the consumer runtime.

## Current status

- **Core platform:** Phases 0–13 complete.
- **Real-project migration:** Phase 14 in progress; `controlled-autonomy-lab` and `getnet-multi-agent-support-v2` are complete, while OpsLens remains deliberately deferred.
- **Evaluation:** all roadmap-listed benchmark classes are represented by reviewed deterministic contracts.
- **Operational evidence:** bounded materialization, best-effort runtime recording and content-addressed source-instance batch handoff are implemented; fleet/shared completeness and online operational-score policy are not active.
- **Local observability evidence:** Collector receipt, Tempo queryability and a file-provisioned read-only Grafana trace dashboard have credential-free CI proofs; this is not a claim of production observability readiness.

For the authoritative project checkpoint and Phase 14 sequencing, see [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md).

## Quality baseline

The latest validated quality gate reports:

- **1107 tests passing** and 2 skipped;
- **83.70% aggregate coverage**;
- strict **mypy** and **Ruff** checks;
- **Bandit: 0 findings** across 22,842 LOC;
- **pip-audit: no known vulnerabilities**;
- architecture, secret-scan and Phase 0 gates passing.

## Validate locally

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

The default quality path is deterministic and credential-free.

## Local trace visualization

The checked-in observability stack provides a read-only Grafana dashboard backed by the provisioned local Tempo datasource:

```bash
docker compose -f compose.observability.yml up -d tempo grafana
```

Open `http://127.0.0.1:3000`. The local demo binds Grafana to loopback, keeps Tempo unexposed from the reusable base Compose stack, and requires no Grafana, provider or Policy Router credential. The anonymous Viewer configuration is local-demo only and is not a production authentication design.

The dashboard uses the stable TraceQL query `{ span:name = "llm.gateway.request" }` and displays real Tempo results rather than fabricated traces or metrics. See [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) for the exact provisioning, CI proof, network boundary and non-claims.

## Repository map

| Path | Responsibility |
|---|---|
| `apps/gateway-api/` | HTTP composition root |
| `packages/gateway-contracts/` | Provider-neutral public contracts |
| `packages/gateway-core/` | Domain, application services and adapters |
| `packages/gateway-client/` | Thin typed client SDK |
| `benchmarks/` | Deterministic evaluation, evidence and promotion |
| `config/` | Model, ranking and provider configuration |
| `tests/` | Contract, integration and end-to-end validation |
| `docs/` | Architecture, roadmap, evaluation and project state |

## Deep dives

- [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) — authoritative project checkpoint
- [`docs/project/ROADMAP.md`](docs/project/ROADMAP.md) — implementation roadmap and phase ledger
- [`docs/project/EVALUATION.md`](docs/project/EVALUATION.md) — benchmark and evidence architecture
- [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) — local read-only Grafana/Tempo trace proof
- [`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) — authorization boundary
- [`docs/evaluation/OPERATIONAL_EVIDENCE.md`](docs/evaluation/OPERATIONAL_EVIDENCE.md) — recent operational-evidence model
- [`docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`](docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md) — structured output and tool authority boundary
