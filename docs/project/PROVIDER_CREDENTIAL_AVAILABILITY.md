# Provider credential availability — internal contracts and local conformance

Status: provider-neutral values, application ports, a process-local reference adapter, and an
adapter-only versioned secret boundary implemented for review only. No serving integration or
shared/durable availability backend exists. The current
string-only secret resolver, static adapter bootstrap, provider error normalization, transient health,
and retry/fallback behavior are unchanged.
See [ADR-0019](../adr/ADR-0019-provider-credential-binding-availability.md) for the proposed full design.

## What this slice implements

`gateway-core/domain/credential_availability.py` contains frozen, slotted internal values:

- `CredentialGeneration`: binding, activation epoch, material identity, exact-version handle,
  secret-free runtime provenance, and authentication-scope provenance.
- `CredentialGenerationPublication`: controller compare-and-set intent for a newer epoch of the
  same binding, with the complete expected prior generation. Same-material activation is representable,
  but it grants no permission to clear retained quarantine.
- `CredentialAvailabilitySnapshot`: a closed state vocabulary and exact-token candidate-eligibility
  predicate. UNKNOWN has no proven generation and always narrows out.
- `CredentialAdmission`: an ordinary attempt or a validation owner with an opaque validation fence
  and explicit positive finite remaining lifetime.
- `CredentialCompletionReceipt`: attribution and a separate completion fence, so store validation
  of a successful promotion need not require its already-retired lease to remain live.
- `CredentialBindingRejection`: a fact attributed to the generation actually used and a separately
  reviewed classifier. It accepts neither raw provider errors nor HTTP statuses as evidence.

Opaque IDs use 1–128 ASCII letters/digits/dot/underscore/hyphen, starting with a letter/digit.
Epochs are integers from 1 through `2**63 - 1`; booleans are not integers for this contract. A future
adapter must preserve their exact value, not round them through floating-point JSON/Lua conversions.
Provenance has the canonical `sha256:<64 lowercase hex>` shape and describes secret-free artifacts/
scope, not a public hash of secret material. Validation lifetimes reject non-numeric, boolean,
non-positive, non-finite, and overflowing numeric values. Deployment timeout selection is deferred.

`secret_version_id` is an opaque trusted-authority handle bound to one exact backend version. It is
not a raw secret reference/locator and does not itself resolve anything. The operational adapter must
verify this mapping and material equality/history before publication/construction. No authority,
version schema, resolver migration, or backend version guarantee is manufactured here.

## Reads are not admission or authorization

The pure snapshot predicate accepts only a matching AVAILABLE or PENDING_VALIDATION generation.
Pending material must be rankable so an ordinary freshly governed request can attempt validation;
otherwise validation would never begin. Execution must still atomically acquire admission. A
VALIDATING snapshot excludes another candidate selection; its existing owner instead checks its
captured admission through the worker port. UNKNOWN, QUARANTINED, or any mismatched token narrows out.
Repeated predicate reads cannot claim/renew ownership or change the snapshot.

None of these predicates grants PDP authorization, registry eligibility, cache access, a retry, or
provider acceptance. Constructing a valid token/admission/receipt proves shape only, not trusted
issuance, ownership, liveness, or an authenticated controller/worker identity.

## Consumer-owned application ports

`gateway-core/application/credential_availability.py` defines three separate capabilities:

- `CredentialAvailabilityReadPort`: validated read-only snapshots; no lease or token publication.
- `CredentialAvailabilityPort`: exact-token atomic admission/check/release, owned validation
  completion, current-completion check, and material-scoped rejection observations.
- `CredentialGenerationPublisher`: trusted controller-only generation publication with explicit
  compare-and-set intent; no provider execution or direct AVAILABLE-state publication.

The worker contract requires one non-renewing finite validation owner, matching-token fencing,
neutral finally release, and rejection tombstones for all activatable versions. Late evidence must
retain quarantine only for its observed binding/material, but also block a newer active epoch if
that same material was reactivated. Ordinary concurrent success cannot promote or clear quarantine.
Accepted completion issues a receipt before retiring ownership; any serving success publication
must separately check that store-issued receipt/current AVAILABLE generation, not just local owner
correlation.

Publisher CAS conflicts return false; infrastructure/corrupt-state failures raise a sanitized
`CredentialAvailabilityError`. Missing authoritative evidence is UNKNOWN/deny. `expected_generation=None`
is first authoritative activation, not a reset of lost/corrupt state. All capabilities require
authoritative reconciliation and retained history; none silently falls back to permissive local state.

These are adapter obligations; the reference implementation below exercises transitions only within
one explicit memory-state object. Separating Python Protocols does not enforce backend ACLs or
authenticate a worker. No durable store, refresh task, provider classifier, or control-error HTTP
mapping is included.

## Process-local reference adapter

`adapters/credential_availability_memory.py` provides an explicit state object plus separate reader,
worker, and synthetic publisher wrappers. Wrappers sharing that exact object observe the same
records. A state-owned thread lock serializes short synchronous metadata-only transitions, including
local clients running in different threads/event loops. Critical sections contain no await or remote
I/O; injected clock callbacks must be synchronous, side-effect-free, and non-reentrant. There are no
background tasks, secret reads, imports into composition/bootstrap, or provider calls.

The state takes an explicit positive finite validation lease and a clock (process-monotonic by
default). Claims capture one fixed deadline and a fresh ownership fence. Rechecks return only the
remaining lifetime; reads project expired ownership as PENDING without claiming or renewing it.
Expiry at the exact deadline denies completion. A replacement, even with the same attempt ID,
gets a different fence. Matching finally release is neutral and cannot release a replacement.
Caller-owned finally fixtures test task cancellation, generator close, and local failure; these
are not tests of the unwired serving executors.

Only complete success asserted by the trusted synthetic caller can promote the current live owner.
The adapter does not examine a provider response or manufacture acceptance evidence. Promotion
atomically stores a separate completion receipt and retires the lease; a still-current accepted
duplicate returns that same receipt without reactivation. Ordinary AVAILABLE attempts are concurrent
but cannot promote. Fabricated/stale handles and receipts do not prove ownership/completion.
Rotation or rejection invalidates subsequent checks, not an already-delivered network response.

Publication compares the full prior token; conflicting intents return false. Exact current-intent
duplicates do not reset validation, availability, or quarantine. Every new unquarantined activation
is conservatively PENDING, including unchanged material under a new epoch. Already-rejected material
is recorded as QUARANTINED rather than being admitted. Epochs remain exact Python integers.
Rejection accepts only an exact generation in this state's published history and retains a
binding/material tombstone. A retired token's fact spares genuinely different material, but blocks
the same material under a new epoch/version alias or rollback. Reconstructing wrappers over the
same retained state does not erase history; equal material labels in separate bindings are not
global equivalence.

Clock exceptions and fence-source failures become sanitized UNAVAILABLE errors with suppressed
raw chaining. Malformed/regressing clocks, reused/invalid fences, unrepresentable deadlines, and
missing/inconsistent known records raise INVALID_STATE without granting admission/promotion.
Clock high-water bookkeeping prevents an observed expired lease from reviving after time regresses.
Cleanup and proven rejection need no clock because neither can promote or renew. Private-record
fault fixtures prove these local branches, not serialized-record validation or backend recovery.

History/tombstones/fences have no TTL or eviction in this reference object. Capacity management and
retirement proofs are deferred. A fresh object is for previously unseen synthetic bindings only:
it projects UNKNOWN and cannot know a prior process's quarantine. No process-restart/failover
durability, authority-issued material identity, exact-version fetch, ACL authentication, or
cross-replica exclusion is provided. This adapter is not a shared-mode fallback and is not selected
by any runtime configuration. It must not be used to claim safe restoration of real credentials.

## Adapter-only versioned secret boundary

`adapters/provider_credentials_versioned.py` defines `VersionedProviderCredential` and the separate
asynchronous `VersionedProviderSecretResolver.resolve_version(generation)` contract. Sensitive
material remains in adapters; domain/application/public contracts contain no new secret-bearing
result type. The result is frozen/slotted, hides every field from default repr, and uses identity
equality/hash rather than comparing or hashing plaintext. Explicit access/serialization remains
possible; this is neither a sandbox nor zeroization.

`resolve_exact_provider_credential` passes the captured generation to the injected resolver once,
rejects untyped requests before resolver access, and rejects untyped/mismatched results across all
six token dimensions. It validates non-empty string material without whitespace or C0/C1 controls,
not a provider-specific key format or complete HTTP-header compatibility. Backend transport/size
bounds, response verification, and deterministic adapter construction remain separate obligations.
Backend exceptions become a fixed UNAVAILABLE error with suppressed raw chaining; invalid result
metadata/material becomes INVALID_RESULT. Cancellation propagates so the concrete resolver's finally
owns resource cleanup. No retry, latest fallback, environment fallback, cache, publication, admission,
provider validation, adapter swap, timeout setting, or background task is introduced.

This checks token correlation only. A forged result with matching metadata can still contain the
wrong material; a constructor/Protocol cannot prove trusted issuance or fetch provenance. The
operational adapter must verify the opaque handle's private locator/exact backend version, stable
binding/material identity, and runtime/authentication-scope provenance before returning a result.
Missing mapping/history or an unavailable authority must deny. The string-only environment resolver
does not implement this capability and cannot mint version/material metadata to satisfy it.

The module is not exported from the adapter facade or imported into bootstrap/executors/config.
Synthetic tests exercise exact correlation, integer epochs, malformed results/material, immutability,
repr/error privacy, and task cancellation. They establish no actual backend fetch, authority identity,
shared-control admission, restart/failover durability, or provider acceptance.

## Operational backend guidance — no backend selected

The inspected deployment documentation describes a local Docker profile and environment-injected
credentials, not an adopted production cloud or versioned authority. Prefer the managed secret
service of the eventual hosting cloud rather than introduce a new cloud solely for this feature:

- AWS: Secrets Manager can request an explicit `VersionId`; omitting version/stage selects
  `AWSCURRENT`. Use exact version, not mutable stage, for generation-bound fetch.
  [GetSecretValue](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html).
- Google Cloud: Secret Manager accepts an explicit version resource; `latest` and aliases are not
  immutable generation identifiers.
  [Access a secret version](https://docs.cloud.google.com/secret-manager/docs/access-secret-version).
- Azure: Key Vault GET accepts a secret version; omitting it returns latest.
  [Get Secret](https://learn.microsoft.com/en-us/rest/api/keyvault/secrets/get-secret/get-secret?view=rest-keyvault-secrets-2025-07-01).

Vault KV v2 is a versioned alternative when cloud-independent operation is a deliberate requirement,
not the default recommendation for the current local profile.
[KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2).

These are candidate storage primitives, not an accepted authority/backend design. Exact backend
versions alone do not establish unchanged-material identity across aliases/republication, monotonic
activation, or retained quarantine. A separately trusted controller and authoritative history must
reconcile those facts with a reviewed durability/recovery model and scoped publisher/worker rights.
Do not equate secret-manager availability with credential AVAILABLE state. Until hosting/authority
choices and conformance are reviewed, keep serving unchanged; no cloud service, SDK dependency,
credentials, permissions, infrastructure, or operational adapter is provisioned by these slices.

## Privacy and non-claims

Identity/version/provenance/fence fields are hidden from default repr, and validation errors never
echo rejected input. Control exceptions accept only closed categories and contain a fixed sanitized
message. Infrastructure adapters must suppress raw backend exception chaining at their boundary.
The objects have no public DTO/codec export or telemetry wiring. Repr hiding is not permission to
serialize them via `asdict`, log attributes, or use IDs as metric labels. Only allowlisted state/
outcome metadata may leave the process under ADR-0008.

The contract tests verify value shape, immutability, exact equality, pure eligibility, publication
intent constraints, owner/receipt correlation, closed evidence categories, and repr/error privacy.
The reference conformance suite additionally verifies local owned transitions, CAS races, thread/
event-loop serialization, expiry, caller finally cleanup, delayed/duplicate facts, rollback, and
fault sanitization. The adapter-only secret boundary suite checks correlation, not actual issuance
or retrieval. None of these suites establishes cross-replica exclusion, quarantine durability,
authority material stability after restart/alias changes, provider acceptance, serving cancellation,
distributed clock coherence, backend ACLs/TLS, or actual generation-fenced serving. Those need
separately verified operational authority/backend conformance and integration.

## Next increments and verification

Local conformance is implemented at the bounded reference scope above. Next separately select
and verify a trusted publisher/exact-version adapter, closed versioned configuration/provenance,
shared-store recovery/durability model, and refresh lifecycle before any fleet activation. Integrate
ranking/preflight/executors/cache checks only after those boundaries are verified. Review each
provider-specific rejection classifier separately; generic 401/403 normalization stays unchanged.

For these slices run all three focused availability/versioned-secret modules,
`uv run python scripts/phase0_gate.py`,
`uv run python scripts/quality_gate.py`, and `git diff --check`. No real credential/provider call,
new benchmark, approved ranking change, consumer migration, or operational rollout is required or
claimed by these credential-free checks.
