# Personal default profile

This profile is the operator's actual day-to-day governed deployment, not a reviewed demo. It reuses
the same authority chain as the `live-development` profile — an external Policy Model Router still
decides the authorized model group; the Gateway never self-authorizes:

```text
consumer (any project)
  -> Gateway client authentication
  -> Policy Model Router (PDP)
  -> authorized model group: balanced | fast-small | structured-fast | reasoning-strong | agentic-strong
  -> Gateway eligibility + deterministic ranking (NVIDIA cost-preferred in balanced)
  -> provider execution
  -> normalized SSE + execution provenance
```

## Why this profile exists

The point of this repository is that a consumer project never has to carry provider credentials,
pick a provider, or pick a model. It declares a `workload`, a `risk_level` and a
`data_classification`; the Policy Router decides the authorized model group, and the Gateway's
deterministic ranking picks one already-authorized deployment.

This profile wires 14 deployments across five model groups, reusing the same six provider bindings
(NVIDIA, Google Gemini, OpenAI, Anthropic, Groq, OpenRouter — no new credentials needed for any of it):

| Workload | Model group | Deployments |
| --- | --- | --- |
| `rag.answer` | `balanced` | NVIDIA (cost-preferred), Gemini, OpenAI, Anthropic, Groq, OpenRouter |
| `classification.simple` | `fast-small` | Groq, NVIDIA |
| `extraction.structured` | `structured-fast` | OpenAI, Gemini |
| `reasoning.complex`, `security.analysis`, `code.generate`, `code.review` | `reasoning-strong` | Anthropic, OpenAI |
| `agent.orchestration`, `agent.tool-use` | `agentic-strong` | OpenAI, Anthropic |

`structured-fast`, `reasoning-strong` and `agentic-strong` only use OpenAI/Anthropic/Gemini — the
three adapters with real, verified provider-native structured-output and tool-calling translation
(`native_structured_output=True, native_tool_calling=True` in `openai_responses.py`,
`anthropic.py`, `gemini.py`). Groq/NVIDIA/OpenRouter keep `supports_native_structured_output` and
`supports_native_tool_calling` at `false` in `provider_runtime.json` because that has not been
verified against those specific APIs; they only serve `fast-small`/`balanced`, which don't need it.

Within `balanced`, NVIDIA is the practical default because its configured tier has zero marginal cost
(`pricing.input_usd_per_million_tokens` / `output_usd_per_million_tokens` are both `"0.00"`); its
`cost` ranking score is set to `"1.00"` against `"0.50"` for the other five, so it wins the
deterministic ranking under normal conditions (`0.60` total score vs `0.50` for everyone else at
equal weights). This is a genuine, defensible preference — not the reproducible-tie-break neutral
scoring used elsewhere. The other four groups use plain neutral scores (like `live-development`)
since there isn't yet a similar cost/quality basis to prefer one deployment over the other within
them.

Fallback stays automatic and within Phase 6's existing bounded rules: ranking/fallback moves only to
the next already-authorized eligible deployment inside the *same* PDP-granted model group, and never
after a permanent (non-retryable) failure.

## Current scope and known limitations

- Individually proven end to end (real operator credentials, through the full Policy Router + Gateway
  chain): NVIDIA, Gemini, OpenAI, Groq and OpenRouter in `balanced`; Groq/NVIDIA in `fast-small`;
  OpenAI/Gemini in `structured-fast`; OpenAI in `reasoning-strong` and `agentic-strong`. Anthropic
  reaches the provider and fails closed on an account credit-balance issue in every group it's wired
  into (not a config defect — confirmed by direct API diagnosis). The full six-deployment profile
  (all of `balanced` enabled at once, nothing disabled) has been booted end to end with
  `scripts/personal_default_launcher.py`, with NVIDIA winning against all five other providers
  simultaneously eligible (`rejected_candidates: null`). See `docs/project/CURRENT_STATE.md`.
- `security.analysis`, `code.generate`, `code.review` (sharing `reasoning-strong`'s deployments) were
  not individually exercised with a live request.
- Real structured-output and real tool-calling requests were both proven end to end (a genuine JSON
  schema through `extraction.structured`/Gemini, and a real `ToolDefinition` + tool call through
  `agent.tool-use`/OpenAI). Two real constraints surfaced doing this, worth knowing before you build
  against this profile:
  - `gemini-3.8-flash`, `gpt-oss-120b` (Groq) and `nvidia/nemotron-3-super-120b-a12b` all spend a
    large, variable share of `max_output_tokens` on internal "thinking" before any visible/structured
    text (see `docs/project/CURRENT_STATE.md` for the reproduced measurements). NVIDIA's `rag.answer`
    deployment measurably returned empty `response.content` in roughly 2 of 5 real calls at
    `max_output_tokens: 128` and roughly half at `512`; `2000` was reliable across repeated calls. Give
    reasoning models real headroom, not a token count sized for the answer alone — this is not a rare
    edge case, it is common enough to hit on an ordinary first try.
  - OpenAI's strict tool/structured-output mode requires `additionalProperties: false` on every object
    node and every property listed in `required` (no optional properties) — the gateway enforces this
    locally before any network call, failing closed in milliseconds with a clear message rather than
    sending a request OpenAI would reject.
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

### One command (recommended)

`scripts/personal_default_launcher.py` starts the Policy Model Router and the Gateway together and
tears both down on Ctrl+C, so you don't manage two terminals by hand:

```bash
set -a; source .env; set +a
uv run --frozen python scripts/personal_default_launcher.py
```

It expects a sibling `policy-model-router` checkout at `../policy-model-router` relative to this
repository; override the path with `POLICY_MODEL_ROUTER_ROOT` if yours lives elsewhere. `--smoke-test`
proves startup/readiness and exits immediately, matching `scripts/local_demo.py`'s existing pattern.
A missing provider credential for an *enabled* deployment fails the whole launch closed within a few
seconds (adapter construction resolves every enabled deployment eagerly) — disable what you don't have
in `model_registry.yaml`/`provider_runtime.json` rather than waiting it out.

### Two terminals (what the launcher automates)

Startup is otherwise identical to the `live-development` profile (see
[`../live-development/README.md`](../live-development/README.md) for the full step-by-step, including
the observability stack), just point the Gateway CLI flags at this directory instead:

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

and calls `GatewayClient.from_env().generate(workload="rag.answer", ...)` (or any of the other eight
reviewed workloads listed above) — no provider, model, or deployment selection.
