# ADR-0012 — Governance Authorization Integration

Status: Accepted  
Date: 2026-09-04

## Context

Phase 13 adds the optional Verifiable AI Governance integration reserved by the project roadmap.

The permanent authority chain remains:

`Verifiable AI Governance → Policy Model Router → Governed LLM Gateway → model provider`

The gateway remains the policy-enforcement point plus operational selector. It must not become a
second governance system or a second policy decision point.

The roadmap requires Phase 13 to add:

- authorization context;
- scope validation;
- a governance event sink;
- runtime evidence.

Acceptance requires:

- the gateway enforces the authorized model group;
- unauthorized expansion fails closed;
- denial produces evidence;
- execution evidence correlates to authorization.

Verifiable AI Governance already publishes a vendor-neutral signed runtime-authorization contract.
The current v1 contract is short-lived, Ed25519-signed, audience-bound, request-bound and scope-bound.
It carries an authorization identity, governed subject identity, exact request binding, reviewed model
routing groups, data-classification scope, scope digest and governance policy/control provenance.

## Decision

Phase 13 integrates with the existing Verifiable AI Governance runtime-authorization wire contract
instead of inventing a gateway-specific governance token.

The integration is optional at deployment/configuration level. When governance authorization is
configured as required for a request path, missing, invalid, expired, not-yet-valid, wrong-audience,
request-mismatched, scope-mismatched or signature-invalid authorization fails closed before provider
execution.

### No new PDP inside the gateway

Governance authorization is an upstream authority constraint, not a ranking input and not runtime
telemetry.

The gateway continues to call Policy Model Router for deterministic model-group authorization.
Governance scope and Policy Router authorization are intersected. The effective gateway candidate set
must satisfy both authorities and the permanent invariant:

`Gateway allowed set ⊆ Policy Router authorized set`

Governance can narrow the candidate set further but can never expand the Policy Router result.

### Runtime-authorization contract

Phase 13 targets the Verifiable AI Governance `SignedRuntimeAuthorization` v1.0 semantics:

- protected media type `application/vnd.verifiable-ai-governance.runtime-authorization+json`;
- signature algorithm `Ed25519`;
- key identity (`kid`);
- authorization UUID;
- issuer and explicit audience;
- UTC `issued_at`, `not_before`, and `expires_at` timestamps;
- maximum authorization lifetime of 600 seconds;
- governed subject identities and reviewed agent digest;
- exact request binding for workflow, task, workload and bounded execution constraints;
- scope containing risk/data classification, reviewed models and routing groups, tools/permissions,
  runtime ceiling, human-approval points and kill-switch state;
- canonical scope digest;
- governance policy and control-catalog provenance.

The gateway must preserve the exact external authorization identity and provenance required for
runtime evidence. It must not reinterpret an invalid external envelope into a weaker local default.

### Verification boundary

Signature verification is an adapter concern behind a narrow core port. Domain/application code
receives only verified immutable authorization facts.

Verification requires an explicitly configured trusted key resolver keyed by `kid`. The gateway must
not download arbitrary keys from untrusted token-controlled URLs, must not accept algorithm
substitution and must not trust caller-supplied governance facts before signature verification.

Audience is deployment-owned configuration. Clock validation uses an injected clock for deterministic
tests. Any allowed clock skew must be explicit, bounded and configuration-owned; the first
implementation should default to zero skew unless a separately reviewed operational need requires it.

### Request and scope binding

After cryptographic verification, the gateway revalidates the authorization against the current
request and trusted gateway context.

At minimum, the verified authorization must match:

- configured gateway audience;
- workload/request binding required by the external v1 contract;
- effective risk level and data classification where represented;
- any gateway-visible request ceilings represented by the authorization;
- the governance scope digest carried by the signed claims.

The authorization's reviewed routing groups define an additional allow-set. A Policy Router-selected
or gateway-ranked model group outside that reviewed set fails closed.

Neither ranking, health filtering, fallback nor manual ranking override may resurrect a model group
excluded by governance authorization.

### Enforcement ordering

For governance-required execution the conceptual ordering is:

1. authenticate caller and derive trusted gateway context;
2. verify signed governance authorization and request/scope binding;
3. obtain Policy Model Router authorization;
4. intersect governance-authorized groups with the Policy Router-authorized set;
5. apply registry eligibility, deterministic ranking and runtime health only inside that intersection;
6. execute provider calls only from the remaining set;
7. emit correlated runtime evidence.

A failure in steps 2–4 is an authorization denial, not a provider failure and not a model-quality
signal.

### Governance event sink

The gateway exposes a narrow asynchronous `GovernanceEventSink`-style port owned by application/core
code and implemented by adapters.

The sink receives minimized, provider-neutral runtime evidence. It must never be an authorization
source on the same request and must never be able to broaden candidate selection.

Sink delivery failure semantics are explicit:

- authorization/scope validation itself remains fail closed;
- evidence delivery happens after the enforcement decision is known;
- the first implementation records a local normalized evidence object before attempting an external
  sink;
- whether remote sink delivery is required to fail an otherwise authorized provider execution is a
  deployment policy and must not be silently inferred.

### Denial evidence

Every governance-related denial produces a normalized evidence record with stable reason code and
correlation identifiers.

Evidence may include metadata such as:

- gateway request ID;
- governance authorization ID;
- governance signing digest/key ID where safe;
- Policy Router decision ID when a PDP decision exists;
- workload;
- effective enforcement outcome;
- selected/blocked model group where applicable;
- stable denial reason code;
- routing decision ID when one exists;
- timestamp and gateway service version.

Prompts, completions, raw provider payloads, gateway secrets and private signing keys are excluded by
default.

### Execution evidence

Successful and failed provider executions emit evidence correlated to the same verified governance
authorization used for enforcement.

Execution evidence must make it possible to reconstruct:

`governance authorization → Policy Router decision → gateway routing decision → provider execution`

without treating evidence as a new authorization input.

### Existing resilience/ranking semantics remain authoritative

Phase 13 does not move retry/fallback, ranking, circuit breaking or provider health into governance.
Those remain gateway responsibilities after authorization intersection.

Fallback is allowed only among deployments whose logical groups remain inside both governance and
Policy Router authorization. Existing replay-safety rules continue unchanged.

## Consequences

Positive:

- the gateway consumes the existing signed governance contract instead of creating a parallel token;
- governance scope can only narrow Policy Router authorization;
- selected model groups are revalidated at the execution boundary;
- denials and executions become traceable to the exact signed authorization;
- cryptographic verification and key management stay isolated in adapters;
- runtime evidence remains provider-neutral and metadata-only by default.

Trade-offs:

- Phase 13 introduces trusted-key and clock configuration when governance integration is enabled;
- strict request binding means authorizations cannot be replayed freely across workloads/tasks;
- remote evidence sinks require explicit delivery/reliability semantics;
- cross-repository compatibility must be tested against the external v1 governance schema.

## Rejected alternatives

### Treat governance authorization as a ranking score

Rejected because governance is an authority boundary, while ranking is operational selection inside
a pre-authorized set.

### Let the gateway mint or widen governance authorization

Rejected because the gateway is not the governance authority and must not broaden upstream approval.

### Trust unsigned caller-supplied governance scope

Rejected because caller metadata is not an authoritative governance fact.

### Auto-discover public keys from token-controlled URLs

Rejected because it would allow untrusted input to influence the signature trust root.

### Make the governance event sink an inline PDP

Rejected because evidence/reporting must not become an implicit second authorization path.

### Persist prompts/completions as default governance evidence

Rejected because Phase 9 established metadata-only telemetry/evidence as the default boundary.
