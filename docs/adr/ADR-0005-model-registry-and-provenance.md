# ADR-0005 — Model Registry and Provenance

Status: Accepted
Date: 2026-08-31

## Context

Routing must be reconstructable and must not hard-code current model catalogs or subjective
preferences in application logic.

## Decision

Concrete deployments live in a validated, versioned model registry. Each entry records provider,
model, deployment, logical group, API family, capabilities, context/modalities, structured/tool/
streaming support, pricing metadata, data policy, allowed environments, source date, and catalog
version.

A canonical validated registry receives a deterministic SHA-256 digest. Every routing/execution result
records the registry digest used for selection.

Provider + model + deployment are distinct identities. The same model family on different providers
is not assumed equivalent.

Pricing is snapshot evidence with source date/version. Unknown or stale pricing cannot silently pass a
hard cost ceiling.

## Consequences

- catalog/model additions are data changes when API semantics are already supported;
- registry tampering/configuration changes become visible in provenance;
- Phase 2 must define canonicalization, schema validation, duplicate rules, capability constraints,
  and deterministic digest tests.
