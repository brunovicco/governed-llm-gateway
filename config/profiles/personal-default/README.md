# Personal default profile

This profile is the operator's actual day-to-day governed deployment, not a reviewed demo. It reuses
the same authority chain as the `live-development` profile — an external Policy Model Router still
decides the authorized model group; the Gateway never self-authorizes:

```text
consumer (any project)
  -> Gateway client authentication
  -> Policy Model Router (PDP)
  -> authorized model group: balanced
  -> Gateway eligibility + deterministic ranking (NVIDIA cost-preferred)
  -> provider execution
  -> normalized SSE + execution provenance
```

## Why this profile exists

The point of this repository is that a consumer project never has to carry provider credentials,
pick a provider, or pick a model. It declares a `workload` (currently `rag.answer`), a `risk_level`
and a `data_classification`; the Policy Router decides the authorized model group, and the Gateway's
deterministic ranking picks one already-authorized deployment.

This profile wires six deployments into the `balanced` group: NVIDIA (native `openai-compatible`),
Google Gemini, OpenAI, Anthropic, Groq and OpenRouter. NVIDIA is the practical default because its
configured tier has zero marginal cost (`pricing.input_usd_per_million_tokens` /
`output_usd_per_million_tokens` are both `"0.00"`); its `cost` ranking score is set to `"1.00"` against
`"0.50"` for the other five, so it wins the deterministic ranking under normal conditions
(`0.60` total score vs `0.50` for everyone else at equal weights). This is a genuine, defensible
preference — not the reproducible-tie-break neutral scoring used by the `live-development` profile.

Fallback stays automatic and within Phase 6's existing bounded rules: if NVIDIA is disabled, missing
its credential, unhealthy, or hits a retryable failure, ranking/fallback moves to the next
already-authorized eligible deployment (Gemini, OpenAI, Anthropic, Groq, or OpenRouter, in ranking
order) without ever widening authorization outside the PDP-granted `balanced` group.

## Current scope and known limitations

- All six deployments currently sit in one model group, `balanced`, serving one workload,
  `rag.answer`. The Policy Router's `examples/policies/gateway-generic.yaml` already defines several
  other model groups/workloads (`fast-small`, `reasoning-strong`, `agentic-strong`,
  `structured-fast`); this profile does not yet wire deployments into them. Extending to those is a
  natural next increment, not something this profile claims today.
- Individually proven with real operator credentials: NVIDIA, Gemini, OpenAI, Groq. Anthropic reached
  the provider and failed closed on an account credit-balance issue (not a config defect); OpenRouter
  is wired but unproven pending real request evidence. See `docs/project/CURRENT_STATE.md`.
- This is still a local/loopback profile: the Policy Router and Gateway run as local processes on
  `127.0.0.1`. It is not a production TLS/IAM/SLA claim, and it does not change the repository's
  fail-closed default `config/` artifacts used by CI and by a fresh clone.

## Required server-side environment variables

Set these only in your local shell, `.env`, or a real secret manager. Never commit the values.

```dotenv
GATEWAY_DEMO_API_KEY=
POLICY_ROUTER_DEMO_API_KEY=
NVIDIA_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
```

Booting the full six-deployment profile requires all six provider credentials to resolve, because
adapter construction resolves every enabled deployment's credential eagerly at startup — a missing
credential fails the whole process closed rather than silently dropping one deployment. If you only
have some of these credentials, disable the corresponding deployment(s) in `model_registry.yaml`
(`enabled: false`) and remove the matching binding from `provider_runtime.json`.

## Running it

Startup is identical to the `live-development` profile (see
[`../live-development/README.md`](../live-development/README.md) for the full step-by-step,
including starting the Policy Model Router and the observability stack), just point the Gateway CLI
flags at this directory instead:

```bash
uv run --frozen --package governed-llm-gateway-api governed-llm-gateway \
  --deployment-root "$PWD" \
  --model-registry-path config/profiles/personal-default/model_registry.yaml \
  --provider-runtime-path config/profiles/personal-default/provider_runtime.json \
  --client-auth-path config/profiles/personal-default/client_auth.json \
  --operations-access-path config/profiles/personal-default/operations_access.json \
  --policy-router-path config/profiles/personal-default/policy_router.json \
  --ranking-policy-path config/profiles/personal-default/ranking_policy.yaml \
  --default-max-latency-ms 60000 \
  --default-max-cost-usd 0.05 \
  --host 127.0.0.1 \
  --port 8000
```

A consumer project then needs only the canonical two-variable contract:

```dotenv
GOVERNED_LLM_GATEWAY_URL=http://127.0.0.1:8000
GOVERNED_LLM_GATEWAY_API_KEY=<the same GATEWAY_DEMO_API_KEY>
```

and calls `GatewayClient.from_env().generate(workload="rag.answer", ...)` — no provider, model, or
deployment selection.
