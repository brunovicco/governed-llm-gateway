# Model Registry — Architecture Contract

Concrete deployments are configuration data, not hard-coded routing branches.

Each registry entry identifies provider, model ID, deployment ID, logical group, API family,
capabilities, context window, supported modalities, pricing metadata, maximum data classification,
allowed environments, enabled state, source date, and catalog version.

Registry membership does **not** authorize a model. Authorization comes from the Policy Model Router;
the gateway may only intersect/filter registry entries inside that PDP decision.

## Capabilities

Capabilities are deployment facts used only after PDP authorization to narrow operational eligibility.
Current capability vocabulary includes text, vision, tool calling, structured output, and streaming.

A streaming request therefore requires `Capability.STREAMING` on the concrete registry deployment.
That registry capability is necessary but not sufficient for execution: the provider/API-family adapter
must separately advertise verified native streaming and final-usage support. Adapter feature support
cannot add a deployment that registry/PDP eligibility excluded.

Generic OpenAI-compatible endpoints do not receive streaming/structured/tool capability by naming
convention. Their adapter feature support remains explicit verified configuration.

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
capabilities, and operational health are separate selection semantics.

Phase 5 ranks concrete deployment identities only after the PDP-authorized logical group has been
established. Phase 8 streaming continues to use the same concrete ranked identities and never creates
an alternate registry enumeration path.

## Pricing lifecycle

Pricing is time-dependent evidence, not a timeless model property. Known pricing carries source date
and snapshot/version metadata; unknown pricing is represented explicitly as `null`.

When a hard/effective `max_cost_usd` is enforced, unknown pricing makes the deployment ineligible
rather than optimistically cheap. A future explicit freshness policy may further restrict stale
pricing; the gateway does not infer freshness semantics absent from configuration.

## Validation and canonicalization

The registry contract provides:

- strict safe-YAML loading;
- duplicate-key rejection;
- closed-schema validation;
- semantic capability/modality validation;
- explicit unknown-pricing representation;
- deterministic canonicalization and SHA-256 digest;
- provider/model/deployment/logical-group identity separation.

Later phases consume this validated registry but do not change its authorization semantics. Streaming
capability is another fail-narrow eligibility fact, not a policy grant.
