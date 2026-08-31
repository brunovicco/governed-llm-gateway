# Engineering Governance Profile

Development baseline: `codex-python-engineering-harness` workspace profile with governance capability
profile `agentic`, without regulatory overlays during initial technical implementation.

This directory records engineering controls only. It does not claim organizational compliance or
certification.

Phase 0 controls:

- architectural decisions require ADRs;
- default-deny package boundaries for contracts/domain;
- external/provider mutations are absent in Phase 0;
- policy/identity failure is fail closed by architecture;
- runtime evidence is metadata-only by default;
- quality, security, dependency, architecture, and secret checks are defined in CI/gates.
