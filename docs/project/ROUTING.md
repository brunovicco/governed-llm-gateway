# Routing

## Stage A — deterministic authorization

The Policy Model Router receives prompt-free policy metadata and returns one authorized logical model
group with decision provenance. It performs no inference.

The gateway validates/correlates that external decision and intersects the model registry with the
authorized logical group. The resulting `AuthorizedCandidateSet` is the only candidate source Phase 5
may rank.

## Stage B — deterministic operational selection

Phase 5 implements static/versioned operational eligibility and ranking inside the Phase 4 authorized
candidate set.

Eligibility is evaluated before score, in deterministic order:

1. deployment enabled state;
2. trusted environment and data-classification allowance;
3. required text/vision/tool/structured-output capability availability;
4. sufficient context capacity;
5. static ranking evidence present for the deployment/workload;
6. versioned pricing evidence present;
7. conservative estimated cost within the projected cost ceiling;
8. versioned expected latency within the projected latency ceiling.

Unknown pricing is not free. Missing score input is not neutral. Either condition makes the deployment
ineligible.

Phase 5 does not use live health or circuit-breaker state. Those are Phase 6 eligibility inputs.

## Authorization invariants at the ranking boundary

Ranking fails closed when:

- the registry digest differs from the registry used to build the authorized candidate set;
- the request/projected workload or environment contradicts trusted context;
- the PDP decision environment contradicts trusted context;
- Phase 4 passes more than one authorized logical group;
- any candidate belongs to a group outside PDP authorization.

The gateway never re-enumerates the global registry after authorization to discover alternative model
groups.

## Score and tie-break

Each workload ranking policy contains five `Decimal` weights that sum exactly to `1`:

- quality;
- reliability;
- latency;
- cost;
- availability.

Each eligible deployment has versioned static inputs for those five dimensions. The score is the exact
weighted sum. Ranking order is:

1. descending total score;
2. ascending `deployment_id` for deterministic ties.

No LLM, randomness, wall clock, live provider result, or network state participates in Phase 5 score
calculation.

## Provenance

Selection evidence records enough metadata to reconstruct the decision without storing prompt or
completion content:

- deterministic routing decision ID;
- PDP policy ID/version/digest and decision ID;
- authorized logical model group;
- model-registry digest;
- ranking-policy version and digest;
- static score snapshot ID;
- selected provider/model/deployment when eligible;
- alternatives and machine-readable candidate rejection reasons.

`benchmark_snapshot_id` remains unset in Phase 5. `score_snapshot_id` identifies static ranking input
and must not be represented as empirical benchmark evidence.

## Explainability

`POST /v1/route/explain` is implemented in `gateway-api` as an authenticated, metadata-only,
no-inference surface.

Its flow is:

```text
Gateway credential
      ↓
trusted EffectivePolicyContext
      ↓
prompt-free PDP authorization
      ↓
AuthorizedCandidateSet
      ↓
static eligibility
      ↓
deterministic ranking
      ↓
selection/rejection provenance
```

The request schema rejects `messages`/prompt content, unsupported schema versions, unknown extra
fields, and invalid workload identifiers. The endpoint does not invoke a provider and does not expose
a global deployment inventory.

## Later routing inputs

Phase 6 adds runtime health, circuit breaker state, retry, and safe fallback while preserving the same
authorized group. Phases 10–11 replace/augment static quality inputs with approved benchmark evidence.
Adaptive routing remains explicitly later work.
