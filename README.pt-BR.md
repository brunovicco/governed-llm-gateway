# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

Gateway reutilizável e neutro em relação a provedores de LLM para **resolução e execução governada de modelos**.

Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados. Evidência offline de qualidade, saúde imediata de runtime e evidência operacional recente versionada com materialização process-local limitada e gravação best-effort de tentativas de runtime permanecem fronteiras explícitas e separadas; nenhuma policy de ranking por telemetria online está ativa.**

O gateway funciona como Policy Enforcement Point (PEP) operacional entre o workload declarado pela aplicação e o deployment concreto de LLM escolhido para execução.

```text
Aplicação / Agente
       │ workload + requisitos + metadados de política
       ▼
Policy Model Router (PDP)
       │ grupo lógico de modelos autorizado + proveniência
       ▼
Governed LLM Gateway (PEP + seletor operacional)
       │ somente candidatos autorizados
       ├─ elegibilidade por capacidade / ambiente
       ├─ ranking determinístico
       ├─ saúde de runtime / circuit breaker
       ├─ retry limitado / fallback seguro
       ├─ structured output / normalização de tool calls
       ├─ streaming / cancelamento
       ├─ evidência de benchmark aprovada
       └─ proveniência de execução provider-neutral
       ▼
Provedor de LLM
       │ output normalizado + evidência metadata-only
       ▼
Aplicação / Agente / runtime MCP
       └─ autoriza e executa business tools / side effects
```

Invariante permanente:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

O gateway pode restringir a autorização por capacidade, política de dados/ambiente, escopo de governança, custo, latência, saúde ou outras restrições operacionais. Ele nunca pode ampliar a autorização do PDP. Ranking, retry/fallback, benchmark, telemetria, estado do SDK e proveniência de runtime não são fontes de autorização.

## Implementação atual

As Phases 0–13 estão concluídas e estabelecem:

- contratos provider-neutral e model registry determinístico;
- integração com Policy Model Router e autorização fail-closed;
- elegibilidade, ranking e `POST /v1/route/explain` determinísticos;
- runtime health, circuit breaker, retry limitado e fallback seguro;
- validação de structured output e normalização provider-neutral de tool calls;
- streaming normalizado, cancelamento e fronteiras de replay seguro;
- OpenTelemetry com defaults metadata-only;
- infraestrutura offline determinística de benchmarks e promoção explícita de evidência;
- evidence-driven ranking com fronteiras de manual override e rollback;
- SDK cliente fino e tipado, sem exigir SDK/API key de provedor nos consumidores;
- integração opcional com Verifiable AI Governance e evidência de runtime;
- proveniência terminal de execução provider-neutral preservada por SSE/API/SDK;
- evidência revisada de componentes de qualidade de benchmark preservada em snapshots imutáveis sem promoção implícita ou autoridade de roteamento;
- schema `1.0` estrito e content-addressed para evidência operacional recente, materialização process-local limitada/fail-closed e gravação opcional best-effort de tentativas de runtime, separados da saúde e não consumidos pelo ranking.

A Phase 14 migra consumidores reais incrementalmente na ordem normativa:

1. `controlled-autonomy-lab` — **COMPLETE**;
2. `getnet-multi-agent-support-v2` — **COMPLETE**;
3. `OpsLens` — **VALIDATED CANDIDATE, DEFERRED** enquanto o repositório evolui de forma independente;
4. `RAGForge` — **NOT STARTED** porque o sequencing guard continua ativo;
5. `Verifiable AI Governance` — **NOT STARTED** como consumer case da Phase 14.

Veja `docs/project/CURRENT_STATE.md` para o checkpoint autoritativo e a issue #18 para o sequencing guard ativo entre OpsLens e RAGForge.

## Programa de benchmarks — classes do roadmap representadas

As classes de workload listadas no roadmap estão representadas por contratos determinísticos revisados e versionados:

| Workload | Contrato revisado atual | Merge |
|---|---|---|
| `classification` | `classification-v1` | PR #45 |
| `structured_extraction` | `structured-extraction-v2` (v1 preservado historicamente) | PRs #19 e #22 |
| `json_schema_compliance` | `json-schema-compliance-v1` | PR #61 |
| `rag_answer` | `rag-answer-v1` | PR #58 |
| `rag_ptbr` | `rag-ptbr-v2` (v1 preservado historicamente) | PRs #20 e #67 |
| `reasoning` | `reasoning-v1` | PR #47 |
| `code_generation` | `code-generation-v1` | PR #21 |
| `code_review` | `code-review-v1` | PR #48 |
| `security_analysis` | `security-analysis-v1` | PR #50 |
| `tool_selection` | `tool-selection-v1` | PR #51 |
| `tool_argument_generation` | `tool-argument-generation-v1` | PR #52 |
| `tool_use` | `tool-use-v1` | PR #23 |
| `multi_step_tool_use` | `multi-step-tool-use-v1` | PR #55 |
| `agent_orchestration` | `agent-orchestration-v1` | PR #24 |
| `multimodal_analysis` | `multimodal-analysis-v1` | PR #32 |
| `long_context` | `long-context-v1` | PR #44 |

Os cinco primeiros workloads do roadmap permanecem como baseline histórico do core; as classes posteriores foram adicionadas como contratos separados em vez de reescrever esse baseline.

As suítes específicas continuam:

- públicas/sintéticas e sem credenciais por padrão;
- determinísticas e reproduzíveis;
- explícitas sobre proveniência de provider/model/API/configuração/data;
- separadas da evidência de disponibilidade de provedores;
- sem LLM-as-judge no CI padrão;
- incapazes de executar business tools, código gerado, agentes ou side effects;
- incapazes de se autopromover ou alterar o roteamento ativo.

Onde os scorers atuais realmente sustentam a medida, o PR #64 estabeleceu evidência offline com componentes preservados e o PR #67 estendeu o vocabulário revisado com qualidade PT-BR limitada:

- `schema_validity`;
- `tool_selection_accuracy`;
- `tool_argument_accuracy`;
- `trajectory_success`;
- `grounding`;
- `pt_br_quality` (conformidade limitada e revisada de localidade/terminologia do português do Brasil).

Falhas de provider continuam sendo evidência de disponibilidade e não se tornam qualidade zero do modelo. Snapshots com componentes usam schema `1.2`; schemas históricos `1.0` e `1.1` permanecem canônicos e inalterados.

O PR #67 adiciona `rag-ptbr-v2`, que preserva `grounding` separadamente de um componente limitado `pt_br_quality`, baseado apenas em regras revisadas de localidade/terminologia do português do Brasil. O histórico `rag-ptbr-v1` permanece inalterado e sem componente de qualidade linguística. Isso não reivindica fluência arbitrária, correção gramatical completa, equivalência semântica irrestrita, estilo/tom ou adequação cultural.

O fluxo de evidência permanece:

```text
dataset / fixture versionado
  -> BenchmarkRunner
  -> scorer determinístico
  -> observation + Scorecard
  -> snapshot content-addressed
  -> promoção explícita
  -> ranking evidence dentro do conjunto já autorizado
```

Veja `docs/evaluation/BENCHMARK_MATRIX.md`, `docs/evaluation/BENCHMARK_QUALITY_COMPONENTS.md` e `docs/project/EVALUATION.md`.

## Structured output e tools

Structured output é capacidade do modelo/API, não convenção de prompt. O enforcement nativo do provedor é seguido por validação local limitada.

A autoridade sobre business tools permanece fora do gateway:

```text
Gateway → normaliza ToolCall
Aplicação / Agente / runtime MCP → autoriza + executa tool → é dono do ToolResult
```

Os benchmarks de tools avaliam somente seleções/argumentos/trajetórias propostas e revisadas. Eles nunca executam a tool.

## Fronteira de agent orchestration

O benchmark `agent_orchestration` avalia somente uma trajetória observável proposta (`agent`, `action`, `handoff_to`). Ele não inspeciona chain-of-thought e não executa agentes, tools, operações de negócio ou handoffs humanos.

Orquestração específica de frameworks continua sendo responsabilidade do consumer/runtime. Frameworks são adapters, não donos das regras de política ou autorização do gateway.

## Retry e fallback seguros

Retry e fallback permanecem limitados à sequência autorizada, elegível e ranqueada:

- retry usa o mesmo deployment concreto;
- fallback só pode avançar para alternativa já autorizada;
- falhas permanentes de validação/autenticação/autorização/configuração não fazem fallback automático;
- circuit-open/unhealthy apenas restringe elegibilidade;
- output semântico visível, side effects ou estado opaco de continuação encerram replay automático.

## Evidência de runtime

Respostas agregadas bem-sucedidas do SDK preservam evidência terminal provider-neutral: provider/model/deployment, identidade do request do gateway, identidade opcional do request do provedor, finish reason, posição de retry/fallback, latência observada da tentativa, token usage normalizado e custo opcional quando realmente conhecido. Proveniência revisada posterior também carrega `api_family` selecionado e `max_output_tokens` concreto e positivo quando a execução terminal consegue atestá-los.

Evidência opcional desconhecida permanece ausente em vez de ser sintetizada. Evidência de runtime é apenas descritiva e nunca se torna autorização.

## Evidência operacional recente

O PR #70 adiciona um artefato schema `1.0` estrito, imutável e content-addressed para janelas operacionais recentes limitadas. O PR #73 adiciona materialização determinística de samples explícitos, timestamped e metadata-only de tentativas reais do provider, e o PR #76 adiciona gravação opcional best-effort e process-local nos dois executores limitados, com invalidação conservadora de completude.

Isso permanece separado de `InMemoryHealthTracker` / `DeploymentHealthSnapshot`, que continuam como estado imediato e process-local de resiliência/elegibilidade. Falha do recorder, cancelamento do caller ou uma falha pós-call não representável não podem fabricar provider-error evidence nem se tornar dependência de disponibilidade da inferência. Fonte de samples compartilhada/de produção e adapters de consulta a backend de métricas continuam pendentes. Essa evidência não altera `StaticDeploymentScore`, pesos de ranking, elegibilidade ou autorização; qualquer scoring online futuro ainda exige uma policy versionada explícita e separada.

Veja `docs/evaluation/OPERATIONAL_EVIDENCE.md`.

## Estrutura do repositório

```text
apps/gateway-api/           composition root HTTP
packages/gateway-contracts contratos provider-neutral
packages/gateway-core/     fronteira domain/application/adapters
packages/gateway-client/   SDK cliente fino e tipado
config/                    configuração de modelos/ranking/provedores
benchmarks/                datasets, scorers, runner, snapshots e promoção offline
examples/                  exemplos limitados
tests/                     suítes contract/integration/e2e
docs/                      fontes duráveis, avaliação e ADRs
```

## Validação

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Baseline validado atual do `main` após o PR #76 (`455c11a24e09adddcfff9fc8c9578d74ec6c6606`):

- **767 testes passaram**;
- **82,47% de cobertura agregada** (threshold 80%);
- mypy passou em **182 arquivos fonte**;
- Ruff lint/format passou em **182 arquivos**;
- Bandit reportou **0 issues** em 17.133 LOC;
- pip-audit reportou **nenhuma vulnerabilidade conhecida**;
- architecture check, secret scan e Phase 0 gate passaram;
- quality run pós-merge no `main` `34062983396` — **PASS**.

O warning conhecido do Starlette TestClient sobre `httpx`/`httpx2` continua não bloqueante.

## Fonte de verdade

Comece por:

- `docs/project/CURRENT_STATE.md` — checkpoint atual;
- `docs/project/ROADMAP.md` e `docs/project/SOURCE_ROADMAP.txt` — ledger de execução e fonte normativa;
- `docs/project/EVALUATION.md` — arquitetura de benchmark/evidência;
- `docs/evaluation/BENCHMARK_MATRIX.md` — matriz completa de workloads do roadmap e fronteira de evidência;
- `docs/evaluation/BENCHMARK_QUALITY_COMPONENTS.md` — componentes revisados, snapshot schema 1.2 e evidência limitada de `pt_br_quality`;
- `docs/evaluation/OPERATIONAL_EVIDENCE.md` — schema de evidência operacional recente versionada e fronteira sem autoridade de autorização/ranking;
- `docs/project/PHASE14_PROVIDER_NEUTRAL_EXECUTION_PROVENANCE.md` — evidência terminal de runtime;
- `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` — fronteira de capacidade/autoridade da Phase 7;
- `docs/project/STREAMING.md` — lifecycle de streaming da Phase 8;
- `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` — fronteira de autorização.
