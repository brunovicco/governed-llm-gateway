# Model Registry Contract

Phase 2 turns the Phase 0 registry draft into a validated, versioned configuration artifact.
ADR-0005 remains the architectural authority for registry identity and provenance.

## Boundary

Registry parsing is an adapter concern. Validation/canonicalization is deterministic domain logic.
Neither layer performs inference or has authorization authority.

Provider, model, deployment, and logical model group are distinct identities. Registry membership does
not grant authorization; the gateway may only select deployments inside the logical model groups
already authorized by the Policy Model Router.

## Schema behavior

The registry uses a closed schema. Unknown fields, missing required fields, duplicate mapping keys,
invalid identifiers, invalid dates/numbers, and invalid semantic combinations are rejected.

Each concrete deployment records:

- provider;
- model identifier;
- logical model group;
- API family;
- capability flags;
- context-token capacity;
- modalities;
- pricing snapshot or explicit unknown pricing;
- maximum data classification;
- allowed environments;
- enabled state;
- source date;
- catalog version.

Text capability and text modality are mandatory. Vision capability and image modality must be
specified together. These are contract-level consistency rules, not claims that every provider shares
identical API behavior.

## YAML safety

The YAML adapter derives from `yaml.SafeLoader` and overrides mapping construction to reject duplicate
keys before a later value can silently replace an earlier one. Python object tags and other unsafe
construction are not permitted.

Parsed YAML remains untrusted input until domain validation succeeds.

## Pricing

Pricing is temporal evidence. Known pricing includes input/output USD per million tokens, source date,
and snapshot version. Unknown pricing is represented explicitly as `null`; it must not be silently
interpreted as free or as satisfying a future hard cost ceiling.

## Deterministic provenance digest

The digest is calculated only after validation. The registry is converted to a canonical
JSON-serializable representation with:

- deployment IDs sorted;
- sets converted to sorted values;
- capability keys emitted deterministically;
- dates normalized to ISO format;
- equivalent decimal values normalized to one textual representation;
- stable JSON key ordering and separators.

The SHA-256 of that canonical representation is the `model_registry_digest` used by later routing and
execution provenance. YAML formatting or ordering changes that preserve semantic content therefore do
not change the digest; meaningful validated content changes do.

## Phase 2 catalog state

`config/model_registry.yaml` is intentionally valid but empty. Phase 2 establishes the contract and
validator without asserting that any concrete provider deployment is production-approved.
