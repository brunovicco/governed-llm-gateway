# ADR-0026 — Explicit ASGI-owned PDP pool lifecycle

## Status

Accepted design on 2026-09-18; implementation under review. Production activation is deferred.

## Date

2026-09-18

## Context

ADR-0025 adds an injectable HTTPS pool, but application bootstrap currently builds synchronous
services without owning that pool's asynchronous lifetime. Process readiness currently proves
bootstrap only. Existing default factories and tests need not run ASGI lifespan.

The recorded local comparison has mixed timing, not production evidence. A subsequent synthetic
control established all four TLS connections before measurement and reduced observed parallel p95.
Incomplete serial warmup is a measurement factor, not proof of general performance or a reason to
send extra single-use policy POSTs during startup.

## Decision

- Add optional, immutable, secret-free deployment pool settings and explicit CLI selection. Omission
  preserves stdlib HTTPS/literal-loopback HTTP defaults. Keep runtime JSON schema 1.0, profiles,
  dependencies, request limits, authorization and provider transports unchanged.
- Validate limits and enabled HTTPS-only PDP compatibility before any client/PDP/provider secret
  access. Explicit pool selection with disabled PDP/plain HTTP or contradictory injection fails;
  do not silently substitute a transport.
- Prepare a stateless API-layer owner during bootstrap. Construct and bind its backend only in ASGI
  startup, on one application/loop/lifetime. New policy exchanges fail closed before startup and
  after shutdown. Retain fresh headers/metadata and existing adapter parsing/binding.
- Mark the owner inactive before shutdown and close its backend in finally, including partial
  startup failure/cancellation. Existing transport cooperative cleanup bounds remain authoritative;
  shutdown failures do not replace a primary failure. Never close externally borrowed transports.
- Thread explicit borrowed PolicyTransport injection through core adapter/process/application
  materializers. API-owned lifespan types stay outside core application/domain/contracts.
- When internally pooled, require Uvicorn lifespan=on without changing the runner host/port interface.
  Custom runners must honor lifespan; missing startup cannot grant policy authority.
- Pooled /readyz additionally requires the local owner to be active. /livez/default readiness remain
  unchanged. Readiness does not probe or claim PDP/provider connectivity or actual TLS availability.
- Do not make startup authorization/warmup calls, cache authority, follow redirects, replay POSTs,
  reacquire authorization or add fallback. Keep the transport default unchanged and production off.

## Alternatives considered

- Switch defaults or reuse one global pool: rejected; lifetime/loop isolation and production benefit
  are not established.
- Create sockets/pools during synchronous bootstrap or close them with a new event loop: rejected;
  resources belong to the serving loop.
- Automatically prewarm by authorizing: rejected; it may consume single-use authority and adds I/O.
- Close every injected transport or suppress startup errors: rejected; ownership must be explicit
  and activation must fail closed.
- Expand runtime artifact schema or add a new dependency: unnecessary for this deployment-owned
  opt-in increment.

## Consequences

Opt-in apps require one ASGI lifetime and must be reconstructed for a new loop/restart. Factories
without the option remain compatible with their existing tests and call patterns. Connections stay
lazy, so cold/partially warm latency remains real. Pool limits are not caller admission/rate limits.

## Security and privacy impact

Gateway allowed set remains a subset of PDP authorized set. No new authorization/cache/replay or
business-tool authority exists. Secrets resolve only after complete no-secret validation. Startup/
shutdown diagnostics are sanitized; no credentials, payloads or raw transport bodies are logged.
Only synthetic loopback TLS/credentials are used in verification; no approved ranking is changed.

## Operational impact

Explicit opt-in can be rolled back by omitting the option and reconstructing the app. No active
profile or deployment is enabled here. Local readiness measures lifecycle, not upstream health.
Cooperative cancellation/cleanup cannot roll back remote envelope consumption or guarantee a hard
return SLA. Production credentials and representative real-PDP/load/proxy tests remain deferred.

## Follow-up

Verify default compatibility, pre-secret rejection, startup/shutdown/cancellation/loop isolation,
fresh verified local TLS exchanges/no replay, readiness and runner enforcement. Run frozen Phase 0
and the complete unchanged quality gate with both >=80% coverage controls. Review separately before
any production use, real PDP validation or default change.
