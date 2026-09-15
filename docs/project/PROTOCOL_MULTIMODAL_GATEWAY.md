# Protocol and Multimodal Gateway

## Architecture

```text
Claude Code -> POST /v1/messages  --\
                                      typed translation -> canonical GatewayRequest
Codex      -> POST /v1/responses --/                       |
                       authenticate -> external PDP -> eligibility -> rank -> execute
```

These surfaces are northbound adapters, not routers. Both call the existing
`GenerateCoordinator`. The client `model` is an opaque response alias; it never names the concrete
model. `X-Gateway-Workload` declares a policy workload and defaults to `agent.tool-use`; client auth
and the external Policy Model Router must authorize it. The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`.

## Capability matrix

| Input/output | Canonical form | Required registry capability | Treatment |
| --- | --- | --- | --- |
| Text | `TextBlock` | `text` | All verified adapters |
| HTTPS image | `ImageBlock(HttpsUrlSource)` | `vision` + `image` modality | Forwarded; Gateway never fetches it |
| Inline image | `ImageBlock(Base64Source)` | `vision` + `image` modality | Anthropic, Responses and Gemini native adapters |
| Inline audio | `AudioBlock(Base64Source)` | `audio` + `audio` modality | Represented; refused unless registry and adapter opt in |
| Inline document | `DocumentBlock(Base64Source)` | `document` + `document` modality | Represented; refused unless registry and adapter opt in |
| Tool definitions/calls | `ToolDefinition` / `ToolUseBlock` | `tool_calling` | Native adapters; compatible endpoints may opt in |
| Parallel tool calls | multiple tool-use blocks | `parallel_tool_calling` | Separate explicit capability |
| Tool results | `ToolResultBlock` | `tool_calling` | Translated; retry/fallback disabled |
| Structured output | `StructuredOutputSchema` | `structured_output` | Provider-native strict schema |
| Streaming | `GatewayStreamEvent` | `streaming` | Encoded as real Messages/Responses SSE events |

New registry capability keys default to false when absent, preserving existing schema 1.0 artifacts
and their digests. Provider availability never enables a capability. The checked-in agentic and
reasoning deployments explicitly opt into parallel tool calls so clients that request them remain
eligible without inferring capability from provider identity.

## Security and error behavior

- The 8 MiB ASGI request limit covers every generation endpoint before JSON parsing. Inline blocks
  use strict base64 and are capped at 4 MiB decoded each.
- Image URLs must be absolute HTTPS without credentials, query strings or fragments. Audio and
  documents are inline-only. File paths, file URLs, redirects and gateway-side media downloads are
  unsupported.
- Unknown fields and controls with no provider-neutral meaning are rejected, not ignored.
- Bearer, Messages `x-api-key`, and `X-Gateway-API-Key` credentials are aliases; conflicting values
  are rejected. Provider credentials stay server-side.
- Compatible responses carry `request-id`/`x-request-id`, `Cache-Control: no-store`, and bounded
  `x-gateway-*` headers for the routing decision, authorized model group, policy version and
  registry digest. No gateway-only body fields are injected into official schemas. Provider and
  model identity remains in metadata-only audit and trace evidence.
- Provider spans record the client protocol, workload, authorized model group, policy identity,
  registry digest, selected deployment, attempt and fallback count. Prompts, media, credentials and
  tool results are excluded.
- A tool-result request is sent to one deployment once. Replay could duplicate an external side
  effect, so retry and fallback are forbidden.

## One-clone governed startup

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway
cp .env.example .env
```

Set the local-only `GATEWAY_LOCAL_DEMO_API_KEY`, `GATEWAY_DEMO_API_KEY`,
`POLICY_ROUTER_DEMO_API_KEY`, and credentials for every enabled provider binding in `.env`. Compose
validates every service definition even when named services are selected, so the operations-demo key
must also be non-empty. The checked-in personal profile enables six providers; disable both a
deployment and its binding when that provider is unavailable:

```bash
set -a; source .env; set +a
export APPROVED_RANKING_ARTIFACT_ID=sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad
docker compose -f compose.gateway.yml --profile governed up --build gateway policy-model-router
```

Compose builds the Gateway and pulls Policy Model Router `0.5.0` by immutable multi-platform digest;
it never uses `latest`. The containers share a network namespace and communicate over literal
loopback, retaining the Gateway's HTTPS-or-loopback PDP transport invariant. Host ports remain bound
to `127.0.0.1`. `compose.pdp-composition.yml` remains the sibling-source cross-repository development
proof.

## Claude Code

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8000
export ANTHROPIC_AUTH_TOKEN="$GATEWAY_DEMO_API_KEY"
claude --model governed-agent
```

Direct Messages streaming check:

```bash
curl -N http://127.0.0.1:8000/v1/messages \
  -H "Authorization: Bearer $GATEWAY_DEMO_API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -H 'content-type: application/json' \
  -H 'X-Gateway-Workload: agent.tool-use' \
  -d '{"model":"governed-agent","max_tokens":2000,"stream":true,"messages":[{"role":"user","content":"Inspect this task and propose the next tool call."}]}'
```

This is a strict stateless subset. Token counting, extended thinking, arbitrary beta fields, hosted
tools and provider pass-through headers are not implemented.

## Codex

Add this provider to `~/.codex/config.toml`:

```toml
model = "governed-agent"
model_provider = "governed-gateway"
model_supports_reasoning_summaries = false

[features]
code_mode = false

[model_providers.governed-gateway]
name = "Governed AI Runtime Gateway"
base_url = "http://127.0.0.1:8000/v1"
env_key = "GATEWAY_DEMO_API_KEY"
wire_api = "responses"
http_headers = { "X-Gateway-Workload" = "agent.tool-use" }
```

```bash
export GATEWAY_DEMO_API_KEY
codex
```

Direct Responses streaming check:

```bash
curl -N http://127.0.0.1:8000/v1/responses \
  -H "Authorization: Bearer $GATEWAY_DEMO_API_KEY" \
  -H 'content-type: application/json' \
  -H 'X-Gateway-Workload: agent.tool-use' \
  -d '{"model":"governed-agent","stream":true,"store":false,"input":"Inspect this repository."}'
```

The Codex target is a strict stateless Responses subset: text, ordinary function tools/results,
prior assistant output items and real SSE output. Current Codex request metadata (`reasoning.effort`,
`include = ["reasoning.encrypted_content"]`, `client_metadata`, and text verbosity) is admitted with
bounded schemas so an ordinary turn and function-tool loop work. These controls are recorded as
client compatibility metadata but are deliberately non-authoritative: they do not select a model,
alter provider options, or widen policy/registry eligibility. Only an absent or `default` service
tier is accepted.

Stateful `previous_response_id`, response compaction, hosted/custom/namespaced/deferred tools,
encrypted reasoning replay, reasoning summaries, non-text function results, background mode,
automatic truncation and non-default service tiers remain fail-closed. `code_mode` is disabled above
because its freeform/namespaced tools are outside this interoperable subset.

## Image, audio and structured output

HTTPS image reference (not fetched by the Gateway):

```bash
curl http://127.0.0.1:8000/v1/messages \
  -H "Authorization: Bearer $GATEWAY_DEMO_API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -H 'content-type: application/json' \
  -d '{"model":"governed-agent","max_tokens":500,"messages":[{"role":"user","content":[{"type":"image","source":{"type":"url","url":"https://example.com/image.png"}},{"type":"text","text":"Describe the image."}]}]}'
```

Inline audio. The checked-in registry has no audio-capable deployment, so this command intentionally
returns `no_eligible_streaming_deployment` until both registry and adapter explicitly opt in:

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "Authorization: Bearer $GATEWAY_DEMO_API_KEY" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"governed-agent\",\"input\":[{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_audio\",\"input_audio\":{\"format\":\"wav\",\"data\":\"$(base64 < sample.wav | tr -d '\\n')\"}}]}]}"
```

Strict structured output:

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "Authorization: Bearer $GATEWAY_DEMO_API_KEY" \
  -H 'content-type: application/json' \
  -H 'X-Gateway-Workload: extraction.structured' \
  -d '{"model":"governed-agent","input":"Return incident severity.","text":{"format":{"type":"json_schema","name":"incident","strict":true,"schema":{"type":"object","properties":{"severity":{"type":"string"}},"required":["severity"],"additionalProperties":false}}}}'
```
