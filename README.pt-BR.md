# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

**Um gateway provider-neutral para execução governada de LLMs em plataformas de IA.**

Ele centraliza autorização de modelos, seleção, resiliência, adaptação entre provedores e evidência de runtime para que aplicações e agentes não precisem ser responsáveis por credenciais de provider, escolha de modelo, retry/fallback ou policy de roteamento.

## Por que este projeto existe

A execução de LLMs fica mais difícil de governar à medida que aplicações passam a usar mais modelos, provedores e workflows com agentes. Este projeto separa **lógica de negócio/aplicação** de **política de execução de modelos** e mantém autorização antes da otimização.

O gateway foi desenhado para oferecer uma fronteira reutilizável para:

- execução provider-neutral de modelos;
- roteamento determinístico e explicável;
- policy enforcement e autorização fail-closed;
- resiliência de runtime e fallback seguro;
- structured output, normalização de tool calls e streaming;
- observabilidade, proveniência e evidência auditável;
- avaliação de modelos baseada em benchmarks sem mutação automática de policy.

## Capacidades principais

| Área | O que o gateway oferece |
|---|---|
| **Governança** | Separação PDP/PEP, autorização fail-closed e integração opcional com governança |
| **Roteamento** | Model registry determinístico, filtros de elegibilidade, ranking e explicabilidade da rota |
| **Resiliência** | Runtime health, circuit breaker, retry limitado e fallback seguro |
| **Abstração de provider** | Contratos provider-neutral, tradução de requests e resultados normalizados |
| **Model I/O** | Validação de structured output, normalização de tool calls, streaming e cancelamento |
| **Observabilidade** | OpenTelemetry, defaults metadata-only e proveniência terminal de execução |
| **Avaliação** | Framework determinístico de benchmarks, evidência imutável, promoção explícita e rollback |
| **Integração com consumidores** | SDK fino e tipado sem exigir SDKs ou API keys de provider nos consumidores |

## Arquitetura

```text
Aplicação / Agente
       │ workload + requisitos + metadados de policy
       ▼
Policy Model Router (PDP)
       │ grupos lógicos de modelos autorizados
       ▼
Governed LLM Gateway (PEP)
       ├─ elegibilidade
       ├─ ranking determinístico
       ├─ health / circuit breaker
       ├─ retry / fallback seguro
       ├─ tradução de provider
       └─ proveniência / telemetria
       ▼
Provedor de LLM
```

Execução de business tools e side effects permanece fora do gateway. O gateway pode normalizar uma tool call, mas o runtime da aplicação/agente é responsável por autorizar e executar a ferramenta.

### Invariante permanente de autorização

```text
Gateway allowed set ⊆ Policy Router authorized set
```

O gateway pode restringir o conjunto autorizado por capacidade, ambiente, governança, custo, latência ou saúde de runtime. Ele nunca pode ampliar a autorização upstream. Ranking, telemetria, benchmark evidence e proveniência de runtime não são fontes de autorização.

## Princípios de design

- **Autorização antes da otimização.** O ranking opera somente dentro do conjunto já autorizado e elegível.
- **Fail-closed diante de ambiguidade.** Estado inválido de policy, proveniência, capacidade ou evidência não degrada silenciosamente para comportamento permissivo.
- **Evidência é descritiva, não autoridade.** Evidência de runtime ou benchmark não pode se autoautorizar nem reescrever a policy ativa.
- **Falha de provider não é falha de qualidade do modelo.** Evidência de disponibilidade e qualidade permanece separada.
- **Side effects permanecem fora do gateway.** Tools e ações da aplicação continuam sob responsabilidade do runtime consumidor.

## Estado atual

- **Plataforma core:** Phases 0–13 concluídas.
- **Migração de projetos reais:** Phase 14 em andamento; `controlled-autonomy-lab` e `getnet-multi-agent-support-v2` estão concluídos, enquanto OpsLens permanece deliberadamente deferido.
- **Avaliação:** todas as classes de benchmark listadas no roadmap estão representadas por contratos determinísticos revisados.
- **Evidência operacional:** materialização limitada, gravação best-effort em runtime e handoff content-addressed por instância de origem estão implementados; completude compartilhada/de frota e policy de scoring operacional online não estão ativas.
- **Evidência local de observabilidade:** receipt do Collector, queryability no Tempo e um dashboard de traces Grafana read-only provisionado por arquivo possuem provas de CI sem credenciais; isso não é uma afirmação de observabilidade pronta para produção.

Para o checkpoint autoritativo do projeto e o sequenciamento da Phase 14, veja [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md).

## Baseline de qualidade

O quality gate da branch atual do PC-27 valida:

- **1107 testes passando** e 2 skipped;
- **83,70% de cobertura agregada**;
- verificações strict de **mypy** e **Ruff**;
- **Bandit: 0 findings** em 22.842 LOC;
- **pip-audit: nenhuma vulnerabilidade conhecida**;
- architecture check, secret scan e Phase 0 gate passando.

Esses resultados de branch só se tornam baseline de `main` depois que o head revisado do PC-27 for mergeado e os gates pós-merge obrigatórios passarem.

## Validar localmente

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

O caminho padrão de qualidade é determinístico e não exige credenciais.

## Visualização local de traces

A stack de observabilidade versionada no repositório fornece um dashboard Grafana read-only apoiado pelo datasource Tempo local provisionado:

```bash
docker compose -f compose.observability.yml up -d tempo grafana
```

Abra `http://127.0.0.1:3000`. O demo local vincula o Grafana ao loopback, mantém o Tempo sem exposição de host no Compose base reutilizável e não exige credencial do Grafana, provider ou Policy Router. A configuração de acesso anônimo como `Viewer` é apenas para o demo local e não representa uma arquitetura de autenticação para produção.

O dashboard usa a query TraceQL estável `{ span:name = "llm.gateway.request" }` e exibe resultados reais do Tempo, sem fabricar traces ou métricas. Veja [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) para provisioning, prova de CI, fronteira de rede e non-claims exatos.

## Mapa do repositório

| Caminho | Responsabilidade |
|---|---|
| `apps/gateway-api/` | Composition root HTTP |
| `packages/gateway-contracts/` | Contratos públicos provider-neutral |
| `packages/gateway-core/` | Domínio, serviços de aplicação e adapters |
| `packages/gateway-client/` | SDK cliente fino e tipado |
| `benchmarks/` | Avaliação determinística, evidência e promoção |
| `config/` | Configuração de modelos, ranking e providers |
| `tests/` | Validação contract, integration e end-to-end |
| `docs/` | Arquitetura, roadmap, avaliação e estado do projeto |

## Aprofundamento

- [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) — checkpoint autoritativo do projeto
- [`docs/project/ROADMAP.md`](docs/project/ROADMAP.md) — roadmap de implementação e ledger de fases
- [`docs/project/EVALUATION.md`](docs/project/EVALUATION.md) — arquitetura de benchmark e evidência
- [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) — prova local read-only de traces com Grafana/Tempo
- [`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) — fronteira de autorização
- [`docs/evaluation/OPERATIONAL_EVIDENCE.md`](docs/evaluation/OPERATIONAL_EVIDENCE.md) — modelo de evidência operacional recente
- [`docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`](docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md) — fronteira de structured output e autoridade de tools
