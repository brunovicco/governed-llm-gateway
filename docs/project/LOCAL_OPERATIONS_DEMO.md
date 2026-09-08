# Local Operations Demo

PC-29 establishes the first bounded OR-8 bootstrap: a local process that exposes only the already-reviewed
read-only Operations surface and process health. It is intentionally separate from the governed serving
process and does not provide model routing or inference.

This document describes a local demonstration boundary, not a production deployment design and not the
completion of OR-8.

## Purpose

The normal `governed-llm-gateway` process requires a materialized Policy Router adapter before serving
requests. That fail-closed requirement is permanent and must not be weakened merely to make a demo easy
to start.

The PC-29 entrypoint therefore composes a second, operations-only application:

```text
local operator
    │ X-Gateway-API-Key
    ▼
operations-only FastAPI process
    ├── GET /livez
    ├── GET /readyz
    ├── GET /v1/ops/overview
    └── GET /v1/ops/deployments
```

No routing, generation, provider or Policy Router execution route is attached.

## Non-executable baseline

Before resolving the local Operations credential, the bootstrap loads and validates the checked-in
secret-free baseline and requires all of the following:

- the model registry contains zero deployments;
- the ranking policy contains zero workload entries;
- provider runtime contains zero bindings;
- provider runtime still exactly matches the empty registry;
- Policy Router runtime is disabled;
- Policy Router runtime has no endpoint and no credential bindings.

Any executable baseline shape is rejected. The operations-only process never imports or calls provider
adapter builders, provider secret resolvers, Policy Router adapter builders or Policy Router secret
resolvers.

The permanent authority invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

PC-29 creates no Gateway allowed set because it exposes no inference path.

## Local identity and credential boundary

`examples/local-demo/client-auth.json` contains one secret-free Gateway identity whose credential is a
reference to `GATEWAY_LOCAL_DEMO_API_KEY`. The raw value is resolved only from the process environment.

`examples/local-demo/operations-access.json` grants Operations visibility only to that exact
`(client_id, environment)` identity. The existing Operations authorization path is reused unchanged:

```text
Gateway credential authentication
    -> exact Operations-read grant
    -> read-only Operations snapshot
```

The Operations grant does not authorize a workload, model group, deployment or provider.

No raw local-demo credential belongs in Git, URLs, traces, logs, committed configuration, browser
persistence or documentation examples.

## Start the bounded demo

Run from the repository root. Generate an ephemeral local value in the shell rather than writing one to
a file:

```bash
export GATEWAY_LOCAL_DEMO_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run --package governed-llm-gateway-api governed-llm-gateway-operations-demo
```

The process binds to `127.0.0.1:8000` by default. The host is not configurable; `--port` may select a
different local TCP port when required.

The existing Gateway Console development proxy already targets `http://127.0.0.1:8000`. An operator may
start the Console separately and enter the same ephemeral Gateway credential in the existing in-memory
connection form. PC-29 does not start the Console, Grafana, Tempo or Collector automatically.

## Expected Operations state

With the committed PC-29 baseline:

- registry `deployment_count` is `0`;
- the deployment catalog is empty;
- process-local health counts are all `0`;
- operational evidence is `not_supplied`.

Those values are descriptive consequences of the explicit empty baseline. They are not fabricated
availability, provider-health or traffic claims.

## Validation contract

The default Python `quality` gate remains credential-free with respect to external systems. PC-29 tests
use only a clearly test-scoped in-memory environment credential and require:

- the exact four-route HTTP surface;
- 401 for missing or invalid Gateway credentials;
- successful read access for the explicitly granted local-demo identity;
- the empty descriptive registry/deployment projection;
- startup failure when the runtime demo credential is absent;
- rejection of executable registry/PDP shapes;
- absence of provider/PDP execution materializers from the operations-only module;
- secret-free committed local-demo artifacts.

Implementation or branch CI is not certification. PC-29 is certified only after its reviewed PR is
squash-merged and the applicable post-merge `main` gates are green.

## Deferred / non-claims

PC-29 does not claim or provide:

- the final one-command OR-8 full-stack orchestration;
- live model inference;
- provider credentials or provider availability;
- a live Policy Router/PDP integration;
- Console process orchestration;
- automatic Collector, Tempo or Grafana startup;
- trace generation or per-trace Console correlation;
- recent routing history;
- production browser identity/session management;
- production IAM, TLS, SSO or observability URL discovery;
- Phase 14 consumer integration.

The next OR-8 increment must compose already-certified components without turning observability or demo
convenience into authorization.