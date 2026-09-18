# ADR-0025 — Explicit PDP-only connection pooling

## Status

Accepted design on 2026-09-18; injectable transport implementation under review.
Production/default bootstrap integration is not part of this increment.

## Date

2026-09-18

## Context

The current HTTPS Policy Router transport executes `http.client.HTTPSConnection` in
`asyncio.to_thread` and closes the connection after every request. The explicit literal-loopback
HTTP transport has the same ownership model. This establishes connection churn, not a proven
production bottleneck. HTTPX 0.28.1 is already a locked adapter-layer dependency.

Policy POSTs may carry a signed, single-use authorization envelope. Reusing a TCP/TLS connection
must never mean reusing an authorization decision or replaying an exchange that may have consumed
that envelope. ADR-0024 supplies a separate optional execution deadline, not implicit policy latency.

## Decision

- Add an explicitly injected `HttpxPolicyTransport`, confined to core adapters, without changing
  `PolicyTransport`, `PolicyRouterHttpAdapter` parsing/binding, runtime schema 1.0, bootstrap,
  active profiles, HTTPS/loopback defaults or dependencies. No production enablement flag is added.
- Bind each instance to one validated HTTPS endpoint and one event loop. Reject a different target,
  userinfo, query, fragment, whitespace or malformed endpoint before I/O. This first slice does not
  add pooled plaintext HTTP, even on loopback; existing loopback behavior remains untouched.
- Use HTTPX's asynchronous low-level HTTP/1.1 transport, not a stateful `AsyncClient`. It has no
  cookie jar or default credential headers, does not follow redirects, has no proxy routing and
  sets connection retries to zero. Build every request from fresh adapter-supplied metadata and
  per-request headers. Do not add an authorization cache, auth reacquisition or stdlib fallback.
- Preserve system TLS trust with `ssl.create_default_context`, certificate validation and hostname
  verification. A deployment-owned explicit SSL context must retain both checks; no `verify=False`
  path exists. The local test fixture trusts only its generated loopback TLS identity.
- Default to eight connections/eight idle connections with 30-second idle expiry. Allow reviewed
  plain-integer limits of 1..64 connections, 0..max idle connections and finite positive expiry up
  to 300 seconds. Request connect/read/write/pool waits use the adapter's finite positive timeout,
  capped at 300 seconds. These are phase/inactivity bounds, not a newly implied total request SLA.
  The existing execution deadline includes pool wait and cancels the owned await when enabled.
- Read raw bytes incrementally with the existing 512 KiB response ceiling; no content decompression
  expands the budget. Parse JSON objects only for 200/422 and expose only status/Retry-After/payload.
  Existing adapter correlation/provenance/denial checks and sanitized failure categories remain
  authoritative. Do not retain arbitrary error bodies, cookies or response headers in results.
- Each request owns an internal await task and explicitly closes its response with a separate
  one-second best-effort cleanup budget. Closing the transport stops admission, cancels only its
  exchanges, joins them within one second and separately closes the pool within one second.
  Shutdown has one independently owned task, so cancelling a close waiter does not cancel shutdown;
  repeated closes join the same result. Cleanup errors cannot permit a success or replace an
  existing failure/cancellation. Cancellation-resistant code can exceed cooperative timeout bounds.
- Compare before/after only against an ephemeral, verified local TLS/HTTP/1.1 wire fixture, using
  synthetic client bindings and no providers. Count fresh exchanges and negotiated connections,
  report cold latency plus per-round p50/p95/throughput, alternate case order and retain unfavorable
  results. This is transport evidence, not approved model benchmark/ranking evidence.

## Alternatives considered

- Change the default immediately: rejected; local timing does not establish production benefit or
  complete application ownership/startup/shutdown integration.
- Build a new stdlib thread-safe pool: rejected; it adds socket/thread/cancellation management while
  an asynchronous transport dependency already exists.
- Use one stateful HTTP client across trusted identities: rejected without explicit statelessness;
  cookie persistence/default credential configuration would change the existing wire boundary.
- Cache PDP decisions or transparently replay broken connections: rejected; expiration, revocation,
  kill switch and single-use authorization forbid treating transport reuse as authority reuse.
- Weaken TLS or add a new HTTP/service dependency for the comparison: rejected as unnecessary.

## Consequences

Callers explicitly injecting this adapter must own its asynchronous lifetime and close it on its
bound loop. A pool bounds open connections and idle lifetime, not incoming request count or server
admission; request-level rate limiting is a separate concern. Timeout and cancellation discard late
results but cannot roll back a PDP that has already consumed an envelope. New explicit exchanges
can open a replacement connection after clean idle/server closure; a failed POST is not replayed.

Local measurements show fewer TLS connections, but mixed latency behavior, including worse parallel
p95 and a first-use cold outlier. No default switch or general latency/availability claim follows.
See [PDP_TRANSPORT_COMPARISON](../project/PDP_TRANSPORT_COMPARISON.md).

## Security and privacy impact

`Gateway allowed set ⊆ PDP authorized set` is unchanged. The connection carries fresh exchanges,
never authority. Identity credentials remain per request; provider transport and business tools are
out of scope. No real secret reads, payload logs, raw transport diagnostics, public credential
references, authorization-cache keyspace or benchmark/ranking changes are introduced.

## Operational impact

The default deployment continues using the existing stdlib/loopback transports. This module is an
injectable option only, not a production rollout, real Policy Router proof, billing guarantee or hard
end-to-end deadline. The local script accepts bounded run sizes, no remote URL/credentials, uses
private temporary TLS material and removes only its own fixture material on exit. Timing is not a
CI pass/fail threshold; functional connection-count and safety regressions run credential-free.

## Follow-up

Run conformance, local TLS safety/reuse, cancellation, stale-connection/no-replay, finite cleanup,
adapter-binding regressions, frozen Phase 0 and complete unchanged quality gates. Review real
application startup/failure/shutdown ownership and opt-in composition separately before enabling
this transport. A real PDP/proxy/load test requires explicit scope/authority and cannot be claimed
from this fixture. Production credentials, SpendGuard reservation and Router body enforcement remain
independent work.
