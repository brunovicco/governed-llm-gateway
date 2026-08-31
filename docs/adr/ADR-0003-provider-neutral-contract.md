# ADR-0003 — Provider-Neutral Request/Response Contract

Status: Accepted (draft contract may evolve compatibly before Phase 2 freeze)
Date: 2026-08-31

## Context

Applications should describe workload/requirements without provider-specific model IDs, APIs, or
credentials. The policy router must not receive prompt content.

## Decision

Create immutable Python contracts for `GatewayRequest`, `GatewayResponse`,
`WorkloadRequirements`, `Usage`, `ToolDefinition`, `ToolCall`, `ToolResult`, `RoutingProvenance`,
`ProviderExecution`, and `GatewayError`.

`Workload` is a validated dotted policy-defined identifier rather than a closed Python enum.
`DataClassification` and `RiskLevel` remain controlled vocabularies.

The canonical request contains declared risk/data metadata, requirements, limits, and messages. Risk,
classification, identity, and environment-related claims do not become authoritative merely because
they appear in the request.

No provider SDK/type may appear in the public contract.

## Consequences

- consumers are insulated from provider API changes;
- provider adapters translate to/from canonical types;
- future HTTP serialization can evolve around a stable semantic contract;
- Phase 2 will finalize validation/schema details and backward-compatibility rules.
