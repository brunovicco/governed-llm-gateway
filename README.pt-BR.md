# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

Gateway reutilizável e neutro em relação a provedores de LLM para **resolução e execução governada de modelos**.

Status: **Phases 0–13 concluídas; Phase 14 em andamento — Cases 1/2 concluídos, Case 3 deferido. Matriz inicial de benchmarks 5/5 concluída.**

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
- integração opcional com Verifiable AI Governance;
- proveniência terminal de execução provider-neutral preservada por SSE/API/SDK.

A Phase 14 migra consumidores reais incrementalmente na ordem normativa:

1. `controlled-autonomy-lab` — **COMPLETE**;
2. `getnet-multi-agent-support-v2` — **COMPLETE**;
3. `OpsLens` — **VALIDATED CANDIDATE, DEFERRED** enquanto o repositório evolui de forma independente;
4. `RAGForge` — **NOT STARTED** porque o sequencing guard continua ativo;
5. `Verifiable AI Governance` — **NOT STARTED** como consumer case da Phase 14.

Veja `docs/project/CURRENT_STATE.md` para o checkpoint autoritativo e a issue #18 para o sequencing guard ativo entre OpsLens e RAGForge.

## Matriz de benchmarks — 5/5 concluída

Os cinco primeiros contratos de benchmark definidos no roadmap estão implementados:

| Workload | Contrato revisado atual | Merge |
|---|---|---|
| `structured_extraction` | `structured-extraction-v2` (v1 preservado historicamente) | PRs #19 e #22 |
| `rag_ptbr` | `rag-ptbr-v1` | PR #20 |
| `code_generation` | `code-generation-v1` | PR #21 |
| `tool_use` | `tool-use-v1` | PR #23 |
| `agent_orchestration` | `agent-orchestration-v1` | PR #24 |

As suítes específicas continuam:

- públicas/sintéticas e sem credenciais por padrão;
- determinísticas e reproduzíveis;
- explícitas sobre proveniência de provider/model/API/configuração/data;
- separadas da evidência de disponibilidade de provedores;
- sem LLM-as-judge no CI padrão;
- incapazes de executar business tools, código gerado, agentes ou side effects;
- incapazes de se autopromover ou alterar o roteamento ativo.

O fluxo de evidência permanece:

```text
dataset versionado
  -> BenchmarkRunner
  -> scorer determinístico
  -> Scorecard
  -> snapshot content-addressed
  -> promoção explícita
  -> ranking evidence dentro do conjunto já autorizado
```

Veja `docs/evaluation/BENCHMARK_MATRIX.md` e `docs/project/EVALUATION.md`.

## Structured output e tools

Structured output é capacidade do modelo/API, não convenção de prompt. O enforcement nativo do provedor é seguido por validação local limitada.

A autoridade sobre business tools permanece fora do gateway:

```text
Gateway → normaliza ToolCall
Aplicação / Agente / runtime MCP → autoriza + executa tool → é dono do ToolResult
```

O benchmark `tool_use` avalia apenas a decisão proposta e seus argumentos. Ele nunca executa a tool.

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

Respostas agregadas bem-sucedidas do SDK preservam evidência terminal provider-neutral: provider/model/deployment, identidade do request do gateway, identidade opcional do request do provedor, finish reason, posição de retry/fallback, latência observada da tentativa, token usage normalizado e custo opcional quando realmente conhecido.

Evidência opcional desconhecida permanece ausente em vez de ser sintetizada. Evidência de runtime é apenas descritiva e nunca se torna autorização.

## Estrutura do repositório

```text
apps/gateway-api/           composition root HTTP
packages/gateway-contracts contratos provider-neutral
packages/gateway-core/     fronteira domain/application/adapters
packages/gateway-client/   SDK cliente fino e tipado
config/                    configuração de modelos/ranking/provedores
benchmarks/                datasets, scorers, runner, snapshots e promoção offline
examples/                  exemplos limitados
 tests/                    suítes contract/integration/e2e
 docs/                     fontes duráveis, avaliação e ADRs
```

## Validação

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Baseline validado atual do `main` após o PR #24 (`a8f2003663eb9ac713df6929a8c7b5bc79573e69`):

- **421 testes passaram**;
- **81,32% de cobertura agregada** (threshold 80%);
- mypy passou em **132 arquivos fonte**;
- Ruff lint/format passou em **132 arquivos**;
- Bandit reportou **0 issues** em 12.883 LOC;
- pip-audit reportou **nenhuma vulnerabilidade conhecida**;
- architecture check, secret scan e Phase 0 gate passaram;
- quality run pós-merge no `main` `33968458431` — **PASS**.

O warning conhecido do Starlette TestClient sobre `httpx`/`httpx2` continua não bloqueante.

## Fonte de verdade

Comece por:

- `docs/project/CURRENT_STATE.md` — checkpoint atual;
- `docs/project/ROADMAP.md` e `docs/project/SOURCE_ROADMAP.txt` — ledger de execução e fonte normativa;
- `docs/project/EVALUATION.md` — arquitetura de benchmark/evidência;
- `docs/evaluation/BENCHMARK_MATRIX.md` — matriz inicial de workloads concluída;
- `docs/project/PHASE14_PROVIDER_NEUTRAL_EXECUTION_PROVENANCE.md` — evidência terminal de runtime;
- `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` — fronteira de capacidade/autoridade da Phase 7;
- `docs/project/STREAMING.md` — lifecycle de streaming da Phase 8;
- `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` — fronteira de autorização.
