# Multi-provider reference bundle

This directory is a reviewed, secret-free **reference bundle** for demonstrating the Governed LLM Gateway provider/catalog boundary. It is not loaded by the default runtime and it does not constitute production approval, benchmark promotion, or authorization.

The default operational artifacts remain intentionally separate:

- `config/model_registry.yaml`
- `config/providers/runtime.json`

## Consumer boundary

A consuming application should receive only:

```text
GOVERNED_LLM_GATEWAY_URL
GOVERNED_LLM_GATEWAY_API_KEY
```

Provider credentials remain inside the Gateway deployment boundary. This reference bundle stores only resolver references such as `OPENAI_API_KEY` and never raw credential values.

## Reviewed model identities

Review date: 2026-09-07.

| Provider | Model ID | API family | Official source |
| --- | --- | --- | --- |
| OpenAI | `gpt-5.6-luna` | `openai-responses` | https://developers.openai.com/api/docs/models/gpt-5.6-luna |
| Anthropic | `claude-sonnet-5` | `anthropic-messages` | https://www.anthropic.com/news/claude-sonnet-5 |
| Google | `gemini-3.8-flash` | `gemini-generate-content` | https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash |
| NVIDIA NIM / Meta | `meta/llama-3.3-70b-instruct` | `openai-compatible` | https://build.nvidia.com/meta/llama-3_3-70b-instruct |

The registry intentionally uses a conservative `32768`-token deployment ceiling for every reference entry. That value is a Gateway reference-deployment limit, not a claim about each provider's advertised maximum context window.

Pricing is `null` by design. Pricing is time-sensitive operational evidence and must be introduced only through a reviewed snapshot when a real deployment is promoted.

Capabilities are also deliberately narrow. The reference entries prove provider/model identity and transport composition; they do not automatically expose every feature supported by the underlying model. Additional vision, tool-calling, structured-output, or streaming claims must be reviewed independently before enablement.

## NVIDIA endpoint handling

NVIDIA NIM supports OpenAI-compatible chat-completions transport for `meta/llama-3.3-70b-instruct`, but hosted/free endpoint availability changes independently of the model and protocol. The checked-in `provider_runtime.json` therefore uses the reserved illustrative hostname:

```text
https://nvidia-nim.example/v1/chat/completions
```

A real deployment must replace that value with its deployment-owned NVIDIA NIM or partner endpoint and independently verify the enabled transport features. The reference binding keeps optional OpenAI-compatible streaming, structured-output, and tool-calling flags disabled.

## Authority boundary

Neither file in this directory has authorization authority.

```text
catalog membership != authorization
runtime availability != authorization
consumer credential != provider credential
```

The production ordering remains:

```text
Gateway authentication
    -> PDP authorization
    -> authorized model group
    -> registry eligibility
    -> complexity/ranking narrowing
    -> selected deployment
    -> provider runtime resolver
    -> provider adapter
```

The provider runtime resolver can only construct an adapter for a concrete deployment selected through governed routing. It cannot create candidates, widen the PDP-authorized set, rank models, or resurrect rejected deployments.

## Validation

Contract tests load these files with the same production loaders used by the Gateway, require exact registry/runtime provider-family equality, compose adapters using opaque fake server-side credentials, and perform no provider network calls.
