# Governed live-inference development profile

This profile is an explicit opt-in development/demo deployment for exercising the real authority and execution chain:

```text
consumer
  -> Gateway client authentication
  -> Policy Model Router (PDP)
  -> authorized model group: balanced
  -> Gateway eligibility + deterministic ranking
  -> provider execution
  -> normalized SSE + execution provenance
```

It does **not** change the repository's default fail-closed artifacts. Provider credentials alone still cannot enable inference.

## Scope and non-claims

The profile is intentionally bounded to:

- client: `gateway-demo`;
- environment: `development`;
- workload: `rag.answer`;
- minimum risk: `low`;
- minimum data classification: `public`;
- authorized logical group supplied by the external PDP: `balanced`;
- providers: native Gemini and native OpenAI Responses;
- concrete deployments: `gemini-3.8-flash` and `gpt-5.6-luna`;
- metadata-only Gateway observability when OTLP is enabled.

This is not a production authentication, TLS, IAM, secret-management, provider-SLA, or production-readiness claim.

The two ranking entries deliberately use identical neutral static component scores and identical planning latency values. They are configuration inputs for a reproducible development tie-break, **not observed quality, availability, latency, or benchmark evidence**. Current provider pricing metadata is retained separately in the Model Registry for cost eligibility.

## Required server-side environment variables

Set these only in your local shell, `.env`, or deployment secret backend. Never commit the values.

```dotenv
GATEWAY_DEMO_API_KEY=
POLICY_ROUTER_DEMO_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
```

`GATEWAY_DEMO_API_KEY` is the credential a consumer presents to the Gateway. The other three values stay server-side.

The Python runtimes do not automatically load `.env`. If you use one locally:

```bash
set -a
source .env
set +a
```

## 1. Start Policy Model Router

PC-33 is compatible with the generalized Policy Model Router contract introduced by `brunovicco/policy-model-router` commit `889b41b3276c453c31fff125cff0397c6c0a4de6` or a later compatible revision.

From that repository:

```bash
export APP_ENV=development
export ROUTING_POLICY_PATH="$PWD/examples/policies/gateway-generic.yaml"
export API_KEYS="$(python - <<'PY'
import json
import os
print(json.dumps({"gateway-demo": os.environ["POLICY_ROUTER_DEMO_API_KEY"]}))
PY
)"

uv run uvicorn policy_model_router.entrypoints.http:app \
  --host 127.0.0.1 \
  --port 8001
```

The Gateway accepts plaintext Policy Router HTTP only for a **literal loopback IP address**. `localhost`, private-LAN addresses and remote HTTP endpoints remain rejected. Non-loopback Policy Router deployments still require HTTPS.

The reviewed generic Policy Router example maps `rag.answer` to `balanced`; the Gateway cannot widen that decision.

## 2. Optional: start local observability

From the Gateway repository:

```bash
docker compose -f compose.observability.yml up -d otel-collector tempo grafana
```

Grafana is then available at `http://127.0.0.1:3000` and the Collector accepts OTLP/HTTP on loopback port `4318`.

## 3. Start the governed Gateway

From the Gateway repository root:

```bash
uv sync --frozen

uv run --frozen --package governed-llm-gateway-api governed-llm-gateway \
  --deployment-root "$PWD" \
  --model-registry-path config/profiles/live-development/model_registry.yaml \
  --provider-runtime-path config/profiles/live-development/provider_runtime.json \
  --client-auth-path config/profiles/live-development/client_auth.json \
  --operations-access-path config/profiles/live-development/operations_access.json \
  --policy-router-path config/profiles/live-development/policy_router.json \
  --ranking-policy-path config/profiles/live-development/ranking_policy.yaml \
  --default-max-latency-ms 60000 \
  --default-max-cost-usd 0.05 \
  --host 127.0.0.1 \
  --port 8000
```

To export metadata-only traces into the optional local observability stack, add the process-owned OTLP flags documented in `docs/project/LOCAL_OBSERVABILITY.md` for the current `a2a-otel-kit` configuration.

Startup validates all no-secret artifacts and cross-artifact invariants before resolving Gateway, PDP, or provider credentials. A missing required credential fails closed.

`operations_access.json` is a separate secret-free visibility policy. It grants Operations read visibility only to the authenticated `gateway-demo/development` identity and is cross-validated against `client_auth.json`. The same presented `GATEWAY_DEMO_API_KEY` is authenticated once, but Operations visibility and inference authorization remain independent policy decisions. Operations access cannot widen PDP-authorized model groups, deployment eligibility, ranking, retry, fallback, or provider execution.

## 4. Optional: connect the Gateway Console and run one bounded request

The Console loads the existing read-only Operations view and can submit one bounded provider-neutral inference request through the governed `/v1/generate` boundary.

With the Gateway from step 3 running, start the Vite Console from the repository root:

```bash
cd apps/gateway-console
npm ci
npm run dev
```

Open `http://127.0.0.1:5173` and enter the current value of `GATEWAY_DEMO_API_KEY` into the `X-Gateway-API-Key` field. The Vite development server proxies only relative `/v1` requests to `http://127.0.0.1:8000`; the credential stays in the page's React state and is cleared on disconnect. Do not place the credential in frontend configuration, URLs, browser storage, or source files.

A successful **Connect** proves only the explicit Operations visibility grant for the authenticated identity. It does not prove or create inference authorization. Selecting **Run governed request** separately submits a bounded `rag.answer` / `low` / `public` request and lets client-auth plus the Policy Router decide whether inference is authorized.

The Console request surface exposes a prompt and reviewed request ceilings only. It contains no provider, model, deployment, ranking, retry, or fallback selector. Provider and Policy Router credentials stay server-side. The browser displays provider/model/deployment identity only after the normalized SSE stream terminates with validated routing provenance, exactly one normalized usage result, and successful execution evidence whose identity is consistent with routing and fallback provenance.

Prompt, completion, routing evidence, usage, and execution evidence remain in React memory and are reset on disconnect; the Console does not persist them in browser storage, cookies, URLs, or frontend configuration. The local Grafana link remains generic because the current inference response does not expose a real backend trace ID, so the Console makes no per-request trace-correlation claim.

The Console implementation and credential-free CI do not by themselves certify live-provider execution. Record a successful explicit operator run against the credential-backed local profile separately before claiming portfolio/demo-ready live inference.

## 5. Execute one governed request with the thin SDK

The canonical consumer contract contains only the Gateway URL and Gateway credential:

```bash
export GOVERNED_LLM_GATEWAY_URL='http://127.0.0.1:8000'
export GOVERNED_LLM_GATEWAY_API_KEY="${GATEWAY_DEMO_API_KEY}"
```

The thin client permits plaintext HTTP only for a **literal loopback IP address** so this local profile can use the same SDK contract as a deployed consumer. `http://localhost:8000`, private-LAN HTTP and remote HTTP remain rejected. Non-loopback deployments must use HTTPS.

Run one provider-neutral request from the Gateway repository root:

```bash
uv run --frozen --package governed-llm-gateway-client python - <<'PY'
import asyncio

from governed_llm_gateway_client import GatewayClient
from governed_llm_gateway_contracts import (
    DataClassification,
    Message,
    MessageRole,
    RiskLevel,
)


async def main() -> None:
    async with GatewayClient.from_env() as gateway:
        response = await gateway.generate(
            workload="rag.answer",
            messages=(
                Message(
                    role=MessageRole.USER,
                    content="Answer in one sentence: what does deterministic model routing mean?",
                ),
            ),
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            context_tokens_estimated=128,
            max_output_tokens=128,
            provider_timeout_seconds=30.0,
        )

    if response.execution is None:
        raise RuntimeError("successful response is missing execution provenance")

    print(response.content)
    print(
        {
            "request_id": str(response.request_id),
            "status": response.status.value,
            "provider": response.execution.provider,
            "model": response.execution.model,
            "deployment": response.execution.deployment,
            "latency_ms": response.execution.latency_ms,
        }
    )


asyncio.run(main())
PY
```

The SDK performs no provider selection and receives no provider or Policy Router credential. It aggregates the normalized SSE stream and requires terminal routing and execution provenance before returning a successful `GatewayResponse`.

### Raw SSE alternative

For transport-level inspection, the same governed request can be observed with `curl` using only the Gateway credential:

```bash
REQUEST_ID="$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"

curl --no-buffer \
  --request POST 'http://127.0.0.1:8000/v1/generate' \
  --header 'Content-Type: application/json' \
  --header "X-Gateway-API-Key: ${GATEWAY_DEMO_API_KEY}" \
  --data "{
    \"schema_version\": \"1.0\",
    \"request_id\": \"${REQUEST_ID}\",
    \"workload\": \"rag.answer\",
    \"risk_level\": \"low\",
    \"data_classification\": \"public\",
    \"stream\": true,
    \"requirements\": {
      \"tool_calling\": false,
      \"structured_output\": false,
      \"vision\": false,
      \"min_context_tokens\": 0
    },
    \"limits\": {
      \"max_latency_ms\": 60000,
      \"max_cost_usd\": \"0.05\"
    },
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"Answer in one sentence: what does deterministic model routing mean?\"
      }
    ],
    \"context_tokens_estimated\": 128,
    \"max_output_tokens\": 128,
    \"provider_timeout_seconds\": 30.0
  }"
```

The SSE stream is backend evidence. Inspect the terminal routing/execution fields rather than inferring provider selection in the client. Retry/fallback may move only to another eligible deployment already inside the PDP-authorized `balanced` group.

## 6. Run the repeatable opt-in smoke harness

After the Policy Router and Gateway are already running, and after exporting only the two consumer variables from step 5, run:

```bash
uv run --frozen --package governed-llm-gateway-client \
  python scripts/live_development_smoke.py --live
```

The `--live` flag is mandatory. Omitting it exits before any network call. The harness uses `GatewayClient.from_env()` and therefore reads only:

```text
GOVERNED_LLM_GATEWAY_URL
GOVERNED_LLM_GATEWAY_API_KEY
```

It does not inspect `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `POLICY_ROUTER_DEMO_API_KEY`. Those values remain server-side prerequisites for the already-running Gateway/PDP processes.

A successful run prints exactly one metadata-only JSON object containing the request ID, authorized model group, provider/model/deployment identity, API family when present, attempt/fallback position, latency and normalized token counts. It does **not** print the prompt or completion text and it accepts either reviewed PC-33 deployment inside the PDP-authorized `balanced` group.

The harness implementation and credential-free unit tests do not by themselves certify live-provider execution. Record a successful explicit operator run separately before claiming portfolio/demo-ready live inference.

## 7. Teardown

Stop the Gateway and Policy Router processes with `Ctrl+C`. If you started the observability stack:

```bash
docker compose -f compose.observability.yml down --volumes --remove-orphans
```

## Provider metadata sources

The profile pins reviewed model/pricing metadata as of 2026-09-08:

- OpenAI model catalog: `https://platform.openai.com/docs/models`
- Google Gemini 3.8 Flash model: `https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash`
- Google Gemini API pricing: `https://ai.google.dev/gemini-api/docs/pricing`

Provider catalog/pricing metadata is time-sensitive. Updating it requires a separately reviewed registry change; runtime discovery does not silently mutate this profile.
