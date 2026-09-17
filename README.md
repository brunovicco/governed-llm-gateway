# Governed LLM Gateway

**English** | [Português (Brasil)](README.pt-BR.md)

[![quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml)
[![console-quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml)
[![observability-compose](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml)

> A provider-neutral LLM execution gateway that keeps **authorization, model selection, provider credentials, resilience and runtime evidence** out of application code.

An application declares a workload and its requirements, while the Gateway decides which authorized
model serves it, calls the provider and returns the answer with the evidence of how it was chosen. No
provider SDK, no API key and no `if provider == ...` in the consumer.

```text
Application/Agent
        │
        │ workload + requirements + Gateway credential
        ▼
Policy Model Router (PDP)
        │ selected_model_group (one authorized logical model group)
        ▼
Governed LLM Gateway (PEP)
        ├─ eligibility + deterministic ranking
        ├─ health/circuit breaker
        ├─ bounded retry + safe fallback
        ├─ provider translation
        └─ provenance + OpenTelemetry
        ▼
LLM providers
```

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The Gateway may narrow an authorized set. It may never widen it.

[One real governed request](#one-real-governed-request) · [What it gives you](#what-it-gives-you) · [How it works](#how-it-works) · [Running it](#running-it) · [Calling it from your own project](#calling-it-from-your-own-project) · [Repository map](#repository-map) · [Scope](#scope) · [Where to read next](#where-to-read-next)

## One real governed request

The caller declared only `workload`, `risk_level` and `data_classification`. Policy authorized the
`balanced` model group, deterministic ranking selected the deployment inside it, and the provider call,
the retry/fallback budget and the trace emission all stayed server-side.

![Gateway Console after a real governed request: authorized group "balanced" under policy 1.0.0, selected provider nvidia, model nvidia/nemotron-3-super-120b-a12b, deployment nvidia-nemotron-3-super-dev at attempt 1 with fallback 0, 1644 ms and 149 normalized tokens, plus routing decision, policy decision, registry digest, ranking policy, score snapshot, fallback sequence and trace ID](docs/assets/screenshots/console-trace-evidence.png)

A real local run of the [`personal-default`](config/profiles/personal-default/README.md) profile with
operator-supplied credentials. Every field is terminal execution evidence: routing and policy decision
IDs, registry and ranking digests, the score snapshot that ranked the candidates, the fallback sequence
actually taken, and the trace ID emitted. The Console's *View this request's trace in Grafana* link
resolves to that exact trace - the matching waterfall is in
[`docs/project/GATEWAY_CONSOLE.md`](docs/project/GATEWAY_CONSOLE.md).

## What it gives you

| Capability | What it means in practice |
| --- | --- |
| **One integration point** | Consumers speak one provider-neutral contract. Adding or replacing a deployment requires a compatible adapter/runtime binding, registry configuration and approved ranking coverage; disabling it narrows registry eligibility. Consumers need no provider-specific edit. |
| **Credentials in one place** | Provider keys belong to the Gateway deployment. Rotating one is a single change in a single place, with no consumer redeploy and no key to find scattered across repositories. |
| **Authorization that holds** | Policy returns one authorized logical model group for the request. The Gateway can only narrow its deployment set, never widen it, and fails closed when policy is unreachable. |
| **Deterministic selection** | Ranking inside the authorized set is reproducible and explainable: same inputs, same deployment, with the reasons and the digests that produced it attached. |
| **Resilience without surprises** | Health tracking, circuit breaking, bounded retry and fallback - all restricted to already-authorized deployments, and shareable across replicas so behavior stays deterministic when you scale out. |
| **Spend accounting components** | Estimated per-client/workload spend from pinned pricing and reported usage. The guard checks observed spend, not reservations, and is not wired into current serving; see [scope and concurrency limits](docs/project/SPEND_ACCOUNTING.md). |
| **Evidence for every request** | Terminal execution provenance plus metadata-only OpenTelemetry: what was authorized, what was selected, what actually ran, and the trace it emitted. |
| **Interoperability both ways** | Native OpenAI Responses, Anthropic Messages and Gemini adapters, explicit OpenAI-compatible adapters, and an OpenAI-shaped ingress so an existing client can repoint its `base_url` here. |

## How it works

1. The consumer authenticates to the Gateway and declares a workload, not a model.
2. The Policy Model Router returns one `selected_model_group`, the request's complete logical-group authorization.
3. The Gateway intersects that authority with registry capability, environment, data/risk and runtime eligibility.
4. Deterministic ranking selects inside what remains; retry stays on the same deployment and fallback moves only to another already-ranked eligible deployment in that same group. There is no cross-group fallback.
5. Provider-specific requests and responses are normalized behind adapters.
6. Terminal provenance and metadata-safe telemetry describe what happened. They never authorize a future request.

An optional governance authority can narrow further what policy authorized; it can never expand it.
The exact contract is in
[`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md).

The Gateway is deliberately not an agent framework, a RAG framework, an MCP tool executor, a
prompt-management platform or an API-management product. It can normalize a tool call, but the
application runtime keeps ownership of tool authorization and side effects.

### Provider credentials in one place

Provider credentials are a deployment concern. A provider-runtime binding references a credential by
name, and a server-side resolver turns that reference into the real value only inside the Gateway
process - a sourced `.env` locally, or the same references injected from AWS Secrets Manager, Azure Key
Vault, GCP Secret Manager or Vault in a real deployment. Rotating a provider key is therefore one
change in one place: no consumer ships a new build, and no repository holds a provider secret.

A consumer application receives exactly two variables (`GOVERNED_LLM_GATEWAY_URL` and
`GOVERNED_LLM_GATEWAY_API_KEY`) and owns no provider, model, retry or fallback policy. The trust
boundary is specified in
[`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) and
[`docs/project/GATEWAY_CLIENT_AUTHENTICATION.md`](docs/project/GATEWAY_CLIENT_AUTHENTICATION.md).

## Running it

Three configurations, in increasing order of what they require:

| Configuration | Requires | What it shows |
| --- | --- | --- |
| **Local operations demo** | Nothing but the toolchain | The read-only Operations API, the Console, and the Collector → Tempo → Grafana chain. Exposes no inference route, so it needs no credential. |
| [**`live-development`**](config/profiles/live-development/README.md) | An external policy router and provider credentials | One reviewed consumer, `rag.answer`, neutral static ranking and six deployments in `balanced`: three native adapters and three OpenAI-compatible bindings. |
| [**`personal-default`**](config/profiles/personal-default/README.md) | The same, plus your own keys | Six providers (NVIDIA, Gemini, OpenAI, Anthropic, Groq, OpenRouter), 14 deployments across five registry groups. The active approved ranking covers only `rag.answer` in `balanced`, with NVIDIA cost-preferred. |

Registry wiring is not active workload coverage. The other eight `personal-default` workloads have
configuration and historical live proofs, but are not served by the currently pinned ranking artifact;
they fail closed with `ranking_policy_unavailable`. Enabling them requires a separately reviewed
approved ranking artifact and a matching runtime pin, not just provider credentials.

The checked-in baseline is fail-closed: no enabled deployment, no provider binding, policy disabled,
no live principal. Adding a provider key by itself does not enable inference - a profile has to be
activated explicitly, so operational availability never becomes authorization by accident.

### Prerequisites

Python **3.13+** (3.13–3.14 supported), [uv](https://docs.astral.sh/uv/), Docker with Compose, and
Node.js 24 with npm.

### Local operations demo

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway
cp .env.example .env
```

Set `GATEWAY_LOCAL_DEMO_API_KEY` in `.env` to any random local value. The Python runtime does not load
`.env` by itself, so export it first:

```bash
set -a; source .env; set +a
uv run --frozen python scripts/local_demo.py
```

| Surface | URL |
| --- | --- |
| Gateway Console | `http://127.0.0.1:5173` |
| Gateway readiness | `http://127.0.0.1:8000/readyz` |
| Operations API | `http://127.0.0.1:8000/v1/ops/overview` |
| Grafana | `http://127.0.0.1:3000` |

`Ctrl+C` stops it; the launcher owns cleanup of its child processes and its Compose project. For an
automated startup/readiness/teardown proof, add `--smoke-test`.

| Console - before connecting | Console - connected, operations-only baseline |
| --- | --- |
| ![Gateway Console, disconnected](docs/assets/screenshots/gateway-console-disconnected.png) | ![Gateway Console, connected, showing the real operations-only baseline: phase2-empty registry, 0 deployments, 0 tracked processes](docs/assets/screenshots/gateway-console-connected.png) |

![Local Grafana trace dashboard, provisioned by this demo](docs/assets/screenshots/grafana-trace-dashboard.png)

Real screenshots of this exact demo: the connected view is the genuine fail-closed baseline
(`phase2-empty` registry, zero deployments), and the dashboard has no rows because this mode exposes no
inference route to produce a trace.

Claude Code and Codex can use the same governed coordinator through native-shaped
`POST /v1/messages` and `POST /v1/responses` adapters. Their `model` value is only a compatibility
alias: it never selects or authorizes a concrete model. The concrete provider/model still comes only
from the authenticated client context, external PDP's authorized set and Gateway eligibility/ranking.
See the
[protocol and multimodal guide](docs/project/PROTOCOL_MULTIMODAL_GATEWAY.md) for the supported subset,
security boundaries and exact client configuration.

### Client compatibility

| Client / protocol | Evidence-backed status |
| --- | --- |
| Native Gateway API | Supported; existing compatibility retained |
| Anthropic Messages API | Contract-tested stateless subset |
| Claude Code | Bounded live CLI E2E through Anthropic: text, streaming, `Read`/`Bash`, local tool execution and tool-result continuation ([PR #258](https://github.com/brunovicco/governed-llm-gateway/pull/258)) |
| OpenAI Responses API | Contract-tested stateless subset |
| Codex | Current HTTP request/replay and native SSE subset contract-tested against official client source; no live CLI claim |
| Images | HTTPS references and bounded inline input supported where the selected deployment/adapter permits |
| Audio/documents | Canonical and capability-gated; fail closed unless registry and adapter explicitly permit them |
| Function tools/results | Ordinary calls and text results supported; application remains responsible for execution |
| Streaming | Provider stream → canonical events → protocol-native SSE |

The Claude Code proof used an approved ranking path covering `agent.tool-use`; it does not make that
workload operational under the stock `personal-default` `rag.answer` artifact. Codex remains
contract-tested only, without a live CLI claim. Unsupported protocol features remain fail-closed;
see the [protocol guide](docs/project/PROTOCOL_MULTIMODAL_GATEWAY.md#claude-code) for the precise limits.

### Container

`Dockerfile` builds the Gateway API and `compose.gateway.yml` runs it. The image carries code only - no
registry, no provider runtime, no policy configuration and no default command - so a container started
without explicit artifact flags exits non-zero instead of serving something unconfigured.

```bash
docker build --tag governed-llm-gateway:local .

export GATEWAY_LOCAL_DEMO_API_KEY=any-random-local-value
docker compose -f compose.gateway.yml up gateway-operations
```

That is the same credential-free operations-only surface. It binds `127.0.0.1` inside the container, so
the container's own `HEALTHCHECK` reaches it and nothing outside does. Governed inference runs under the
`governed` compose profile. It builds this Gateway and pulls a reviewed Policy Model Router release by
immutable digest, so normal startup needs only this repository plus local gateway/PDP/provider
credentials. Exact commands are in
[`docs/project/CONTAINER_DEPLOYMENT.md`](docs/project/CONTAINER_DEPLOYMENT.md).

## Calling it from your own project

Two services run: the external Policy Model Router and the Gateway, but normal governed startup needs
only this repository. Compose pulls the reviewed Router image by immutable digest; your application
talks only to the Gateway URL and credential. A sibling Router checkout is needed only for explicit
cross-repository development/composition work.

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway
cp .env.example .env
```

Put the two local shared secrets you created, plus the provider keys you actually have, in `.env`:

```dotenv
GATEWAY_DEMO_API_KEY=...
POLICY_ROUTER_DEMO_API_KEY=...
NVIDIA_API_KEY=...
GEMINI_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
```

A missing key for an **enabled** deployment fails the process closed at startup. With fewer than six
providers, disable the others in `model_registry.yaml` (`enabled: false`) and remove their bindings
from `provider_runtime.json` first. NVIDIA has a free tier at [build.nvidia.com](https://build.nvidia.com).

```bash
set -a; source .env; set +a
export APPROVED_RANKING_ARTIFACT_ID=sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad
docker compose -f compose.gateway.yml --profile governed up --build gateway policy-model-router
```

The normal path above does not require a Policy Model Router source checkout. The source-based
`scripts/personal_default_launcher.py` and `compose.pdp-composition.yml` remain available for
cross-repository development. This startup selects `approved_ranking.json`, which covers only
`rag.answer`; it does not activate the other registry workloads. Then add the client to your own
project - not published to PyPI, install straight from this repository:

```bash
uv add "governed-llm-gateway-client @ git+https://github.com/brunovicco/governed-llm-gateway.git#subdirectory=packages/gateway-client"
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
    # Chosen by the Gateway's ranking, not by your code.
    print(response.execution.provider, response.execution.model, response.execution.deployment)


asyncio.run(main())
```

`max_output_tokens=2000` is not arbitrary: the NVIDIA, Gemini and Groq deployments here spend a
variable, sometimes large share of the budget on internal reasoning before any visible text, so a tight
budget returns empty content a measurable fraction of the time. The full runbook, the current scope
(`rag.answer` in `balanced`) and the per-provider proof status are in
[its README](config/profiles/personal-default/README.md).

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
| `Dockerfile`, `compose.gateway.yml` | Container image and deployment for the Gateway API |
| `deploy/observability/` | Collector, Tempo and Grafana local provisioning |
| `scripts/` | Quality, evidence and deterministic local-demo tooling |
| `tests/` | Contract tests plus opt-in integration proofs against real servers |
| `docs/` | Architecture, security boundaries and evidence contracts - start at [`docs/project/README.md`](docs/project/README.md) |

The default quality path is deterministic and credential-free:

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Frontend, observability, container and real-server integration proofs run in dedicated GitHub Actions
workflows. Live-provider tests stay opt-in by design.

## Scope

A reference implementation built to be run and read, not a hosted product:

- **Not production infrastructure**: no TLS termination, production IAM/SSO, browser session handling, rate limiting or CSRF policy. Every demonstrated path runs as local loopback processes.
- **Not an SLA over any provider**: pricing and catalog entries are pinned metadata reviewed on a date and can drift from the live provider catalog.
- **Benchmarks are fixtures, not production traffic**: they inform ranking eligibility inside an already-authorized set - never authorization, and never a substitute for live user feedback.
- **Provider proofs are real**: every governed-inference proof cited in the checkpoint log is a real request, with credentials, through the full policy → Gateway → provider chain, with the terminal evidence inspected. Not a mock, not a stub, not a credential-free simulation.

Phase status, deferred scope and the dated evidence behind each claim live in
[`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) and
[`docs/project/CHECKPOINT_LOG.md`](docs/project/CHECKPOINT_LOG.md).

## Where to read next

Every document under `docs/project/` is grouped and explained in its
[documentation index](docs/project/README.md). The shortest paths through it:

- **Architecture** - [`ARCHITECTURE.md`](docs/project/ARCHITECTURE.md), the authorization contract in [`PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md), and the decisions behind both in [`docs/adr/`](docs/adr/);
- **Security and secrets** - [`SECURITY_MODEL.md`](docs/project/SECURITY_MODEL.md) and [`PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md);
- **Deployment** - [`CONTAINER_DEPLOYMENT.md`](docs/project/CONTAINER_DEPLOYMENT.md), [`SHARED_RUNTIME_STATE.md`](docs/project/SHARED_RUNTIME_STATE.md) and [`SPEND_ACCOUNTING.md`](docs/project/SPEND_ACCOUNTING.md);
- **Evidence** - [`GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) and [`EVALUATION.md`](docs/project/EVALUATION.md);
- **Release history** - [`CHANGELOG.md`](CHANGELOG.md).

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
