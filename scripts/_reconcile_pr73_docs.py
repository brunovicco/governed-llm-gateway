from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one marker, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1))


replace_once(
    "README.md",
    "Status: **Phases 0–13 complete; Phase 14 in progress — Cases 1/2 complete, Case 3 deferred. All roadmap-listed benchmark classes are represented by reviewed deterministic contracts. Offline quality evidence, immediate runtime health and versioned recent operational evidence remain explicit separate boundaries; no online-telemetry ranking policy is active.**",
    "Status: **Phases 0–13 complete; Phase 14 in progress — Cases 1/2 complete, Case 3 deferred. All roadmap-listed benchmark classes are represented by reviewed deterministic contracts. Offline quality evidence, immediate runtime health and versioned recent operational evidence with bounded process-local materialization remain explicit separate boundaries; no online-telemetry ranking policy is active.**",
)
replace_once(
    "README.md",
    "- strict content-addressed recent operational evidence schema `1.0`, preserved separately from process-local health and not yet consumed by ranking.",
    "- strict content-addressed recent operational evidence schema `1.0` plus bounded fail-closed process-local materialization, preserved separately from health and not consumed by ranking.",
)
replace_once(
    "README.md",
    "PR #70 adds a strict, immutable, content-addressed schema `1.0` artifact for bounded recent operational windows. It preserves collector provenance, request/provider-attempt counts, provider errors, rate limits, timeouts, fallback requests and provider latency p50/p95 per `(runtime_workload, deployment_id)`.\n\nThis is separate from `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, which remain immediate process-local resilience and eligibility state. No production materializer or metrics-backend query is implemented yet, and operational evidence does not modify `StaticDeploymentScore`, ranking weights, eligibility or authorization. A later reviewed increment may materialize this evidence from a metadata-only runtime source before any separate versioned online-scoring policy is considered.",
    "PR #70 adds a strict, immutable, content-addressed schema `1.0` artifact for bounded recent operational windows. PR #73 adds a deterministic materializer over explicit timestamped metadata-only provider-attempt samples plus a bounded process-local source that fails closed when requested-window completeness cannot be proven.\n\nThis remains separate from `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, which are immediate process-local resilience and eligibility state. Runtime recorder wiring, a production/shared sample source and metrics-backend query adapters remain pending. Operational evidence does not modify `StaticDeploymentScore`, ranking weights, eligibility or authorization; any future online scoring still requires a separate explicit versioned policy.",
)
replace_once(
    "README.md",
    "Current validated `main` baseline after PR #70 (`7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`):\n\n- **746 tests passed**;\n- **82.28% aggregate coverage** (threshold 80%);\n- mypy passed across **177 source files**;\n- Ruff lint/format passed across **177 files**;\n- Bandit reported **0 issues** across 16,550 LOC;\n- pip-audit reported **no known vulnerabilities**;\n- architecture check, secret scan and Phase 0 gate passed;\n- post-merge `main` quality run `34055635049` — **PASS**.",
    "Current validated `main` baseline after PR #73 (`09adba564cd996f03f8363f44dce7f2b6fd5c303`):\n\n- **756 tests passed**;\n- **82.46% aggregate coverage** (threshold 80%);\n- mypy passed across **180 source files**;\n- Ruff lint/format passed across **180 files**;\n- Bandit reported **0 issues** across 16,925 LOC;\n- pip-audit reported **no known vulnerabilities**;\n- architecture check, secret scan and Phase 0 gate passed;\n- post-merge `main` quality run `34060829312` — **PASS**.",
)

replace_once(
    "README.pt-BR.md",
    "Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados. Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada permanecem fronteiras explícitas e separadas; nenhuma policy de ranking por telemetria online está ativa.**",
    "Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados. Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada com materialização process-local limitada permanecem fronteiras explícitas e separadas; nenhuma policy de ranking por telemetria online está ativa.**",
)
replace_once(
    "README.pt-BR.md",
    "- schema `1.0` estrito e content-addressed para evidência operacional recente, separado da saúde process-local e ainda não consumido pelo ranking.",
    "- schema `1.0` estrito e content-addressed para evidência operacional recente com materialização process-local limitada e fail-closed, separado da saúde e não consumido pelo ranking.",
)
replace_once(
    "README.pt-BR.md",
    "O PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. Ele preserva proveniência do collector, contagens de requests/tentativas do provider, erros do provider, rate limits, timeouts, requests com fallback e latência p50/p95 do provider por `(runtime_workload, deployment_id)`.\n\nIsso permanece separado de `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, que continuam como estado imediato e process-local de resiliência/elegibilidade. Ainda não existe materializer de produção nem consulta a backend de métricas, e essa evidência não altera `StaticDeploymentScore`, pesos de ranking, elegibilidade ou autorização. Um incremento revisado posterior pode materializar essa evidência a partir de uma fonte de runtime metadata-only antes de qualquer policy versionada separada de scoring online.",
    "O PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. O PR #73 adiciona um materializer determinístico sobre samples explícitos, timestamped e metadata-only de tentativas reais do provider, além de uma fonte process-local limitada que falha de forma fechada quando não consegue provar a completude da janela solicitada.\n\nIsso permanece separado de `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, que continuam como estado imediato e process-local de resiliência/elegibilidade. Wiring do recorder de runtime, fonte de samples compartilhada/de produção e adapters de consulta a backend de métricas continuam pendentes. Essa evidência não altera `StaticDeploymentScore`, pesos de ranking, elegibilidade ou autorização; qualquer scoring online futuro ainda exige uma policy versionada explícita e separada.",
)
replace_once(
    "README.pt-BR.md",
    "Baseline validado atual do `main` após o PR #70 (`7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`):\n\n- **746 testes passaram**;\n- **82,28% de cobertura agregada** (threshold 80%);\n- mypy passou em **177 arquivos fonte**;\n- Ruff lint/format passou em **177 arquivos**;\n- Bandit reportou **0 issues** em 16.550 LOC;\n- pip-audit reportou **nenhuma vulnerabilidade conhecida**;\n- architecture check, secret scan e Phase 0 gate passaram;\n- quality run pós-merge no `main` `34055635049` — **PASS**.",
    "Baseline validado atual do `main` após o PR #73 (`09adba564cd996f03f8363f44dce7f2b6fd5c303`):\n\n- **756 testes passaram**;\n- **82,46% de cobertura agregada** (threshold 80%);\n- mypy passou em **180 arquivos fonte**;\n- Ruff lint/format passou em **180 arquivos**;\n- Bandit reportou **0 issues** em 16.925 LOC;\n- pip-audit reportou **nenhuma vulnerabilidade conhecida**;\n- architecture check, secret scan e Phase 0 gate passaram;\n- quality run pós-merge no `main` `34060829312` — **PASS**.",
)

replace_once(
    "docs/project/CURRENT_STATE.md",
    "- PR #70 — strict schema `1.0` recent operational evidence with collector/time-window provenance, content-derived identity and explicit request/error/fallback/latency measurements; no collector, ranking-score normalization or routing-policy change.",
    "- PR #70 — strict schema `1.0` recent operational evidence with collector/time-window provenance, content-derived identity and explicit request/error/fallback/latency measurements; no collector, ranking-score normalization or routing-policy change.\n- PR #73 — deterministic materialization from bounded timestamped metadata-only provider-attempt samples, including fail-closed process-local coverage/eviction semantics and canonical schema `1.0` snapshot creation; no executor recorder wiring, ranking or authorization change.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "Latest validated gateway baseline after PR #70:\n\n`7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`\n\nPost-merge quality run:\n\n`34055635049` — PASS.\n\nValidation:\n\n- 746 tests passed;\n- aggregate coverage 82.28%;\n- strict mypy passed across 177 source files;\n- Ruff lint/format passed across 177 files;\n- Bandit reported no issues across 16,550 LOC;",
    "Latest validated gateway baseline after PR #73:\n\n`09adba564cd996f03f8363f44dce7f2b6fd5c303`\n\nPost-merge quality run:\n\n`34060829312` — PASS.\n\nValidation:\n\n- 756 tests passed;\n- aggregate coverage 82.46%;\n- strict mypy passed across 180 source files;\n- Ruff lint/format passed across 180 files;\n- Bandit reported no issues across 16,925 LOC;",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "## Recent operational evidence — CONTRACT COMPLETE, MATERIALIZER PENDING\n\nPR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. It records collector identity/version, UTC window provenance, content-derived identity and explicit request/provider-attempt/error/rate-limit/timeout/fallback/provider-latency p50/p95 measurements.\n\nThis does not reinterpret `InMemoryHealthTracker` / `DeploymentHealthSnapshot` as historical evidence. Those objects remain immediate process-local resilience/eligibility state. No production materializer, metrics-backend query, shared health store, online-score normalization or ranking-policy change exists yet.\n\nThe next admissible consumer-agnostic step is a metadata-only materializer for a bounded recent runtime window. Only after that evidence-production path is reviewed should a separate explicit versioned policy define how operational measurements could influence score dimensions. Operational evidence cannot authorize or restore an otherwise ineligible candidate.",
    "## Recent operational evidence — CONTRACT + BOUNDED MATERIALIZER COMPLETE, LIVE SOURCE PENDING\n\nPR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples, a canonical snapshot factory and a bounded process-local source with fail-closed coverage/eviction semantics.\n\nThis does not reinterpret `InMemoryHealthTracker` / `DeploymentHealthSnapshot` as historical evidence. Those objects remain immediate process-local resilience/eligibility state. The PR #73 source is intentionally local to one process and suitable for deterministic CI/replay; it does not claim distributed completeness.\n\nRuntime recorder wiring, a production/shared sample source, metrics-backend query adapters, online-score normalization and ranking-policy changes remain pending. Operational evidence cannot authorize or restore an otherwise ineligible candidate, and any future use in scoring requires a separate explicit versioned policy.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-PR #70 evidence baseline.",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-PR #73 operational-evidence materialization baseline.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "8. The next operational-evidence increment may materialize schema `1.0` from a bounded metadata-only runtime source; it must not invent online score normalization or adaptive policy.",
    "8. A future operational-evidence increment may add best-effort runtime recording or a production/shared metadata-only sample source with explicit completeness semantics; it must not make evidence collection part of inference availability or invent online score normalization/adaptive policy.",
)

replace_once(
    "docs/project/EVALUATION.md",
    "This evidence is descriptive and immutable. It is not an authorization source, does not modify eligibility, is not automatically loaded by ranking and does not create adaptive policy. No production materializer or metrics-backend adapter exists yet. A later reviewed materializer may build these snapshots from a metadata-only runtime source; only a subsequent explicit versioned ranking policy may define how operational measurements influence score dimensions.\n\n`InMemoryHealthTracker` / `DeploymentHealthSnapshot` remain the immediate process-local resilience boundary and are not historical window reconstruction.",
    "This evidence is descriptive and immutable. It is not an authorization source, does not modify eligibility, is not automatically loaded by ranking and does not create adaptive policy. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples plus a bounded process-local source that fails closed when complete requested-window coverage cannot be proven.\n\n`InMemoryHealthTracker` / `DeploymentHealthSnapshot` remain the immediate process-local resilience boundary and are not historical window reconstruction. Runtime recorder wiring, a production/shared sample source and metrics-backend adapters remain pending. Only a subsequent explicit versioned ranking policy may define how operational measurements influence score dimensions.",
)

replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "Latest validated `main` baseline after PR #70:\n\n- commit `7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`;\n- post-merge quality run `34055635049` — PASS;\n- 746 tests passed;\n- 82.28% aggregate coverage;\n- strict mypy and Ruff passed across 177 source files;\n- Bandit reported no issues across 16,550 LOC;",
    "Latest validated `main` baseline after PR #73:\n\n- commit `09adba564cd996f03f8363f44dce7f2b6fd5c303`;\n- post-merge quality run `34060829312` — PASS;\n- 756 tests passed;\n- 82.46% aggregate coverage;\n- strict mypy and Ruff passed across 180 source files;\n- Bandit reported no issues across 16,925 LOC;",
)
replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "Until that changes, further gateway work should be consumer-agnostic and independently justified. The Roadmap measurement audit preserves every currently reviewed deterministic quality dimension, including bounded `pt_br_quality`. PR #70 now also preserves versioned recent operational evidence separately from immediate runtime health and ranking. The next admissible operational step is a metadata-only materializer for bounded runtime windows; online score normalization remains a separate future versioned policy decision. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.",
    "Until that changes, further gateway work should be consumer-agnostic and independently justified. The Roadmap measurement audit preserves every currently reviewed deterministic quality dimension, including bounded `pt_br_quality`. PR #70 preserves versioned recent operational evidence separately from immediate runtime health and ranking, and PR #73 adds bounded deterministic materialization without ranking authority. A future recorder/shared-source increment must preserve metadata-only completeness semantics and must not make evidence collection part of inference availability; online score normalization remains a separate future versioned policy decision. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.",
)

replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "Status: **Schema `1.0` COMPLETE in PR #70; bounded process-local materialization is implemented by the current issue #72 increment. Runtime recorder wiring, production/shared sources and online ranking policy remain pending.**",
    "Status: **COMPLETE through PR #73 for schema `1.0` plus bounded process-local materialization. Runtime recorder wiring, production/shared sources and online ranking policy remain pending.**",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "PR #70 introduced the first bounded step toward Roadmap online-telemetry ranking: a strict, immutable, content-addressed contract for preserving recent operational measurements. Issue #72 adds a deterministic materialization path from explicit metadata-only provider-attempt samples. **Neither increment changes ranking.**",
    "PR #70 introduced the strict, immutable, content-addressed contract for preserving recent operational measurements. PR #73 completes issue #72 by adding a deterministic materialization path from explicit metadata-only provider-attempt samples. **Neither increment changes ranking.**",
)
