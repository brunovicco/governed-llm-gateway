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

These are inputs/claims. They may make a request stricter, but cannot by themselves weaken an
authoritative restriction.

## Authoritative context

Before the PDP decision is accepted for enforcement, the gateway/authentication boundary must bind at
least:

- authenticated client/workload identity;
- deployment environment;
- policy version/decision provenance;
- permitted workload namespace(s);
- minimum effective data classification and risk constraints applicable to the identity.

## Reconciliation

If caller and authoritative context conflict, the gateway/policy layer chooses the stricter outcome or
rejects the request. It never trusts a caller downgrade such as `confidential → public` or a workload
outside the identity's allowed scope.

The exact identity provider/API-key mapping is deferred beyond Phase 0; the trust rule is not.
