# ADR-0001 — Gateway vs Policy Router Boundary

Status: Accepted
Date: 2026-08-31

## Context

Authorization and operational model selection are different authorities. Mixing them would allow
health, cost, benchmark, or availability logic to become a security decision.

## Decision

`policy-model-router` remains a separate deterministic Policy Decision Point (PDP). It authorizes one
or more logical model groups and returns policy provenance without performing inference or receiving
message payloads.

`governed-llm-gateway` is the Policy Enforcement Point (PEP) plus operational selector. It may only
select from the authorized set and may further restrict it.

Invariant: `Gateway allowed set ⊆ Policy Router authorized set`.

Policy/identity failure is fail-closed. Operational availability may fail over only inside the
original authorization.

Caller `risk_level`, `data_classification`, `agent_identity`, environment, and limits are claims until
validated/reconciled with authenticated workload identity and policy.

## Consequences

- gateway cannot translate generic workloads into legacy credit-desk authorization internally;
- policy service rejection/unavailability prevents provider execution;
- fallback/ranking/health logic cannot widen authorization;
- authorization provenance and routing provenance remain separate but correlated.
