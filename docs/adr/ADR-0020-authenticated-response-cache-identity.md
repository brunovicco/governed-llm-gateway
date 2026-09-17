# ADR-0020 — Authenticated response-cache identity

## Status

Accepted for this focused implementation increment. Cache remains off by default;
deployment activation and mixed-version coordination are operator responsibilities.

## Date

2026-09-17

## Context

At `origin/main@b0cd589`, `ResponseCacheIdentity` binds workload, effective risk/data
classification, authorized group, registry/ranking digests, output budget, and exact
messages. It omits authenticated client identity and the PDP policy digest. Distinct
clients can therefore produce the same cache key when those other fields are equal.

`GenerateCoordinator` already authenticates through `EffectivePolicyContext`, calls the
PDP, ranks inside its single authorized group, and completes deterministic streaming
preflight before computing cache eligibility. `StreamingExecutionService` reads the
cache afterward and serves a hit only for the currently selected deployment. These
controls are retained, not replaced by stronger cache keys.

No authorized tenant is present in `EffectivePolicyContext` or the current wire contract.
`GatewayRequest.agent_identity` is a caller claim, not a cache isolation authority.

## Decision

- Require the effective `client_id` and the accepted PDP `policy_digest` in the internal
  immutable cache identity. Validate client identifier shape and canonical
  `sha256:<64 lowercase hex>` PDP provenance; no empty/shared default is allowed.
- Populate them only from authenticated effective context and accepted routing policy
  provenance, never a payload identity, API key, provider credential, or caller digest.
- Change cache identity and stored-entry schema to `2.0`. New RESP keys have the form
  `<deployment-prefix>:cache:2.0:<identity-hex-digest>`. There is no legacy-key fallback,
  payload upconversion, or broad deletion. A copied schema 1.0 payload is a miss.
- Keep fresh authentication/PDP authorization/ranking/preflight before every lookup.
  A policy digest scopes an answer; it is not a decision-cache token, TTL authorization,
  signature, revocation check, or reusable governance envelope.
- Preserve opt-in workload allowlisting, the effective PUBLIC ceiling, bounded TTL,
  tools/structured/multimodal exclusions, current-deployment matching, cached execution
  provenance, and best-effort writes. Do not change retry/fallback or health admission.

## Alternatives considered

- Caller-declared identity: rejected because spoofing could select another client's entry.
- API-key identity: rejected because keys are secrets and credential rotation must not
  manufacture a new principal; the authenticated stable client ID is the boundary.
- Tenant field without an authoritative tenant contract: rejected; do not invent trust facts.
- Client ID alone: insufficient to invalidate an answer after PDP policy changes while
  group/registry/ranking remain equal.
- Read/upconvert old entries: rejected because their keys prove no client or PDP policy
  binding. Deleting the whole shared keyspace is unnecessary and may affect other users.
- Cache PDP decisions by policy digest: rejected; fresh denial, expiry, use-once, revocation,
  and kill-switch semantics remain outside response caching.

## Consequences

Clients and changed PDP policies get different keys; unchanged authorized context still
reuses an exact answer. The deployment will experience a cold cache after upgrade.
Required internal constructor arguments change; public request/SSE/SDK schema stays 1.0.
No tenant isolation beyond the existing authenticated client boundary is claimed.

## Security and privacy impact

Client IDs are hidden from the identity's default repr and appear only inside the hashed
canonical identity, not plaintext RESP keys or stored response payloads. No new logs,
traces, public metadata, or credential-derived identity is added. Hashes are not encryption:
guessable inputs can be tested, and stored completions still require appropriate storage
access controls, transport security, residency, and retention. ADR-0008 remains normative.

This is response-cache isolation, not authorization caching or production certification.
It does not add payload classification, new model permission, business-tool execution,
or replay permission. The deployment prefix must still isolate independent deployments.

## Operational impact

Old entries remain untouched and expire under their original TTL; new workers cannot read
them. Drain or upgrade legacy workers before claiming the new isolation across a fleet:
separate keyspaces do not repair old workers' cross-client behavior. Rollback to old code
restores the old limitation; keep response caching disabled there rather than treating
the new namespace as proof that all workers enforce it.

## Follow-up

Verify domain/key separation and migration using a controlled RESP emulator, then the
real coordinator with synthetic authentication/PDP/provider boundaries: distinct clients,
spoofing, fresh decisions, policy changes, classification floors, denial/outage, and health
selection changes. Run focused regressions, Phase 0, and the full canonical quality gate.
No real credential reads/provider calls or approved benchmark/ranking changes are needed.
