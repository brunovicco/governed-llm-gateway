# Governed LLM Gateway

**English** | [Português (Brasil)](README.pt-BR.md)

[![quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml)
[![console-quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml)
[![observability-compose](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml)

> A provider-neutral LLM execution gateway that keeps **authorization, model selection, provider credentials, resilience and runtime evidence** out of application code.

Applications and agents call one governed execution boundary instead of embedding OpenAI, Anthropic, Gemini, NVIDIA, Groq or OpenRouter-specific credentials and routing logic in every service.

```text
Application / Agent
        │
        │ workload + requirements + Gateway credential
        ▼
Policy Model Router (PDP)
        │ authorized logical model groups
        ▼
Governed LLM Gateway (PEP)
        ├─ eligibility + deterministic ranking
        ├─ health / circuit breaker
        ├─ bounded retry + safe fallback
        ├─ provider translation
        └─ provenance + OpenTelemetry
        ▼
LLM providers
```

The permanent authority rule is:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The Gateway may narrow an authorized set. It may never widen upstream authorization.

## What this project demonstrates

The repository is a practical reference implementation of an AI Platform execution layer rather than a thin multi-provider proxy.

| Area | Demonstrated capability |
|---|---|
| **AI Platform architecture** | Provider-neutral contracts, model registry, explicit composition roots and thin consumer SDK |
| **Governed execution** | PDP/PEP separation, deterministic authorization boundary and fail-closed behavior |
| **Model routing** | Capability/environment filtering, deterministic ranking and route explainability |
| **Reliability** | Runtime health, circuit breaking, bounded retry, safe fallback, streaming and cancellation |
| **LLM interoperability** | Native OpenAI Responses, Anthropic Messages, Gemini and explicit OpenAI-compatible adapters |
| **Structured model I/O** | Structured-output validation and normalized tool-call contracts without taking ownership of tool execution |
| **Observability** | Metadata-only OpenTelemetry, real Collector → Tempo proof and file-provisioned Grafana trace dashboard |
| **Evaluation** | Deterministic benchmark contracts, immutable evidence and explicit promotion/rollback boundaries |
| **Security** | Server-side provider secrets, client authentication boundaries, secret scanning and no allow-all fallback |
| **Engineering quality** | Strict typing, architecture checks, security gates, automated tests and real-container CI proofs |

## What you can run today

### 1. Bounded local platform demo — ready now

The repository includes a deterministic one-command **operations-only** local demo that starts:

- the read-only Gateway Operations API;
- the React/TypeScript Gateway Console;
- OpenTelemetry Collector;
- Tempo;
- Grafana with the provisioned Gateway trace dashboard.

It requires **no provider API key and no Policy Router credential** because it deliberately exposes no inference route. This makes the platform/control/evidence surfaces demonstrable without introducing a fake allow-all authorization path.

### 2. Governed live inference — explicit development profile

The checked-in default deployment baseline remains intentionally fail-closed:

- `config/model_registry.yaml` has no enabled deployments;
- `config/providers/runtime.json` has no provider bindings;
- `config/policy/router.json` is disabled;
- checked-in default client-auth artifacts contain no live principals/secrets.

Therefore **adding `OPENAI_API_KEY` or another provider key by itself still does not enable live inference**.

For an explicit opt-in development path, `config/profiles/live-development/` now provides a reviewed secret-free profile for one `development` / `public` / `rag.answer` consumer, an external Policy Model Router authorization boundary, deterministic ranking, and two native provider deployments in the same authorized `balanced` logical group.

See [`config/profiles/live-development/README.md`](config/profiles/live-development/README.md) for the exact startup and request flow. The profile is a development/demo configuration, not a production TLS, IAM, secret-management or provider-SLA claim. Live-provider execution remains opt-in and credential-backed; the required quality CI stays credential-free.

This separation is intentional: operational availability never becomes authorization by accident.

## Quick start: local operations demo

### Prerequisites

- Python **3.13+** (the workspace currently supports Python 3.13–3.14);
- [uv](https://docs.astral.sh/uv/);
- Docker with Docker Compose;
- Node.js 24 + npm.

### Start

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway

cp .env.example .env
```

Edit `.env` and set a random local-only value:

```dotenv
GATEWAY_LOCAL_DEMO_API_KEY=replace-with-a-random-local-value
```

The Python runtime does **not** automatically load `.env`. Export it into the process environment before starting:

```bash
set -a
source .env
set +a

uv run --frozen python scripts/local_demo.py
```

When readiness succeeds, open:

| Surface | URL | Purpose |
|---|---|---|
| Gateway Console | `http://127.0.0.1:5173` | Read-only operational view |
| Gateway readiness | `http://127.0.0.1:8000/readyz` | Process readiness |
| Operations API | `http://127.0.0.1:8000/v1/ops/overview` | Authenticated bounded operational state |
| Grafana | `http://127.0.0.1:3000` | Local trace visualization |

Press `Ctrl+C` to stop the interactive demo. The launcher owns cleanup of its child processes and dedicated Compose project.

For an automated startup/readiness/teardown proof:

```bash
uv run --frozen python scripts/local_demo.py --smoke-test
```

For governed provider execution, use the separate [`live-development` profile runbook](config/profiles/live-development/README.md); it intentionally requires an external PDP and server-side provider credentials.

## Where do API keys go?

**Never put real API keys in Model Registry files, provider-runtime JSON, README files, logs, traces or Git.**

The repository uses a reference-based secret model:

```text
provider-runtime artifact
    credential_reference: "OPENAI_API_KEY"
                         │
                         ▼
Gateway process environment / secret manager
    OPENAI_API_KEY=<real secret>
                         │
                         ▼
provider adapter
```

### Local demo credential

The operations-only demo requires:

```text
GATEWAY_LOCAL_DEMO_API_KEY
```

Put it in your local `.env`, source/export the file, and then run the launcher. The launcher passes this credential only to the operations-only Gateway child; Docker, npm and Vite receive sanitized environments without it.

### Governed live-development credentials

The opt-in live-development profile references:

```text
GATEWAY_DEMO_API_KEY
POLICY_ROUTER_DEMO_API_KEY
OPENAI_API_KEY
GEMINI_API_KEY
```

The consumer presents only `GATEWAY_DEMO_API_KEY`. The Policy Router and provider credentials remain server-side. The profile does not contain the raw values and does not automatically activate when those variables are present.

### Provider API keys

Provider credentials belong to the **Gateway deployment**, not consumer applications. The initial server-side resolver reads environment variables whose names are referenced by the selected provider-runtime artifact.

Common examples are included as comments in `.env.example`:

```dotenv
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=
# NVIDIA_API_KEY=
# GROQ_API_KEY=
# OPENROUTER_API_KEY=
```

They become relevant only when a reviewed provider-runtime binding references them and a matching deployment exists in the selected Model Registry.

For local development you may source `.env`. For a real deployment, inject the same environment references through your orchestrator or secret manager. The secret-resolution port is intentionally designed so AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault or another backend can replace the environment resolver without changing consumer contracts.

### Consumer credentials

A consumer should receive only:

```text
GOVERNED_LLM_GATEWAY_URL
GOVERNED_LLM_GATEWAY_API_KEY
```

It should **not** receive provider API keys. Consumer applications also do not own provider/model selection or retry/fallback policy.

See [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) and [`docs/project/GATEWAY_CLIENT_AUTHENTICATION.md`](docs/project/GATEWAY_CLIENT_AUTHENTICATION.md) for the detailed trust boundary.

## How governed execution works

A request does not simply choose the cheapest or fastest available model.

1. The consumer authenticates to the Gateway.
2. The Policy Model Router determines the logical model groups the workload is authorized to use.
3. The Gateway intersects that authority with registry capability, environment, data/risk and runtime eligibility.
4. Deterministic ranking operates only inside that remaining set.
5. Retry/fallback may move only to another already-authorized eligible deployment.
6. Provider-specific requests/responses are normalized behind adapters.
7. Terminal execution provenance and metadata-safe telemetry describe what happened; they never authorize a future request.

Business tool execution remains outside the Gateway. The Gateway can normalize a tool call, but the application/agent runtime owns tool authorization and side effects.

## Architecture boundaries

```text
                    Governance authority (optional)
                              │
                              ▼
                      Policy Model Router
                              │ PDP
                              ▼
                     Governed LLM Gateway
                              │ PEP
          ┌───────────────────┼────────────────────┐
          ▼                   ▼                    ▼
   Model providers      a2a-otel-kit         Evidence / evals
          │                   │
          │                   ▼
          │             OTel Collector
          │                   │
          │                   ▼
          │                 Tempo
          │                   │
          │                   ▼
          │                 Grafana
          ▼
 normalized execution
```

The Gateway is intentionally **not** an agent framework, RAG framework, MCP tool executor, prompt-management platform or general API-management product. Its responsibility is governed model resolution and execution.

## Current status

| Track | Status |
|---|---|
| Core platform — Phases 0–13 | **Complete** |
| Real-project integrations — Phase 14 | **In progress**: two integrations complete; OpsLens intentionally deferred |
| Local operational demo — OR-8 | **Complete** at the bounded operations-only local-demo scope |
| Live-inference development profile | **Implemented in PC-33**; a first opt-in live-provider proof (native Gemini deployment) was executed and recorded 2026-09-08 — see `docs/project/CURRENT_STATE.md` |
| Broader operational-surface auth/security — OR-9 | **Not started** |
| Final screenshots/demo/product-readiness validation — OR-10 | **Not started** |
| Per-trace Console correlation | **Deferred pending an explicit reviewed correlation source** |

The authoritative checkpoint is [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md).

### What remains before calling the application finished

For a **portfolio/demo-ready live product path**, the main remaining work is:

1. ~~execute and record an opt-in real-provider proof through the PC-33 profile while keeping required CI credential-free~~ — done 2026-09-08 for the native Gemini deployment; the native OpenAI deployment in the same profile is not yet separately proven;
2. decide whether the current Console should gain a bounded live-request/provenance view and per-trace navigation, based only on real backend evidence;
3. complete the minimum OR-9 security hardening appropriate to the demonstrated operational surfaces and clearly separate production-only hardening;
4. complete OR-10: reproducible end-to-end validation, final documentation, screenshots/assets where useful, architecture/security/CI review and explicit local/demo/production non-claims;
5. decide and cut the `v1.0.0` release boundary before presenting the repository as a reusable open-source package (the repository license is now [Apache-2.0](LICENSE)).

For **full roadmap completion**, Phase 14 also remains sequentially gated: OpsLens must be reconciled before RAGForge and later integrations are started unless that normative order is explicitly revised.

## Validate the repository

The default quality path is deterministic and credential-free:

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Frontend, observability and integration proofs are also isolated in dedicated GitHub Actions workflows. Live-provider tests remain opt-in by design.

## Repository map

| Path | Responsibility |
|---|---|
| `apps/gateway-api/` | FastAPI composition root and executable Gateway processes |
| `apps/gateway-console/` | Read-only React/TypeScript operational console |
| `packages/gateway-contracts/` | Provider-neutral public contracts |
| `packages/gateway-core/` | Domain, application services and provider/runtime adapters |
| `packages/gateway-client/` | Thin typed consumer SDK |
| `config/` | Secret-free registry, provider, client, policy and routing artifacts |
| `benchmarks/` | Deterministic evaluation and evidence |
| `deploy/observability/` | Collector, Tempo and Grafana local provisioning |
| `scripts/` | Quality, evidence and deterministic local-demo tooling |
| `tests/` | Unit, contract, integration and end-to-end validation |
| `docs/` | Architecture, security boundaries, roadmap and evidence contracts |

## Recommended reading

If you are evaluating the repository, start here:

- [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) — authoritative current checkpoint;
- [`docs/project/OPERATIONAL_READINESS.md`](docs/project/OPERATIONAL_READINESS.md) — local demo/operations readiness sequence;
- [`config/profiles/live-development/README.md`](config/profiles/live-development/README.md) — governed live-development runbook;
- [`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) — authorization boundary;
- [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) — provider and secret model;
- [`docs/project/GATEWAY_CONSOLE.md`](docs/project/GATEWAY_CONSOLE.md) — Console boundary;
- [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) — real local Grafana/Tempo proof;
- [`docs/project/EVALUATION.md`](docs/project/EVALUATION.md) — benchmark/evidence architecture.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
