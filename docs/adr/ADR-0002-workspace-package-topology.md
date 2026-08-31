# ADR-0002 — Workspace and Package Topology

Status: Accepted
Date: 2026-08-31

## Context

Contracts must remain lightweight for consumer projects while provider/infrastructure concerns need a
separate composition boundary.

## Decision

Use a virtual uv workspace with explicit members:

- `packages/gateway-contracts` — immutable provider-neutral types;
- `packages/gateway-core` — domain/application/adapters;
- `packages/gateway-client` — thin consumer SDK boundary;
- `apps/gateway-api` — future HTTP composition root.

The root is coordination infrastructure (`package = false`).

Consumer business repositories may depend on the gateway; the gateway must never import them.

## Consequences

Provider SDKs, FastAPI, database, and OpenTelemetry SDK are forbidden in `gateway-contracts` and
gateway domain. Architecture checks enforce the most important forbidden imports.
