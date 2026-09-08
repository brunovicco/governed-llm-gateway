# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

[![quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml)
[![console-quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml)
[![observability-compose](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml)

> Um gateway provider-neutral para execução de LLMs que mantém **autorização, seleção de modelos, credenciais de providers, resiliência e evidência de runtime** fora do código das aplicações.

Aplicações e agentes chamam uma única fronteira de execução governada, em vez de espalhar credenciais e lógica específica de OpenAI, Anthropic, Gemini, NVIDIA, Groq ou OpenRouter por cada serviço.

```text
Aplicação / Agente
        │
        │ workload + requisitos + credencial do Gateway
        ▼
Policy Model Router (PDP)
        │ grupos lógicos de modelos autorizados
        ▼
Governed LLM Gateway (PEP)
        ├─ elegibilidade + ranking determinístico
        ├─ health / circuit breaker
        ├─ retry limitado + fallback seguro
        ├─ tradução entre providers
        └─ proveniência + OpenTelemetry
        ▼
Providers de LLM
```

A regra permanente de autoridade é:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

O Gateway pode restringir um conjunto autorizado. Ele nunca pode ampliar uma autorização recebida do upstream.

## O que este projeto demonstra

Para recrutadores, gestores de engenharia e times de plataforma, o repositório funciona como uma implementação prática de uma camada de execução de AI Platform — e não apenas como um proxy multi-provider.

| Área | Capacidade demonstrada |
|---|---|
| **Arquitetura de AI Platform** | Contratos provider-neutral, model registry, composition roots explícitos e SDK consumidor fino |
| **Execução governada** | Separação PDP/PEP, fronteira determinística de autorização e comportamento fail-closed |
| **Roteamento de modelos** | Filtros por capacidade/ambiente, ranking determinístico e explicabilidade da rota |
| **Confiabilidade** | Runtime health, circuit breaker, retry limitado, fallback seguro, streaming e cancelamento |
| **Interoperabilidade LLM** | Adapters nativos para OpenAI Responses, Anthropic Messages, Gemini e providers explicitamente OpenAI-compatible |
| **Model I/O estruturado** | Validação de structured output e contratos normalizados de tool calls sem assumir a execução das ferramentas |
| **Observabilidade** | OpenTelemetry metadata-only, prova real Collector → Tempo e dashboard Grafana provisionado por arquivo |
| **Avaliação** | Benchmarks determinísticos, evidência imutável e fronteiras explícitas de promoção/rollback |
| **Segurança** | Secrets de provider no servidor, fronteiras de autenticação de clientes, secret scanning e ausência de fallback allow-all |
| **Qualidade de engenharia** | Tipagem strict, architecture checks, gates de segurança, testes automatizados e provas de CI com containers reais |

## O que já é possível executar hoje

### 1. Demo local limitada da plataforma — pronta agora

O repositório possui uma demo local determinística, executada por um único comando, em modo **operations-only**. Ela inicia:

- a API read-only de Operations do Gateway;
- o Gateway Console em React/TypeScript;
- OpenTelemetry Collector;
- Tempo;
- Grafana com o dashboard de traces do Gateway já provisionado.

Ela **não exige API key de provider nem credencial do Policy Router**, porque propositalmente não expõe nenhuma rota de inferência. Isso permite demonstrar as superfícies de plataforma, operação e evidência sem criar um caminho falso de autorização allow-all.

### 2. Inferência governada real — foundation implementada, mas ainda sem perfil copy/paste

Os adapters de provider, roteamento governado, retry/fallback e o processo executável do Gateway já existem, mas o baseline versionado no repositório vem propositalmente fail-closed:

- `config/model_registry.yaml` não possui deployments habilitados;
- `config/providers/runtime.json` não possui bindings de providers;
- `config/policy/router.json` vem desabilitado;
- os artefatos de client-auth versionados não possuem principals/secrets reais.

Por isso, **adicionar `OPENAI_API_KEY` ou qualquer outra chave de provider, sozinho, não habilita inferência real**. Um deployment live precisa configurar de forma explícita e coerente o registry, o runtime de provider, a identidade cliente e a fronteira do Policy Router.

Isso é intencional: disponibilidade operacional não pode virar autorização acidentalmente.

## Quick start: demo local

### Pré-requisitos

- Python **3.13+** — o workspace atualmente suporta Python 3.13–3.14;
- [uv](https://docs.astral.sh/uv/);
- Docker com Docker Compose;
- Node.js 24 + npm.

### Executar

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway

cp .env.example .env
```

Edite `.env` e defina um valor aleatório apenas para uso local:

```dotenv
GATEWAY_LOCAL_DEMO_API_KEY=substitua-por-um-valor-local-aleatorio
```

O runtime Python **não carrega `.env` automaticamente**. Exporte o arquivo para o ambiente do processo antes de iniciar:

```bash
set -a
source .env
set +a

uv run --frozen python scripts/local_demo.py
```

Quando a readiness estiver concluída, abra:

| Superfície | URL | Finalidade |
|---|---|---|
| Gateway Console | `http://127.0.0.1:5173` | Visão operacional read-only |
| Gateway readiness | `http://127.0.0.1:8000/readyz` | Readiness do processo |
| Operations API | `http://127.0.0.1:8000/v1/ops/overview` | Estado operacional limitado e autenticado |
| Grafana | `http://127.0.0.1:3000` | Visualização local de traces |

Use `Ctrl+C` para encerrar a demo interativa. O launcher é responsável pelo cleanup dos processos filhos e do projeto Compose dedicado.

Para executar apenas a prova automatizada de startup/readiness/teardown:

```bash
uv run --frozen python scripts/local_demo.py --smoke-test
```

## Onde informar as API keys?

**Nunca coloque API keys reais em `config/model_registry.yaml`, `config/providers/runtime.json`, READMEs, logs, traces ou no Git.**

O projeto usa um modelo de secrets baseado em referências:

```text
config/providers/runtime.json
    credential_reference: "OPENAI_API_KEY"
                         │
                         ▼
ambiente do processo Gateway / secret manager
    OPENAI_API_KEY=<secret real>
                         │
                         ▼
adapter do provider
```

### Credencial da demo local

A demo operations-only exige:

```text
GATEWAY_LOCAL_DEMO_API_KEY
```

Coloque essa variável no seu `.env`, faça `source`/export do arquivo e execute o launcher. O launcher envia essa credencial somente para o processo filho do Gateway operations-only; Docker, npm e Vite recebem ambientes sanitizados sem essa variável.

### API keys dos providers

As credenciais dos providers pertencem ao **deployment do Gateway**, não às aplicações consumidoras. O primeiro resolver server-side implementado lê variáveis de ambiente cujos nomes são referenciados pelo artefato de runtime de providers.

Exemplos comuns aparecem comentados no `.env.example`:

```dotenv
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=
# NVIDIA_API_KEY=
# GROQ_API_KEY=
# OPENROUTER_API_KEY=
```

Elas só passam a ser utilizadas quando um binding revisado em `config/providers/runtime.json` referencia a variável e existe um deployment correspondente no Model Registry.

Para desenvolvimento local, você pode carregar `.env`. Em um deployment real, injete as mesmas referências de ambiente pelo orquestrador ou secret manager utilizado na infraestrutura. A porta de resolução de secrets foi desenhada para permitir substituir o resolver de ambiente por AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault ou outro backend sem mudar os contratos dos consumidores.

### Credenciais dos consumidores

Uma aplicação consumidora deve receber apenas:

```text
GOVERNED_LLM_GATEWAY_URL
GOVERNED_LLM_GATEWAY_API_KEY
```

Ela **não** deve receber API keys de providers. O consumidor também não deve ser responsável pela seleção provider/model nem pela policy de retry/fallback.

Veja [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) e [`docs/project/GATEWAY_CLIENT_AUTHENTICATION.md`](docs/project/GATEWAY_CLIENT_AUTHENTICATION.md) para a fronteira completa de confiança.

## Como funciona a execução governada

Uma requisição não escolhe simplesmente o modelo mais barato ou mais rápido disponível.

1. O consumidor se autentica no Gateway.
2. O Policy Model Router determina quais grupos lógicos de modelos o workload está autorizado a utilizar.
3. O Gateway cruza essa autoridade com capacidades do registry, ambiente, dados/risco e elegibilidade de runtime.
4. O ranking determinístico opera somente dentro do conjunto restante.
5. Retry/fallback pode migrar apenas para outro deployment que já esteja autorizado e elegível.
6. Requests/responses específicos de providers são normalizados por adapters.
7. Proveniência terminal de execução e telemetria metadata-safe descrevem o que aconteceu; elas nunca autorizam uma nova requisição.

Execução de business tools permanece fora do Gateway. O Gateway pode normalizar uma tool call, mas o runtime da aplicação/agente é responsável pela autorização da ferramenta e pelos side effects.

## Fronteiras de arquitetura

```text
                    Autoridade de governança (opcional)
                              │
                              ▼
                      Policy Model Router
                              │ PDP
                              ▼
                     Governed LLM Gateway
                              │ PEP
          ┌───────────────────┼────────────────────┐
          ▼                   ▼                    ▼
   Model providers      a2a-otel-kit         Evidência / evals
          │                   │
          │                   ▼
          │             OTel Collector
          │                   │
          │                   ▼
          │                 Tempo
          │                   │
          │                   ▼
          │                 Grafana
          ▼
 execução normalizada
```

O Gateway propositalmente **não é** um agent framework, RAG framework, executor de tools MCP, plataforma de prompt management nem um produto genérico de API management. Sua responsabilidade é resolução e execução governada de modelos.

## Estado atual

| Track | Estado |
|---|---|
| Plataforma core — Phases 0–13 | **Concluída** |
| Integrações com projetos reais — Phase 14 | **Em andamento**: duas integrações concluídas; OpsLens deliberadamente deferido |
| Demo operacional local — OR-8 | **Concluída** no escopo limitado operations-only |
| Perfil copy/paste de live inference | **Pendente** |
| Hardening mais amplo das superfícies operacionais — OR-9 | **Não iniciado** |
| Screenshots/demo/validação final de product readiness — OR-10 | **Não iniciado** |
| Correlação per-trace no Console | **Deferida até existir uma fonte de correlação explicitamente revisada** |

O checkpoint autoritativo é [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md).

### O que falta para considerar a aplicação finalizada

Para um caminho **live e demonstrável de portfólio/produto**, os principais itens restantes são:

1. adicionar um perfil live-inference de desenvolvimento revisado, com deployment real no Model Registry, binding de provider-runtime e configuração do Policy Router;
2. provar esse perfil com smoke tests live-provider opt-in, mantendo a CI padrão sem credenciais;
3. concluir o hardening restante do OR-9 para as superfícies operacionais;
4. concluir OR-10: documentação final, screenshots/fluxo de demo e validação de product readiness;
5. decidir se correlação per-trace no Console é necessária para a demo final e, se for, implementá-la somente após existir um contrato real de correlação/persistência;
6. adicionar licença e política de releases antes de apresentar o repositório como pacote open source reutilizável.

Para **concluir todo o roadmap**, a Phase 14 também continua sequencialmente bloqueada: OpsLens precisa ser reconciliado antes de iniciar RAGForge e as integrações seguintes.

## Validar o repositório

O quality path padrão é determinístico e não exige credenciais:

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Frontend, observabilidade e provas de integração também ficam isolados em workflows específicos do GitHub Actions. Testes com providers reais permanecem opt-in por design.

## Mapa do repositório

| Caminho | Responsabilidade |
|---|---|
| `apps/gateway-api/` | Composition root FastAPI e processos executáveis do Gateway |
| `apps/gateway-console/` | Console operacional read-only em React/TypeScript |
| `packages/gateway-contracts/` | Contratos públicos provider-neutral |
| `packages/gateway-core/` | Domínio, serviços de aplicação e adapters de provider/runtime |
| `packages/gateway-client/` | SDK consumidor fino e tipado |
| `config/` | Registry e artefatos secret-free de provider, cliente, policy e routing |
| `benchmarks/` | Avaliação determinística e evidência |
| `deploy/observability/` | Provisioning local de Collector, Tempo e Grafana |
| `scripts/` | Ferramentas de quality, evidência e demo local determinística |
| `tests/` | Testes unitários, de contrato, integração e end-to-end |
| `docs/` | Arquitetura, fronteiras de segurança, roadmap e contratos de evidência |

## Leitura recomendada

Se você está avaliando o projeto, comece por:

- [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) — checkpoint atual autoritativo;
- [`docs/project/OPERATIONAL_READINESS.md`](docs/project/OPERATIONAL_READINESS.md) — sequência de readiness/demo operacional;
- [`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) — fronteira de autorização;
- [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) — modelo de providers e secrets;
- [`docs/project/GATEWAY_CONSOLE.md`](docs/project/GATEWAY_CONSOLE.md) — fronteira do Console;
- [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) — prova local real com Grafana/Tempo;
- [`docs/project/EVALUATION.md`](docs/project/EVALUATION.md) — arquitetura de benchmarks/evidência.
