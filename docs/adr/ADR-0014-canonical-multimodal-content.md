# ADR-0014: Canonical multimodal content and fail-closed capabilities

- Status: Accepted
- Date: 2026-09-15

## Context

The original message contract represented text plus HTTPS image URLs. Agent protocols also carry
inline images, audio, documents, prior tool calls and tool results. Passing provider dictionaries
through core would couple governance to a vendor and make unsupported inputs easy to ignore.

## Decision

Messages expose an immutable union of text, image, audio, document, tool-use and tool-result blocks.
Legacy `content`/`images` remain valid and project to the same canonical view. HTTPS media references
are forwarded but never fetched; inline data is strict base64 capped at 4 MiB decoded per block;
audio and documents are inline-only. Tool results must correlate with a prior tool-use block.

Registry capabilities add audio, document and parallel tool calling. They default to false when
absent from a 1.0 registry, preserving old artifacts and digests. Eligibility is the intersection of
request requirements, PDP-authorized candidates, registry capabilities and adapter wire support.
Unsupported features fail before transport. A request containing tool results gets one provider
attempt and no fallback because replay could duplicate an external side effect.

## Consequences

- Provider-specific payload types remain in adapters.
- A deployment must explicitly opt into every new capability; provider availability grants nothing.
- The runtime represents audio/documents today even when a deployed registry has no eligible model.
  Such requests receive a stable no-eligible-deployment failure rather than silent degradation.
