# Gateway Client Authentication

## Product boundary

Consumer applications authenticate to the Governed LLM Gateway. They do not receive provider credentials or Policy Model Router credentials.

```text
consumer application
    ├─ Gateway endpoint
    └─ Gateway credential
              ↓
      Gateway authentication
              ↓
    EffectivePolicyContext
              ↓
      Policy Model Router
              ↓
 governed routing / execution
```

A valid Gateway credential establishes trusted client/workload context. It does **not** authorize a model group, provider, model, deployment, retry, fallback, or business action.

The permanent model-authority invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Caller claims are not authority

`GatewayRequest` contains caller-declared metadata such as:

- `workload`;
- `risk_level`;
- `data_classification`;
- `agent_identity`;
- capability requirements and limits.

These fields are request claims. `agent_identity` is never used as the authenticated Gateway client identity.

PC-3 introduces a concrete API authentication boundary that binds a presented Gateway API key to deployment-owned identity metadata before the existing PDP flow receives `EffectivePolicyContext`.

## Secret-free binding

`GatewayClientAuthBinding` contains only deployment-owned metadata:

- normalized `client_id`;
- trusted deployment `environment`;
- `credential_reference`, never a raw credential value;
- exact, sorted `allowed_workloads`;
- authoritative `minimum_risk_level`;
- authoritative `minimum_data_classification`.

Bindings are immutable. Workload wildcards are deliberately not supported in PC-3; exact membership keeps authorization scope explicit and reviewable.

A generic credential reference may identify an environment variable today or another deployment-specific secret backend later. `EnvironmentGatewayClientSecretResolver` applies the stricter environment-variable reference vocabulary when that backend is selected.

## Construction order

`build_static_gateway_client_context_resolver(...)` follows a fail-closed two-stage sequence:

```text
client auth bindings
    -> validate all binding structure and uniqueness
    -> resolve server-side credential references
    -> validate returned credentials
    -> reject duplicate resolved credentials
    -> immutable StaticGatewayClientContextResolver
```

Duplicate client IDs, duplicate credential references, malformed binding objects, or invalid workload metadata fail before any secret backend call.

Arbitrary secret-backend exceptions are normalized to `GatewayClientSecretResolutionError` without retaining backend exception text in the visible exception chain.

Resolved credentials live only in private in-process resolver state and are excluded from dataclass representation. They are not written to configuration, routing provenance, logs, traces, normalized errors, or evidence.

## Request-time trust reconciliation

For each request the static resolver performs:

```text
X-Gateway-API-Key
    -> validate bounded ASCII credential shape
    -> constant-time comparison against all configured credentials
    -> require exactly one authenticated binding
    -> exact workload allowlist membership
    -> monotonic risk reconciliation
    -> monotonic data-classification reconciliation
    -> EffectivePolicyContext
```

Credential comparison uses `hmac.compare_digest`. Unknown, malformed, or ambiguous credentials produce the same sanitized authentication failure.

A valid credential used outside its configured workload scope produces a distinct `403 gateway_client_not_authorized` response. This distinguishes authentication failure from client/workload authorization failure without exposing configured client identities or workload lists.

## Monotonic risk and classification

The caller may make a request stricter but cannot downgrade deployment-owned minima.

For risk:

```text
effective_risk = max(caller_risk, configured_minimum_risk)
```

with the explicit order:

```text
low < medium < high < critical
```

For data classification:

```text
effective_classification = max(caller_classification, configured_minimum_classification)
```

with the explicit order:

```text
public < internal < confidential < restricted
```

Examples:

- caller `low` + configured minimum `high` -> effective `high`;
- caller `critical` + configured minimum `high` -> effective `critical`;
- caller `public` + configured minimum `confidential` -> effective `confidential`;
- caller `restricted` + configured minimum `confidential` -> effective `restricted`.

This reconciled context is what the existing prompt-free PDP projection consumes. The caller cannot lower policy risk/classification by changing request metadata.

## Versioned artifact progression

PC-3 established the in-memory authentication and trusted-context composition contract.

PC-4 adds the committed `config/clients/auth.json` artifact and `GatewayClientAuthDocument` loader. The artifact is deliberately closed, versioned, and secret-free. Its root contains only:

```text
schema_version
config_version
bindings
```

Each binding contains exactly the PC-3 trust fields:

```text
client_id
environment
credential_reference
allowed_workloads
minimum_risk_level
minimum_data_classification
```

Raw API-key values such as `api_key`, `credential`, or `secret_value` are not valid schema fields.

The loader rejects duplicate JSON keys before normal object construction can overwrite them. It also rejects unknown/missing fields, unsupported schema versions, malformed trust vocabulary, duplicate client IDs, duplicate credential references, and any binding that violates `GatewayClientAuthBinding` validation.

`GatewayClientAuthDocument.digest` is SHA-256 over canonical validated content. Formatting, root key order, and binding order therefore do not change document identity. Binding-local workload order remains explicit and must already satisfy the deterministic sorted PC-3 contract.

Loading the artifact is side-effect free with respect to authentication infrastructure: it does not resolve credentials, inspect process environment secrets, authenticate a request, call the Policy Model Router, enumerate models, or contact providers.

The checked-in artifact is intentionally:

```json
{
  "schema_version": "1.0",
  "config_version": "pc4-empty",
  "bindings": []
}
```

This default is fail-closed. Zero bindings means the repository does not implicitly authorize any Gateway client.

## Process bootstrap remains a separate increment

PC-4 does **not** add:

- a module-level FastAPI singleton;
- a `uvicorn` or container process entrypoint;
- automatic secret resolution while loading the artifact;
- OAuth/OIDC/JWT or mTLS authentication;
- cloud-specific secret-manager integration;
- live client bindings or credentials;
- provider/model catalog entries;
- model authorization or routing authority.

A later increment may load the client-auth artifact once, resolve its credential references server-side, and compose the resulting `StaticGatewayClientContextResolver` into the full Gateway process alongside provider runtime, Policy Model Router, ranking, health, and observability dependencies. That future bootstrap must preserve the same fail-closed trust flow and must not make authentication an independent model-authority source.
