# Trusted vs Untrusted Request Attributes

## Rule

A value supplied by a consumer is not automatically an authorization fact.

## Caller-declared context

The initial request can carry:

- `workload`;
- `risk_level`;
- `data_classification`;
- `agent_identity`;
- capability requirements;
- latency/cost limits.

These are inputs/claims. They may make a request stricter, but cannot by themselves weaken an authoritative restriction.

## Authoritative context

Before the PDP decision is accepted for enforcement, the gateway/authentication boundary binds:

- authenticated client identity;
- deployment environment;
- exact permitted workload scope;
- minimum effective data classification applicable to the identity;
- minimum effective risk applicable to the identity.

Policy version/decision provenance remains authoritative PDP output rather than a caller-authentication attribute.

## Reconciliation

PC-3 makes the API-key reconciliation rule concrete:

1. authenticate `X-Gateway-API-Key` against server-side resolved Gateway client credentials;
2. bind the matching deployment-owned client identity and environment;
3. require exact workload allowlist membership;
4. compute the stricter of caller risk and the configured authoritative minimum risk;
5. compute the stricter of caller data classification and the configured authoritative minimum classification;
6. emit `EffectivePolicyContext` for the existing prompt-free PDP projection.

If caller and authoritative context conflict, the gateway chooses the stricter risk/classification or rejects the request. It never trusts a caller downgrade such as `confidential → public`, a workload outside the identity's allowed scope, or caller-controlled `agent_identity` as authentication evidence.

Invalid credentials fail as authentication errors. A valid credential outside its configured workload scope fails separately as client authorization. Neither condition can trigger provider execution.

See `docs/project/GATEWAY_CLIENT_AUTHENTICATION.md` for the concrete PC-3 boundary.
