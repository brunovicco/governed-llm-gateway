# Optional ASGI-owned PDP HTTPS pool

## Scope and explicit selection

[ADR-0026](../adr/ADR-0026-asgi-owned-pdp-pool-lifecycle.md) integrates ADR-0025's transport into
application lifecycle without changing transport defaults. Omission preserves stdlib HTTPS and the
existing explicit literal-loopback HTTP path. No profile, production deployment, dependency or
runtime JSON schema is changed.

The installed command accepts these additional non-secret arguments alongside its required
deployment/ranking arguments:

```text
--pdp-http-pool
--pdp-http-max-connections 8
--pdp-http-max-keepalive-connections 8
--pdp-http-keepalive-expiry-seconds 30
```

Only the first flag enables pooling. Limits without that flag fail rather than implicitly enabling
it. Defaults are 8/8/30; connection counts must be plain integers, total 1..64 and idle 0..total.
Expiry must be finite, positive and at most 300 seconds. Values are independently defaulted:
reducing total below eight also requires an explicit compatible idle limit.

Python deployment settings accept `policy_router_pool=PolicyRouterHttpPoolSettings(...)`; direct
application bootstrap/materialization accepts the same option. The configured PDP must be enabled
with a normalized HTTPS endpoint without userinfo/query/fragment. Disabled PDP, plain HTTP,
invalid limits or contradictory owned/borrowed injection fail before client/PDP/provider secret
lookup. Secret ordering otherwise stays client → PDP → providers. Endpoints and credentials remain
trusted server configuration, never caller selectors.

## Lifecycle, readiness and shutdown

Synchronous bootstrap prepares one stateless owner per factory-created application, not an HTTP
backend. ASGI startup constructs and binds the backend on the serving loop. Connections remain
lazy: startup sends zero policy POSTs, opens zero TLS connections and performs no upstream probe.
The internal Uvicorn runner requires `lifespan="on"` for this selection and still runs one worker.
Custom runners must execute the app's lifespan; they receive no new runner arguments.

The owner accepts fresh exchanges only after successful startup on its loop. New policy work fails
closed before startup, on another loop and after shutdown. `/livez` is unchanged; pooled `/readyz`
additionally requires this local active state, otherwise returning HTTP 503 and the bounded code
`policy_transport_not_ready`. A ready owner does not prove an established connection, valid remote
credentials or reachable PDP/provider. Default readiness and telemetry independence are unchanged.

Shutdown marks the owner inactive before closing the backend in `finally`. Partial startup,
application failure and cancellation also close owned resources. ADR-0025's cooperative cancellation/
join/close bounds remain unchanged; sanitized shutdown errors cannot replace a primary application
failure. Each owner permits only one lifespan; create a new app for a restart/new loop.

Explicit `policy_router_transport` injection is borrowed: core builder/process/application
materializers forward it but do not start or close it. The embedder owns that transport's complete
lifetime. Borrowed injection cannot be combined with owned pool settings or a disabled PDP.

Pool settings do not authorize, rate-limit, expand candidates or replace the execution deadline.
Fresh per-call credentials/metadata, response binding and fail-closed normalization remain intact.
There is no decision cache, retry, redirect, fallback, policy reacquisition or startup authorization
warmup. Cancellation cannot reverse remote consumption of a single-use envelope.

Rollback means omitting the option and reconstructing the app, not switching transports mid-request.
Production credential operations and representative real-PDP/load/proxy validation remain deferred.

## Separate local warmup diagnostic — 2026-09-18

This follow-up does not replace the mixed original run in
[PDP transport comparison](PDP_TRANSPORT_COMPARISON.md). An ephemeral diagnostic used the same
verified synthetic loopback TLS fixture and two synthetic credentials, not a real PDP/provider.
It compared four sequential warmups with a four-request concurrent warmup barrier that kept all four
connections occupied before release. Case order rotated over three rounds; each case made exactly
four warmup plus 48 measured fresh POSTs, concurrency four. Timing includes adapter/pool wait but
excludes the harness semaphore; p95 is nearest rank per round.

The diagnostic ran alongside focused tests on the same local machine, not an isolated load host.
It is not a new production/startup feature or an approved ranking/benchmark artifact. Concurrent
warmup cold timing was not measured comparably and is explicitly absent below.

| Round | Transport / warmup | Warm TLS | Measured TLS | Total TLS | Cold ms | p50 ms | p95 ms | Requests/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | stdlib / sequential | 4 | 48 | 52 | 7.498 | 3.427 | 4.148 | 1052.04 |
| 1 | pool / sequential | 1 | 3 | 4 | 54.181 | 2.447 | 7.231 | 1295.70 |
| 1 | pool / concurrent | 4 | 0 | 4 | — | 2.465 | 3.197 | 1461.97 |
| 2 | pool / sequential | 1 | 3 | 4 | 2.660 | 2.359 | 6.804 | 1370.22 |
| 2 | pool / concurrent | 4 | 0 | 4 | — | 2.387 | 2.819 | 1521.37 |
| 2 | stdlib / sequential | 4 | 48 | 52 | 1.855 | 3.380 | 3.804 | 1099.78 |
| 3 | pool / concurrent | 4 | 0 | 4 | — | 2.441 | 3.042 | 1476.57 |
| 3 | stdlib / sequential | 4 | 48 | 52 | 1.793 | 3.261 | 3.868 | 1103.64 |
| 3 | pool / sequential | 1 | 3 | 4 | 2.492 | 2.390 | 7.034 | 1343.10 |

Opening three connections during measurement is a local p95 factor: establishing all four first
reduced the observed tail in this control. This does not isolate every source of latency, establish
a production bottleneck or justify changing defaults. In particular, authorization prewarming is
not implemented: extra POSTs could consume single-use authority.

## Verification boundaries

Contract tests cover default compatibility, pre-secret rejection, per-app/loop/lifetime ownership,
partial startup and shutdown errors/cancellation, borrowed non-ownership, readiness and Uvicorn
enforcement. Real verified local TLS tests cover fresh sequential reuse and shutdown cancellation of
active/queued exchanges without replay. They make no real provider or production PDP calls.

Frozen Phase 0, unchanged strict typing/security/composition checks and both >=80% coverage controls
remain required. Functional tests assert behavior/counts, not timing thresholds.
