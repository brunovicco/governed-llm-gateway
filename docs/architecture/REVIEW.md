# Phase 0 Architecture Review

Reviewer pass: second-pass architecture/security review during artifact construction.
Preferred external reviewer from project plan: Claude Code (not available in the build sandbox).

## Findings checked

### PDP/PEP authority

PASS. `gateway-core/domain/authorization.py` encodes and tests the monotonic subset invariant. No
operational logic can broaden authorization in Phase 0.

### Caller-controlled security attributes

PASS. Contracts explicitly describe classification/risk as declared context, and the architecture
adds authenticated/effective policy context. A downgrade cannot self-authorize.

### Package contamination

PASS. Static architecture checks reject provider SDK, FastAPI, HTTP client, OpenTelemetry, database,
and selected infrastructure imports from contracts/domain.

### Consumer dependency inversion

PASS. Static checks reject imports of named business consumer projects from gateway code.

### Provider API calls in Phase 0

PASS. No provider SDK, endpoint, credential, or concrete deployment exists in runtime code/config.

### Admin/explain information disclosure

RESOLVED IN DESIGN. Future `/v1/models`, `/v1/route/explain`, metrics/readiness surfaces are explicitly
defined as authorized/scoped surfaces rather than globally public catalog endpoints.

### Fallback/idempotency boundary

RESOLVED IN DESIGN. Cross-provider fallback after side effects or opaque provider state is blocked by
default until an explicit replay strategy exists.

### Pricing provenance

RESOLVED IN DESIGN. Pricing is a dated/versioned snapshot; stale/unknown price does not satisfy a hard
cost ceiling optimistically.

### Evidence privacy

PASS IN DESIGN. Routing evidence is reconstructable from metadata and does not require prompt,
completion, tool content, secret, or raw provider error storage.

## Remaining review action

Run the same repository through Claude Code using `CLAUDE.md` before production-oriented Phase 1/2
merge. Any architecture change resulting from that review requires an ADR.
