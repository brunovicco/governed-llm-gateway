from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one marker, found {count}")
    target.write_text(text.replace(old, new, 1))


# README EN.
replace_once(
    "README.md",
    "Status: **Phases 0–13 complete; Phase 14 in progress — Cases 1/2 complete, Case 3 deferred. All roadmap-listed benchmark classes are represented by reviewed deterministic contracts. Offline quality evidence, immediate runtime health and versioned recent operational evidence with bounded process-local materialization remain explicit separate boundaries; no online-telemetry ranking policy is active.**",
    "Status: **Phases 0–13 complete; Phase 14 in progress — Cases 1/2 complete, Case 3 deferred. All roadmap-listed benchmark classes are represented by reviewed deterministic contracts. Offline quality evidence, immediate runtime health and versioned recent operational evidence with bounded process-local materialization and best-effort runtime recording remain explicit separate boundaries; no online-telemetry ranking policy is active.**",
)
replace_once(
    "README.md",
    "- strict content-addressed recent operational evidence schema `1.0` plus bounded fail-closed process-local materialization, preserved separately from health and not consumed by ranking.",
    "- strict content-addressed recent operational evidence schema `1.0`, bounded fail-closed process-local materialization and optional best-effort runtime attempt recording, preserved separately from health and not consumed by ranking.",
)
replace_once(
    "README.md",
    "PR #70 adds a strict, immutable, content-addressed schema `1.0` artifact for bounded recent operational windows. PR #73 adds a deterministic materializer over explicit timestamped metadata-only provider-attempt samples plus a bounded process-local source that fails closed when requested-window completeness cannot be proven.\n\nThis remains separate from `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, which are immediate process-local resilience and eligibility state. Runtime recorder wiring, a production/shared sample source and metrics-backend query adapters remain pending. Operational evidence does not modify `StaticDeploymentScore`, ranking weights, eligibility or authorization; any future online scoring still requires a separate explicit versioned policy.",
    "PR #70 adds a strict, immutable, content-addressed schema `1.0` artifact for bounded recent operational windows. PR #73 adds deterministic materialization from explicit timestamped metadata-only provider-attempt samples, and PR #76 adds optional process-local best-effort recording in both bounded runtime executors with conservative completeness invalidation.\n\nThis remains separate from `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, which are immediate process-local resilience and eligibility state. Recorder failure, caller cancellation or an unrepresentable post-call failure cannot fabricate provider-error evidence or become an inference-availability dependency. A production/shared sample source and metrics-backend query adapters remain pending. Operational evidence does not modify `StaticDeploymentScore`, ranking weights, eligibility or authorization; any future online scoring still requires a separate explicit versioned policy.",
)
replace_once(
    "README.md",
    "Current validated `main` baseline after PR #73 (`09adba564cd996f03f8363f44dce7f2b6fd5c303`):\n\n- **756 tests passed**;\n- **82.46% aggregate coverage** (threshold 80%);\n- mypy passed across **180 source files**;\n- Ruff lint/format passed across **180 files**;\n- Bandit reported **0 issues** across 16,925 LOC;\n- pip-audit reported **no known vulnerabilities**;\n- architecture check, secret scan and Phase 0 gate passed;\n- post-merge `main` quality run `34060829312` — **PASS**.",
    "Current validated `main` baseline after PR #76 (`455c11a24e09adddcfff9fc8c9578d74ec6c6606`):\n\n- **767 tests passed**;\n- **82.47% aggregate coverage** (threshold 80%);\n- mypy passed across **182 source files**;\n- Ruff lint/format passed across **182 files**;\n- Bandit reported **0 issues** across 17,133 LOC;\n- pip-audit reported **no known vulnerabilities**;\n- architecture check, secret scan and Phase 0 gate passed;\n- post-merge `main` quality run `34062983396` — **PASS**.",
)

# README PT-BR.
replace_once(
    "README.pt-BR.md",
    "Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados. Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada com materialização process-local limitada permanecem fronteiras explícitas e separadas; nenhuma policy de ranking por telemetria online está ativa.**",
    "Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados. Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada com materialização process-local limitada e gravação best-effort de tentativas de runtime permanecem fronteiras explícitas e separadas; nenhuma policy de ranking por telemetria online está ativa.**",
)
replace_once(
    "README.pt-BR.md",
    "- schema `1.0` estrito e content-addressed para evidência operacional recente com materialização process-local limitada e fail-closed, separado da saúde e não consumido pelo ranking.",
    "- schema `1.0` estrito e content-addressed para evidência operacional recente, materialização process-local limitada/fail-closed e gravação opcional best-effort de tentativas de runtime, separados da saúde e não consumidos pelo ranking.",
)
replace_once(
    "README.pt-BR.md",
    "O PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. O PR #73 adiciona um materializer determinístico sobre samples explícitos, timestamped e metadata-only de tentativas reais do provider, além de uma fonte process-local limitada que falha de forma fechada quando não consegue provar a completude da janela solicitada.\n\nIsso permanece separado de `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, que continuam como estado imediato e process-local de resiliência/elegibilidade. Wiring do recorder de runtime, fonte de samples compartilhada/de produção e adapters de consulta a backend de métricas continuam pendentes. Essa evidência não altera `StaticDeploymentScore`, pesos de ranking, elegibilidade ou autorização; qualquer scoring online futuro ainda exige uma policy versionada explícita e separada.",
    "O PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. O PR #73 adiciona materialização determinística de samples explícitos, timestamped e metadata-only de tentativas reais do provider, e o PR #76 adiciona gravação opcional best-effort e process-local nos dois executores limitados, com invalidação conservadora de completude.\n\nIsso permanece separado de `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, que continuam como estado imediato e process-local de resiliência/elegibilidade. Falha do recorder, cancelamento do caller ou uma falha pós-call não representável não podem fabricar provider-error evidence nem se tornar dependência de disponibilidade da inferência. Fonte de samples compartilhada/de produção e adapters de consulta a backend de métricas continuam pendentes. Essa evidência não altera `StaticDeploymentScore`, pesos de ranking, elegibilidade ou autorização; qualquer scoring online futuro ainda exige uma policy versionada explícita e separada.",
)
replace_once(
    "README.pt-BR.md",
    "Baseline validado atual do `main` após o PR #73 (`09adba564cd996f03f8363f44dce7f2b6fd5c303`):\n\n- **756 testes passaram**;\n- **82,46% de cobertura agregada** (threshold 80%);\n- mypy passou em **180 arquivos fonte**;\n- Ruff lint/format passou em **180 arquivos**;\n- Bandit reportou **0 issues** em 16.925 LOC;\n- pip-audit reportou **nenhuma vulnerabilidade conhecida**;\n- architecture check, secret scan e Phase 0 gate passaram;\n- quality run pós-merge no `main` `34060829312` — **PASS**.",
    "Baseline validado atual do `main` após o PR #76 (`455c11a24e09adddcfff9fc8c9578d74ec6c6606`):\n\n- **767 testes passaram**;\n- **82,47% de cobertura agregada** (threshold 80%);\n- mypy passou em **182 arquivos fonte**;\n- Ruff lint/format passou em **182 arquivos**;\n- Bandit reportou **0 issues** em 17.133 LOC;\n- pip-audit reportou **nenhuma vulnerabilidade conhecida**;\n- architecture check, secret scan e Phase 0 gate passaram;\n- quality run pós-merge no `main` `34062983396` — **PASS**.",
)

# CURRENT_STATE ledger and boundary.
replace_once(
    "docs/project/CURRENT_STATE.md",
    "- PR #73 — deterministic materialization from bounded timestamped metadata-only provider-attempt samples, including fail-closed process-local coverage/eviction semantics and canonical schema `1.0` snapshot creation; no executor recorder wiring, ranking or authorization change.",
    "- PR #73 — deterministic materialization from bounded timestamped metadata-only provider-attempt samples, including fail-closed process-local coverage/eviction semantics and canonical schema `1.0` snapshot creation; no executor recorder wiring, ranking or authorization change.\n- PR #76 — optional process-local best-effort provider-attempt recording in non-streaming and streaming executors, with separate monotonic/UTC clocks and conservative completeness invalidation for cancellation, unrepresentable post-call failures or recorder failure; no ranking or authorization change.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "Latest validated gateway baseline after PR #73:\n\n`09adba564cd996f03f8363f44dce7f2b6fd5c303`\n\nPost-merge quality run:\n\n`34060829312` — PASS.\n\nValidation:\n\n- 756 tests passed;\n- aggregate coverage 82.46%;\n- strict mypy passed across 180 source files;\n- Ruff lint/format passed across 180 files;\n- Bandit reported no issues across 16,925 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
    "Latest validated gateway baseline after PR #76:\n\n`455c11a24e09adddcfff9fc8c9578d74ec6c6606`\n\nPost-merge quality run:\n\n`34062983396` — PASS.\n\nValidation:\n\n- 767 tests passed;\n- aggregate coverage 82.47%;\n- strict mypy passed across 182 source files;\n- Ruff lint/format passed across 182 files;\n- Bandit reported no issues across 17,133 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "## Recent operational evidence — CONTRACT + BOUNDED MATERIALIZER COMPLETE, LIVE SOURCE PENDING\n\nPR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples, a canonical snapshot factory and a bounded process-local source with fail-closed coverage/eviction semantics.\n\nThis does not reinterpret `InMemoryHealthTracker` / `DeploymentHealthSnapshot` as historical evidence. Those objects remain immediate process-local resilience/eligibility state. The PR #73 source is intentionally local to one process and suitable for deterministic CI/replay; it does not claim distributed completeness.\n\nRuntime recorder wiring, a production/shared sample source, metrics-backend query adapters, online-score normalization and ranking-policy changes remain pending. Operational evidence cannot authorize or restore an otherwise ineligible candidate, and any future use in scoring requires a separate explicit versioned policy.",
    "## Recent operational evidence — CONTRACT + MATERIALIZER + LOCAL RECORDER COMPLETE, SHARED SOURCE PENDING\n\nPR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples, a canonical snapshot factory and a bounded process-local source with fail-closed coverage/eviction semantics. PR #76 adds optional process-local best-effort recording to both bounded executors.\n\nThis does not reinterpret `InMemoryHealthTracker` / `DeploymentHealthSnapshot` as historical evidence. Those objects remain immediate process-local resilience/eligibility state. The recorder/source is intentionally local to one process and does not claim distributed completeness. Cancellation, generator close, unrepresentable post-call failures and recorder failures conservatively invalidate completeness rather than fabricate provider errors or fail inference.\n\nA production/shared sample source, metrics-backend query adapters, online-score normalization and ranking-policy changes remain pending. Operational evidence cannot authorize or restore an otherwise ineligible candidate, and any future use in scoring requires a separate explicit versioned policy.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-PR #73 operational-evidence materialization baseline.",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-PR #76 operational-evidence runtime-recording baseline.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "8. A future operational-evidence increment may add best-effort runtime recording or a production/shared metadata-only sample source with explicit completeness semantics; it must not make evidence collection part of inference availability or invent online score normalization/adaptive policy.",
    "8. A future operational-evidence increment may add a production/shared metadata-only sample source or exporter decoupled from provider execution with explicit completeness semantics; it must not make remote evidence delivery part of inference availability or invent online score normalization/adaptive policy.",
)

# EVALUATION boundary.
replace_once(
    "docs/project/EVALUATION.md",
    "This evidence is descriptive and immutable. It is not an authorization source, does not modify eligibility, is not automatically loaded by ranking and does not create adaptive policy. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples plus a bounded process-local source that fails closed when complete requested-window coverage cannot be proven.\n\n`InMemoryHealthTracker` / `DeploymentHealthSnapshot` remain the immediate process-local resilience boundary and are not historical window reconstruction. Runtime recorder wiring, a production/shared sample source and metrics-backend adapters remain pending. Only a subsequent explicit versioned ranking policy may define how operational measurements influence score dimensions.",
    "This evidence is descriptive and immutable. It is not an authorization source, does not modify eligibility, is not automatically loaded by ranking and does not create adaptive policy. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples plus a bounded process-local source that fails closed when complete requested-window coverage cannot be proven. PR #76 adds optional process-local best-effort recording in both bounded executors without making evidence collection an inference-availability dependency.\n\n`InMemoryHealthTracker` / `DeploymentHealthSnapshot` remain the immediate process-local resilience boundary and are not historical window reconstruction. Cancellation, generator close, unrepresentable post-call failures and recorder failures invalidate sample-source completeness conservatively instead of fabricating provider errors. A production/shared sample source and metrics-backend adapters remain pending. Only a subsequent explicit versioned ranking policy may define how operational measurements influence score dimensions.",
)

# Benchmark matrix baseline / next boundary.
replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "Latest validated `main` baseline after PR #73:\n\n- commit `09adba564cd996f03f8363f44dce7f2b6fd5c303`;\n- post-merge quality run `34060829312` — PASS;\n- 756 tests passed;\n- 82.46% aggregate coverage;\n- strict mypy and Ruff passed across 180 source files;\n- Bandit reported no issues across 16,925 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
    "Latest validated `main` baseline after PR #76:\n\n- commit `455c11a24e09adddcfff9fc8c9578d74ec6c6606`;\n- post-merge quality run `34062983396` — PASS;\n- 767 tests passed;\n- 82.47% aggregate coverage;\n- strict mypy and Ruff passed across 182 source files;\n- Bandit reported no issues across 17,133 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
)
replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "Until that changes, further gateway work should be consumer-agnostic and independently justified. The Roadmap measurement audit preserves every currently reviewed deterministic quality dimension, including bounded `pt_br_quality`. PR #70 preserves versioned recent operational evidence separately from immediate runtime health and ranking, and PR #73 adds bounded deterministic materialization without ranking authority. A future recorder/shared-source increment must preserve metadata-only completeness semantics and must not make evidence collection part of inference availability; online score normalization remains a separate future versioned policy decision. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.",
    "Until that changes, further gateway work should be consumer-agnostic and independently justified. The Roadmap measurement audit preserves every currently reviewed deterministic quality dimension, including bounded `pt_br_quality`. PR #70 preserves versioned recent operational evidence separately from immediate runtime health and ranking, PR #73 adds bounded deterministic materialization, and PR #76 adds optional best-effort local runtime recording with conservative completeness invalidation. A future shared-source/export increment must remain decoupled from provider execution and preserve metadata-only completeness semantics; online score normalization remains a separate future versioned policy decision. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.",
)

# Operational-evidence durable status after merge.
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "Status: **Schema `1.0` and bounded process-local materialization are COMPLETE through PR #73. Issue #75 adds optional best-effort runtime attempt recording for both bounded executors. Production/shared sources and online ranking policy remain pending.**",
    "Status: **COMPLETE through PR #76 for schema `1.0`, bounded process-local materialization and optional best-effort runtime attempt recording in both bounded executors. Production/shared sources and online ranking policy remain pending.**",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "Issue #75 adds the `OperationalAttemptRecorder` application port and optional recorder dependencies to both `ResilientExecutionService` and `StreamingExecutionService`.",
    "PR #76 adds the `OperationalAttemptRecorder` application port and optional recorder dependencies to both `ResilientExecutionService` and `StreamingExecutionService`.",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "## Explicitly not implemented by issue #75",
    "## Explicitly not implemented by PR #76",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "After issue #75 is merged and validated, a later consumer-agnostic increment may define a production/shared metadata-only source or exporter that is decoupled from provider execution and has explicit completeness semantics.",
    "After PR #76, a later consumer-agnostic increment may define a production/shared metadata-only source or exporter that is decoupled from provider execution and has explicit completeness semantics.",
)
