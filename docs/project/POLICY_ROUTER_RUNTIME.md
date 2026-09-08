# Policy Router Runtime Configuration

## Purpose

The Policy Router runtime artifact is the deployment-owned connectivity and credential boundary for the deterministic Policy Model Router (PDP).

It closes composition between trusted Gateway client identity and the external PDP without moving authorization into startup configuration. The runtime artifact can establish how the Gateway reaches the PDP and which server-side credential reference belongs to each trusted client. It cannot authorize a workload, model group, provider, model, deployment, retry, or fallback.

## Checked-in default

`config/policy/router.json` remains intentionally disabled:

```json
{
  "schema_version": "1.0",
  "config_version": "pc7-empty",
  "enabled": false,
  "endpoint": null,
  "timeout_seconds": 5.0,
  "bindings": []
}
```

The repository default therefore has no Policy Router endpoint, no credential reference, and no secret read.

A disabled Policy Router runtime is valid only when Gateway client authentication is also empty. If authenticated Gateway clients are configured while the Policy Router remains disabled, startup validation fails closed.

## Enabled runtime

A normal deployment uses a secret-free HTTPS document such as:

```json
{
  "schema_version": "1.0",
  "config_version": "deployment-v1",
  "enabled": true,
  "endpoint": "https://policy-router.example/route",
  "timeout_seconds": 5.0,
  "bindings": [
    {
      "client_id": "agent-a",
      "credential_reference": "POLICY_AGENT_A_KEY"
    }
  ]
}
```

The artifact contains only credential references. Raw Policy Router credentials remain inside the Gateway deployment boundary and are resolved only after every no-secret validation gate succeeds.

Enabled configuration requires:

- an absolute HTTPS endpoint, except for the explicit literal-loopback development exception described below;
- no endpoint userinfo, query, or fragment;
- a finite positive timeout no greater than 300 seconds;
- at least one `client_id` binding;
- unique client IDs;
- unique credential references;
- deterministic client ordering after parsing.

## Literal-loopback development exception

PC-33 adds one narrow transport exception so the reviewed local Policy Model Router quick start can participate in a real PDP -> PEP development flow without requiring local TLS termination.

Plain HTTP is accepted only when the endpoint host is a **literal loopback IP address**, for example:

```json
{
  "endpoint": "http://127.0.0.1:8001/route"
}
```

Accepted examples include IPv4 `127.0.0.0/8` addresses and IPv6 `::1`. The following remain rejected:

- `http://localhost:...`;
- private-LAN or container-network addresses over HTTP;
- remote/non-loopback HTTP;
- HTTP endpoints with userinfo, query strings, or fragments.

This restriction is checked both while validating runtime configuration and again inside the dedicated `LoopbackHttpPolicyTransport` before opening a connection. HTTPS continues to use the existing `StdlibPolicyTransport` unchanged.

The exception is development connectivity only. It is not an authorization source, is not production TLS guidance, and does not permit the Gateway to widen the logical model group returned by the PDP.

## Validation-before-secret ordering

The process bootstrap enforces this sequence:

```text
load Model Registry / provider runtime / Gateway client auth / Policy Router runtime
        ↓
validate each closed schema
validate provider-runtime ↔ registry coherence
validate Policy Router activation invariants
validate exact Gateway-client ↔ PDP-client identity set
        ↓
all no-secret gates passed
        ↓
resolve Gateway client credentials
resolve Policy Router credentials
resolve provider credentials
        ↓
materialize governed application services
```

The exact client-set equality is intentional. `GatewayClientAuthBinding.client_id` becomes the trusted client identity in `EffectivePolicyContext`, and `PolicyRouterHttpAdapter` uses that same `client_id` to choose the PDP credential. A client that can authenticate to the Gateway but has no configured PDP credential is therefore a startup configuration error, not a request-time fallback condition.

If the client sets differ, no Policy Router credential is read.

## Secret resolver boundary

`PolicyRouterSecretResolver` is deliberately separate from both:

- `GatewayClientSecretResolver` — credentials presented by consumers to the Gateway;
- `ProviderSecretResolver` — credentials used by the Gateway to call model providers.

This preserves least-privilege boundaries between three distinct credential classes.

`EnvironmentPolicyRouterSecretResolver` is the initial deployment adapter. It resolves only normalized uppercase environment references and returns sanitized errors for invalid, missing, or malformed values. Cloud secret-manager adapters can implement the same protocol without changing Policy Router authorization semantics.

## Authority boundary

Policy Router runtime configuration supplies connectivity and credentials. It does not authorize a model or workload.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The runtime artifact can establish that an authenticated Gateway client has a credential capable of asking the PDP for a decision. Only a successful Policy Router decision can establish the upstream logical model-group authorization.

Neither runtime enablement, endpoint availability, credential presence, provider availability, ranking, complexity, benchmark evidence, telemetry, nor fallback can manufacture or widen that authorization.

## Current process composition

The executable governed server now composes the validated runtime bundles, ranking source, health/resilience state, optional observability, coordinators, and FastAPI routes through the explicit deployment activation boundary.

The checked-in default remains non-executable because its model registry/provider/client/PDP artifacts are empty or disabled. The opt-in `config/profiles/live-development/` profile is the first reviewed local profile that materializes the full governed serving path; it still requires an external Policy Model Router decision and server-side credentials before provider execution can occur.

Still deferred beyond this boundary are production OAuth/OIDC/workload identity, production TLS termination, production secret-manager adapters, and production IAM hardening.
