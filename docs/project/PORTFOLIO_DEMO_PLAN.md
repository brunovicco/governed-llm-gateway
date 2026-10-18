# Portfolio demonstration implementation plan

Status: Delivery 1 merged as PR #277; local and hosted quality/execution checks passed on
2026-10-18. Delivery 2 evidence review is complete and its separate tool-use artifact is now
versioned; walkthrough packaging and operator-bounded live refresh remain. Prepared against the
PR #275 baseline on 2026-10-17 under [ADR-0028](../adr/ADR-0028-portfolio-scope-and-evidence.md). These are bounded
deliveries, not new numbered phases.

## Baseline and assumptions

- `scripts/local_demo.py` already owns startup/readiness/cleanup for the operations-only Console
  and observability stack. Preserve that command's existing contract.
- `scripts/composition_proof.py` and `compose.pdp-composition.yml` already exercise the real
  external Policy Model Router and Redis, with a fixture governance issuer. They stop at
  authorization; development-mode enforcement does not establish staging/production readiness.
- Existing streaming/failure/deadline contract tests are the source of expected semantics.
  Reuse production orchestration; do not copy authorization/ranking/replay logic into the demo.
- The reviewer can install the documented toolchain and Docker. Paid provider accounts and AWS
  access are optional. Local simulation cannot establish real-provider support or billing behavior.

## Delivery 1 — credential-free local execution demonstration

Create a separate, explicit demonstration entry point that composes the real Gateway API and
external PDP, plus deterministic simulated provider adapters. Pin the Router version/commit and
validate its policy/catalog. Reuse existing configuration loaders and service composition wherever
their contracts permit injection. Fixtures must live in demonstration/test code and must not become
a production provider type, implicit startup default or endpoint-validation exception.

The working-branch harness entry point is:

```bash
uv run --frozen --python 3.13 --all-packages python -m scripts.portfolio_execution_demo
```

It requires Docker Compose and a sibling Policy Model Router checkout at the exact revision in
`config/composition-proof/router.commit`. The harness creates an isolated Compose project, local
ephemeral runtime credentials, a trusted loopback HTTPS bridge, temporary artifacts and simulated
providers, then tears down the project.

Local proof, 2026-10-18: 5/5 scenarios passed against Policy Model Router
`3140181c45ce55a3139a292dbe30448012909fdf`; the final Compose checks found no remaining
containers, project networks or project volumes.
The model registry digest was `cd9381414b170a63e2356c0ed66c0efb343ced8a063d77c79e368a983863da18`
and ranking-policy digest was `fe55bd3118554745cf01e9bf9c6b3fb631e0c158acee8ee5e8d7b0d6d37d4d32`.
Focused lifecycle tests also cover cleanup after a failed scenario, unexpected outcome and
`KeyboardInterrupt`. The read-only workflow is
`.github/workflows/portfolio-execution-demo.yml`; its hosted execution-demo and quality checks
passed on PR #277.

Begin with a CLI report over actual execution; reuse the Console/trace stack only after the
underlying execution assertions pass. Do not make UI work a prerequisite for correctness.

| Scenario | Required observable result |
| --- | --- |
| Authorized success | Authenticated request gets a fresh real PDP decision; selected deployment belongs to its group; final usage occurs once before completion. |
| Policy denial | The real PDP denies the request; provider execution count remains zero. |
| Retryable failure before output | Exhaust the reviewed same-deployment retry bound, then fall back only to an already-ranked deployment in the same authorized group. |
| Failure after semantic output | Terminal partial failure; no replay, no fallback and no later successful completion. |
| Client cancellation | Close the response/upstream and release owned resources; no additional provider attempt and no provider-failure classification for cancellation. |

Keep an attractive but unauthorized deployment in the fixture registry and assert that its
execution count stays zero in every scenario. Scenario selection belongs to the local harness;
it must not become a caller-controlled model override on the serving API.

Use ephemeral local credentials, loopback listeners, bounded readiness/cleanup and an isolated
Compose project. Simulated provider behavior must be conspicuous in the report and any UI. If an
HTTP/SSE provider fixture is used, preserve normal HTTPS validation with a trusted local test CA;
never disable certificate verification. Report scenario outcomes, event types/counts, deployment
IDs and digests only, with no payloads, keys or raw error bodies.

Acceptance: one documented command runs the five scenarios, exits nonzero for an unexpected
outcome and verifies teardown after success, failure and interruption. Add focused integration
tests and a credential-free read-only CI job once the external Router dependency is pinned and
available. The full repository quality gate must pass. Record exact revisions and proof type.

## Delivery 2 — two optional real-provider walkthroughs

Consolidate `rag.answer` and `agent.tool-use` as separate, explicitly selected paths. Inspect the
existing approved RAG artifact and historical Claude Code evidence before creating new artifacts.
The untracked local tool-use scorecards/artifact require their own provenance review; do not stage,
overwrite, promote or merge them merely to satisfy this plan.

### Read-only evidence inventory, 2026-10-18

The repository audit was run against both artifacts with their exact expected IDs. The active,
tracked `approved_ranking.json` validates at
`sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad` and covers only
`rag.answer`; its benchmark snapshot is
`sha256:6f6b4ae1928132ce2b3f6f4212151e60617ec511af128fc6833add971691334f` (run 2026-09-10).
The checkpoint log records a later governed live `rag.answer` request through PDP and Gateway to
NVIDIA, with normalized usage and terminal provenance, on 2026-09-15. The launcher remains pinned to
this RAG-only artifact and resolves credentials for all enabled deployments when it starts.

The separate portfolio artifact at
`config/portfolio/agent-tool-use/approved_ranking.json` validates at
`sha256:53cb9aeca737b2b4daa1e62b977bcb74128e238175f936292f74d`; it covers only
`agent.tool-use` and two deployments (Anthropic and OpenAI). It references benchmark snapshot
`sha256:9f299cd0747b59c7ed9675e7c3af31d3a26fb8f1eb23b763f0dd6ff49dc8e89b`, run 2026-09-15, from
dataset digest `sha256:cfc503f5dbec24d2a197bb0888e6eee13850a6dcac39bd46d1e816679eba8e9f`. That snapshot
has four benchmark cases per deployment and zero quality failures; the benchmark scores proposed
tool trajectories and does not execute business tools. Two earlier local snapshots for that
workload had quality failures (4/4 and 1/4 per deployment), so the artifact's exact snapshot
reference matters. A separate dated Claude Code E2E record in `CHECKPOINT_LOG.md` documents 31
admitted tool definitions and actual client-side `Read`/`Bash` tool execution through the governed
loop; it does not give the Gateway tool-execution authority.

Both read-only coverage audits passed and independently confirmed that each artifact covers exactly
one workload, with the other eight declared profile workloads missing. The tool-use artifact is now
available in clean checkouts at the separate portfolio path; it remains outside the active launcher,
whose pin remains RAG-only. The original local candidate and scorecards remain unmodified and
untracked. The referenced benchmark snapshot was reviewed locally but is not included in this copy;
its digest and outcome summary above preserve the provenance link without adding the user-owned
scorecards. The tool-use artifact must not be merged into the RAG artifact. No provider request was
made during this audit.

### Proposed walkthrough bounds

These limits define a reviewable live demonstration, not a provider billing ceiling. No new request
has been sent. Both paths require `GATEWAY_DEMO_API_KEY`, `POLICY_ROUTER_DEMO_API_KEY`, and the six
provider keys required by the full `personal-default` profile because enabled adapters resolve their
credentials at startup; their exact environment-variable names are listed in the
[profile instructions](../../config/profiles/personal-default/README.md#required-server-side-environment-variables).
Keep values in the local secret environment; do not print or record them.

| Path | Request and output bounds | Expected terminal evidence | Cleanup |
| --- | --- | --- | --- |
| `rag.answer` | At most one Gateway request, `max_output_tokens=2000`, using the active RAG artifact. The Gateway may make only its existing bounded provider retries/fallbacks. | One successful terminal response with authorized group, routing/execution identity agreement, normalized usage and the exact active artifact/registry identities. Report metadata only. | Stop the local launcher with Ctrl+C; verify its owned Router/Gateway processes and loopback ports are released. |
| `agent.tool-use` | At most two Gateway requests for one tool proposal and one continuation; `max_tokens=4096` per response; at most one client-executed read of a temporary local fixture. Use the separate portfolio artifact and the existing `agentic-strong` authorization. | Preserve the provider-correlated tool-call ID across the consumer-owned read/result round trip; record authorized group, selected deployment, terminal status and usage as metadata only. The Gateway does not execute the tool. | Remove the temporary fixture and stop the separately launched Gateway and Router; verify their processes and ports are released. |

The request, token and tool limits still do not guarantee a maximum invoice: spend admission is not
active in the serving profile and provider prices can change. Any refresh run still needs the
operator's explicit request-count/output scope and total spend ceiling before sending provider
traffic.

Document required credentials, exact artifact/pin, request bounds, expected terminal evidence and
cleanup. Any new provider run needs a concrete request count, output bound and operator-approved
scope. Provider secrets remain at the Gateway; tools remain consumer-owned. A video or screenshot
is supporting material, not a substitute for the executable path.

Acceptance: each walkthrough has a reviewed reproducible configuration and dated governed live
evidence, with optional execution outside default CI. `personal-default` remains RAG-only until a
separate explicit activation changes its pin/configuration. Enabling all nine workloads or merging
multiple ranking artifacts is outside this delivery.

## Delivery 3 — local verified-HTTPS PDP exercise

Extend the laboratory with the real Router behind a local TLS endpoint and a trusted test CA.
Compare default and pooled transports against the same fresh authorization sequence. Cover denial,
invalid certificates, saturation and startup/shutdown; never reuse or replay decisions. Exercise the
deadline before commitment and after semantic output, including upstream closure and no late success.

Acceptance: record exact revisions, concurrency, request counts and latency/error observations,
including unfavorable results. Demonstrate behavior without inventing a performance threshold or
changing serving defaults. This proves the local integration only; AWS load, proxy behavior and
production readiness remain separate claims.

## Validation and stop conditions

Use the existing full Python quality gate and focused tests appropriate to each delivery. Run the
Console gate only for Console changes. Keep the Phase 0 gate and 80% coverage checks intact.
Review the completed diff independently before publishing evidence as accepted. Do not broaden
testing into paid provider runs as part of routine CI.

After these deliveries, prefer maintenance and evidence refresh over more features. Reopen cloud
deployment, durable credential/spend controls, additional providers or consumer migrations only
when a concrete use case demonstrates their value. Their requirements are retained in the
[conditional readiness record](POST_CORE_READINESS.md).
