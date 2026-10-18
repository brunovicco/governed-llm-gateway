# ADR-0028 — Portfolio scope and evidence priorities

## Status

Accepted as a scope decision at the repository owner's request. The implementation and evidence
status of each capability remain separate from this decision.

## Date

2026-10-17

## Context

The repository's primary purpose is to demonstrate engineering knowledge and serve as a portfolio.
The execution core, two consumer integrations, benchmark pipeline, local observability and bounded
live-provider proofs already demonstrate substantial implementation. The current operations demo
does not execute inference, and the signed PDP composition proof stops at authorization. A reviewer
still needs several separate paths to understand the full system.

PR #275 prepared AWS infrastructure and a production-readiness sequence. Its resources have not
been applied. Durable credential quarantine, spend reconciliation and an always-on cloud deployment
would add operating responsibilities before making the existing work easier to evaluate.

## Decision

Prioritize reproducible demonstrations, concise engineering case studies and evidence with explicit
limits. Maintain three categories:

1. **Implemented behavior**: the governed runtime, evaluation pipeline, SDK, observability and
   completed consumer integrations. Each claim points to its tests or dated execution evidence.
2. **Executable references**: private credential/spend contracts and process-local implementations,
   plus validated Terraform configuration. Retain their code and checks; do not represent them as
   deployed authorities or active serving controls.
3. **Future work**: durable control backends, production identity/operations, fleet evidence,
   additional consumer migrations and permanent cloud infrastructure. Resume only for a named
   consumer need or a distinct, bounded engineering demonstration.

The active portfolio sequence is:

- publish a reviewer guide, status matrix and concrete demonstration acceptance plan;
- build a local execution demonstration using the real Gateway and external Policy Model Router,
  with explicitly simulated providers and deterministic failure injection;
- consolidate two optional real-provider walkthroughs, `rag.answer` and `agent.tool-use`, using
  separately approved and explicitly pinned artifacts;
- extend the local laboratory to a real PDP behind verified HTTPS for deadline/pool behavior.

The last three items are planned work, not completed by this ADR. The full nine-workload ranking
matrix, a general artifact-merging mechanism and additional providers are not portfolio completion
requirements. Existing approved evidence and the default runtime pin remain authoritative.

Keep AWS São Paulo Terraform as a validated reference with credential-free CI. This decision
supersedes ADR-0027's deployment priority, not its conditional technical design. A temporary AWS
experiment may be proposed with a specific proof, budget, lifecycle and teardown procedure;
permanent infrastructure is not required to complete the portfolio.

Numbered phase history and the Phase 14 consumer order remain intact. Cases 3–5 are unfinished
future integrations; portfolio scope does not mark them complete or permit parallel migrations.
`SOURCE_ROADMAP.txt` remains the preserved original specification; this ADR records the later scope
decision without rewriting that source.

## Alternatives considered

- Complete the AWS deployment and durable controls first: useful for an operational service, but
  introduces recurring costs and maintenance beyond the portfolio's immediate objective.
- Remove unfinished reference code: would discard useful tested design evidence and history.
- Present every feature as operational: would conceal important distinctions between unit tests,
  simulation, live-provider proof and deployed-environment validation.

## Consequences

Portfolio completion is evaluated through the bounded acceptance criteria in
[PORTFOLIO_DEMO_PLAN.md](../project/PORTFOLIO_DEMO_PLAN.md), independently of production readiness
and completion of every original consumer migration. New runtime work still needs focused review,
the full quality gate and evidence appropriate to its claim. Core correctness defects remain
actionable even when they fall outside the presentation work.

## Security and privacy impact

`Gateway allowed set ⊆ Policy Router authorized set` remains mandatory. Simulated providers cannot
authorize requests, add deployments after a denial or bypass production transport validation. Keep
fixtures in explicitly selected demonstration/test composition. Report metadata only; neither
demonstrations nor recordings should expose prompts, completions, tool data, credentials or raw
provider/PDP errors as telemetry. Live tests retain explicit operator credentials and bounded scope.

## Operational impact

No cloud resources, IAM grants, secret versions, ranking promotions or serving flags are activated.
Terraform CI performs formatting, backend-disabled initialization with the committed lockfile and
validation. Those checks do not prove deployment, cost, backend durability or application behavior.
The current local operations demo remains supported at its existing scope.

## Follow-up

Use [the portfolio guide](../project/PORTFOLIO_GUIDE.md) as the reviewer entry point and
[the demonstration plan](../project/PORTFOLIO_DEMO_PLAN.md) for the next implementation increments.
Retain [POST_CORE_READINESS.md](../project/POST_CORE_READINESS.md) as historical local evidence and
conditional production requirements, not the active implementation queue.
