# Model Registry — Architecture Contract

Concrete deployments are configuration data, not hard-coded routing branches.

Each future registry entry must identify at least provider, model ID, deployment ID, logical group,
API family, capabilities, context, modalities, structured output/tool/stream support, pricing metadata,
data-policy classification, allowed environments, source date, and catalog version.

## Provenance

A canonical representation of the validated registry receives a deterministic SHA-256 digest. Every
routing/execution result records the digest used for selection.

## Deployment identity

The same model family exposed through different providers/deployments is not assumed equivalent.
Provider, deployment, data policy, API family, pricing, approval environment, and operational health
are part of selection semantics.

## Pricing lifecycle

Pricing is time-dependent evidence, not a timeless model property. Entries must carry source date and
snapshot/version metadata. If a hard `max_cost_usd` must be enforced and current pricing is unknown or
outside its approved freshness policy, that deployment is ineligible rather than optimistically cheap.

Phase 2 will implement schema validation, canonicalization, digest, duplicate detection, capability
validation, and registry-loading tests.
