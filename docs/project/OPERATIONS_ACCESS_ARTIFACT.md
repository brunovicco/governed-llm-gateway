# Deployment-Owned Operations Access Artifact

## Purpose

PC-21 / OR-4B binds the PC-20 operations-read authorization boundary to explicit deployment-owned configuration before any Operations HTTP route exists.

The artifact selects which already-configured Gateway client identities may view future process-wide descriptive operations metadata. It does not contain credentials and it does not create inference authority.

## Closed schema

The JSON document is intentionally small and closed:

```json
{
  "schema_version": "1.0",
  "config_version": "ops-read-v1",
  "principals": [
    {
      "client_id": "operations-console",
      "environment": "development"
    }
  ]
}
```

Only these root fields are accepted:

- `schema_version`;
- `config_version`;
- `principals`.

Each principal contains exactly:

- `client_id`;
- `environment`.

The loader rejects duplicate JSON keys, missing or unknown fields, malformed identifiers, duplicate principals and principals that are not already in deterministic `(client_id, environment)` order.

An empty `principals` array is valid and means deny all.

## Secret-free validation stage

`operations_access_path` is optional. There is no scanning, globbing, newest-file discovery or implicit fallback.

When omitted:

```text
operations_access_path = None
        ↓
OperationsReadAccessPolicy(principals=())
        ↓
deny all operations visibility
```

When supplied:

```text
explicit operations_access_path
        ↓
load_operations_read_access_document(...)
        ↓
closed-schema validation
        ↓
validate_operations_access_client_auth(...)
        ↓
all principals must exactly match loaded Gateway client-auth identities
        ↓
only then may secret-backed runtime materialization begin
```

The cross-artifact check is performed inside `GovernedProcessArtifacts`, alongside the existing provider-registry and Policy Router/client-auth gates. An unknown client ID or wrong environment therefore fails before Gateway client, Policy Router or provider credentials are read.

## Runtime composition

After all secret-free artifacts validate, `materialize_governed_process_runtime(...)` resolves the existing Gateway client credentials once and constructs the existing `StaticGatewayClientContextResolver`.

`OperationsReadAccessService` receives that same resolver as its authenticator:

```text
Gateway client-auth artifact
        ↓
secret-free structural validation
        ↓
operations-access cross-validation
        ↓
resolve Gateway credentials once
        ↓
StaticGatewayClientContextResolver
        ├── inference resolve(...)
        └── operations authenticate(...)
                    ↓
          OperationsReadAccessService
```

No second client secret resolver or credential copy is created for operations access. `GovernedProcessRuntimeBundle.operations_read_access` is carried unchanged into `GovernedGatewayServices.operations_read_access`.

## Deployment and executable settings

`GovernedDeploymentSettings.operations_access_path` uses the same explicit deployment-root path resolution as other artifacts:

- relative paths are resolved under `deployment_root`;
- a relative path that escapes `deployment_root` fails closed;
- an absolute path remains explicitly deployment-owned;
- `None` means deny all.

The executable process exposes only:

```text
--operations-access-path <path>
```

There is no CLI argument for an operations API key, raw principal grant, wildcard admin role or authorization bypass.

## Provenance

A validated `OperationsReadAccessDocument` exposes:

- `schema_version`;
- `config_version`;
- deterministic SHA-256 `digest` over canonical validated content;
- the immutable `OperationsReadAccessPolicy`.

The digest is provenance for the visibility configuration only. It is not an authorization token and never participates in model eligibility, ranking or provider execution.

## Authority invariant

The permanent inference invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operations-access configuration can only permit descriptive operations visibility for an already-authenticated Gateway identity. It cannot:

- authorize a model group or deployment;
- widen or restore Policy Router output;
- change capability eligibility;
- change complexity assessment or narrowing;
- affect ranking;
- change health/circuit state;
- widen retry or fallback;
- execute a provider request;
- mutate registry, policy, ranking, evidence or runtime state.

## Transport remains deferred

PC-21 deliberately adds no `/v1/ops/*` route.

The next OR-4 increment may attach a first authenticated read-only endpoint such as `GET /v1/ops/overview` only after using the already-composed `OperationsReadAccessService` before reading the PC-19 `OperationsReadModelService` snapshot.

Recent routing history, operational-evidence source binding, fleet aggregation, external IAM and operator mutation surfaces remain separate increments.
