# Phase 0 and Phase 2 Validation Record

Date: 2026-08-31

## Toolchain

- Python project runtime: 3.13+
- project pin: Python 3.13.12
- quality-tool execution pinned to Python 3.13
- uv workspace with locked dependencies

## Phase 0 baseline

The Architecture Gate baseline passed:

- `uv lock --check`;
- Ruff lint/format;
- mypy;
- pytest + coverage;
- Bandit;
- pip-audit;
- architecture validation;
- secret scanning;
- `scripts/phase0_gate.py`.

The Phase 0 independent Claude Code review remains a separate review criterion recorded in
`docs/architecture/REVIEW.md`.

## Phase 2 implementation validation

Phase 2 — Contracts and Model Registry was validated against the complete repository quality gate.

Results:

- `uv lock --check` — PASS;
- Ruff lint — PASS;
- Ruff formatting — PASS;
- mypy — PASS across 27 source files;
- pytest — PASS, 30 tests;
- total coverage — 88.19% (minimum 80%);
- Bandit — PASS, no identified issues and no skipped files;
- pip-audit — PASS, no known vulnerabilities;
- architecture validation — PASS;
- secret scanning — PASS;
- Phase 0 regression gate — PASS.

## Phase 2 acceptance evidence

The test suite verifies that the registry:

- rejects unknown root, deployment, capability, and pricing fields through closed-schema validation;
- rejects duplicate YAML mapping/deployment keys before parser overwrite;
- rejects invalid capability/modality combinations;
- requires text capability and text modality;
- uses safe YAML semantics and rejects Python object tags;
- enforces deployment source-date/catalog-version consistency;
- permits unknown pricing only when represented explicitly as `null`;
- produces a deterministic SHA-256 digest from canonical validated content;
- keeps the digest stable across irrelevant YAML ordering and equivalent decimal representations;
- changes the digest when meaningful registry content changes.

The domain and contracts remain provider-neutral and contain no provider inference SDK dependency.
The only new runtime dependency is `PyYAML==6.0.3`, owned by the configuration adapter boundary.

## Quality-gate execution model

Ruff, Bandit, and pip-audit remain isolated quality tools. mypy and pytest execute with `uv run
--all-packages` so tools that import workspace code see the actual locked project dependencies.
This avoids the Phase 0 assumption that isolated `uvx` environments are sufficient when the runtime
has no third-party dependencies.

## Phase 2 status

Implementation quality gates: **PASS**

Architecture/security regressions: **PASS**

Phase 2 merge review: **PENDING**
