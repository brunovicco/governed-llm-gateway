from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one marker, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Operational sample batch source-of-truth.
replace_once(
    "docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md",
    "Status: **IN DEVELOPMENT through issue #78.**",
    "Status: **COMPLETE through PR #79 for immutable schema `1.0` source-instance-scoped batch handoff. Shared/fleet ingestion and completeness remain pending.**",
)
replace_once(
    "docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md",
    "Issue #78 defines a durable handoff artifact for that purpose.",
    "PR #79 completed issue #78 by adding the durable handoff artifact, strict JSON loader and batch-backed sample source for that purpose.",
)
replace_once(
    "docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md",
    "## Explicitly not implemented by issue #78",
    "## Explicitly not implemented through PR #79",
)
replace_once(
    "docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md",
    "After a validated batch handoff exists, a later consumer-agnostic increment may define a shared ingestion/source contract or fleet-level completeness model. Remote transport must remain decoupled from inference availability, and any operational-score use still requires a separate explicit versioned ranking policy.",
    "After PR #79, a later consumer-agnostic increment may define shared ingestion plus a fleet/source-membership completeness model over validated source-instance batches. Remote transport must remain decoupled from inference availability, and any operational-score use still requires a separate explicit versioned ranking policy.",
)

# Operational evidence ledger.
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "Status: **COMPLETE through PR #76 for schema `1.0`, bounded process-local materialization and optional best-effort runtime attempt recording in both bounded executors. Production/shared sources and online ranking policy remain pending.**",
    "Status: **COMPLETE through PR #79 for schema `1.0`, bounded process-local materialization, optional best-effort runtime attempt recording and content-addressed source-instance batch handoff. Shared/fleet ingestion-completeness and online ranking policy remain pending.**",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "PR #70 introduced the strict, immutable, content-addressed contract for preserving recent operational measurements. PR #73 completed issue #72 by adding a deterministic materialization path from explicit metadata-only provider-attempt samples. Issue #75 adds an optional process-local recorder boundary for the existing non-streaming and streaming executors. **None of these increments changes ranking or authorization.**",
    "PR #70 introduced the strict, immutable, content-addressed contract for preserving recent operational measurements. PR #73 completed issue #72 by adding a deterministic materialization path from explicit metadata-only provider-attempt samples. PR #76 added the optional process-local recorder boundary for the existing non-streaming and streaming executors. PR #79 adds a content-addressed source-instance batch handoff that can be exported and loaded outside provider execution. **None of these increments changes ranking or authorization.**",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "## Explicitly not implemented by PR #76",
    "## Explicitly not implemented through PR #79",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "- no production/shared operational-evidence source;",
    "- no fleet/shared operational-evidence aggregator or source-membership contract;",
)
replace_once(
    "docs/evaluation/OPERATIONAL_EVIDENCE.md",
    "After PR #76, a later consumer-agnostic increment may define a production/shared metadata-only source or exporter that is decoupled from provider execution and has explicit completeness semantics. Remote delivery must not become a required provider-execution dependency. Only after a complete reviewed evidence-production path exists should a separate versioned policy define how recent operational measurements may influence score dimensions.",
    "After PR #79, the next consumer-agnostic boundary is shared ingestion plus explicit fleet/source-membership completeness over validated source-instance batches. Remote delivery must not become a required provider-execution dependency. Only after a complete reviewed fleet evidence-production path exists should a separate versioned policy define how recent operational measurements may influence score dimensions.",
)

# English README.
replace_once(
    "README.md",
    "Offline quality evidence, immediate runtime health and versioned recent operational evidence with bounded process-local materialization and best-effort runtime recording remain explicit separate boundaries; no online-telemetry ranking policy is active.",
    "Offline quality evidence, immediate runtime health and versioned recent operational evidence with bounded process-local materialization, best-effort runtime recording and content-addressed source-instance batch handoff remain explicit separate boundaries; no fleet-completeness or online-telemetry ranking policy is active.",
)
replace_once(
    "README.md",
    "- strict content-addressed recent operational evidence schema `1.0`, bounded fail-closed process-local materialization and optional best-effort runtime attempt recording, preserved separately from health and not consumed by ranking.",
    "- strict content-addressed recent operational evidence schema `1.0`, bounded fail-closed process-local materialization, optional best-effort runtime attempt recording and source-instance-scoped content-addressed batch handoff, preserved separately from health and not consumed by ranking.",
)
replace_once(
    "README.md",
    "PR #70 adds a strict, immutable, content-addressed schema `1.0` artifact for bounded recent operational windows. PR #73 adds deterministic materialization from explicit timestamped metadata-only provider-attempt samples, and PR #76 adds optional process-local best-effort recording in both bounded runtime executors with conservative completeness invalidation.",
    "PR #70 adds a strict, immutable, content-addressed schema `1.0` artifact for bounded recent operational windows. PR #73 adds deterministic materialization from explicit timestamped metadata-only provider-attempt samples, PR #76 adds optional process-local best-effort recording in both bounded runtime executors with conservative completeness invalidation, and PR #79 adds content-addressed source-instance batch export/load outside provider execution.",
)
replace_once(
    "README.md",
    "A production/shared sample source and metrics-backend query adapters remain pending.",
    "Shared ingestion, fleet/source-membership completeness and production backend adapters remain pending.",
)
replace_once(
    "README.md",
    "See `docs/evaluation/OPERATIONAL_EVIDENCE.md`.",
    "See `docs/evaluation/OPERATIONAL_EVIDENCE.md` and `docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md`.",
)
replace_once(
    "README.md",
    "Current validated `main` baseline after PR #76 (`455c11a24e09adddcfff9fc8c9578d74ec6c6606`):",
    "Current validated `main` baseline after PR #79 (`51a9196f066a7ae4035322ccda7aefb147003b0c`):",
)
replace_once("README.md", "- **767 tests passed**;", "- **782 tests passed**;")
replace_once("README.md", "- **82.47% aggregate coverage** (threshold 80%);", "- **82.52% aggregate coverage** (threshold 80%);")
replace_once("README.md", "- mypy passed across **182 source files**;", "- mypy passed across **186 source files**;")
replace_once("README.md", "- Ruff lint/format passed across **182 files**;", "- Ruff lint/format passed across **186 files**;")
replace_once("README.md", "- Bandit reported **0 issues** across 17,133 LOC;", "- Bandit reported **0 issues** across 17,632 LOC;")
replace_once("README.md", "- post-merge `main` quality run `34062983396` — **PASS**.", "- post-merge `main` quality run `34064435787` — **PASS**.")
replace_once(
    "README.md",
    "- `docs/evaluation/OPERATIONAL_EVIDENCE.md` — versioned recent operational evidence schema and non-authorizing/non-ranking boundary;",
    "- `docs/evaluation/OPERATIONAL_EVIDENCE.md` — versioned recent operational evidence schema and non-authorizing/non-ranking boundary;\n- `docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md` — source-instance-scoped content-addressed sample handoff and fleet-completeness boundary;",
)

# PT-BR README.
replace_once(
    "README.pt-BR.md",
    "Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada com materialização process-local limitada e gravação best-effort de tentativas de runtime permanecem fronteiras explícitas e separadas; nenhuma policy de ranking por telemetria online está ativa.",
    "Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada com materialização process-local limitada, gravação best-effort de tentativas de runtime e handoff content-addressed por instância de origem permanecem fronteiras explícitas e separadas; nenhuma completude de frota ou policy de ranking por telemetria online está ativa.",
)
replace_once(
    "README.pt-BR.md",
    "- schema `1.0` estrito e content-addressed para evidência operacional recente, materialização process-local limitada/fail-closed e gravação opcional best-effort de tentativas de runtime, separados da saúde e não consumidos pelo ranking.",
    "- schema `1.0` estrito e content-addressed para evidência operacional recente, materialização process-local limitada/fail-closed, gravação opcional best-effort de tentativas de runtime e handoff content-addressed limitado por instância de origem, separados da saúde e não consumidos pelo ranking.",
)
replace_once(
    "README.pt-BR.md",
    "O PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. O PR #73 adiciona materialização determinística de samples explícitos, timestamped e metadata-only de tentativas reais do provider, e o PR #76 adiciona gravação opcional best-effort e process-local nos dois executores limitados, com invalidação conservadora de completude.",
    "O PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. O PR #73 adiciona materialização determinística de samples explícitos, timestamped e metadata-only de tentativas reais do provider, o PR #76 adiciona gravação opcional best-effort e process-local nos dois executores limitados, com invalidação conservadora de completude, e o PR #79 adiciona export/load de batches content-addressed por instância de origem fora da execução do provider.",
)
replace_once(
    "README.pt-BR.md",
    "Fonte de samples compartilhada/de produção e adapters de consulta a backend de métricas continuam pendentes.",
    "Ingestão compartilhada, completude de frota/membership de instâncias e adapters de backend de produção continuam pendentes.",
)
replace_once(
    "README.pt-BR.md",
    "Veja `docs/evaluation/OPERATIONAL_EVIDENCE.md`.",
    "Veja `docs/evaluation/OPERATIONAL_EVIDENCE.md` e `docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md`.",
)
replace_once(
    "README.pt-BR.md",
    "Baseline validado atual do `main` após o PR #76 (`455c11a24e09adddcfff9fc8c9578d74ec6c6606`):",
    "Baseline validado atual do `main` após o PR #79 (`51a9196f066a7ae4035322ccda7aefb147003b0c`):",
)
replace_once("README.pt-BR.md", "- **767 testes passaram**;", "- **782 testes passaram**;")
replace_once("README.pt-BR.md", "- **82,47% de cobertura agregada** (threshold 80%);", "- **82,52% de cobertura agregada** (threshold 80%);")
replace_once("README.pt-BR.md", "- mypy passou em **182 arquivos fonte**;", "- mypy passou em **186 arquivos fonte**;")
replace_once("README.pt-BR.md", "- Ruff lint/format passou em **182 arquivos**;", "- Ruff lint/format passou em **186 arquivos**;")
replace_once("README.pt-BR.md", "- Bandit reportou **0 issues** em 17.133 LOC;", "- Bandit reportou **0 issues** em 17.632 LOC;")
replace_once("README.pt-BR.md", "- quality run pós-merge no `main` `34062983396` — **PASS**.", "- quality run pós-merge no `main` `34064435787` — **PASS**.")
replace_once(
    "README.pt-BR.md",
    "- `docs/evaluation/OPERATIONAL_EVIDENCE.md` — schema de evidência operacional recente versionada e fronteira sem autoridade de autorização/ranking;",
    "- `docs/evaluation/OPERATIONAL_EVIDENCE.md` — schema de evidência operacional recente versionada e fronteira sem autoridade de autorização/ranking;\n- `docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md` — handoff content-addressed por instância de origem e fronteira de completude de frota;",
)

# Current state ledger.
replace_once(
    "docs/project/CURRENT_STATE.md",
    "- PR #76 — optional process-local best-effort provider-attempt recording in non-streaming and streaming executors, with separate monotonic/UTC clocks and conservative completeness invalidation for cancellation, unrepresentable post-call failures or recorder failure; no ranking or authorization change.",
    "- PR #76 — optional process-local best-effort provider-attempt recording in non-streaming and streaming executors, with separate monotonic/UTC clocks and conservative completeness invalidation for cancellation, unrepresentable post-call failures or recorder failure; no ranking or authorization change.\n- PR #79 — immutable content-addressed operational sample batch handoff with explicit `source_instance_id`, strict JSON/tamper validation, out-of-band export and batch-backed source coverage; no fleet-completeness, ranking or authorization change.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "Latest validated gateway baseline after PR #76:",
    "Latest validated gateway baseline after PR #79:",
)
replace_once("docs/project/CURRENT_STATE.md", "`455c11a24e09adddcfff9fc8c9578d74ec6c6606`", "`51a9196f066a7ae4035322ccda7aefb147003b0c`")
replace_once("docs/project/CURRENT_STATE.md", "`34062983396` — PASS.", "`34064435787` — PASS.")
replace_once("docs/project/CURRENT_STATE.md", "- 767 tests passed;", "- 782 tests passed;")
replace_once("docs/project/CURRENT_STATE.md", "- aggregate coverage 82.47%;", "- aggregate coverage 82.52%;")
replace_once("docs/project/CURRENT_STATE.md", "- strict mypy passed across 182 source files;", "- strict mypy passed across 186 source files;")
replace_once("docs/project/CURRENT_STATE.md", "- Ruff lint/format passed across 182 files;", "- Ruff lint/format passed across 186 files;")
replace_once("docs/project/CURRENT_STATE.md", "- Bandit reported no issues across 17,133 LOC;", "- Bandit reported no issues across 17,632 LOC;")
replace_once(
    "docs/project/CURRENT_STATE.md",
    "## Recent operational evidence — CONTRACT + MATERIALIZER + LOCAL RECORDER COMPLETE, SHARED SOURCE PENDING",
    "## Recent operational evidence — CONTRACT + MATERIALIZER + LOCAL RECORDER + BATCH HANDOFF COMPLETE, FLEET COMPLETENESS PENDING",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "PR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples, a canonical snapshot factory and a bounded process-local source with fail-closed coverage/eviction semantics. PR #76 adds optional process-local best-effort recording to both bounded executors.",
    "PR #70 establishes schema `1.0` `OperationalEvidenceSnapshot` as immutable recent-window evidence. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples, a canonical snapshot factory and a bounded process-local source with fail-closed coverage/eviction semantics. PR #76 adds optional process-local best-effort recording to both bounded executors. PR #79 adds a content-addressed batch handoff that preserves explicit source-instance/exporter/window provenance and can be loaded as an `OperationalSampleSource` outside provider execution.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "A production/shared sample source, metrics-backend query adapters, online-score normalization and ranking-policy changes remain pending.",
    "Shared ingestion, fleet/source-membership completeness, production backend adapters, online-score normalization and ranking-policy changes remain pending.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-PR #76 operational-evidence runtime-recording baseline.",
    "1. Keep `governed-llm-gateway/main` stable at the validated post-PR #79 operational-evidence source-instance batch-handoff baseline.",
)
replace_once(
    "docs/project/CURRENT_STATE.md",
    "8. A future operational-evidence increment may add a production/shared metadata-only sample source or exporter decoupled from provider execution with explicit completeness semantics; it must not make remote evidence delivery part of inference availability or invent online score normalization/adaptive policy.",
    "8. A future operational-evidence increment may add shared ingestion and an explicit fleet/source-membership completeness model over validated source-instance batches; it must not make remote evidence delivery part of inference availability or invent online score normalization/adaptive policy.",
)

# Evaluation ledger.
replace_once(
    "docs/project/EVALUATION.md",
    "This evidence is descriptive and immutable. It is not an authorization source, does not modify eligibility, is not automatically loaded by ranking and does not create adaptive policy. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples plus a bounded process-local source that fails closed when complete requested-window coverage cannot be proven. PR #76 adds optional process-local best-effort recording in both bounded executors without making evidence collection an inference-availability dependency.",
    "This evidence is descriptive and immutable. It is not an authorization source, does not modify eligibility, is not automatically loaded by ranking and does not create adaptive policy. PR #73 adds deterministic materialization from explicit timestamped metadata-only actual provider-attempt samples plus a bounded process-local source that fails closed when complete requested-window coverage cannot be proven. PR #76 adds optional process-local best-effort recording in both bounded executors without making evidence collection an inference-availability dependency. PR #79 adds immutable content-addressed source-instance batch handoff outside provider execution, with strict load/tamper/coverage checks and no fleet-completeness claim.",
)
replace_once(
    "docs/project/EVALUATION.md",
    "A production/shared sample source and metrics-backend adapters remain pending.",
    "Shared ingestion, fleet/source-membership completeness and production backend adapters remain pending.",
)
replace_once(
    "docs/project/EVALUATION.md",
    "See `docs/evaluation/OPERATIONAL_EVIDENCE.md`.",
    "See `docs/evaluation/OPERATIONAL_EVIDENCE.md` and `docs/evaluation/OPERATIONAL_SAMPLE_BATCH.md`.",
)

# Benchmark/evidence matrix baseline and boundary.
replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "Latest validated `main` baseline after PR #76:",
    "Latest validated `main` baseline after PR #79:",
)
replace_once("docs/evaluation/BENCHMARK_MATRIX.md", "- commit `455c11a24e09adddcfff9fc8c9578d74ec6c6606`;", "- commit `51a9196f066a7ae4035322ccda7aefb147003b0c`;")
replace_once("docs/evaluation/BENCHMARK_MATRIX.md", "- post-merge quality run `34062983396` — PASS;", "- post-merge quality run `34064435787` — PASS;")
replace_once("docs/evaluation/BENCHMARK_MATRIX.md", "- 767 tests passed;", "- 782 tests passed;")
replace_once("docs/evaluation/BENCHMARK_MATRIX.md", "- 82.47% aggregate coverage;", "- 82.52% aggregate coverage;")
replace_once("docs/evaluation/BENCHMARK_MATRIX.md", "- strict mypy passed across 182 source files;", "- strict mypy passed across 186 source files;")
replace_once("docs/evaluation/BENCHMARK_MATRIX.md", "- Ruff lint/format passed across 182 files;", "- Ruff lint/format passed across 186 files;")
replace_once("docs/evaluation/BENCHMARK_MATRIX.md", "- Bandit reported no issues across 17,133 LOC;", "- Bandit reported no issues across 17,632 LOC;")
replace_once(
    "docs/evaluation/BENCHMARK_MATRIX.md",
    "PR #70 preserves versioned recent operational evidence separately from immediate runtime health and ranking, PR #73 adds bounded deterministic materialization, and PR #76 adds optional best-effort local runtime recording with conservative completeness invalidation. A future shared-source/export increment must remain decoupled from provider execution and preserve metadata-only completeness semantics; online score normalization remains a separate future versioned policy decision.",
    "PR #70 preserves versioned recent operational evidence separately from immediate runtime health and ranking, PR #73 adds bounded deterministic materialization, PR #76 adds optional best-effort local runtime recording with conservative completeness invalidation, and PR #79 adds content-addressed source-instance batch handoff outside provider execution. A future shared-ingestion/fleet-completeness increment must operate over validated source-instance batches and remain decoupled from provider execution; online score normalization remains a separate future versioned policy decision.",
)
