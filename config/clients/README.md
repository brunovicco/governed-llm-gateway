# Gateway client authentication configuration

Gateway client authentication is deployment-owned by the Governed LLM Gateway. Consumer applications receive only a Gateway endpoint and Gateway credential; they do not receive provider or Policy Model Router credentials.

`auth.json` is the committed, closed, versioned, secret-free client-auth artifact. It contains only:

- trusted client identity;
- deployment environment;
- a server-side credential **reference**;
- exact allowed workloads;
- authoritative minimum risk;
- authoritative minimum data classification.

Raw Gateway API-key values are not part of the artifact schema.

The checked-in artifact is intentionally empty. This keeps the repository credential-free and fail-closed: with zero bindings, no Gateway client can authenticate through the static PC-3 resolver.

Loading the artifact performs schema validation and deterministic digest calculation only. It does not resolve credentials, authenticate requests, call the Policy Model Router, enumerate models, or contact providers.

See `docs/project/GATEWAY_CLIENT_AUTHENTICATION.md` for the full trust and authority boundary.
