# ADR-0015: Northbound Anthropic Messages and OpenAI Responses protocols

- Status: Accepted
- Date: 2026-09-15

## Context

Claude Code and Codex use native agent protocols, not the Gateway's canonical `/v1/generate` wire
shape. A compatibility route must not become a second authorization or execution path, and a client
model string must not select a concrete deployment.

## Decision

Add bounded adapters for `POST /v1/messages` and `POST /v1/responses`. Each translates to an
immutable `GatewayRequest` and calls the existing `GenerateCoordinator`. The coordinator still
performs client binding, external PDP authorization, health/eligibility filtering and deterministic
ranking before any provider I/O. The invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`.

The protocol `model` is an opaque response alias. `X-Gateway-Workload` selects a policy-defined
workload and defaults to `agent.tool-use`; client authentication and the PDP must authorize it.
Unknown fields and unsupported controls are rejected rather than ignored. Standard bearer/API-key
headers are accepted but conflicting credentials are rejected. Protocol-native SSE event sequences,
error envelopes, request IDs and no-store headers are emitted without gateway-only body fields.
Bounded metadata that current Codex always emits (`reasoning.effort`, encrypted-reasoning inclusion,
client metadata and text verbosity) is accepted and identified at the ingress boundary, but it is
non-authoritative and never becomes provider selection or an authorization input. Only ordinary
function tools are translated, including non-strict Codex schemas and stateless replay of prior
assistant messages, calls and text results.

## Consequences

- Compatibility is an explicitly tested stateless subset, not transparent provider pass-through.
- Stateful `previous_response_id`, hosted/custom/namespaced/deferred tools, reasoning summaries,
  encrypted reasoning replay, response compaction and arbitrary beta fields remain unsupported until
  a provider-neutral semantic and policy treatment is accepted.
- Client protocol choice cannot widen authorization, change fallback bounds or bypass evidence.
