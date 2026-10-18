# Portfolio demonstration implementation plan

Status: accepted direction, implementation pending. Prepared against the PR #275 baseline on
2026-10-17 under [ADR-0028](../adr/ADR-0028-portfolio-scope-and-evidence.md). These are bounded
portfolio deliveries, not new numbered phases. No completed demo is implied by this plan.

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
