from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one marker in {path}, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "README.md",
    "Status: **Phases 0–13 complete; Phase 14 in progress — Cases 1/2 complete, Case 3 deferred. All roadmap-listed benchmark classes are represented by reviewed deterministic contracts. Reviewed quality-component evidence is preserved separately from operational health, including bounded PT-BR locale/terminology quality in `rag-ptbr-v2`; no universal fluency or grammar claim is made.**",
    "Status: **Phases 0–13 complete; Phase 14 in progress — Cases 1/2 complete, Case 3 deferred. All roadmap-listed benchmark classes are represented by reviewed deterministic contracts. Offline quality evidence, immediate runtime health and versioned recent operational evidence remain explicit separate boundaries; no online-telemetry ranking policy is active.**",
)
replace_once(
    "README.md",
    "- reviewed benchmark quality-component evidence preserved in immutable snapshots without implicit promotion or routing authority.\n",
    "- reviewed benchmark quality-component evidence preserved in immutable snapshots without implicit promotion or routing authority;\n- strict content-addressed recent operational evidence schema `1.0`, preserved separately from process-local health and not yet consumed by ranking.\n",
)
replace_once(
    "README.md",
    "Unknown optional evidence remains absent instead of being synthesized. Runtime evidence is descriptive only and never becomes authorization.\n\n## Repository layout",
    "Unknown optional evidence remains absent instead of being synthesized. Runtime evidence is descriptive only and never becomes authorization.\n\n## Recent operational evidence\n\nPR #70 adds a strict, immutable, content-addressed schema `1.0` artifact for bounded recent operational windows. It preserves collector provenance, request/provider-attempt counts, provider errors, rate limits, timeouts, fallback requests and provider latency p50/p95 per `(runtime_workload, deployment_id)`.\n\nThis is separate from `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, which remain immediate process-local resilience and eligibility state. No production materializer or metrics-backend query is implemented yet, and operational evidence does not modify `StaticDeploymentScore`, ranking weights, eligibility or authorization. A later reviewed increment may materialize this evidence from a metadata-only runtime source before any separate versioned online-scoring policy is considered.\n\nSee `docs/evaluation/OPERATIONAL_EVIDENCE.md`.\n\n## Repository layout",
)
replace_once(
    "README.md",
    "Current validated `main` baseline after PR #67 (`a92e7961ae2de6d3ec40aaa0dda3a955b4e92660`):\n\n- **725 tests passed**;\n- **82.16% aggregate coverage** (threshold 80%);\n- mypy passed across **174 source files**;\n- Ruff lint/format passed across **174 files**;\n- Bandit reported **0 issues** across 16,170 LOC;\n- pip-audit reported **no known vulnerabilities**;\n- architecture check, secret scan and Phase 0 gate passed;\n- post-merge `main` quality run `34050920267` — **PASS**.",
    "Current validated `main` baseline after PR #70 (`7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`):\n\n- **746 tests passed**;\n- **82.28% aggregate coverage** (threshold 80%);\n- mypy passed across **177 source files**;\n- Ruff lint/format passed across **177 files**;\n- Bandit reported **0 issues** across 16,550 LOC;\n- pip-audit reported **no known vulnerabilities**;\n- architecture check, secret scan and Phase 0 gate passed;\n- post-merge `main` quality run `34055635049` — **PASS**.",
)
replace_once(
    "README.md",
    "- `docs/evaluation/BENCHMARK_QUALITY_COMPONENTS.md` — reviewed component metrics, snapshot schema 1.2 and bounded `pt_br_quality` evidence;\n",
    "- `docs/evaluation/BENCHMARK_QUALITY_COMPONENTS.md` — reviewed component metrics, snapshot schema 1.2 and bounded `pt_br_quality` evidence;\n- `docs/evaluation/OPERATIONAL_EVIDENCE.md` — versioned recent operational evidence schema and non-authorizing/non-ranking boundary;\n",
)

replace_once(
    "README.pt-BR.md",
    "Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados. Evidência revisada de componentes de qualidade é preservada separadamente da saúde operacional, incluindo qualidade limitada de localidade/terminologia PT-BR em `rag-ptbr-v2`; não há alegação de fluência ou gramática universal.**",
    "Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados. Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada permanecem fronteiras explícitas e separadas; nenhuma policy de ranking por telemetria online está ativa.**",
)
replace_once(
    "README.pt-BR.md",
    "- evidência revisada de componentes de qualidade de benchmark preservada em snapshots imutáveis sem promoção implícita ou autoridade de roteamento.\n",
    "- evidência revisada de componentes de qualidade de benchmark preservada em snapshots imutáveis sem promoção implícita ou autoridade de roteamento;\n- schema `1.0` estrito e content-addressed para evidência operacional recente, separado da saúde process-local e ainda não consumido pelo ranking.\n",
)
replace_once(
    "README.pt-BR.md",
    "Evidência opcional desconhecida permanece ausente em vez de ser sintetizada. Evidência de runtime é apenas descritiva e nunca se torna autorização.\n\n## Estrutura do repositório",
    "Evidência opcional desconhecida permanece ausente em vez de ser sintetizada. Evidência de runtime é apenas descritiva e nunca se torna autorização.\n\n## Evidência operacional recente\n\nO PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. Ele preserva proveniência do collector, contagens de requests/tentativas do provider, erros do provider, rate limits, timeouts, requests com fallback e latência p50/p95 do provider por `(runtime_workload, deployment_id)`.\n\nIsso permanece separado de `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, que continuam como estado imediato e process-local de resiliência/elegibilidade. Ainda não existe materializer de produção nem consulta a backend de métricas, e essa evidência não altera `StaticDeploymentScore`, pesos de ranking, elegibilidade ou autorização. Um incremento revisado posterior pode materializar essa evidência a partir de uma fonte de runtime metadata-only antes de qualquer policy versionada separada de scoring online.\n\nVeja `docs/evaluation/OPERATIONAL_EVIDENCE.md`.\n\n## Estrutura do repositório",
)
replace_once(
    "README.pt-BR.md",
    "Baseline validado atual do `main` após o PR #67 (`a92e7961ae2de6d3ec40aaa0dda3a955b4e92660`):\n\n- **725 testes passaram**;\n- **82,16% de cobertura agregada** (threshold 80%);\n- mypy passou em **174 arquivos fonte**;\n- Ruff lint/format passou em **174 arquivos**;\n- Bandit reportou **0 issues** em 16.170 LOC;\n- pip-audit reportou **nenhuma vulnerabilidade conhecida**;\n- architecture check, secret scan e Phase 0 gate passaram;\n- quality run pós-merge no `main` `34050920267` — **PASS**.",
    "Baseline validado atual do `main` após o PR #70 (`7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`):\n\n- **746 testes passaram**;\n- **82,28% de cobertura agregada** (threshold 80%);\n- mypy passou em **177 arquivos fonte**;\n- Ruff lint/format passou em **177 arquivos**;\n- Bandit reportou **0 issues** em 16.550 LOC;\n- pip-audit reportou **nenhuma vulnerabilidade conhecida**;\n- architecture check, secret scan e Phase 0 gate passaram;\n- quality run pós-merge no `main` `34055635049` — **PASS**.",
)
replace_once(
    "README.pt-BR.md",
    "- `docs/evaluation/BENCHMARK_QUALITY_COMPONENTS.md` — componentes revisados, snapshot schema 1.2 e evidência limitada de `pt_br_quality`;\n",
    "- `docs/evaluation/BENCHMARK_QUALITY_COMPONENTS.md` — componentes revisados, snapshot schema 1.2 e evidência limitada de `pt_br_quality`;\n- `docs/evaluation/OPERATIONAL_EVIDENCE.md` — schema de evidência operacional recente versionada e fronteira sem autoridade de autorização/ranking;\n",
)

replace_once(
    "docs/project/CURRENT_STATE.md",
    "- metadata-only evidence remains the default;\n",
    "- metadata-only evidence remains the default;\n- immediate process-local runtime health and versioned recent operational evidence remain distinct from ranking policy and from each other;\n",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "- PR #67 — `rag-ptbr-v2`, preserving historical v1 while adding separate grounding and bounded reviewer-authored Brazilian Portuguese locale/terminology quality evidence as `pt_br_quality`, with no provider/model forcing or promotion/ranking change.\n",
    "- PR #67 — `rag-ptbr-v2`, preserving historical v1 while adding separate grounding and bounded reviewer-authored Brazilian Portuguese locale/terminology quality evidence as `pt_br_quality`, with no provider/model forcing or promotion/ranking change.\n- PR #70 — strict schema `1.0` recent operational evidence with collector/time-window provenance, content-derived identity and explicit request/error/fallback/latency measurements; no collector, ranking-score normalization or routing-policy change.\n",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "Latest validated gateway baseline after PR #67:\n\n`a92e7961ae2de6d3ec40aaa0dda3a955b4e92660`\n\nPost-merge quality run:\n\n`34050920267` — PASS.\n\nValidation:\n\n- 725 tests passed;\n- aggregate coverage 82.16%;\n- strict mypy passed across 174 source files;\n- Ruff lint/format passed across 174 files;\n- Bandit reported no issues across 16,170 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
    "Latest validated gateway baseline after PR #70:\n\n`7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`\n\nPost-merge quality run:\n\n`34055635049` — PASS.\n\nValidation:\n\n- 746 tests passed;\n- aggregate coverage 82.28%;\n- strict mypy passed across 177 source files;\n- Ruff lint/format passed across 177 files;\n- Bandit reported no issues across 16,550 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "The detailed benchmark ledger is documented in `docs/evaluation/BENCHMARK_MATRIX.md`.\n\n## Phase 14 — Real Project Integrations",
    "The detailed benchmark ledger is documented in `docs/evaluation/BENCHMARK_MATRIX.md`.\n\n## Recent operational evidence — CONTRACT COMPLETE, MATERIALIZER PENDING\n\nPR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. It records collector identity/version, UTC window provenance, content-derived identity and explicit request/provider-attempt/error/rate-limit/timeout/fallback/provider-latency p50/p95 measurements.\n\nThis does not reinterpret `InMemoryHealthTracker` / `DeploymentHealthSnapshot` as historical evidence. Those objects remain immediate process-local resilience/eligibility state. No production materializer, metrics-backend query, shared health store, online-score normalization or ranking-policy change exists yet.\n\nThe next admissible consumer-agnostic step is a metadata-only materializer for a bounded recent runtime window. Only after that evidence-production path is reviewed should a separate explicit versioned policy define how operational measurements could influence score dimensions. Operational evidence cannot authorize or restore an otherwise ineligible candidate.\n\nSee `docs/evaluation/OPERATIONAL_EVIDENCE.md`.\n\n## Phase 14 — Real Project Integrations",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-core benchmark/provenance baseline.",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-PR #70 evidence baseline.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "7. Keep quality-component evidence outside promotion/ranking until a separate explicit versioned contract reviews such use.\n8. A future live gateway-backed benchmark executor must use an already-authorized gateway path, preserve target/effective-execution integrity checks, and remain outside credential-free default CI.\n9. When OpsLens is resumed, reconcile against the then-current gateway commit and rerun the full OpsLens Python and Terraform gates before merge.",
    "7. Keep benchmark quality components and recent operational evidence outside new ranking semantics until separate explicit versioned contracts review such use.\n8. The next operational-evidence increment may materialize schema `1.0` from a bounded metadata-only runtime source; it must not invent online score normalization or adaptive policy.\n9. A future live gateway-backed benchmark executor must use an already-authorized gateway path, preserve target/effective-execution integrity checks, and remain outside credential-free default CI.\n10. When OpsLens is resumed, reconcile against the then-current gateway commit and rerun the full OpsLens Python and Terraform gates before merge.",
)

replace_once(
    "docs/project/EVALUATION.md",
    "Online gateway runtime health and circuit-breaker state remain separate mutable operational evidence.",
    "Online gateway runtime health and circuit-breaker state remain immediate mutable process-local state; PR #70 adds a separate immutable recent operational-evidence snapshot contract rather than reinterpreting that health state as historical evidence.",
)
replace_once(
    "docs/project/EVALUATION.md",
    "## Snapshot reproducibility",
    "## Recent operational evidence boundary\n\nPR #70 introduces schema `1.0` `OperationalEvidenceSnapshot` for bounded recent runtime windows. It preserves collector identity/version, UTC window provenance, a content-derived `evidence_id`, request/provider-attempt counts, provider errors, rate-limit errors, timeouts, fallback requests and provider latency p50/p95 per `(runtime_workload, deployment_id)`.\n\nThis evidence is descriptive and immutable. It is not an authorization source, does not modify eligibility, is not automatically loaded by ranking and does not create adaptive policy. No production materializer or metrics-backend adapter exists yet. A later reviewed materializer may build these snapshots from a metadata-only runtime source; only a subsequent explicit versioned ranking policy may define how operational measurements influence score dimensions.\n\n`InMemoryHealthTracker` / `DeploymentHealthSnapshot` remain the immediate process-local resilience boundary and are not historical window reconstruction.\n\nSee `docs/evaluation/OPERATIONAL_EVIDENCE.md`.\n\n## Snapshot reproducibility",
)

replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "Latest validated `main` baseline after PR #67:\n\n- commit `a92e7961ae2de6d3ec40aaa0dda3a955b4e92660`;\n- post-merge quality run `34050920267` — PASS;\n- 725 tests passed;\n- 82.16% aggregate coverage;\n- strict mypy and Ruff passed across 174 source files;\n- Bandit reported no issues across 16,170 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
    "Latest validated `main` baseline after PR #70:\n\n- commit `7ac70d69f34aea8b0f2a2b6c49f0e7ef89439006`;\n- post-merge quality run `34055635049` — PASS;\n- 746 tests passed;\n- 82.28% aggregate coverage;\n- strict mypy and Ruff passed across 177 source files;\n- Bandit reported no issues across 16,550 LOC;\n- pip-audit reported no known vulnerabilities;\n- architecture check, secret scan and Phase 0 gate passed.",
)
replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "Until that changes, further gateway work should be consumer-agnostic and independently justified. The Roadmap measurement audit now preserves every currently reviewed deterministic quality dimension, including bounded `pt_br_quality`; broader language-quality claims remain intentionally out of scope unless a separate explicit contract is justified. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.",
    "Until that changes, further gateway work should be consumer-agnostic and independently justified. The Roadmap measurement audit preserves every currently reviewed deterministic quality dimension, including bounded `pt_br_quality`. PR #70 now also preserves versioned recent operational evidence separately from immediate runtime health and ranking. The next admissible operational step is a metadata-only materializer for bounded runtime windows; online score normalization remains a separate future versioned policy decision. A future live benchmark executor must use normal gateway authorization and must not introduce a benchmark-only provider/model forcing path.",
)

replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "# Recent Operational Evidence\n",
    "# Recent Operational Evidence\n\nStatus: **CONTRACT COMPLETE — merged in PR #70; materializer and online ranking policy remain pending.**\n",
)
