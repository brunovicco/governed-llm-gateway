# Local Demo Orchestration

PC-30 adds the repository-owned orchestration layer for the bounded local Governed LLM Gateway demo. It
coordinates only components whose authority and local-network boundaries were already reviewed in prior
increments.

The orchestration path is intentionally **operations-only**. It does not start the governed inference
server, materialize a provider adapter, materialize a Policy Router adapter, or create an authorized model
set.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

PC-30 creates no Gateway allowed set because no inference-capable route is started.

## Components

One launcher coordinates:

```text
Gateway Console              http://127.0.0.1:5173
       │ /v1 proxy
       ▼
Operations-only Gateway      http://127.0.0.1:8000
       ├── /livez
       ├── /readyz
       ├── /v1/ops/overview
       └── /v1/ops/deployments

OTel Collector               http://127.0.0.1:4318
       │
       ▼
Tempo                         Compose-internal only
       │
       ▼
Grafana                      http://127.0.0.1:3000
```

The existing `compose.observability.yml`, PC-29 Operations bootstrap and Gateway Console are reused. The
launcher does not add a second provider/PDP composition path or a second frontend configuration model.

## Prerequisites

The local machine needs:

- Docker with Docker Compose;
- `uv`;
- Node.js 24 and npm;
- the repository checkout.

The launcher validates the Compose model before startup and installs Console dependencies with the
committed lockfile through `npm ci --ignore-scripts`.

## Runtime-only credential

Generate an ephemeral Gateway demo credential in the current shell:

```bash
export GATEWAY_LOCAL_DEMO_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

Then start the stack from the repository root:

```bash
uv run --frozen --python 3.13 python scripts/local_demo.py
```

The launcher never prints the credential. It creates two child environments:

- the operations-only Gateway child receives `GATEWAY_LOCAL_DEMO_API_KEY`;
- Docker/Compose, npm and Vite receive an environment with that variable removed.

The credential is never placed in command-line arguments, URLs, committed files or generated `.env`
files. The Console does not receive it automatically. To use the Console, the operator enters the same
ephemeral value through the existing in-memory connection form; the Console's previously reviewed
browser-storage restrictions remain unchanged.

## Deterministic startup and readiness

PC-30 does not declare success because child processes were created. Readiness is bounded and requires all
of the following before the launcher reports the demo ready:

1. the operations-only Gateway returns exactly `{"status":"ready"}` from `/readyz`;
2. an authenticated `/v1/ops/overview` read succeeds with the PC-29 empty baseline;
3. that overview still reports zero registry deployments, `process_local` health with zero deployments,
   and operational evidence `not_supplied`;
4. Grafana health reports its database as `ok`;
5. the Console root is reachable and contains the expected React mount point;
6. `otel-collector`, `tempo` and `grafana` are all running in the dedicated Compose project
   `governed-llm-gateway-demo`.

The readiness loop uses a monotonic deadline. A child that exits before readiness causes the launcher to
fail closed rather than treating the remaining components as a successful demo.

## Cleanup ownership

The launcher starts the Gateway and Console children in separate process sessions. Cleanup signals their
entire process groups, not just the `uv` or npm parent process, and escalates from termination to kill only
after a bounded wait.

The dedicated Compose project is always taken down with volumes and orphans removed after launcher-owned
cleanup. This avoids colliding with unrelated local Compose projects and makes `--smoke-test` suitable for
CI.

Interactive mode stays active until interruption or until an owned foreground child exits. In either
case, cleanup still runs.

## Smoke-test mode

For a non-interactive startup/readiness/teardown proof:

```bash
uv run --frozen --python 3.13 python scripts/local_demo.py --smoke-test
```

`--smoke-test` starts the real local components, waits for the same readiness contract, reports only safe
local URLs, and tears everything down before returning.

The `local-demo-smoke` GitHub Actions workflow generates a fresh test-only credential at runtime, masks it
in Actions output, runs the real smoke-test on Ubuntu with Docker, Python/uv and Node.js 24, and verifies
that the dedicated Compose project and reviewed local listeners are gone after the launcher returns.
Docker diagnostics and final workflow cleanup explicitly remove `GATEWAY_LOCAL_DEMO_API_KEY` from their
environment.

No provider, Policy Router, SaaS observability or production credential is required by this CI proof.

## Capability, proof and certification states

These states are deliberately separate:

- **implemented**: the launcher, contracts and smoke workflow exist on a candidate branch;
- **proven in CI**: `quality` and `local-demo-smoke` pass on the exact reviewed candidate SHA;
- **certified**: the reviewed PR is squash-merged and the applicable post-merge `main` gates pass on the
  resulting immutable `main` SHA.

Do not call PC-30 certified based only on local execution, branch CI or a green pull request.

## Non-claims

PC-30 does not provide or claim:

- live model inference;
- provider credentials or provider availability;
- a live Policy Router/PDP integration;
- automatic browser credential injection;
- fabricated traces, routing history, cost or traffic;
- per-trace Console correlation;
- production process supervision or container packaging for Gateway/Console;
- production IAM, TLS, SSO or browser session architecture;
- fleet/global health semantics;
- Phase 14 consumer integration;
- production observability readiness.

Grafana may legitimately show no request traces in this demo because the operations-only launcher does not
fabricate inference traffic merely to make a dashboard look populated.
