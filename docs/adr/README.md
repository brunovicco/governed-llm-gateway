# Architecture Decision Records

Accepted in Phase 0:

- ADR-0001 — Gateway vs Policy Router boundary
- ADR-0002 — Workspace/package topology
- ADR-0003 — Provider-neutral request/response contract
- ADR-0004 — Native APIs vs OpenAI-compatible adapters
- ADR-0005 — Model registry and provenance

Accepted after Phase 0 when implementation evidence became available:

- ADR-0006 — Deterministic candidate ranking (Phase 5)
- ADR-0007 — Fallback safety semantics (Phase 6)
- ADR-0008 — Metadata-only telemetry (Phase 9)
- ADR-0009 — Benchmark-derived routing scores (Phase 11)
- ADR-0010 — Client SDK boundary (Phase 12)
- ADR-0011 — Streaming normalization (Phase 8)
- ADR-0012 — Governance authorization integration (Phase 13)
- ADR-0013 — Structured output and tool normalization (Phase 7)
- ADR-0014 — Canonical multimodal content and fail-closed capabilities
- ADR-0015 — Northbound Anthropic Messages and OpenAI Responses protocols
- ADR-0016 — Pinned external Policy Router in governed Compose
- ADR-0017 — Deterministic streaming preflight before HTTP response commit

The ADR numbers preserve the original roadmap reservations. Acceptance order follows implementation
evidence rather than numeric order; later decisions do not rewrite earlier accepted records.

See `ADR-BACKLOG.md` for any decision topics that remain intentionally unpromoted from backlog to an
accepted ADR.

Proposed for design review (not implemented):

- [ADR-0019 — Versioned provider credential-binding availability](ADR-0019-provider-credential-binding-availability.md)
