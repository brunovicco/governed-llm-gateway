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

Opt-in through the `governed` Compose profile. Normal local startup needs only this repository.
Compose builds the Gateway and pulls the reviewed Policy Model Router `0.5.0` image by immutable
multi-platform digest; it does not use `latest` and it does not copy Router code into this repository.
The operator supplies:

1. provider credentials in the environment for every enabled deployment;
2. separate Gateway-consumer and Gateway-to-PDP credentials;
3. a non-empty local operations-demo key because Compose validates the unselected service definition.

```bash
set -a; source .env; set +a
export APPROVED_RANKING_ARTIFACT_ID=sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad
docker compose -f compose.gateway.yml --profile governed up --build gateway policy-model-router
```

The approved ranking artifact ID is passed explicitly rather than discovered, so an artifact
that changes without the pin being updated fails the container closed at startup. See
[the profile README](../../config/profiles/personal-default/README.md) for how that artifact
is regenerated.

The selected `personal-default/approved_ranking.json` covers only `rag.answer` in `balanced`.
Other configured workloads, including the protocol adapters' default `agent.tool-use`, fail closed
with `ranking_policy_unavailable` under this startup. Serving them requires a separately reviewed
approved artifact covering the workload and explicit selection of its path and matching ID; changing
only the ID cannot add coverage to the mounted artifact.

The Compose-specific Gateway artifact points to `http://127.0.0.1:8000/route`. The two containers
share one network namespace, allowing literal-loopback transport without weakening the runtime's
HTTPS-or-loopback validation; the Gateway listens on port 8002 in that namespace and is published as
`127.0.0.1:8000`. The normal host profile remains unchanged. Both services run with
`read_only: true`, `no-new-privileges`, all capabilities dropped, loopback-only published ports, and
a small `tmpfs` for `/tmp`. The Router policy is deployment-owned configuration, not imported
authorization logic.

### Local policy/catalog consistency

Both this Compose profile and `scripts/personal_default_launcher.py` select the Gateway-owned
`config/deployment/governed-compose-routing-policy.yaml`, rather than the Router's independent
generic example. The sibling Router checkout owns its implementation; this deployment owns its
policy and catalog. The local policy clears all five groups for **public only**. `balanced` and
`fast-small` advertise neither structured output nor tool calling. Capability configuration for
other groups does not activate them under the current `rag.answer` ranking pin.

The credential-free canonical quality gate runs:

```bash
uv run --frozen --all-packages python scripts/check_governed_composition.py
```

This offline check compares policy assertions with every catalog member of the group whose
`allowed_environments` includes `development`, **including disabled members**. One compatible
deployment cannot establish clearance for the entire pool. Disabling a deployment, excluding it by
health, or lacking approved ranking coverage does not prove data clearance; to remove it from the
declared pool, change its group/environment or remove the entry. Empty pools, missing group references,
and tool workloads mapped to groups without tool support fail the check. Advertised structured/tool
support is conservatively checked across every member of the same local pool too. This is a deployment
consistency assertion, not a new Router authorization rule or automatic content classification.

The check imports no Router implementation, needs no second checkout or Docker, and neither changes
nor derives approved ranking evidence. It validates only the policy projection needed for consistency;
the external Router remains responsible for validating its complete policy schema at startup.

### Two distinct token-cost estimates

Router group rates are independent static **PDP planning estimates**, as specified by the Router's
ADR-0010. Gateway deployment rates are versioned catalog pricing. Both calculate
`input_tokens * input_rate / 1_000_000 + output_tokens * output_rate / 1_000_000` for the same
projected request token counts and enforce the same effective `max_cost_usd` ceiling at their own
boundary. Neither is an invoice, a total-spend reservation, or a live provider-price feed.

There is intentionally no equality or pool-maximum constraint between these rates. The local
`balanced` group estimate is `0.50/2.00` USD per million input/output tokens, while its catalog ranges
from a configured zero-cost tier to `3.00/15.00`. A PDP allow can therefore still be narrowed by the
Gateway's deployment-price check; a PDP denial cannot be reversed because a cheaper deployment exists.
Automatically imposing maximum pool rates would change which requests policy admits, not just detect
drift, and requires a separate reviewed policy decision. The checker does not impose that change.

For cross-repository development, `compose.pdp-composition.yml` deliberately keeps the sibling-source
workflow and builds the Router checkout. It tests a different concern: byte-compatible signed runtime
authorization across the two repositories.

## What this is not

An image is a packaging artifact, not a production posture. This adds no TLS termination, no
production IAM/OIDC/workload identity, no session handling, no rate limiting and no CSRF
policy, and the compose file publishes only to `127.0.0.1`. Every entry in the README's
[Scope](../../README.md#scope) still stands. What the image does change is that the
Gateway now has a reproducible deployment artifact instead of only local launcher scripts.
