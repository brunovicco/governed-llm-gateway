# OpenAI-Compatible Ingress

`POST /v1/chat/completions` lets a consumer keep its existing OpenAI client and repoint
`base_url` at the Gateway. It is adoption friction removed, not a second execution path:
the route translates the request onto the existing `GenerateRequestModel` and hands it to
the same `GenerateCoordinator` that serves `/v1/generate`. Authentication, Policy Router
authorization, deterministic ranking, retry/fallback and evidence are the governed path,
unchanged. Nothing in this route can authorize anything.

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="<GATEWAY_DEMO_API_KEY>")

completion = client.chat.completions.create(
    model="rag.answer",                     # a workload, not a provider model
    messages=[{"role": "user", "content": "Explain deterministic routing."}],
)
```

## `model` is the workload

The caller never chooses a provider or a model — that is the whole thesis — so `model`
carries the **workload**.

Shape validation catches the obvious confusions: `openai/gpt-4`, uppercase names and
undotted names are refused with HTTP 422. It is deliberately **not** the protection that
matters. A dotted provider model name such as `gpt-5.6-luna` is shaped exactly like a
workload and passes shape validation — what refuses it is authorization. An unregistered
workload is absent from every client-auth binding's `allowed_workloads` and from the
Policy Router's decision, so it fails closed there. Treating the pattern as the guard
would be a protection that only looks like one.

## Risk level and data classification

The OpenAI request has no equivalent of either field, so they come from the
deployment-owned client-auth binding rather than from the caller. The translated request
presents the lowest possible pair and the binding's `minimum_risk_level` /
`minimum_data_classification` raise it.

A caller therefore **cannot lower its own classification** through this surface, and
cannot raise it either. That is a deliberate trade: a client that handles confidential
data is given a binding whose minimums say so, which is stronger than trusting a
self-declared field. A caller that must declare sensitivity per request uses
`/v1/generate`, where both fields are required and explicit.

## Accepted fields

| Field | Behavior |
| --- | --- |
| `model` | Required. The workload identifier. |
| `messages` | Required. `system` / `user` / `assistant` with text content. |
| `stream` | Optional. `true` emits `chat.completion.chunk` events and `data: [DONE]`. |
| `max_tokens` / `max_completion_tokens` | Optional, at most one. Defaults to 2000. |

Everything else is rejected with HTTP 422 rather than ignored. Sampling controls
(`temperature`, `top_p`, `seed`, `n`) are deployment-owned here: accepting and silently
dropping them would let a caller believe it had influenced execution when it had not.

The 2000-token default is not arbitrary — several reasoning-style deployments spend a
large, variable share of the budget on internal thinking before any visible text, and a
tight budget measurably returns empty content. See the
[`personal-default` profile README](../../config/profiles/personal-default/README.md).

## Evidence

Responses carry an `x_gateway` object alongside the OpenAI shape: routing decision ID,
model group, ranking policy version, and the terminal provider/model/deployment with
attempt and fallback counters plus the trace ID when tracing is enabled. OpenAI clients
ignore unknown fields, so governed evidence survives without breaking SDK parsing.

`model` in the response echoes the workload the caller asked for. The deployment that
actually served it is reported as evidence under `x_gateway`, never substituted into the
OpenAI field.

## Streaming failure semantics

Once a streamed response begins, HTTP 200 is committed and a status code can no longer
reach the caller. A mid-stream failure is therefore reported in band: the final chunk
carries `finish_reason: "error"` and an `x_gateway.error` code with a `partial` flag. A
non-streaming failure returns an OpenAI-shaped error envelope with HTTP 502.

## What this is not

Not full OpenAI API coverage. There is no tool/function calling, no `response_format`,
no image input, no `n > 1`, no embeddings, no assistants, and no completions endpoint on
this surface. Those exist natively on `/v1/generate` where they are already governed and
validated; extending them here is future work, not a silent gap.
