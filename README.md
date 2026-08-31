# Governed LLM Gateway

Reusable provider-neutral LLM execution gateway whose responsibility is **governed model resolution
and execution**.

Status: **Phase 0 — Architecture Gate complete baseline**.

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

## Phase 0 contents

- uv workspace with `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api` boundaries;
- Codex-native harness instructions and minimal Claude reviewer compatibility;
- provider-neutral immutable contract draft;
- architecture and security source documents;
- ADR-0001 through ADR-0005 accepted;
- trust-boundary and PDP/PEP contract drafts;
- model-registry and ranking-policy draft configuration;
- threat model draft;
- architecture/phase gates and contract tests;
- no provider SDK and no provider API call.

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

## Validate Phase 0

```bash
python scripts/phase0_gate.py
```

Full quality gate after dependencies are synchronized:

```bash
uv sync --frozen
python scripts/quality_gate.py
```

## Source of truth

Start with `docs/project/CURRENT_STATE.md` for continuation and
`docs/project/SOURCE_ROADMAP.txt` for the original project specification.
