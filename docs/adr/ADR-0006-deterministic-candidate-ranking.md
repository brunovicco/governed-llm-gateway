# ADR-0006 — Deterministic Candidate Ranking

Status: Accepted  
Date: 2026-08-31

## Context

Phase 4 establishes the authorization boundary between the Policy Model Router (PDP) and the
Governed LLM Gateway (PEP):

`Gateway allowed set ⊆ Policy Router authorized set`

Phase 5 must choose one concrete deployment from that already-authorized set. The initial ranking
inputs are static and versioned. Runtime health, circuit-breaker state, retry/fallback behavior and
benchmark-derived scores belong to later phases.

The ranking decision must be explainable without prompt storage and reproducible from metadata.

## Decision

The gateway uses a strict versioned ranking policy with:

- one workload-specific set of five non-negative weights that sum exactly to `1`;
- one static score record per configured deployment containing quality, reliability, latency, cost
  and availability dimensions in `[0, 1]`;
- a versioned expected-latency input used for the Phase 5 latency eligibility ceiling;
- `policy_version`, `score_snapshot_id`, `source_date`, and a canonical SHA-256 ranking-policy digest.

Ranking uses `Decimal` arithmetic. Eligible candidates are ordered by:

1. descending weighted score;
2. ascending `deployment_id` as the explicit deterministic tie-breaker.

The score is:

`quality*wq + reliability*wr + latency*wl + cost*wc + availability*wa`

No LLM, random value, wall-clock value, provider call, live health signal, or dynamic network input
participates in the Phase 5 ranking calculation.

## Eligibility before ranking

Only the Phase 4 authorized candidate set may enter Phase 5.

The Phase 5 static eligibility gate can only remove deployments. It evaluates, in deterministic
order:

1. deployment enabled state;
2. trusted environment and data-classification allowance;
3. required capabilities;
4. context capacity;
5. presence of versioned static ranking inputs;
6. known versioned pricing;
7. conservative estimated cost against the already-projected cost ceiling;
8. versioned expected latency against the already-projected latency ceiling.

Unknown pricing is not treated as zero cost. Missing ranking inputs are not treated as neutral or
default scores. Both conditions make the deployment ineligible.

Phase 6 will add runtime health and circuit-breaker eligibility. Phase 5 does not synthesize those
signals.

## Cost estimate

The Phase 5 eligibility cost estimate uses the Policy Model Router projection metadata already
computed from trusted context:

- `context_tokens_estimated`;
- `max_output_tokens_estimated`.

It applies the registry's versioned input/output token prices and compares the conservative estimate
with the effective projected `max_cost_usd`.

## Selection provenance

Every ranking decision carries metadata sufficient to reconstruct the selection:

- deterministic routing decision ID (`sha256:...`);
- PDP policy provenance;
- authorized logical model group;
- model-registry digest;
- ranking-policy version and digest;
- static score snapshot ID;
- selected provider/model/deployment when one is eligible;
- machine-readable rejection reasons for evaluated candidates.

The deterministic routing decision ID is derived from canonical metadata inputs, scores and
rejections. Prompt/message content is never part of the decision ID.

`benchmark_snapshot_id` remains unset in Phase 5. The static score snapshot is not represented as an
empirical benchmark.

## Explainability surface

`POST /v1/route/explain` performs:

authentication-context resolution → PDP authorization → eligibility → ranking → explanation.

It performs no provider inference and its request schema intentionally rejects prompt/message fields.

The API is a security boundary. It requires a gateway credential and receives trusted effective
context through an injected resolver. The endpoint never accepts caller-supplied effective
environment/risk/classification as authoritative.

## Consequences

Positive:

- same validated inputs produce the same ranking and decision ID;
- an ineligible deployment cannot win;
- ties are stable across processes;
- missing pricing or ranking evidence fails closed;
- policy and registry provenance remain distinct;
- explainability can be provided without prompt storage.

Trade-offs:

- Phase 5 scores are static and must not be presented as benchmark evidence;
- expected latency is a versioned planning input, not live health;
- runtime availability and adaptive routing are intentionally deferred.

## Rejected alternatives

### Hard-coded model preferences

Rejected because they are not versioned, explainable policy inputs and would encode subjective model
preferences directly in application code.

### Random or load-dependent tie-breaking

Rejected because the same inputs would no longer produce the same decision.

### Treat unknown price as free

Rejected because it can bypass cost ceilings.

### Rank before eligibility

Rejected because a high score could make a policy- or capability-ineligible deployment win.

### Include runtime health in Phase 5

Rejected because health state and circuit breakers belong to Phase 6 and would make the initial
ranking input set dynamic.
