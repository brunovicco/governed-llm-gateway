# PDP transport — local before/after comparison

## Scope and current implementation

`StdlibPolicyTransport` remains the default HTTPS transport. `LoopbackHttpPolicyTransport` remains
the explicit literal-loopback HTTP option. Both use one blocking connection per exchange in
`asyncio.to_thread`, then close it. No deployment config, active profile or bootstrap is changed.

An optional `HttpxPolicyTransport` can be explicitly injected into `PolicyRouterHttpAdapter`:

```python
from governed_llm_gateway_core.adapters.policy_router import PolicyRouterHttpAdapter
from governed_llm_gateway_core.adapters.policy_router_httpx import HttpxPolicyTransport

async with HttpxPolicyTransport(endpoint=trusted_endpoint) as transport:
    adapter = PolicyRouterHttpAdapter(
        endpoint=trusted_endpoint,
        api_keys_by_client=trusted_pdp_bindings,
        transport=transport,
    )
    decision = await adapter.authorize(trusted_policy_metadata)
```

The endpoint and bindings are trusted server configuration, not arbitrary caller selectors. Each
instance owns one HTTPS pool on one event loop; close it on that loop. It preserves certificate and
hostname verification using system trust by default. A verified explicit SSL context is supported;
an unverified context is rejected. Connection limits/idle expiry are finite; request pool wait is
bounded along with connect/read/write waits. The already-enabled execution deadline covers this
await without renewing the budget. No timer remains active across an external stream yield.

The low-level transport has no cookie jar, stored client credential headers, redirects, proxy
routing, automatic retries, decision cache or fallback. Response bytes remain raw and bounded to
512 KiB; only 200/422 JSON objects are parsed. Existing adapter request/provenance/environment
binding and fail-closed status normalization are unchanged. Response cleanup has a separate
one-second best-effort budget; shutdown cancels only owned exchanges, bounds joining and pool
closure separately to one second each, and remains owned if an individual close waiter is cancelled.
These are cooperative cleanup bounds, not additional authorized execution time or hard return SLAs.

See [ADR-0025](../adr/ADR-0025-pdp-connection-pooling.md). There is no server enablement flag or
production integration in this increment.

## Reproduce the bounded local experiment

```sh
uv run --frozen --all-packages --python 3.13.12 python -m scripts.pdp_transport_comparison
```

Optional run bounds: `--requests` 1..200, `--rounds` 1..5, `--concurrency` values 1..16.
No target URL, credential, output artifact or model-selector argument exists. The script does not
load profiles/environment credentials or invoke a provider. It prints timing/count metadata only.

The asyncio server binds only `127.0.0.1` on an ephemeral port. A freshly generated, one-hour TLS
certificate includes that literal IP; clients verify both certificate and hostname. Its generated
private key lives only inside an owner-private temporary directory and is removed on fixture exit.
The stdlib case injects this same trusted fixture CA at the adapter's local connection binding:
neither sockets/responses nor the original `http.client.HTTPSConnection` class are mocked/replaced.
The pooled case uses the same CA explicitly. System/production trust is not modified.

This server is a synthetic policy-wire fixture, not the real Policy Model Router. It authenticates
two synthetic client bindings, echoes fresh correlation metadata and emits explicitly synthetic
policy provenance. It does not prove real policy evaluation, signed-envelope consumption/revocation,
multi-replica state, proxies, deployment TLS or production load. No synthetic decision is exported
as approved ranking or benchmark authority.

The recorded run uses 48 measured exchanges plus four **sequential** warmups per case, concurrency
one/four, three rounds, alternating case order. Each authorize call gets fresh metadata. Both
transports make exactly 52 exchanges per case: connection reuse does not reduce PDP invocations.
Latency measures adapter entry-to-decision including pool wait, excluding the harness semaphore
wait. p95 uses nearest rank within each round. Four sequential warmups do not fully warm the
parallel pool: opening three additional connections during measurement is intentionally retained.
Cold latency also includes first-use import/transport setup; it is not excluded from the report.

## Observed local results — 2026-09-18

Environment: Python 3.13.12, HTTPX 0.28.1, macOS 26.6.2 arm64. This is one local run, not a
production sample. TLS connection totals include four warmup exchanges; measured timing excludes
warmups. Every row has 52 fresh policy exchanges, with no retries or provider calls.

| Concurrent | Round | Transport | TLS connections | Cold ms | p50 ms | p95 ms | Requests/s |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 1 | stdlib | 52 | 8.601 | 1.731 | 2.012 | 547.43 |
| 1 | 1 | pool | 1 | 124.116 | 0.744 | 1.030 | 1221.67 |
| 1 | 2 | stdlib | 52 | 2.205 | 1.575 | 1.705 | 613.28 |
| 1 | 2 | pool | 1 | 2.945 | 0.735 | 0.920 | 1252.02 |
| 1 | 3 | stdlib | 52 | 1.700 | 1.512 | 1.803 | 625.17 |
| 1 | 3 | pool | 1 | 2.637 | 0.711 | 0.888 | 1291.52 |
| 4 | 1 | stdlib | 52 | 1.933 | 3.473 | 4.389 | 1042.46 |
| 4 | 1 | pool | 4 | 2.636 | 2.738 | 8.604 | 1201.06 |
| 4 | 2 | stdlib | 52 | 1.942 | 3.378 | 4.361 | 1050.26 |
| 4 | 2 | pool | 4 | 2.653 | 2.823 | 9.779 | 1127.74 |
| 4 | 3 | stdlib | 52 | 1.559 | 3.495 | 4.360 | 1039.36 |
| 4 | 3 | pool | 4 | 2.734 | 2.502 | 7.364 | 1297.43 |

The measured connection counts are 48 new TLS connections in each stdlib case, zero in sequential
pool cases, and three in parallel pool cases. Pools total one/four connections versus 52.
Sequential p50/p95 and parallel p50/throughput improved in this fixture, **not every latency metric**:
parallel p95 worsened, and the first pooled cold call took 124.116 ms. These unfavorable observations
are retained, not replaced by best-of-round values or generalized into a production bottleneck.

Conclusion: real local TLS reuse is established; a general performance improvement is not. This
does not justify switching the default. Any future rollout needs separately reviewed application
lifecycle ownership and representative authorized PDP/load/proxy evidence. No real credentials,
production services, approved benchmark/ranking artifacts, model scores or dependency files changed.

## Verification boundaries

Deterministic conformance tests cover configuration, stateless per-call headers, raw response ceiling,
JSON/error normalization, no redirect/replay, total-deadline/external cancellation and finite cleanup.
Local TLS integration tests cover verified reuse, certificate rejection, fresh decisions/denial,
correlation mismatch, pool saturation, failed POST on a reused connection, server closure/replacement,
bounded concurrent connection counts and the comparison's exchange/count invariants.
CI asserts functional behavior/counts, not timing thresholds. Frozen Phase 0, both >=80% coverage
controls and the complete repository quality gate remain unchanged.
