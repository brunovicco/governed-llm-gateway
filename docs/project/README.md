# Project documentation

This library records the gateway's contracts, implementation details and dated proof. Start with
the portfolio guide; open a technical reference when reviewing that specific boundary.

## Start here

| Document | Purpose |
| --- | --- |
| [Portfolio guide](PORTFOLIO_GUIDE.md) | Short reviewer path, engineering cases, runnable checks and evidence limits |
| [Current state](CURRENT_STATE.md) | What is implemented, active, reference-only and deferred |
| [Architecture](ARCHITECTURE.md) | Authorization, selection, execution and package boundaries |
| [Roadmap](ROADMAP.md) | Numbered phase history and current portfolio delivery priority |
| [Checkpoint log](CHECKPOINT_LOG.md) | Dated, append-only implementation and proof record |
| [Project instructions](PROJECT_INSTRUCTIONS.md) | Normative engineering constraints |

## Choose a topic

- **Understand the request path:** [PDP/PEP contract](../architecture/PDP_PEP_CONTRACT_DRAFT.md),
  [routing](ROUTING.md), [fallback and retry](FALLBACK_AND_RETRY.md),
  [streaming](STREAMING.md), [structured output and tools](STRUCTURED_OUTPUT_AND_TOOLS.md).
- **Run or review a demonstration:** [portfolio demo plan](PORTFOLIO_DEMO_PLAN.md),
  [local operations demo](LOCAL_OPERATIONS_DEMO.md),
  [cross-repository PDP proof](PDP_COMPOSITION_PROOF.md),
  [local real-PDP HTTPS exercise](PDP_REAL_HTTPS_EXERCISE.md).
- **Review provider and client boundaries:** [provider contract](PROVIDER_CONTRACT.md),
  [protocol guide](PROTOCOL_MULTIMODAL_GATEWAY.md),
  [client authentication](GATEWAY_CLIENT_AUTHENTICATION.md).
- **Review deployment and operations:** [container deployment](CONTAINER_DEPLOYMENT.md),
  [deployment activation](DEPLOYMENT_ACTIVATION.md),
  [security model](SECURITY_MODEL.md), [observability](OBSERVABILITY.md).
- **Review evaluation and ranking:** [evaluation guide](EVALUATION.md),
  [benchmark matrix](../evaluation/BENCHMARK_MATRIX.md),
  [operational evidence](../evaluation/OPERATIONAL_EVIDENCE.md).
- **Review future and reference work:** [post-core evidence](POST_CORE_READINESS.md),
  [credential reference](PROVIDER_CREDENTIAL_AVAILABILITY.md),
  [spend reference](SPEND_ADMISSION_REFERENCE.md),
  [AWS infrastructure reference](../../infra/terraform/https-integration/README.md).

## Technical reference library

These focused documents preserve implementation contracts and proof details. They are supporting
references; most readers can start with the six documents above and the topic links.

<details>
<summary>Architecture and runtime composition</summary>

- [PDP runtime](POLICY_ROUTER_RUNTIME.md), [application bootstrap](APPLICATION_BOOTSTRAP.md), [process bootstrap](PROCESS_BOOTSTRAP.md), [process entrypoint](PROCESS_ENTRYPOINT.md), [runtime bootstrap](GATEWAY_RUNTIME_BOOTSTRAP.md)
- [Service composition](SERVICE_COMPOSITION.md), [Gateway application composition](GATEWAY_APPLICATION_COMPOSITION.md), [process health](PROCESS_HEALTH.md), [shared runtime state](SHARED_RUNTIME_STATE.md)
- [Model registry](MODEL_REGISTRY.md), [trusted attributes](../architecture/TRUSTED_ATTRIBUTES.md), [threat model](THREAT_MODEL.md), [complexity routing](COMPLEXITY_ROUTING.md), [complexity generation](COMPLEXITY_GENERATION.md)

</details>

<details>
<summary>Credentials, cost and spend references</summary>

- [Credential availability](PROVIDER_CREDENTIAL_AVAILABILITY.md), [spend accounting](SPEND_ACCOUNTING.md), [admission contracts](SPEND_ADMISSION_CONTRACTS.md), [admission reference](SPEND_ADMISSION_REFERENCE.md)
- [Cost evidence contracts](SPEND_COST_EVIDENCE_CONTRACTS.md), [v1 reference](SPEND_COST_EVIDENCE_REFERENCE.md), [v2 contracts](SPEND_COST_EVIDENCE_V2_CONTRACTS.md), [v2 reference](SPEND_COST_EVIDENCE_V2_REFERENCE.md), [v2 plan](SPEND_COST_EVIDENCE_V2_PLAN.md)
- [OpenAI cost capability](SPEND_OPENAI_CAPABILITY_ASSESSMENT.md), [input-count projection](SPEND_OPENAI_INPUT_COUNT_PROJECTION.md), [native usage counters](SPEND_OPENAI_NATIVE_USAGE_COUNTERS.md)

</details>

<details>
<summary>Operations and observability proofs</summary>

- [Operations access](OPERATIONS_ACCESS.md), [access artifact](OPERATIONS_ACCESS_ARTIFACT.md), [read model](OPERATIONS_READ_MODEL.md), [HTTP contract](OPERATIONS_HTTP.md), [evidence binding](OPERATIONAL_EVIDENCE_BINDING.md)
- [Console](GATEWAY_CONSOLE.md), [local demo orchestration](LOCAL_DEMO_ORCHESTRATION.md), [operational readiness history](OPERATIONAL_READINESS.md)
- [Observability](OBSERVABILITY.md), [local stack](LOCAL_OBSERVABILITY.md), [Collector receipt](COLLECTOR_RECEIPT.md), [Tempo query proof](TEMPO_QUERY_PROOF.md), [Grafana dashboard](GRAFANA_TRACE_DASHBOARD.md)
- [PDP transport comparison](PDP_TRANSPORT_COMPARISON.md), [pool lifecycle](PDP_POOL_LIFECYCLE.md),
  [local real-PDP HTTPS exercise](PDP_REAL_HTTPS_EXERCISE.md), [HTTP cache policy](HTTP_CACHE_POLICY.md)

</details>

<details>
<summary>Deployment, protocols and multimodal details</summary>

- [Provider runtime configuration](PROVIDER_RUNTIME_CONFIGURATION.md), [provider artifact](PROVIDER_RUNTIME_ARTIFACT.md), [OpenAI-compatible ingress](OPENAI_COMPATIBLE_INGRESS.md)
- [Multimodal input](MULTIMODAL_INPUT.md), [protocol scope](PROTOCOL_MULTIMODAL_GATEWAY.md), [deployment activation](DEPLOYMENT_ACTIVATION.md)
- [AWS profile setup](AWS_PROFILE_SETUP.md), [AWS plan checkpoint](AWS_SAO_PAULO_INFRA_PLAN.md), [AWS cost and access](AWS_SAO_PAULO_COST_AND_ACCESS.md)

</details>

## Decisions and source material

- [Architecture decisions](../adr/README.md) — durable choices and their alternatives.
- [Architecture references](../architecture/) — protocol contract and Phase 0 reviews.
- [Evaluation references](../evaluation/) — benchmark and operational evidence contracts.
- [Sources](SOURCES.md) — normative inputs and derived documentation.
