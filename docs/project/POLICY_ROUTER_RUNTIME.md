# Policy Router Runtime Configuration

## Purpose

PC-7 adds an explicit deployment-owned runtime boundary for the deterministic Policy Model Router (PDP).

Before this increment, `PolicyRouterHttpAdapter` accepted an already-resolved `api_keys_by_client` mapping, while the rest of the Gateway process already had versioned artifacts for model registry, provider runtime, Gateway client authentication, ranking, and complexity routing.

The new Policy Router runtime artifact closes that composition gap without moving authorization into startup configuration.

## Checked-in default

`config/policy/router.json` is intentionally disabled:

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

An enabled deployment uses a secret-free document such as:

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

- an absolute HTTPS endpoint without userinfo, query, or fragment;
- a finite positive timeout no greater than 300 seconds;
- at least one `client_id` binding;
- unique client IDs;
- unique credential references;
- deterministic client ordering after parsing.

## Validation-before-secret ordering

`bootstrap_policy_router_runtime(...)` enforces this sequence:

```text
load Policy Router runtime JSON
load Gateway client-auth JSON
        ↓
validate each closed schema
validate Policy Router activation invariants
validate exact client_id set equality
        ↓
all no-secret gates passed
        ↓
resolve Policy Router credential references
        ↓
build PolicyRouterHttpAdapter
```

The exact client-set equality is intentional. `GatewayClientAuthBinding.client_id` becomes the trusted client identity in `EffectivePolicyContext`, and `PolicyRouterHttpAdapter` uses that same `client_id` to choose the PDP credential. A client that can authenticate to the Gateway but has no configured PDP credential is therefore a startup configuration error, not a request-time fallback condition.

If the client sets differ, no Policy Router credential is read.

## Secret resolver boundary

`PolicyRouterSecretResolver` is deliberately separate from both:

- `GatewayClientSecretResolver` — credentials presented by consumers to the Gateway;
- `ProviderSecretResolver` — credentials used by the Gateway to call model providers.

This preserves least-privilege boundaries between three distinct credential classes.

`EnvironmentPolicyRouterSecretResolver` is the first deployment adapter. It resolves only normalized uppercase environment references and returns sanitized errors for invalid, missing, or malformed values. Cloud secret-manager adapters remain future deployment work and can implement the same protocol without changing Policy Router authorization semantics.

## Authority boundary

Policy Router runtime configuration supplies connectivity and credentials. It does not authorize a model or workload.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The runtime artifact can establish that an authenticated Gateway client has a credential capable of asking the PDP for a decision. Only a successful Policy Router decision can establish the upstream logical model-group authorization.

Neither runtime enablement, endpoint availability, credential presence, provider availability, ranking, complexity, benchmark evidence, telemetry, nor fallback can manufacture or widen that authorization.

## Deferred process activation

PC-7 still does not add:

- a module-level FastAPI `app` singleton;
- a `uvicorn` or container entrypoint;
- live Policy Router credentials or network calls;
- production provider/model/client activation;
- ranking or complexity policy construction inside a process entrypoint;
- OAuth/OIDC/JWT/mTLS;
- cloud-specific secret-manager adapters;
- Phase 14 integration changes.

A later process-composition increment can combine the validated runtime bundles, ranking/complexity artifacts, health/resilience state, observability, coordinators, and `create_gateway_app(...)`. That step must preserve the same validation-before-secret ordering and authorization boundary.
