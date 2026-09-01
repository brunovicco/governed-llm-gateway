# Security Model

## Assets

Provider credentials, PDP credentials/authorization decisions, model registry/ranking policy,
workload identity, prompt/customer payload, routing provenance, runtime health/circuit state, retry
budgets, and cost budgets.

## Trust boundaries

1. consumer → gateway authentication;
2. gateway → Policy Model Router;
3. gateway configuration/registry/ranking-policy supply chain;
4. Phase 4 authorized candidate set → Phase 5 ranking;
5. Phase 5 ranked candidates → Phase 6 resilient execution;
6. gateway → provider;
7. gateway telemetry/evidence sinks;
8. authenticated explain and later administrative/catalog surfaces.

## Authorization

Identity and policy failures fail closed. Operational selection and resilience may only narrow or
traverse the candidate set already authorized by the PDP.

Phase 5 validates registry continuity, single-group PMR 1.0 semantics, and candidate group membership.
Phase 6 pre-validates the bounded fallback sequence against the same authorized logical model group
before the first provider call.

A provider failure never grants permission to re-enumerate the registry, select a different logical
model group, or reacquire a wider PDP authorization.

Caller metadata can request stricter constraints but cannot downgrade authoritative classification,
risk, environment, or authorization.

## Resilience safety

Automatic replay is restricted to normalized provider errors that are both retryable and classified
as rate-limit, timeout, unavailable, or transport failures.

Permanent validation/authentication/authorization/configuration errors stop automatic retry/fallback.
Retry attempts, fallback count, backoff, jitter, and provider `Retry-After` influence are bounded.

`FallbackSafetyState` blocks replay after:

- observed provider/model output;
- an external side effect;
- opaque provider continuation/reasoning state.

This conservative boundary prevents availability behavior from duplicating external actions or
continuing provider-specific hidden state across providers.

## Runtime health and circuit state

Circuit breaker state is per concrete deployment and initially per process. Open circuit makes the
deployment operationally ineligible. Missing active health evidence fails closed when runtime-health
filtering is enabled.

Health state can remove a deployment but cannot authorize one. Runtime health is not written into the
Phase 5 static score and is not benchmark evidence.

## Configuration integrity

Model registry and ranking policy remain security-relevant untrusted configuration until strict safe
parsing, duplicate-key rejection, closed-schema/semantic validation, and deterministic
canonicalization succeed.

The registry digest binds the concrete catalog to authorization. Ranking-policy digest/static score
snapshot bind the deterministic selection inputs. Phase 6 does not modify these authorization or
ranking provenance identities when an execution failure occurs.

## Explainability surface

`POST /v1/route/explain` is authenticated, prompt-free, metadata-only, and provider-free. It exposes
decision-scoped information rather than a global deployment inventory.

## Secrets

Consumers receive only gateway credentials. Provider/PDP keys never enter consumer request contracts,
registry/ranking policy, routing/attempt evidence, logs, traces, benchmark artifacts, or normalized
error responses.

## Runtime privacy

Metadata-only evidence is the default. Phase 6 records normalized error categories/status, timing,
health/circuit state, and deployment progression—not raw provider bodies, arbitrary headers, prompt or
completion content.

Payload capture must not be introduced implicitly by SDK logging, exception serialization,
middleware, explain output, retry handling, circuit state, or future telemetry exporters.
