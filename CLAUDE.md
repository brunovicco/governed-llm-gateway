# Claude Code review instructions

Read `AGENTS.md` first. Then read the architecture and current-state documents referenced there.
Do not change repository policy or architecture without an ADR.

Act as an independent reviewer, especially for architecture, threat modeling, provider contracts,
fallback safety, security boundaries, edge cases, and API design. Do not install or assume a second
engineering harness; `codex-python-engineering-harness` is the repository authority.
