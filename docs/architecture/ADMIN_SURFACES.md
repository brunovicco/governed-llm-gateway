# Administrative and Explainability Surfaces

Future HTTP surfaces are not all equivalent to ordinary inference.

- `POST /v1/generate`: client-authorized workload execution.
- `POST /v1/route/explain`: no inference, but potentially exposes policy/ranking/deployment data.
- `GET /v1/models`: must be identity/policy-aware or restricted to an administrative role.
- `GET /metrics`: operationally sensitive; deployment/network policy required.
- `GET /health` and `GET /readyz`: minimal information only; no secret/catalog leakage.
- future `GET /v1/ops/*`: authenticated descriptive metadata that requires an explicit operations-read grant before the process-wide read model may be exposed.

The implementation must never use a global unauthenticated catalog response as the default. A caller
should not learn deployments/model groups that it is not authorized to discover unless explicit admin
policy permits that visibility.

PC-20 introduces the first explicit operations-read access boundary without attaching an HTTP route.
It reuses the existing Gateway credential authenticator to produce `GatewayClientIdentity`, then
requires exact `(client_id, environment)` membership in a separate secret-free
`OperationsReadAccessPolicy`. Workload allowlists do not imply administrative visibility, and
operations-read grants do not imply model/deployment execution authority.
