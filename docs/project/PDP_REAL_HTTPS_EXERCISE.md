# Local real-PDP HTTPS exercise

This opt-in exercise checks the existing deadline and PDP-pool controls against the pinned Policy
Model Router behind a locally trusted HTTPS bridge. It does not change serving defaults, use AWS,
or call a model provider.

## Run

Requirements: Python 3.13+, Docker Compose, and the sibling `policy-model-router` checkout at the
exact commit recorded in `config/composition-proof/router.commit`.

```sh
uv run --frozen --all-packages python -m scripts.pdp_real_https_exercise
```

Optional bounds are `--requests` (2..16, default 4) and `--rounds` (1..3, default 2). The command
starts a unique Compose project, verifies the Router revision, creates ephemeral signing/API keys
and a loopback certificate authority in private temporary storage, then removes the Compose
containers, networks and volumes. The report contains revisions, counts, sanitized outcomes and
timings only. Each successful authorization call receives a new single-use runtime-authorization
ID; decision reuse and POST replay are not part of this exercise.

## What it checks

- Concurrent fresh authorizations through the unchanged stdlib HTTPS transport and an explicitly
  injected HTTPX pool configured to the request concurrency. Case order alternates by round; each
  decision is returned by the real Router.
- A separate pool-saturation case with four concurrent calls and a one-connection limit.
- A real Router 403 denial without a runtime-authorization envelope.
- Rejection of the local certificate by an empty, verification-enabled trust store, before any
  policy exchange reaches the Router.
- Pool lifecycle behavior against the real Router: requests fail before startup and after shutdown,
  readiness is local to the active lifespan, and startup does not send a warmup authorization.
- A delayed real-PDP response that expires the Gateway deadline before SSE commitment, returning
  HTTP 504 with zero provider calls and no late provider success.
- Deadline expiry after a simulated provider emits content: the stream ends with
  `response.failed`, the provider stream closes, and no fallback or late completion occurs.

The deterministic provider used for deadline scenarios is in-memory and conspicuously simulated.
The Router is real; the local TLS bridge holds responses for a fixed short delay only to make pool
saturation and the deadline edge reproducible.

## Recorded run — 2026-10-18

Command: `uv run --frozen --all-packages python -m scripts.pdp_real_https_exercise`.

Router commit: `3140181c45ce55a3139a292dbe30448012909fdf`. Python 3.13.12, two alternating rounds,
four concurrent fresh authorization calls per transport per round. Every measured transport case
made four fresh Router exchanges and returned four unique decision IDs. The concurrency-sized pool
was configured for four connections. Observed TLS connection counts were four for the stdlib
transport and four for the pool in these saturated concurrency-four rounds.

| Round | Transport | Fresh Router exchanges | TLS connections | p50 ms | p95 ms |
|---:|---|---:|---:|---:|---:|
| 1 | stdlib default | 4 | 4 | 49.632 | 54.484 |
| 1 | HTTPX pool, limit 4 | 4 | 4 | 70.218 | 73.097 |
| 2 | HTTPX pool, limit 4 | 4 | 4 | 40.651 | 42.159 |
| 2 | stdlib default | 4 | 4 | 35.021 | 35.558 |

In the separate saturation case, four fresh Router exchanges completed through one TLS connection
with the pool limited to one. The local comparison does not establish a performance win: the
sample is small, the bridge adds a deliberate 25 ms response delay, and the two rounds vary. Timing
is reported without a pass/fail threshold.

The denial returned HTTP 403 with no retry; the untrusted certificate resulted in a normalized
`transport` failure and zero Router exchanges. Pool readiness/startup/shutdown checks passed. The
50 ms pre-commit deadline returned HTTP 504 `execution_deadline_exceeded` after one real PDP
exchange and made zero provider calls. The 100 ms post-content deadline emitted
`response.started`, `content.delta`, and `response.failed`, closed the simulated provider stream,
and emitted no `response.completed`. Compose teardown passed.

## Evidence boundary

This is local integration evidence for one pinned Router revision, one process, and a verified
loopback TLS bridge. It does not establish AWS behavior, production proxy/load characteristics,
multi-replica pool behavior, a remote cancellation guarantee, a billing ceiling, or an end-to-end
latency SLA. Defaults remain unchanged. See [ADR-0024](../adr/ADR-0024-explicit-execution-deadline.md),
[ADR-0025](../adr/ADR-0025-pdp-connection-pooling.md), and
[ADR-0026](../adr/ADR-0026-asgi-owned-pdp-pool-lifecycle.md).
