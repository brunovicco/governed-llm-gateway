# Gateway HTTP Cache Policy

The governed Gateway applies explicit no-store semantics to authenticated operational evidence surfaces that can reveal routing or execution decisions.

## Protected response surfaces

- `POST /v1/route/explain` — every framework-generated response for the exact route path is emitted with `Cache-Control: no-store` in the full Gateway application composition.
- `POST /v1/generate` — successful governed SSE responses are emitted with `Cache-Control: no-store`.
- `/v1/ops/*` — Operations responses are emitted with `Cache-Control: no-store`.

The route-explanation rule covers successful responses and sanitized validation, authentication, policy, and ranking failures because the cache policy is applied at the ASGI response boundary rather than inside the handler body.

This cache policy is transport hardening only. It does not authorize requests, change the Policy Router decision, rank deployments, select providers or models, execute inference, or widen the Gateway allowed set.

`Gateway allowed set ⊆ Policy Router authorized set`
