# Observability and Evidence

Runtime OpenTelemetry integration begins in Phase 9 using `a2a-otel-kit`; Phase 0 fixes the privacy and
provenance contract.

Metadata evidence should include request/correlation IDs, workload, policy decision ID and
policy ID/version/digest, model group, registry digest, ranking policy version, benchmark snapshot,
provider/model/deployment, retry/fallback counts or sequence, token usage, latency, and outcome.

Default telemetry must not contain prompts, completions, tool arguments/results, API keys,
Authorization headers, arbitrary customer payloads, or unsanitized provider error bodies.

W3C trace context should eventually remain continuous across application → gateway → provider and
MCP/A2A boundaries without making a2a-otel-kit a domain dependency.
