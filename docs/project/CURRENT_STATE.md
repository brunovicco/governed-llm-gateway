# Current State

Last updated: 2026-08-31

## Phase status

| Phase | Status |
|---|---|
| Phase 0 — Architecture Gate | COMPLETE BASELINE |
| Phase 1 — Policy Model Router generalization | COMPLETE (`policy-model-router` PR #20) |
| Phase 2 — Contracts and Model Registry | IMPLEMENTED — IN REVIEW |
| Phase 3+ | NOT STARTED |

## Phase 0 delivered

- uv workspace root with four explicit members;
- provider-neutral immutable contract baseline;
- explicit domain/application/adapters separation and authorization invariant guard;
- durable project source documents and ADR-0001 through ADR-0005;
- trusted/untrusted attribute model, PDP/PEP contract draft, threat model, and architecture gates.

## Phase 1 dependency completed

`policy-model-router` was generalized so workload and logical model-group identifiers are policy-defined
rather than credit-desk-specific closed enums. Unknown workloads remain fail-closed and deterministic
policy provenance is preserved. The gateway does not implement a legacy compatibility translation.

## Phase 2 implemented

- provider-neutral `Capability` and `Modality` vocabularies;
- immutable model-registry domain objects separating provider, model, deployment, and logical group;
- strict closed-schema validation with required-field enforcement;
- duplicate YAML mapping/deployment-key rejection before silent overwrite can occur;
- safe YAML parsing through a `yaml.SafeLoader` derivative;
- semantic capability/modality validation, including text requirements and vision/image consistency;
- versioned pricing metadata with explicit `null` for unknown pricing;
- source-date and catalog-version consistency validation;
- deterministic canonical representation and SHA-256 registry digest;
- semantic digest stability across YAML ordering and equivalent decimal representation;
- checked-in empty Phase 2 registry with no provider/model claim;
- project-aware mypy/pytest quality-gate execution through `uv run --all-packages`;
- regression coverage for Phase 0 architecture/security invariants.

## Phase 2 validation

The complete repository gate passes with:

- 30 tests;
- 88.19% total coverage (minimum 80%);
- Ruff lint/format PASS;
- mypy PASS;
- Bandit PASS with no identified issues;
- pip-audit PASS with no known vulnerabilities;
- architecture check PASS;
- secret scan PASS;
- Phase 0 regression gate PASS.

## Explicitly deferred

- provider SDKs and live inference;
- FastAPI endpoint implementation;
- Policy Model Router runtime/API integration (Phase 4);
- operational ranking, retries, fallback runtime, circuit breakers, streaming;
- OpenTelemetry runtime and benchmark-driven ranking;
- client HTTP transport.

## Next phase

After Phase 2 review/merge, start Phase 3 — Provider Execution Foundation. Introduce provider execution
ports/adapters by API family, not by model family, while keeping all authorization authority outside
provider adapters and preserving `Gateway allowed set ⊆ Policy Router authorized set`.
