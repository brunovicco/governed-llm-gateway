# Project documentation index

This folder holds the working documentation of the Governed LLM Gateway: the current state, the
architecture contracts, and the record of how each capability was built and proven.

The documents were written increment by increment, so many open with an internal identifier. You do
not need those identifiers to read them — this index says what each document answers — but they
decode as:

| Identifier | Meaning |
| --- | --- |
| `Phase N` | One numbered stage of the original roadmap, preserved verbatim in `SOURCE_ROADMAP.txt` and summarized in [`ROADMAP.md`](ROADMAP.md) |
| `PC-n` | One numbered increment of the post-core hardening sequence; each corresponds to one merged pull request |
| `OR-n` | One increment of the operational-readiness track described in [`OPERATIONAL_READINESS.md`](OPERATIONAL_READINESS.md) |
| `CR-n` | One increment of the complexity-routing track described in [`COMPLEXITY_ROUTING.md`](COMPLEXITY_ROUTING.md) |

A document scoped to a past phase (for example [`THREAT_MODEL.md`](THREAT_MODEL.md), "through Phase 8")
states that scope in its own title or first lines. Where a later increment changed something, the change
is recorded in [`CHECKPOINT_LOG.md`](CHECKPOINT_LOG.md), which is append-only.

## Start here

| Document | What it answers |
| --- | --- |
| [`CURRENT_STATE.md`](CURRENT_STATE.md) | What is true today — the authoritative checkpoint |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | How authorization, selection and execution are separated |
| [`ROADMAP.md`](ROADMAP.md) | Which phases exist, which are complete, and what comes next |
| [`CHECKPOINT_LOG.md`](CHECKPOINT_LOG.md) | The dated, append-only proof record behind every claim |
| [`PROJECT_INSTRUCTIONS.md`](PROJECT_INSTRUCTIONS.md) | The original objective and the constraints the project is held to |
| [`SOURCES.md`](SOURCES.md) | Which inputs are normative and which are derived |

## Authorization and security boundaries

| Document | What it answers |
| --- | --- |
| [`SECURITY_MODEL.md`](SECURITY_MODEL.md) | What is secret, who owns it, and where each asset may travel |
| [`THREAT_MODEL.md`](THREAT_MODEL.md) | Which abuse cases are controlled, and which are deferred to a named phase |
| [`GATEWAY_CLIENT_AUTHENTICATION.md`](GATEWAY_CLIENT_AUTHENTICATION.md) | How a consumer authenticates without ever holding a provider credential |
| [`POLICY_ROUTER_RUNTIME.md`](POLICY_ROUTER_RUNTIME.md) | How the Gateway reaches the external policy decision point, and why that connection cannot authorize anything |
| [`OPERATIONS_ACCESS.md`](OPERATIONS_ACCESS.md) | Why permission to run a workload is not permission to see process-wide state |
| [`OPERATIONS_ACCESS_ARTIFACT.md`](OPERATIONS_ACCESS_ARTIFACT.md) | How a deployment declares, without secrets, who may read operations state |
| [`HTTP_CACHE_POLICY.md`](HTTP_CACHE_POLICY.md) | Why authenticated evidence responses are never storable |

## Model resolution and execution

| Document | What it answers |
| --- | --- |
| [`MODEL_REGISTRY.md`](MODEL_REGISTRY.md) | How deployments are declared as reviewed configuration rather than routing branches |
| [`ROUTING.md`](ROUTING.md) | What the policy decision point returns and what the Gateway may do with it |
| [`PROVIDER_CONTRACT.md`](PROVIDER_CONTRACT.md) | The provider-neutral execution contract every adapter implements |
| [`FALLBACK_AND_RETRY.md`](FALLBACK_AND_RETRY.md) | How resilience moves between deployments without widening authorization |
| [`STREAMING.md`](STREAMING.md) | How provider streams are normalized, and how cancellation behaves |
| [`STRUCTURED_OUTPUT_AND_TOOLS.md`](STRUCTURED_OUTPUT_AND_TOOLS.md) | How structured output and tool calls are normalized without owning tool execution |
| [`MULTIMODAL_INPUT.md`](MULTIMODAL_INPUT.md) | What image input supports today, and what it deliberately does not |
| [`COMPLEXITY_ROUTING.md`](COMPLEXITY_ROUTING.md) | How task complexity narrows an already-authorized set, as evidence only |
| [`COMPLEXITY_GENERATION.md`](COMPLEXITY_GENERATION.md) | How that narrowing reaches streaming execution, behind an opt-in |
| [`SPEND_ACCOUNTING.md`](SPEND_ACCOUNTING.md) | How estimated spend accumulates per client and workload, and how a budget refuses a request |
| [`OPENAI_COMPATIBLE_INGRESS.md`](OPENAI_COMPATIBLE_INGRESS.md) | How an existing OpenAI client can repoint at the Gateway without a second execution path |

## Runtime composition and deployment

| Document | What it answers |
| --- | --- |
| [`APPLICATION_BOOTSTRAP.md`](APPLICATION_BOOTSTRAP.md) | In what order artifacts are staged before any secret is materialized |
| [`PROCESS_BOOTSTRAP.md`](PROCESS_BOOTSTRAP.md) | Why every bootstrap must fail closed before credentials resolve |
| [`GATEWAY_RUNTIME_BOOTSTRAP.md`](GATEWAY_RUNTIME_BOOTSTRAP.md) | How runtime artifacts and secret resolvers compose without a module-level singleton |
| [`SERVICE_COMPOSITION.md`](SERVICE_COMPOSITION.md) | Which layer is pure composition and therefore does no I/O |
| [`GATEWAY_APPLICATION_COMPOSITION.md`](GATEWAY_APPLICATION_COMPOSITION.md) | What the single FastAPI application factory mounts |
| [`DEPLOYMENT_ACTIVATION.md`](DEPLOYMENT_ACTIVATION.md) | Where a deployment declares the exact artifacts one activation uses |
| [`PROVIDER_RUNTIME_CONFIGURATION.md`](PROVIDER_RUNTIME_CONFIGURATION.md) | How provider endpoints and credentials stay a deployment concern |
| [`PROVIDER_RUNTIME_ARTIFACT.md`](PROVIDER_RUNTIME_ARTIFACT.md) | The committed, secret-free shape of that provider binding |
| [`PROCESS_ENTRYPOINT.md`](PROCESS_ENTRYPOINT.md) | How the Gateway runs as an installed executable process |
| [`PROCESS_HEALTH.md`](PROCESS_HEALTH.md) | What liveness and readiness claim — and what they deliberately do not probe |
| [`SHARED_RUNTIME_STATE.md`](SHARED_RUNTIME_STATE.md) | How health and circuit state are shared across replicas |
| [`CONTAINER_DEPLOYMENT.md`](CONTAINER_DEPLOYMENT.md) | How the image is built and the two ways it runs |

## Operational surfaces

| Document | What it answers |
| --- | --- |
| [`OPERATIONS_READ_MODEL.md`](OPERATIONS_READ_MODEL.md) | The typed projection the operations surface is allowed to expose |
| [`OPERATIONS_HTTP.md`](OPERATIONS_HTTP.md) | The authenticated read-only endpoints and their exact contracts |
| [`OPERATIONAL_EVIDENCE_BINDING.md`](OPERATIONAL_EVIDENCE_BINDING.md) | How reviewed evidence reaches that read path without gaining authority |
| [`GATEWAY_CONSOLE.md`](GATEWAY_CONSOLE.md) | What the browser console is, and why it is not a control plane |
| [`OPERATIONAL_READINESS.md`](OPERATIONAL_READINESS.md) | The readiness track that turns the execution core into a demonstrable platform |
| [`LOCAL_OPERATIONS_DEMO.md`](LOCAL_OPERATIONS_DEMO.md) | The credential-free local demo that exposes no inference route |
| [`LOCAL_DEMO_ORCHESTRATION.md`](LOCAL_DEMO_ORCHESTRATION.md) | How that demo's processes are started, waited on and torn down |

## Observability and evidence

| Document | What it answers |
| --- | --- |
| [`OBSERVABILITY.md`](OBSERVABILITY.md) | What telemetry carries, and why it stays metadata-only |
| [`LOCAL_OBSERVABILITY.md`](LOCAL_OBSERVABILITY.md) | The reproducible local Collector, Tempo and Grafana foundation |
| [`COLLECTOR_RECEIPT.md`](COLLECTOR_RECEIPT.md) | Proof that the Collector actually received Gateway telemetry |
| [`TEMPO_QUERY_PROOF.md`](TEMPO_QUERY_PROOF.md) | Proof that a trace survives the full path and is queryable |
| [`GRAFANA_TRACE_DASHBOARD.md`](GRAFANA_TRACE_DASHBOARD.md) | The provisioned dashboard, and why Grafana holds no authority |
| [`EVALUATION.md`](EVALUATION.md) | How benchmark evidence is produced, promoted, and kept out of authorization |

## Related documentation outside this folder

| Location | Contents |
| --- | --- |
| [`../adr/`](../adr/) | Architecture decision records — the decisions, their alternatives, and their consequences |
| [`../architecture/`](../architecture/) | The policy decision point / enforcement point wire contract, trusted attributes and admin surfaces |
| [`../evaluation/`](../evaluation/) | The benchmark matrix and the operational-evidence contracts |
| [`../../config/profiles/`](../../config/profiles/) | Runnable profiles, each with its own scope, proof status and non-claims |
