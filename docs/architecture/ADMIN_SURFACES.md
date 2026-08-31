# Administrative and Explainability Surfaces

Future HTTP surfaces are not all equivalent to ordinary inference.

- `POST /v1/generate`: client-authorized workload execution.
- `POST /v1/route/explain`: no inference, but potentially exposes policy/ranking/deployment data.
- `GET /v1/models`: must be identity/policy-aware or restricted to an administrative role.
- `GET /metrics`: operationally sensitive; deployment/network policy required.
- `GET /health` and `GET /readyz`: minimal information only; no secret/catalog leakage.

The implementation must never use a global unauthenticated catalog response as the default. A caller
should not learn deployments/model groups that it is not authorized to discover unless explicit admin
policy permits that visibility.
