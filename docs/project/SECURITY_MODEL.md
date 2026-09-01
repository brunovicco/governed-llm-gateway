# Security Model

## Assets

Provider credentials, PDP credentials and authorization decisions, model registry/ranking policy,
workload identity, prompt/customer payload, routing provenance, operational health, and cost budgets.

## Trust boundaries

1. consumer → gateway authentication;
2. gateway → Policy Model Router;
3. gateway configuration/registry/ranking-policy supply chain;
4. Phase 4 authorized candidate set → Phase 5 ranking;
5. gateway → provider;
6. gateway telemetry/evidence sinks;
7. authenticated explain and later administrative/catalog surfaces.

## Authorization

Identity and policy failures fail closed. Operational selection may only narrow the candidate set
already authorized by the PDP.

Phase 5 treats `AuthorizedCandidateSet` as an authority boundary. Ranking fails closed if the current
registry digest no longer matches the authorization snapshot, if more than one logical group appears
under the current PMR 1.0 binding, or if a candidate falls outside PDP authorization.

Caller metadata can request stricter constraints but cannot downgrade authoritative classification,
risk, environment, or model authorization. The explain endpoint resolves trusted effective context
from the gateway credential before policy/ranking work.

Availability failures may later fail over only inside the already-authorized logical model group.
Retry/fallback/circuit-breaker behavior belongs to Phase 6 and receives no authority to widen policy.

## Configuration integrity

Model registry and ranking policy are security-relevant configuration. Both are treated as untrusted
until strict safe parsing, duplicate-key rejection, closed-schema/semantic validation, and
deterministic canonicalization succeed.

The registry digest binds the concrete candidate catalog to authorization. The ranking-policy digest
and static score snapshot ID bind the inputs used to order eligible deployments.

Unknown pricing and missing score inputs fail closed rather than becoming permissive defaults.

## Explainability surface

`POST /v1/route/explain` is an authenticated metadata-only surface. Its request schema rejects prompt
or message fields, unsupported schema versions, invalid workload identifiers, and unknown fields. It
performs no provider inference and does not expose a global deployment inventory.

## Secrets

Consumers receive only gateway credentials. Provider/PDP keys never enter consumer request
contracts, registry, ranking policy, logs, traces, benchmark artifacts, selection provenance, or
normalized error responses.

## Runtime privacy

Metadata-only evidence is the default. Payload capture must not be introduced implicitly by SDK
logging, exception serialization, middleware, explain output, or future telemetry exporters.
