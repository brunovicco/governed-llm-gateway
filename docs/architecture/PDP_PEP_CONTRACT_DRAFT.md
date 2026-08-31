# PDP ↔ PEP Contract Draft

## Policy request projection

The gateway projects only policy-relevant metadata. The message payload is excluded.

Conceptual input:

```json
{
  "schema_version": "1.0",
  "request_id": "uuid",
  "authenticated_client_id": "service-a",
  "workload": "agent.orchestration",
  "effective_risk_level": "medium",
  "effective_data_classification": "public",
  "requirements": {
    "tool_calling": true,
    "structured_output": true,
    "vision": false,
    "min_context_tokens": 128000
  },
  "limits": {
    "max_latency_ms": 15000,
    "max_cost_usd": 0.05
  }
}
```

## Policy decision

Conceptual response:

```json
{
  "decision": "allow",
  "decision_id": "...",
  "policy_id": "...",
  "policy_version": "...",
  "policy_digest": "sha256:...",
  "authorized_model_groups": ["agentic-strong"],
  "effective_limits": {
    "max_latency_ms": 15000,
    "max_cost_usd": 0.05
  }
}
```

The final versioned API belongs to Phase 1 in `policy-model-router`.

## Failure semantics

- explicit deny → fail closed, no provider execution;
- unknown workload → fail closed;
- invalid decision/provenance → fail closed;
- policy timeout/unavailability → fail closed;
- incompatible policy contract version → fail closed;
- expired/stale decision when expiry semantics exist → fail closed.

The PEP does not synthesize authorization when the PDP is unavailable.

## Enforcement

The gateway operational candidate set is intersected with PDP authorization. Subsequent health,
capability, cost, latency, environment, and circuit filtering can only remove candidates.
