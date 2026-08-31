# PDP ↔ PEP Contract — Phase 4 binding

This file began as the Phase 0 contract draft. As of Phase 4 it records the actual gateway binding to
the Policy Model Router `POST /route` wire schema `1.0`. The historical filename is retained to avoid
breaking references while the contract evolves.

## Authority model

The Policy Model Router is the Policy Decision Point (PDP). The gateway is the Policy Enforcement
Point (PEP) plus, beginning in Phase 5, the operational selector.

Invariant:

`Gateway allowed set ⊆ Policy Router authorized set`

The gateway may reject more deployments. It may never synthesize or broaden authorization.

## Policy request projection

The application boundary is `PolicyDecisionPort.authorize(PolicyRequestMetadata)`. It does not accept
`GatewayRequest`, so prompt/message content is not available to the PDP adapter through this port.

The Phase 4 projection is:

| Gateway source | Policy Model Router field | Authority / semantics |
|---|---|---|
| constant | `schema_version` | `1.0` |
| adapter UTC clock | `requested_at` | gateway-generated UTC timestamp |
| `GatewayRequest.request_id` | `workflow_id` | Phase 4 correlation identity |
| `GatewayRequest.request_id` | `task_id` | Phase 4 correlation identity |
| trusted `EffectivePolicyContext.client_id` | `agent_name` | authenticated/trusted identity |
| trusted `EffectivePolicyContext.workload` | `workload` | must match request workload |
| trusted `EffectivePolicyContext.risk_level` | `risk_level` | caller cannot downgrade |
| trusted `EffectivePolicyContext.data_classification` | `data_classification` | caller cannot downgrade |
| execution metadata argument | `context_tokens_estimated` | input estimate; not context capability |
| execution metadata argument | `max_output_tokens_estimated` | positive output estimate |
| `GatewayRequest.requirements.structured_output` | `structured_output_required` | request requirement |
| caller limit narrowed by gateway default | `max_latency_ms` | stricter value wins |
| caller limit narrowed by gateway default | `max_cost_usd` | stricter value wins |

The adapter selects the `x-api-key` from gateway configuration using the trusted `client_id`. A caller
cannot choose the PDP credential by spoofing `GatewayRequest.agent_identity`.

`EffectivePolicyContext.environment` is not a request field in Policy Model Router API 1.0. The PDP
returns its deployment environment in the decision; the gateway requires it to equal the trusted
environment before accepting the decision.

### Deliberately excluded fields

`GatewayRequest.messages` is never sent to the Policy Model Router.

`GatewayRequest.requirements.min_context_tokens` is a minimum model-capability requirement, not an
estimate of current prompt tokens. It is therefore not translated into `context_tokens_estimated`.
The execution layer must supply an actual estimate separately.

Policy Model Router API 1.0 models tool-calling requirements through the policy workload rule rather
than a per-request field. The gateway does not invent `tool_calling_required` on the wire.

Vision/modality and other operational capabilities are not added to the PDP request unless/until the
upstream versioned contract defines them. They remain Phase 5 gateway eligibility concerns inside the
already-authorized logical group.

## Accepted policy decision

Policy Model Router API 1.0 returns one `selected_model_group`, not an
`authorized_model_groups` array. The gateway interprets that selected logical group as the complete
Phase 4 authorization set for the request.

A success response must contain exactly the expected API 1.0 decision fields, including:

```text
schema_version
routing_decision_id
decided_at
workflow_id
task_id
selected_model_group
reason
rejected_candidates
policy_id
policy_version
policy_digest
service_version
environment
```

The gateway verifies:

- schema version is `1.0`;
- `workflow_id` and `task_id` equal the gateway request ID;
- returned environment equals trusted `EffectivePolicyContext.environment`;
- `selected_model_group` is a valid policy identifier;
- policy digest has the exact `sha256:<64 lowercase hex>` form;
- required provenance/service fields are normalized non-empty strings;
- `decided_at` is expressed in UTC.

Accepted provenance retained by the application layer includes the routing decision ID, policy ID,
policy version, policy digest, Policy Model Router service version, decision timestamp/reason, and
environment.

## Explicit denial

Policy Model Router `422` is parsed only to distinguish and validate the documented
`no_viable_model_group` denial.

A `no_viable_model_group` rejection must contain full rejection decision provenance. Before treating
it as an authoritative denial, the gateway requires:

- exact rejection decision fields for API 1.0;
- matching `workflow_id` and `task_id`;
- matching workload;
- matching trusted environment;
- valid policy provenance and policy digest;
- a normalized reason code.

The denial is then exposed internally as a non-retryable `PolicyDecisionError(REJECTED)` carrying
policy provenance. No provider call is permitted.

A different 422 payload is treated as an invalid projected request or invalid response, never as an
allow decision.

## Other failure semantics

| Condition | Gateway classification | Retryable | Provider execution |
|---|---|---:|---:|
| no configured credential for trusted client | authentication | no | forbidden |
| PDP 401 | authentication | no | forbidden |
| PDP 403 | authorization | no | forbidden |
| PDP 429 | rate limit | yes | forbidden |
| PDP 500 | misconfigured | no | forbidden |
| other PDP 5xx | unavailable | yes | forbidden |
| transport timeout | timeout | yes | forbidden |
| network failure | transport | yes | forbidden |
| malformed/unexpected response | invalid response | no | forbidden |
| `no_viable_model_group` | rejected | no | forbidden |

Retryability is descriptive metadata only. Phase 4 does not retry the Policy Model Router.

For non-200/non-422 responses the stdlib policy transport does not parse or retain arbitrary response
bodies. PDP API keys and raw transport internals must not enter normalized errors/evidence.

## Candidate-set enforcement

After a successful PDP decision:

```text
PDP selected logical group
        ∩
model registry deployments
        =
Phase 4 authorized registry candidates
```

`authorized_registry_candidates` performs only this group intersection. It intentionally does not
apply enabled flags, capability, context, environment, health, cost, circuit state, or ranking. Those
are later operational filters and may only reduce this candidate set.

Phase 4 `execute_selected` receives a deployment ID from outside the service because deterministic
selection is not implemented until Phase 5. Before any provider call it verifies:

1. the deployment exists in the current registry;
2. the deployment's logical group is inside the PDP authorization;
3. the deployment is a member of the authorized registry candidate set.

Any failure raises an authorization-boundary error and results in zero provider calls.

## Provider projection

After authorization/enforcement, provider execution is built from execution data only:

```text
model
messages
max_output_tokens
timeout_seconds
```

Policy-only fields such as risk, data classification, PDP API key, policy ID/version/digest,
routing-decision ID, trusted client identity, and environment are not copied into the provider wire
request.

## Signed governance authorization

Some Policy Model Router deployments may additionally require signed runtime authorization. The
current gateway Phase 4 adapter does not fabricate or bypass that artifact. Until the optional
Verifiable AI Governance integration phase implements the signed boundary, such a deployment returns
403 and the gateway fails closed before provider execution.

## Phase 4 acceptance evidence

Contract tests prove:

- caller spoofing cannot override trusted policy identity/risk/classification;
- prompt/message content does not enter the PDP payload;
- successful PDP provenance is bound to request/trusted environment;
- rejection provenance is bound to request ID, workload, and environment;
- a PDP denial causes zero provider calls;
- an out-of-authorization deployment causes zero provider calls;
- policy metadata does not leak into provider execution;
- malformed/unsupported PDP responses fail closed.
