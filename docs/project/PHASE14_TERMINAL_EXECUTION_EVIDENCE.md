# Phase 14 — Terminal Execution Evidence Contract

Date: 2026-09-04

## Context

The OpsLens integration case exposed a thin-client evidence gap: the gateway runtime already knew the
selected provider/model/deployment and normalized usage, while `GatewayClient.generate()` returned a
`GatewayResponse` with `execution=None`.

That behavior prevented consumers from retaining measured execution evidence such as provider/model
identity, deployment, token usage, latency, and provider-normalized cost.

## Contract

Terminal provider execution evidence is runtime evidence, not authorization input.

For successful executions produced by the current gateway runtime:

- the terminal SSE event carries `ProviderExecution`;
- provider/model/deployment come from the actual selected deployment;
- `latency_ms` is measured by the gateway from provider-attempt start through normalized provider
  completion; it is distinct from TTFT;
- token usage and cost come only from normalized provider usage;
- unavailable cost remains absent (`None`) and is never reconstructed as zero;
- terminal execution identity must match terminal `RoutingProvenance`;
- terminal execution usage must match the final `usage.completed` event;
- `GatewayClient.generate()` fails closed when a successful terminal event omits execution evidence.

A failed terminal event may omit `ProviderExecution` when failure happened before a real provider
attempt. When failed execution evidence is present, its status and provider identity must still agree
with the terminal response and routing provenance.

## Compatibility

`GatewayStreamEvent.execution` remains optional in the generic event data model so existing stream
event construction is not made wire-incompatible solely by the schema extension. The current runtime
emits execution evidence on successful terminal events, and the aggregate SDK `generate()` path
requires it before returning a successful `GatewayResponse`.

The SDK does not synthesize missing provider evidence from routing metadata or standalone usage events.

## Validation scope

Contract tests cover:

- provider/model/deployment preservation;
- measured terminal latency propagation;
- input/output token propagation;
- provider-normalized total cost propagation;
- omission of unknown cost rather than fabrication;
- routing/execution identity consistency;
- stream usage/terminal usage consistency;
- fail-closed behavior when successful terminal execution evidence is missing.
