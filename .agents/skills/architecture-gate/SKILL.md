# Architecture Gate Skill

Use this skill for changes that affect Phase 0 boundaries.

1. Read `AGENTS.md`, `docs/project/CURRENT_STATE.md`, `docs/project/ARCHITECTURE.md`, and applicable ADRs.
2. Preserve `Gateway allowed set ⊆ Policy Router authorized set`.
3. Keep provider/FastAPI/database/OpenTelemetry dependencies out of contracts/domain.
4. Treat caller security metadata as claims until authenticated/policy-validated.
5. Add/change an ADR before changing an accepted architecture decision.
6. Run `python scripts/phase0_gate.py` and then the repository quality gate.
