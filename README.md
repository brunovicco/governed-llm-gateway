# Governed LLM Gateway

Reusable provider-neutral LLM execution gateway whose responsibility is **governed model resolution
and execution**.

Status: **Phase 2 — Contracts and Model Registry implemented; under review**.

The project separates authorization from operational selection:

```text
Application / Agent
       │ workload + requirements + policy metadata
       ▼
Policy Model Router (PDP)
       │ authorized logical model group + provenance
       ▼
Governed LLM Gateway (PEP + operational selection)
       │ concrete eligible deployment
       ▼
LLM Provider
```

Core invariant:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The gateway may make authorization narrower due to capability, health, environment, cost, latency,
or other operational constraints. It must never make authorization broader.

## Current implementation

Phase 0 established the uv workspace, architecture boundaries, security model, provider-neutral
contract baseline, ADR-0001 through ADR-0005, and fail-closed authorization invariant.

Phase 1 was completed in the existing `policy-model-router` repository, generalizing workload and
logical model-group identifiers while preserving deterministic policy decisions and provenance.

Phase 2 adds:

- provider-neutral capability and modality vocabularies;
- immutable model-registry domain objects;
- strict safe-YAML loading with duplicate-key rejection;
- closed-schema and semantic validation;
- explicit versioned pricing metadata and unknown-pricing representation;
- deterministic canonicalization and SHA-256 registry provenance digest;
- contract tests for invalid fields, duplicate IDs, capability combinations, safe YAML, and digest
  determinism;
- no provider SDK and no provider API call.

The checked-in `config/model_registry.yaml` remains intentionally empty in Phase 2. Concrete provider
entries arrive only with later provider work and evidence-backed catalog changes.

## Repository layout

```text
apps/gateway-api/          future HTTP composition root
packages/gateway-contracts provider-neutral contracts
packages/gateway-core/     domain/application/adapters boundary
packages/gateway-client/   thin consumer SDK boundary
config/                    model/ranking/provider configuration
benchmarks/                future benchmark framework
examples/                  future consumers/examples
tests/                     contract/integration/e2e suites
docs/                      durable project sources and ADRs
```

## Validate

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

The quality gate includes Ruff, mypy, pytest/coverage, Bandit, pip-audit, architecture validation,
secret scanning, and the Phase 0 architecture regression gate.

## Source of truth

Start with `docs/project/CURRENT_STATE.md` for continuation and
`docs/project/SOURCE_ROADMAP.txt` for the original project specification.
