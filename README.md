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
| --- | --- |
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

### 3. Your own project — the personal-default profile

`config/profiles/personal-default/` is the profile built for actually calling the Gateway from your
own applications, not a reviewed demo. It wires six providers (NVIDIA, Gemini, OpenAI, Anthropic, Groq,
OpenRouter) into the same authorized model group. NVIDIA is the practical default — it has a genuine
ranking preference reflecting its free tier — and deterministic ranking with automatic bounded fallback
picks whichever authorized deployment is actually eligible. Your application never selects a provider or
model; it only declares `workload`, `risk_level` and `data_classification`. See
["Quick start: call the Gateway from your own project"](#quick-start-call-the-gateway-from-your-own-project)
below and [`config/profiles/personal-default/README.md`](config/profiles/personal-default/README.md) for
the full picture, including its current one-workload/one-group scope and proof status per provider.

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
| --- | --- | --- |
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

## Quick start: call the Gateway from your own project

This is the actual "no friction" path: your application never picks a provider or model, only a
`workload`. It requires two running processes — the Policy Model Router (a separate repository) and the
Gateway — plus your consumer project pointed at the Gateway's URL and credential.

### 1. Install both services

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway
uv sync --frozen

git clone https://github.com/brunovicco/policy-model-router.git ../policy-model-router
cd ../policy-model-router
uv sync --frozen
cd ../governed-llm-gateway
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
GATEWAY_DEMO_API_KEY=replace-with-a-random-local-value
POLICY_ROUTER_DEMO_API_KEY=replace-with-a-random-local-value
NVIDIA_API_KEY=your-real-nvidia-key
GEMINI_API_KEY=your-real-gemini-key
OPENAI_API_KEY=your-real-openai-key
ANTHROPIC_API_KEY=your-real-anthropic-key
GROQ_API_KEY=your-real-groq-key
OPENROUTER_API_KEY=your-real-openrouter-key
```

`GATEWAY_DEMO_API_KEY`/`POLICY_ROUTER_DEMO_API_KEY` are just local shared secrets you invent; the six
provider keys are real credentials from each provider (NVIDIA has a free tier at
[build.nvidia.com](https://build.nvidia.com)). Adapter construction resolves every **enabled**
deployment's credential eagerly at startup, so a missing key fails the whole process closed. If you
don't have all six, disable the corresponding deployment(s) in
`config/profiles/personal-default/model_registry.yaml` (`enabled: false`) and remove the matching
binding from `provider_runtime.json` before starting the Gateway.

### 3. Start the Policy Router and the Gateway

```bash
cd governed-llm-gateway
set -a; source .env; set +a
uv run --frozen python scripts/personal_default_launcher.py
```

This one command starts both services (it assumes `../policy-model-router` from step 1; override with
`POLICY_MODEL_ROUTER_ROOT` otherwise) and tears both down on Ctrl+C. See
[`config/profiles/personal-default/README.md`](config/profiles/personal-default/README.md#running-it)
for the two-terminal manual equivalent and the `--smoke-test` switch.

### 4. Call it from your own project

Add the thin client (not published to PyPI; install straight from this repository):

```bash
uv add "governed-llm-gateway-client @ git+https://github.com/brunovicco/governed-llm-gateway.git#subdirectory=packages/gateway-client"
```

Your consumer project needs only two environment variables — never a provider key:

```dotenv
GOVERNED_LLM_GATEWAY_URL=http://127.0.0.1:8000
GOVERNED_LLM_GATEWAY_API_KEY=<the same GATEWAY_DEMO_API_KEY from step 2>
```

```python
import asyncio

from governed_llm_gateway_client import GatewayClient
from governed_llm_gateway_contracts import DataClassification, Message, MessageRole, RiskLevel


async def main() -> None:
    async with GatewayClient.from_env() as gateway:
        response = await gateway.generate(
            workload="rag.answer",
            messages=(
                Message(role=MessageRole.USER, content="Explain deterministic routing in one sentence."),
            ),
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            context_tokens_estimated=128,
            max_output_tokens=2000,
            provider_timeout_seconds=30.0,
        )

    print(response.content)
    # Decided by the Gateway's ranking, not by your code — NVIDIA under normal conditions,
    # automatically falling back to another authorized provider otherwise.
    print(response.execution.provider, response.execution.model, response.execution.deployment)


asyncio.run(main())
```

`max_output_tokens: 2000` above is not arbitrary: NVIDIA, Gemini and Groq's deployments in this
profile all spend a variable, sometimes large share of the budget on internal "thinking" before any
visible text — a tight budget like `128` measurably returns empty `response.content` a meaningful
fraction of the time (this was reproduced directly, not theoretical). Give reasoning-style models real
headroom, not a token count sized for the answer alone.

No provider SDK, no API key, and no `if provider == ...` branch belongs in your project. See
[`config/profiles/personal-default/README.md`](config/profiles/personal-default/README.md) for the full
runbook, current scope (`rag.answer` in the `balanced` model group) and per-provider proof status.

## The secret model

**Never put real API keys in Model Registry files, provider-runtime JSON, README files, logs, traces or Git.** Per-profile `.env` variables are covered inline in each quick start above; this section is the underlying model, not another list of the same names.

Provider credentials belong to the **Gateway deployment**, never to consumer applications. Every provider-runtime binding references a credential by name; a secret resolver turns that reference into the real value only inside the Gateway process:

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

For local development this is a sourced `.env`. For a real deployment, inject the same environment references through your orchestrator or secret manager instead — the resolver port is designed so AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault or another backend can replace it without changing consumer contracts.

A consumer application should receive only two variables, never a provider key:

```text
GOVERNED_LLM_GATEWAY_URL
GOVERNED_LLM_GATEWAY_API_KEY
```

It does not own provider/model selection or retry/fallback policy either. See [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) and [`docs/project/GATEWAY_CLIENT_AUTHENTICATION.md`](docs/project/GATEWAY_CLIENT_AUTHENTICATION.md) for the detailed trust boundary.

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
| --- | --- |
| Core platform — Phases 0–13 | **Complete** |
| Real-project integrations — Phase 14 | **In progress**: two integrations complete; OpsLens intentionally deferred |
| Local operational demo — OR-8 | **Complete** at the bounded operations-only local-demo scope |
| Live-inference development profile | **Implemented in PC-33**, extended to six providers; individually proven with real credentials: Gemini, OpenAI, Groq, NVIDIA. Anthropic reached the provider and failed on an account credit issue (not a config defect); OpenRouter not yet proven — see `docs/project/CURRENT_STATE.md` |
| Personal-default profile (your own projects) | **Implemented**; NVIDIA cost-preferred ranking proven against four other simultaneously-enabled competing providers — see `config/profiles/personal-default/README.md` |
| Broader operational-surface auth/security — OR-9 | **In progress** through bounded increments PC-34..PC-51 (see `docs/project/CURRENT_STATE.md`); production IAM/TLS/SSO, session handling, rate limiting and CSRF remain separate |
| Final screenshots/demo/product-readiness validation — OR-10 | **In progress**: reproducible e2e validation, a security review of the session's new code and of the existing HTTP/adapter surface (no findings in either pass), and this repository's consolidated [non-claims](#non-claims) section are done — see `docs/project/CURRENT_STATE.md`; screenshots/assets remain |
| Per-trace Console correlation | **Deferred pending an explicit reviewed correlation source** |

The authoritative checkpoint is [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md).

### What remains before calling the application finished

For a **portfolio/demo-ready live product path**, the main remaining work is:

1. ~~execute and record an opt-in real-provider proof through the PC-33 profile while keeping required CI credential-free~~ — done 2026-09-08 for the native Gemini deployment; the native OpenAI deployment in the same profile is not yet separately proven;
2. decide whether the current Console should gain a bounded live-request/provenance view and per-trace navigation, based only on real backend evidence;
3. complete the minimum OR-9 security hardening appropriate to the demonstrated operational surfaces and clearly separate production-only hardening;
4. complete OR-10: reproducible end-to-end validation, a security review of both the session's new code and the existing HTTP/adapter surface, and the consolidated [non-claims](#non-claims) section are done (see `docs/project/CURRENT_STATE.md`); screenshots/assets remain;
5. decide and cut the `v1.0.0` release boundary before presenting the repository as a reusable open-source package (the repository license is now [Apache-2.0](LICENSE)).

For **full roadmap completion**, Phase 14 also remains sequentially gated: OpsLens must be reconciled before RAGForge and later integrations are started unless that normative order is explicitly revised.

## Non-claims

Scattered non-claims already exist next to the specific feature they bound (each profile's own README, the OR-9/OR-10 rows above). This section is the single place to read all of them at once.

This repository does **not** claim to be:

- **Production infrastructure.** No TLS termination, no production IAM/OAuth/OIDC/workload identity, no browser session management, no rate limiting, no CSRF policy. OR-9's bounded PC-34–PC-51 hardening narrows specific gaps on the surfaces this repo actually exposes (non-storable responses, header sanitization, bounded bodies); it does not complete any of the above.
- **An SLA or uptime guarantee for any third-party model provider.** Provider pricing/model catalog entries are pinned metadata reviewed as of specific dates (see each profile's README) and can drift from the real provider catalog; NVIDIA/Groq/OpenRouter pricing in `personal-default` is an approximate placeholder pending a separately reviewed update.
- **A benchmark of real production traffic.** Everything in `benchmarks/` runs against public/synthetic fixtures with deterministic scoring, credential-free by default. It is evidence for ranking eligibility inside an already-authorized set, never authorization, and never a substitute for live user feedback.
- **A multi-tenant or remote deployment.** Every demonstrated path (`scripts/local_demo.py`, `live-development`, `personal-default`) runs as local loopback (`127.0.0.1`) processes an operator starts and stops. None of it has been exercised behind a real reverse proxy, load balancer, or public DNS name.
- **A complete Phase 14 rollout.** Two of five planned consumer integrations are complete; OpsLens is a validated-but-deliberately-deferred candidate pending its own repository stabilizing; RAGForge and the Verifiable AI Governance integration have not started, by explicit sequencing decision, not oversight.
- **A finished OR-9 or OR-10.** OR-9 is bounded hardening for the operational surfaces this repo already exposes, not a production security certification. OR-10's reproducible end-to-end validation and two security-review passes (this session's new code, and the existing HTTP/adapter surface) are done; screenshots/assets remain open.

What every governed-inference proof cited in `docs/project/CURRENT_STATE.md` **is**: a real request, with real operator-supplied provider credentials, executed through the full Policy Router → Gateway → provider chain, with the terminal routing/execution evidence inspected — not a mock, not a stub, and not a credential-free simulation.

## Validate the repository

The default quality path is deterministic and credential-free:

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Frontend, observability and integration proofs are also isolated in dedicated GitHub Actions workflows. Live-provider tests remain opt-in by design.

## Repository map

| Path | Responsibility |
| --- | --- |
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
- [`config/profiles/personal-default/README.md`](config/profiles/personal-default/README.md) — how to call the Gateway from your own project, NVIDIA cost-preferred ranking;
- [`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) — authorization boundary;
- [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) — provider and secret model;
- [`docs/project/GATEWAY_CONSOLE.md`](docs/project/GATEWAY_CONSOLE.md) — Console boundary;
- [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) — real local Grafana/Tempo proof;
- [`docs/project/EVALUATION.md`](docs/project/EVALUATION.md) — benchmark/evidence architecture.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
