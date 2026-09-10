# Container Deployment

`Dockerfile` builds the Gateway API as a container image. `compose.gateway.yml` runs it two
ways: the credential-free operations-only surface, and opt-in governed inference.

## What the image contains

The image carries **code only**. It ships no model registry, no provider runtime, no client
auth, no policy-router configuration and no ranking artifact, and it has no default `CMD`.
The entrypoint requires explicit artifact flags and exits non-zero without them, so a
container started with no configuration cannot serve anything.

Deployment artifacts are mounted read-only at run time. Provider credentials arrive through
the process environment, where a real secret manager (AWS Secrets Manager, Azure Key Vault,
GCP Secret Manager, Vault) injects them — the same server-side secret model described in
[`PROVIDER_RUNTIME_CONFIGURATION.md`](PROVIDER_RUNTIME_CONFIGURATION.md). Nothing baked into
the image can widen what a deployment authorizes.

Build details:

- both stages pin **one identical base image by digest**, because the virtualenv records the
  interpreter path it was built against;
- dependencies resolve from `uv.lock` in a layer that a source-only change cannot invalidate;
- `uv sync --no-editable` builds real wheels, so the runtime stage copies the virtualenv and
  nothing else — no source tree, no build tooling, no `uv`;
- `governed-llm-gateway-client` is deliberately absent: it is the consumer SDK, and no
  Gateway deployment imports it;
- the container runs as a non-root system user (`uid 10001`) and declares a `HEALTHCHECK`
  against `/livez`.

## Build

```bash
docker build --tag governed-llm-gateway:local .
```

To rebuild against an internal mirror of the same base image:

```bash
docker build --build-arg PYTHON_IMAGE=registry.example.internal/python:3.13.12-slim-bookworm .
```

## Run: operations-only

Credential-free apart from a local shared secret you invent. This is the service CI builds
and health-checks on every relevant change.

```bash
export GATEWAY_LOCAL_DEMO_API_KEY=replace-with-a-random-local-value
docker compose -f compose.gateway.yml up gateway-operations
```

The operations-only entrypoint binds `127.0.0.1` and exposes no `--host` flag, so it is
reachable **only from inside the container**; the container's own `HEALTHCHECK` probes it
there. Publishing that surface would need a `--host` option the entrypoint does not have
today — a deliberate limitation, not a configuration mistake.

## Run: governed inference

Opt-in through the `governed` compose profile, because it needs three things the file cannot
supply on its own:

1. provider credentials in the environment for every enabled deployment;
2. a reachable Policy Model Router;
3. a profile whose `policy_router.json` endpoint resolves **from inside a container**. The
   checked-in `personal-default` profile points at `127.0.0.1:8001`, which inside a container
   is the container itself. Point it at `host.docker.internal:8001` — mapped in the compose
   file — or at the PDP's own service name first.

```bash
set -a; source .env; set +a
export APPROVED_RANKING_ARTIFACT_ID="$(python3 -c 'import json;print(json.load(open("config/profiles/personal-default/approved_ranking.json"))["artifact_id"])')"
docker compose -f compose.gateway.yml --profile governed up gateway
```

The approved ranking artifact ID is passed explicitly rather than discovered, so an artifact
that changes without the pin being updated fails the container closed at startup. See
[the profile README](../../config/profiles/personal-default/README.md) for how that artifact
is regenerated.

Both services run with `read_only: true`, `no-new-privileges`, all capabilities dropped, and
a small `tmpfs` for `/tmp`.

## What this is not

An image is a packaging artifact, not a production posture. This adds no TLS termination, no
production IAM/OIDC/workload identity, no session handling, no rate limiting and no CSRF
policy, and the compose file publishes only to `127.0.0.1`. Every entry in the README's
[Scope](../../README.md#scope) still stands. What the image does change is that the
Gateway now has a reproducible deployment artifact instead of only local launcher scripts.
