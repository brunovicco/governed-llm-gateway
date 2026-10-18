# Post-core evidence and conditional production readiness

Status: historical local evidence checkpoint and conditional production requirements, 2026-10-17.
[ADR-0028](../adr/ADR-0028-portfolio-scope-and-evidence.md) supersedes this document as the active
implementation queue. Follow [PORTFOLIO_DEMO_PLAN.md](PORTFOLIO_DEMO_PLAN.md) for current work:
local demonstration, two explicit live walkthroughs and local HTTPS evidence. AWS deployment and
durable credential/spend controls remain future work. The evidence below is preserved; the
conditional increments are not started by recording them here. Phase 14 and its ordered consumer
migrations retain their status
in [ROADMAP.md](ROADMAP.md#phase-14--real-project-integrations). Nothing in this plan authorizes a
new model group, provider, credential, spend limit, or production rollout.

## Current evidence and decision

| Workstream | Verified local baseline | Decision now |
| --- | --- | --- |
| Credential availability | Private values, ports, process-local conformance and an adapter-only exact-version secret boundary exist. The focused contract/reference suite passed on 2026-10-17. | Retain as an executable reference outside serving. AWS is the conditional infrastructure direction; a trusted publisher, backend, durable quarantine and multi-replica recovery remain unimplemented. |
| Spend admission and cost evidence | Private admission and v2 cost contracts/references exist. The focused contract/reference suite passed on 2026-10-17. | Keep out of serving. Native counters and synthetic reports do not prove charging, exact-attempt finality, durable holds or a billing ceiling. |
| `personal-default` ranking | The pinned artifact validates at `sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad` and covers only `rag.answer`. A separate, untracked local artifact validates at `sha256:53cb9aeca737b2b4daa1e62b977bcb74128e238175f936292f74d515ca28274d` for `agent.tool-use`; it remains outside the launcher and this change. The read-only coverage audit and local Gateway/PDP readiness smoke passed on 2026-10-17. | Keep the existing pin and fail-closed behavior. Startup readiness is not a governed inference proof; a valid single-workload artifact is not nine-workload coverage or authorization to combine artifacts. |
| Explicit deadline | The focused deadline suite passed on 2026-10-17. The feature remains opt-in. | Keep the default off until representative governed traffic proves the chosen budget and termination behavior. |
| PDP HTTPS pool | The focused lifecycle suite and a verified synthetic TLS comparison passed on 2026-10-17. The comparison has mixed latency results. | Keep the default stdlib transport. Synthetic loopback reuse is not representative PDP/load/proxy proof. |

The focused suite ran with the frozen Python 3.13.12 workspace and pinned pytest across the
credential, spend, ranking, deadline and pool contract modules. It made no provider/PDP call. The
complete repository quality gate then passed, including the two new audit tests, with 86.67% coverage;
lockfile, lint, formatting, typing, governed composition, both coverage checks, security, dependency
audit and Phase 0 also passed. This is credential-free repository validation, not a live proof. The
profile smoke loaded the local environment without printing credential values, started the Gateway
and sibling Policy Model Router on literal loopback, received HTTP 200 from both `/readyz` endpoints,
and closed both processes. It made no PDP route POST or provider inference call. The
synthetic PDP comparison used 12 measured requests plus four warmups per transport at concurrency
one and four, one round. Every case made 16 fresh policy exchanges. At concurrency one, pooled
p50/p95 were 3.195/7.961 ms versus stdlib 10.112/25.226 ms. At concurrency four, pooled
p50/p95 were 28.827/42.924 ms versus stdlib 10.112/12.494 ms. These are one local macOS run,
not production performance or an authorization test. Preserve the unfavorable concurrent result.

The credential-free checks are reproducible with the pinned workspace toolchain:

```sh
uv run --frozen --all-packages --python 3.13.12 --with pytest==8.4.1 pytest -q \
  tests/contract/test_credential_availability_contracts.py \
  tests/contract/test_credential_availability_memory.py \
  tests/contract/test_spend_admission_contracts.py \
  tests/contract/test_spend_admission_memory.py \
  tests/contract/test_spend_cost_evidence_v2.py \
  tests/contract/test_spend_cost_evidence_v2_synthetic.py \
  tests/contract/test_personal_default_approved_ranking.py \
  tests/contract/test_execution_deadline.py \
  tests/contract/test_policy_router_pool_lifecycle.py
uv run --frozen --all-packages --python 3.13.12 \
  python -m scripts.pdp_transport_comparison --requests 12 --rounds 1 --concurrency 1 4
uv run python scripts/quality_gate.py
```

## Conditional increment 1 — qualify evidence before changing serving

1. Record the target deployment, operator, exact code/configuration identities, rollback owner,
   approved request budget and metadata-only evidence destination. Use a real HTTPS Policy Model
   Router and authorized provider traffic for any production-readiness claim. Never copy credentials,
   prompts, tool arguments/results or raw provider/PDP errors into evidence.
2. Prove the existing baseline on the same target: fresh PDP decision per request, bounded selected
   candidates, fail-closed denial, usage and terminal evidence, cancellation and no replay after
   semantic output. Record the actual default transport and absence of a total execution deadline.
3. Run the complete quality gate and an independent review before each serving increment. Keep
   activation explicit and reversible; do not revise Phase 14 ordering or infer permission from this
   plan.

## Ranking evidence — two portfolio paths, broader coverage deferred

The active portfolio target is `rag.answer` plus a separately reviewed `agent.tool-use` walkthrough.
The remaining workload expansion and general artifact merging are future work. The requirements
below apply if that expansion is resumed; nine-workload coverage is not a portfolio completion gate.

The current launcher and Compose pin cover `rag.answer` only. `classification.simple`,
`extraction.structured`, `reasoning.complex`, `security.analysis`, `code.generate`, `code.review`,
`agent.orchestration` and `agent.tool-use` remain unavailable under that startup artifact. A local
`agent.tool-use` artifact is useful review input, but it is untracked and separate from the active
pin. Do not stage, overwrite or silently select it.

Run the read-only audit against an independently pinned ID before claiming coverage. It compares
every active workload's deployment set with the declared profile and prints only artifact identity
and covered/missing workload names:

```sh
uv run --frozen --all-packages --python 3.13.12 python scripts/audit_ranking_coverage.py \
  --profile config/profiles/personal-default \
  --artifact config/profiles/personal-default/approved_ranking.json \
  --expected-artifact-id sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad
```

For each workload, first approve a versioned dataset, target matrix and semantics appropriate to its
PDP-authorized group. Run all reviewed deployments, retain immutable attempts/snapshot, distinguish
provider availability from quality, and obtain explicit promotion approval. Then compile and verify
an approved artifact with complete deployment coverage and an exact pin. The current publication
script emits one workload per artifact. Combining multiple workload artifacts into one startup policy
needs a separately reviewed merge/conflict/provenance contract and, if it changes architecture, an
ADR. A partial merge must fail closed; neither static placeholder scores nor the presence of an API
key can fill a missing workload. Validate the resulting pinned startup and an authorized request for
each enabled workload before updating the profile's operational claim. Roll back by restoring the
previous artifact and pin together.

## Conditional increment 3 — durable credential availability (deferred)

The selected infrastructure direction is AWS `sa-east-1` with Terraform: AWS Secrets Manager for
exact-version credential material and private Multi-AZ PostgreSQL RDS for durable control state.
[ADR-0027](../adr/ADR-0027-aws-sao-paulo-readiness-infrastructure.md) and the
[Terraform foundation](../../infra/terraform/https-integration/README.md) are proposed for review.
The target account and new isolated VPC/domain choice have been reviewed, but no cloud resources
have been applied. The [infrastructure checkpoint](AWS_SAO_PAULO_INFRA_PLAN.md) records the
read-only inventory and plan previews. This choice does not activate serving or satisfy the backend
conformance steps below.

If a named operational requirement reactivates this work, implement the versioned secret authority
and authenticated controller on the selected AWS account/network.
Specify exact-version retrieval, stable material identity across aliases, activation epochs and
runtime/authentication-scope provenance. Implement an authoritative durable shared store with
atomic admission, fencing, retained material quarantine, restart/failover recovery and separately
scoped publisher/worker rights. Verify backend ACL/TLS and provider-specific rejection classifiers;
generic 401/403 cannot by itself quarantine a credential.

Only after backend conformance should a separate serving increment integrate preflight, ranking,
cache, execution and cancellation checks. Exercise rotation, late rejection, rollback, concurrent
replicas and loss of authority. Missing or inconsistent evidence must narrow eligibility. Activate
behind an explicit deployment opt-in with a documented rollback; never substitute the process-local
reference for shared production state. See [credential availability](PROVIDER_CREDENTIAL_AVAILABILITY.md)
and [ADR-0019](../adr/ADR-0019-provider-credential-binding-availability.md).

## Conditional increment 4 — durable spend admission (deferred)

The process-local reference remains portfolio evidence. The following requirements apply only if
a real consumer need justifies durable serving integration.

Qualify an immutable provider/model/account/tier price source and exact native count semantics for
each enabled shape. Establish charged-category completeness, output/reasoning inclusion, drift and
expiry behavior, plus a private trusted preparation/issuance path. Correlate complete final usage to
the exact authorized execution attempt; missing, provisional, failed and cancelled usage must not be
settled as zero. Preserve original price/hold provenance on late reconciliation.

Implement durable atomic all-scope reservation/journal, opening balances, failover/recovery and
retention before either executor admits paid provider I/O. Acknowledge settlement before public
terminal success and bound cleanup even if response construction or iteration fails. Unknown cost
holds remain reserved until authoritative reconciliation. Test concurrent replicas and outage
recovery, then use an explicit opt-in and controlled real-provider proof. No current synthetic
reference or native counter is a billing ceiling. See [v2 slices C–E](SPEND_COST_EVIDENCE_V2_PLAN.md)
and [ADR-0021](../adr/ADR-0021-conservative-spend-admission-and-settlement.md).

## Conditional increment 5 — production deadline/pool qualification (deferred)

The active portfolio plan first exercises a real PDP behind verified local HTTPS. That bounded
laboratory needs no AWS deployment and will not satisfy the production claims below.

The same AWS foundation proposes an internal HTTPS ALB and private DNS for a future Policy Model
Router integration deployment. It has no Router targets or Governance Runtime Control projection;
until those are deployed and verified, it supplies no representative real-PDP evidence.

Use the same real HTTPS PDP, proxy/TLS path and authorized request mix for default versus opt-in
tests. Record fresh decision count, response binding, p50/p95/tail latency, connection count,
throughput, errors and resource use under sequential and expected peak concurrency. A pool must not
cache decisions, replay a POST or weaken envelope single use. Include denial, malformed response,
pool saturation, startup/shutdown, certificate failure and disconnect. The synthetic experiment above
does not set a performance threshold or justify a default change.

Choose a finite total deadline from measured end-to-end behavior, separate from policy
`max_latency_ms` and provider per-attempt timeout. Prove pre-commit HTTP 504, post-commit terminal
failure, no fallback after semantic output, upstream closure, no late completion and no extra
provider attempt. Record cancellation-resistant/remote-spend non-claims. Activate both options
separately in a canary, compare to the baseline, and roll back by omitting each flag and restarting
the application. A default change requires its own evidence and review. See
[deadline behavior](STREAMING.md#explicit-local-execution-deadline) and
[pool lifecycle](PDP_POOL_LIFECYCLE.md).

## Completion criteria for resumed production work

These criteria are separate from the portfolio acceptance criteria in
[PORTFOLIO_DEMO_PLAN.md](PORTFOLIO_DEMO_PLAN.md).

Mark an increment complete only with its reviewed artifact/ADR where needed, exact deployment
configuration and pin, passing focused and full quality gates, representative governed proof,
metadata-only rollback record and a dated update to [CHECKPOINT_LOG.md](CHECKPOINT_LOG.md). Until
then, leave serving defaults unchanged and describe the increment as a candidate or reference.
