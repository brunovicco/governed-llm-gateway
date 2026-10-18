# Portfolio guide

This repository demonstrates governed LLM execution: applications declare a workload, an external
Policy Model Router authorizes a model group, and the Gateway selects and executes only inside
that authorization. The portfolio emphasizes working code, reproducible evidence and explicit
tradeoffs. Its scope decision is [ADR-0028](../adr/ADR-0028-portfolio-scope-and-evidence.md).

## A short review path

1. Read the [request flow and real execution screenshot](../../README.md#one-real-governed-request).
   Follow the terminal deployment, policy/ranking digests and trace correlation. This is dated
   live evidence, not a claim that every configured workload runs today.
2. Inspect three decisions and their failure cases in the table below. They explain why the
   architecture has separate authorization, selection and execution boundaries.
3. Run the local operations smoke or the repository quality gate below. Choose the separate PDP
   composition proof when a sibling Policy Model Router checkout and Docker are available.
4. Use the optional live walkthroughs only with operator-owned credentials and approved artifacts.
   The full credential-free execution demonstration is the next planned increment.

## Three engineering cases

| Case | Decision and implementation evidence | What to look for |
| --- | --- | --- |
| Safe recovery from provider failure | [Fallback rules](FALLBACK_AND_RETRY.md), [ADR-0007](../adr/ADR-0007-fallback-safety-semantics.md), [streaming failures](../../tests/contract/test_streaming_failure_paths.py) | Retry stays on one deployment; fallback uses only the frozen authorized sequence; semantic output ends replay eligibility. |
| Failure before versus after HTTP commitment | [ADR-0017](../adr/ADR-0017-deterministic-streaming-preflight.md), [streaming contract](STREAMING.md), [dated PR #259 proof](CHECKPOINT_LOG.md#deterministic-streaming-preflight--pr-259-executed-2026-09-15) | Deterministic provider validation completes before SSE HTTP 200; runtime failures remain explicit terminal outcomes. |
| Contract correctness across repositories | [PDP composition proof](PDP_COMPOSITION_PROOF.md), [executable proof](../../scripts/composition_proof.py) | Signed-request identity, canonical serialization, trust and replay behavior must agree across independently implemented services. The issuer is a fixture; the Router is real. |

## Run existing evidence

From the repository root with Python 3.13+ and uv:

```sh
uv run python scripts/quality_gate.py
```

This runs repository tests and quality checks without provider credentials. Dependency installation
and vulnerability auditing can require internet access. A passing gate proves the tested contracts,
not a live provider request.

For the operations stack, also install Docker/Compose and Node.js 24/npm, start Docker and use a
fresh local-only credential:

```sh
export GATEWAY_LOCAL_DEMO_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run --frozen python scripts/local_demo.py --smoke-test
unset GATEWAY_LOCAL_DEMO_API_KEY
```

The smoke starts the real Console, operations API and observability stack, checks readiness and
cleans up its owned resources. It performs no inference. Omit `--smoke-test` for an interactive
session; see [local orchestration](LOCAL_DEMO_ORCHESTRATION.md).

The [PDP composition instructions](PDP_COMPOSITION_PROOF.md#running-it) run a real Router and Redis
with a fixture issuer. They verify accepted authorization, missing authorization, untrusted signing
key and replay denial. They stop before provider execution and currently run separately from CI.

## Capability and evidence status

| Area | Current status | Portfolio decision |
| --- | --- | --- |
| Authorization, deterministic ranking, retry/fallback, streaming and SDK | Implemented, contract-tested, with bounded historical live proofs | Maintain as the core; make critical success/failure paths easy to reproduce. |
| Console, metadata-only traces and operations demo | Implemented; real local runs recorded | Reuse existing surfaces and screenshots. Do not invent traffic to populate them. |
| Full local execution demo with simulated providers | Planned; current operations demo has no inference route | Next implementation, with explicit simulation and five observable scenarios. |
| `rag.answer` live path | Approved artifact is active in `personal-default`; historical live evidence exists | Retain the exact pin and refresh bounded evidence when consolidating the walkthrough. |
| `agent.tool-use` live path | Separate historical Claude Code proof; absent from the stock runtime's approved artifact | Consolidate a separate reviewed walkthrough; do not silently activate the local candidate. |
| Deadline and PDP HTTPS pool | Implemented opt-ins; contract and synthetic TLS evidence | Add a local real-PDP HTTPS exercise; default changes and production performance claims remain deferred. |
| Credential availability and conservative spend admission | Tested private process-local references; outside serving | Preserve executable design evidence; durable authorities/controllers are future work. |
| AWS Terraform | Two validated roots and historical read-only plan previews; never applied | Maintain formatting/validation in credential-free CI; deployment is optional future work. |
| Consumer integrations | Two complete; OpsLens deferred; RAGForge and Governance consumer migrations not started | Use completed cases as evidence. Remaining migrations are not portfolio completion prerequisites. |

## Optional real-provider walkthroughs

- **Text/RAG:** [personal-default](../../config/profiles/personal-default/README.md) documents the
  current `rag.answer` artifact, its benchmark provenance, runtime pin and launcher. Its full
  enabled profile requires all six configured provider credentials; it is not a one-key demo.
- **Tool loop:** [Claude Code](PROTOCOL_MULTIMODAL_GATEWAY.md#claude-code) and the
  [dated proof](CHECKPOINT_LOG.md#claude-code-live-e2e--pr-258-executed-2026-09-15) record the
  separate `agent.tool-use` path. Business tools run in the consumer. Historical proof does not
  activate that workload under today's default artifact.

A future consolidated walkthrough must identify the exact approved artifact, request scope and
observed deployment. The current local untracked tool-use candidate is not published evidence.

## Completion boundary

The [demonstration plan](PORTFOLIO_DEMO_PLAN.md) defines the remaining bounded work. A complete
portfolio should let a reviewer explain the decisions, reproduce critical failures without paid
credentials, and inspect dated live evidence with its limitations. It does not require an always-on
cloud service, nine enabled workloads or all Phase 14 migrations.

Retain AWS, durable credential/spend authorities and fleet operations as future designs. Resume
them only for a named consumer requirement or a specific demonstration with a bounded lifecycle.
The original phase history remains in [ROADMAP.md](ROADMAP.md); production requirements and earlier
local measurements remain in [POST_CORE_READINESS.md](POST_CORE_READINESS.md).
