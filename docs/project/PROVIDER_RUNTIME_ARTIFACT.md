# Provider Runtime Artifact

## Purpose

PC-1 turns the PC-0 typed provider runtime boundary into a committed deployment artifact without
moving provider configuration into the Model Registry and without introducing provider secrets into
source control.

The artifact is `config/providers/runtime.json`.

## Closed document schema

The root contains exactly:

- `schema_version` — currently `1.0`;
- `config_version` — normalized deployment snapshot identity;
- `bindings` — provider/API-family runtime bindings.

Each binding requires:

- `provider`;
- `api_family`;
- `credential_reference`;
- `endpoint`.

`anthropic_api_version` is optional and valid only for `anthropic-messages`.
`openai_compatible` is mandatory for `openai-compatible` and invalid for native API families. Its
feature fields are all explicit so compatible endpoints cannot acquire optional capabilities by
convention or omitted defaults.

Unknown fields, missing fields, duplicate JSON object keys, duplicate `(provider, api_family)`
bindings, unsupported schema/API-family values, unsafe endpoints, and malformed credential references
fail closed.

The schema has no API-key or raw credential field. `credential_reference` is resolver-neutral and is
not dereferenced during parsing.

## Why JSON

PC-1 uses JSON for this operational artifact so duplicate keys can be rejected with the standard
library while retaining strict typing and without adding new untyped YAML suppressions. This is a
format choice at the adapter boundary; it does not alter the provider-neutral runtime contract.

## Deterministic provenance

After validation, the document is canonicalized with:

- stable root field values;
- bindings sorted by `(provider, api_family)`;
- explicit compatible feature fields;
- stable JSON key ordering and separators.

A SHA-256 digest over that canonical payload identifies the exact provider runtime configuration
snapshot. Whitespace, JSON key ordering, and binding ordering therefore do not change the digest when
the validated semantics are equivalent.

The digest is operational provenance, not authorization evidence.

## Model Registry cross-check

PC-1 derives the set of runtime bindings required by **enabled** Model Registry deployments:

```text
required = {(deployment.provider, deployment.api_family) for enabled deployments}
configured = {(binding.provider, binding.api_family) for runtime bindings}
```

The sets must be equal.

Consequences:

- a missing binding fails closed before provider execution;
- an extra/stale binding with no enabled registry deployment also fails closed;
- multiple enabled concrete deployments may share one provider/API-family binding;
- disabled registry deployments do not require active runtime bindings.

This equality is an operational completeness invariant only. The provider artifact cannot enumerate
an executable candidate set, grant a logical model group, bypass the PDP, or resurrect a rejected
candidate. Normal routing remains:

```text
PDP authorization
    -> authorized model group
    -> registry eligibility
    -> complexity/ranking narrowing
    -> selected concrete deployment
    -> provider runtime resolver
```

## Secret and I/O boundary

`load_provider_runtime_document(...)` and `validate_provider_runtime_registry(...)` perform no secret
resolution, provider network I/O, model calls, or credential validation against an external backend.

Only later composition passes validated `ProviderRuntimeConfig` values to a `ProviderSecretResolver`
and adapter factory. This ordering keeps malformed/stale deployment artifacts separate from secret
backend access.

## Current repository state

`config/model_registry.yaml` currently contains an empty `deployments` mapping, so
`config/providers/runtime.json` intentionally contains an empty `bindings` array. These two empty
artifacts satisfy the PC-1 operational-set invariant without asserting that any provider/model is
production-approved.

## Deferred startup composition

PC-1 does not yet make the FastAPI process load these artifacts automatically. A subsequent startup
composition increment can load the Model Registry plus provider runtime document, validate their
relationship, then resolve server-side credentials and construct the provider resolver.

That startup work must continue to fail closed and must not give configuration any routing authority.
