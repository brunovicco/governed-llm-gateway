# Model Registry — Architecture Contract

Concrete deployments are configuration data, not hard-coded routing branches.

Each registry entry identifies provider, model ID, deployment ID, logical group, API family,
capabilities, context window, supported modalities, pricing metadata, maximum data classification,
allowed environments, enabled state, source date, and catalog version.

Registry membership does **not** authorize a model. Authorization comes from the Policy Model Router;
the gateway may only intersect/filter registry entries inside that PDP decision.

## Provenance

A canonical representation of the validated registry receives a deterministic SHA-256 digest. The
digest is bound into authorization/routing evidence so later selection can prove which concrete
catalog snapshot was evaluated.

Phase 5 requires the current registry digest to match the digest attached to the Phase 4
`AuthorizedCandidateSet`. A mismatch is a fail-closed invariant violation rather than an opportunity
to re-enumerate the new registry.

## Deployment identity

The same model family exposed through different providers/deployments is not assumed equivalent.
Provider, model, deployment, logical group, data policy, API family, pricing, approval environment,
and later operational health are separate selection semantics.

Phase 5 ranks concrete deployment identities only after the PDP-authorized logical group has been
established.

## Pricing lifecycle

Pricing is time-dependent evidence, not a timeless model property. Known pricing carries source date
and snapshot/version metadata; unknown pricing is represented explicitly as `null`.

When a hard/effective `max_cost_usd` is enforced in Phase 5, unknown pricing makes the deployment
ineligible rather than optimistically cheap. A future explicit freshness policy may further restrict
stale pricing; Phase 5 does not silently infer freshness semantics that are absent from configuration.

## Validation and canonicalization

Phase 2 delivered:

- strict safe-YAML loading;
- duplicate-key rejection;
- closed-schema validation;
- semantic capability/modality validation;
- explicit unknown-pricing representation;
- deterministic canonicalization and SHA-256 digest;
- provider/model/deployment/logical-group identity separation.

Phase 5 consumes that validated registry; it does not change registry authorization semantics.
