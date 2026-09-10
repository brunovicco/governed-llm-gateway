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

## Uma requisição governada real

A aplicação chamadora declarou apenas `workload`, `risk_level` e `data_classification`. O Policy Model Router autorizou o grupo de modelos `balanced`, o ranking determinístico do Gateway selecionou o deployment dentro dele, e a chamada ao provider, o orçamento de retry/fallback e a emissão do trace permaneceram inteiramente server-side.

![Gateway Console após uma requisição governada real: grupo autorizado "balanced" sob a policy 1.0.0, provider selecionado nvidia, modelo nvidia/nemotron-3-super-120b-a12b, deployment nvidia-nemotron-3-super-dev na tentativa 1 com fallback 0, 1644 ms e 149 tokens normalizados, além de routing decision, policy decision, registry digest, ranking policy, score snapshot, fallback sequence e trace ID](docs/assets/screenshots/console-trace-evidence.png)

Execução local real do perfil [`personal-default`](config/profiles/personal-default/README.md) com credenciais de provider fornecidas pelo operador — não é mockup nem stub. Cada campo é evidência terminal de execução: IDs de decisão de routing e de policy, digests de registry e de ranking, o score snapshot que ranqueou os candidatos, a sequência de fallback efetivamente percorrida e o trace ID emitido pelo Gateway. O próprio link *View this request's trace in Grafana* do Console resolve exatamente para esse trace — o waterfall correspondente no Grafana está em [`docs/project/GATEWAY_CONSOLE.md`](docs/project/GATEWAY_CONSOLE.md). O que esta execução **não** afirma está em [Non-claims](#non-claims).

## O que este projeto demonstra

O repositório funciona como uma implementação prática de uma camada de execução de AI Platform — e não apenas como um proxy multi-provider.

| Área | Capacidade demonstrada |
| --- | --- |
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

Uma autoridade de governança opcional só pode restringir o que o Policy Model Router (PDP) autoriza; o Gateway (PEP) executa apenas dentro desse conjunto já restringido, normaliza a chamada ao provider, e emite em paralelo telemetria metadata-only (OTel Collector → Tempo → Grafana) e evidência de avaliação junto com a requisição real ao provider. Veja [`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) para o contrato exato de wire.

O Gateway propositalmente **não é** um agent framework, RAG framework, executor de tools MCP, plataforma de prompt management nem um produto genérico de API management. Sua responsabilidade é resolução e execução governada de modelos.

### O modelo de secrets

**Nunca coloque API keys reais em arquivos do Model Registry, JSON de provider runtime, READMEs, logs, traces ou no Git.** As credenciais de provider pertencem ao **deployment do Gateway**, nunca às aplicações consumidoras: um binding de provider-runtime referencia uma credencial pelo nome, e um resolver de secrets no servidor transforma essa referência no valor real só dentro do processo do Gateway — um `.env` carregado via `source` localmente, ou as mesmas referências de ambiente injetadas por um secret manager real (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault, ...) em um deployment real.

Uma aplicação consumidora recebe apenas duas variáveis, nunca uma chave de provider, e não é responsável pela seleção provider/model nem pela policy de retry/fallback: `GOVERNED_LLM_GATEWAY_URL` e `GOVERNED_LLM_GATEWAY_API_KEY`. Veja [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) e [`docs/project/GATEWAY_CLIENT_AUTHENTICATION.md`](docs/project/GATEWAY_CLIENT_AUTHENTICATION.md) para a fronteira completa de confiança.

## O que já é possível executar hoje

### 1. Demo local limitada da plataforma — pronta agora

O repositório possui uma demo local determinística, executada por um único comando, em modo **operations-only**. Ela inicia:

- a API read-only de Operations do Gateway;
- o Gateway Console em React/TypeScript;
- OpenTelemetry Collector;
- Tempo;
- Grafana com o dashboard de traces do Gateway já provisionado.

Ela **não exige API key de provider nem credencial do Policy Router**, porque propositalmente não expõe nenhuma rota de inferência. Isso permite demonstrar as superfícies de plataforma, operação e evidência sem criar um caminho falso de autorização allow-all.

Screenshots reais dessa mesma demo, capturadas contra uma execução local de verdade (não são mockups):

| Console — antes de conectar | Console — conectado, baseline operations-only (sem rota de inferência) |
| --- | --- |
| ![Gateway Console, desconectado](docs/assets/screenshots/gateway-console-disconnected.png) | ![Gateway Console, conectado, mostrando o baseline real do operations-only: registry phase2-empty, 0 deployments, 0 processos rastreados](docs/assets/screenshots/gateway-console-connected.png) |

A view conectada é o baseline fail-closed real, não encenado — registry `phase2-empty`, `0 deployments` (veja [Non-claims](#non-claims)).

![Dashboard local de traces no Grafana, provisionado por esta demo](docs/assets/screenshots/grafana-trace-dashboard.png)

O dashboard real e consultável do Grafana/Tempo local aparece sem linhas aqui porque esse modo de demo não expõe nenhuma rota de inferência para gerar um trace — veja [`live-development`](config/profiles/live-development/README.md) ou [`personal-default`](config/profiles/personal-default/README.md) para uma requisição que produz um trace de verdade.

### 2. Inferência governada real — perfil explícito de desenvolvimento

O baseline padrão versionado no repositório continua propositalmente fail-closed:

- `config/model_registry.yaml` não possui deployments habilitados;
- `config/providers/runtime.json` não possui bindings de providers;
- `config/policy/router.json` vem desabilitado;
- os artefatos padrão de client-auth não possuem principals/secrets reais.

Por isso, **adicionar `OPENAI_API_KEY` ou qualquer outra chave de provider, sozinho, continua sem habilitar inferência real**.

Para um caminho explícito de opt-in, `config/profiles/live-development/` fornece um perfil secret-free revisado para um consumidor limitado a `development` / `public` / `rag.answer`, com fronteira externa do Policy Model Router, ranking determinístico e dois deployments nativos no mesmo grupo autorizado `balanced`. Veja [o README dele](config/profiles/live-development/README.md) para o fluxo de startup/requisição — é uma configuração de desenvolvimento/demo, não uma promessa de TLS/IAM/SLA de produção, e a CI obrigatória continua credential-free.

Essa separação é intencional: disponibilidade operacional não pode virar autorização acidentalmente.

### 3. Seu próprio projeto — o perfil personal-default

`config/profiles/personal-default/` é o perfil para chamar o Gateway a partir das suas próprias aplicações, não uma demo revisada. Ele conecta seis providers (NVIDIA, Gemini, OpenAI, Anthropic, Groq, OpenRouter) no mesmo grupo autorizado, com NVIDIA como padrão prático de custo; ranking determinístico com fallback limitado escolhe qualquer deployment autorizado que esteja elegível. Sua aplicação só declara `workload`, `risk_level` e `data_classification`. Veja ["Quick start: chamar o Gateway a partir do seu próprio projeto"](#quick-start-chamar-o-gateway-a-partir-do-seu-próprio-projeto) abaixo e [o README dele](config/profiles/personal-default/README.md) para o escopo completo e status de prova por provider.

## Estado atual

| Track | Estado |
| --- | --- |
| Plataforma core — Phases 0–13 | **Concluída** |
| Integrações com projetos reais — Phase 14 | **Em andamento**: duas integrações concluídas; OpsLens deliberadamente deferido |
| Demo operacional local — OR-8 | **Concluída** no escopo limitado operations-only |
| Perfil de live-inference para desenvolvimento | **Implementado no PC-33**, estendido para seis providers; todo deployment provado individualmente com credenciais reais (Gemini, OpenAI, Groq, NVIDIA, OpenRouter, Anthropic) — ver `docs/project/CHECKPOINT_LOG.md` |
| Perfil personal-default (seus próprios projetos) | **Implementado**; ranking com preferência de custo do NVIDIA provado concorrendo com quatro outros providers simultaneamente habilitados — ver `config/profiles/personal-default/README.md` |
| Hardening mais amplo das superfícies operacionais — OR-9 | **Hardening mínimo apropriado concluído** através dos incrementos limitados PC-34..PC-51 mais uma investigação dedicada de lacunas (ver `docs/project/CURRENT_STATE.md`); IAM/TLS/SSO de produção, gestão de sessão, rate limiting e CSRF continuam como trabalho futuro explícito, não uma lacuna silenciosa |
| Screenshots/demo/validação final de product readiness — OR-10 | **Concluída**: validação e2e reproduzível, revisão de segurança do código novo da sessão e da superfície HTTP/adapters já existente (sem findings em nenhuma das duas), a seção consolidada de [non-claims](#non-claims), e screenshots reais do Console/Grafana da demo operations-only — ver `docs/project/CURRENT_STATE.md` |
| Correlação per-trace no Console | **Implementada no PC-52**; provada ao vivo contra um trace real capturado, no navegador, não só via SDK — ver `docs/project/CURRENT_STATE.md` |

O checkpoint autoritativo é [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md). A lista de
pendências que ainda estava aberta no corte da `v1.0.0` (prova opt-in com provider real, a decisão de
navegação per-trace no Console, o hardening mínimo da OR-9, a validação da OR-10) está totalmente
fechada — veja [`CHANGELOG.md`](CHANGELOG.md#unreleased) para o que cada item fechou e em qual PR, e
`docs/project/CHECKPOINT_LOG.md` para a evidência datada por trás disso. Isso fecha a lista que estava
aberta no corte da v1.0.0, não o roadmap como um todo — o escopo exclusivo de produção da OR-9
(TLS/IAM/SSO, gestão de sessão, rate limiting, CSRF) e os casos restantes da Phase 14 continuam abertos
por design; veja [Non-claims](#non-claims). Concluir todo o roadmap também continua sequencialmente
bloqueado: OpsLens precisa ser reconciliado antes de iniciar RAGForge e as integrações seguintes, a menos
que essa ordem normativa seja revisada explicitamente.

## Non-claims

Non-claims pontuais já existem perto da feature específica que limitam (o README de cada perfil, as linhas de OR-9/OR-10 acima). Esta seção é o lugar único para ler todas de uma vez.

Este repositório **não** afirma ser:

- **Infraestrutura de produção.** Sem terminação TLS, sem IAM/OAuth/OIDC/workload identity de produção, sem gestão de sessão de browser, sem rate limiting, sem política de CSRF. O hardening limitado PC-34–PC-51 da OR-9 estreita lacunas específicas nas superfícies que este repositório realmente expõe (respostas não-armazenáveis, sanitização de headers, corpos limitados); não completa nada do acima.
- **Um SLA ou garantia de uptime de qualquer provider de modelo terceiro.** As entradas de pricing/catálogo de modelo são metadados fixados, revisados em datas específicas (ver o README de cada perfil), e podem se distanciar do catálogo real do provider; o pricing de NVIDIA/Groq/OpenRouter no `personal-default` é um placeholder aproximado pendente de atualização revisada separadamente.
- **Um benchmark de tráfego real de produção.** Tudo em `benchmarks/` roda contra fixtures públicas/sintéticas com scoring determinístico, credential-free por padrão. É evidência para elegibilidade de ranking dentro de um conjunto já autorizado, nunca autorização, e nunca um substituto para feedback real de usuários.
- **Um deployment multi-tenant ou remoto.** Todo caminho demonstrado (`scripts/local_demo.py`, `live-development`, `personal-default`) roda como processos loopback locais (`127.0.0.1`) que um operador inicia e encerra. Nada disso foi exercitado atrás de um reverse proxy real, load balancer ou DNS público.
- **Um rollout completo da Phase 14.** Duas das cinco integrações de consumidor planejadas estão completas; o OpsLens é um candidato validado mas deliberadamente adiado até seu próprio repositório estabilizar; RAGForge e a integração com Verifiable AI Governance nem começaram, por decisão explícita de sequenciamento, não por omissão.
- **Uma OR-9 finalizada.** A OR-9 é hardening limitado para as superfícies operacionais que este repositório já expõe, não uma certificação de segurança de produção. A OR-10 (validação end-to-end reproduzível, duas passadas de revisão de segurança, e screenshots reais da demo) está completa; IAM/TLS/SSO de produção, gestão de sessão, rate limiting e CSRF da OR-9 continuam como trabalho futuro separado.

O que cada prova de inferência governada citada em `docs/project/CHECKPOINT_LOG.md` **é**: uma requisição real, com credenciais reais de provider fornecidas pelo operador, executada através da cadeia completa Policy Router → Gateway → provider, com a evidência terminal de rota/execução inspecionada — não é mock, não é stub, e não é simulação sem credenciais.

## Quick start: demo local operations-only

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
| --- | --- | --- |
| Gateway Console | `http://127.0.0.1:5173` | Visão operacional read-only |
| Gateway readiness | `http://127.0.0.1:8000/readyz` | Readiness do processo |
| Operations API | `http://127.0.0.1:8000/v1/ops/overview` | Estado operacional limitado e autenticado |
| Grafana | `http://127.0.0.1:3000` | Visualização local de traces |

Use `Ctrl+C` para encerrar a demo interativa. O launcher é responsável pelo cleanup dos processos filhos e do projeto Compose dedicado.

Para executar apenas a prova automatizada de startup/readiness/teardown:

```bash
uv run --frozen python scripts/local_demo.py --smoke-test
```

Para execução governada com providers, use o runbook separado do [`live-development` profile](config/profiles/live-development/README.md); ele exige deliberadamente um PDP externo e credenciais server-side dos providers.

## Quick start: chamar o Gateway a partir do seu próprio projeto

Esse é o caminho "sem fricção" de verdade: sua aplicação nunca escolhe provider nem modelo, só um
`workload`. Ele exige dois processos rodando — o Policy Model Router (um repositório separado) e o
Gateway — mais o seu projeto consumidor apontado para a URL e a credencial do Gateway.

### 1. Instalar os dois serviços

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway
uv sync --frozen

git clone https://github.com/brunovicco/policy-model-router.git ../policy-model-router
cd ../policy-model-router
uv sync --frozen
cd ../governed-llm-gateway
```

### 2. Configurar

```bash
cp .env.example .env
```

Edite o `.env`:

```dotenv
GATEWAY_DEMO_API_KEY=substitua-por-um-valor-local-aleatorio
POLICY_ROUTER_DEMO_API_KEY=substitua-por-um-valor-local-aleatorio
NVIDIA_API_KEY=sua-chave-nvidia-real
GEMINI_API_KEY=sua-chave-gemini-real
OPENAI_API_KEY=sua-chave-openai-real
ANTHROPIC_API_KEY=sua-chave-anthropic-real
GROQ_API_KEY=sua-chave-groq-real
OPENROUTER_API_KEY=sua-chave-openrouter-real
```

`GATEWAY_DEMO_API_KEY`/`POLICY_ROUTER_DEMO_API_KEY` são segredos locais que você inventa; as seis
chaves de provider são credenciais reais (o NVIDIA tem tier gratuito em
[build.nvidia.com](https://build.nvidia.com)). Uma chave faltando para um deployment **habilitado**
derruba o processo inteiro fechado no boot — se não tiver as seis, desabilite o(s) deployment(s)
correspondente(s) em `model_registry.yaml` (`enabled: false`) e remova o binding do
`provider_runtime.json` primeiro.

### 3. Iniciar o Policy Router e o Gateway

```bash
cd governed-llm-gateway
set -a; source .env; set +a
uv run --frozen python scripts/personal_default_launcher.py
```

Esse comando único sobe os dois serviços (assume `../policy-model-router` do passo 1; sobrescreva com
`POLICY_MODEL_ROUTER_ROOT`) e derruba os dois com Ctrl+C. Veja
[o README dele](config/profiles/personal-default/README.md#running-it) para o equivalente manual com
dois terminais e a flag `--smoke-test`.

### 4. Chamar a partir do seu próprio projeto

Adicione o SDK fino (não publicado no PyPI; instale direto deste repositório):

```bash
uv add "governed-llm-gateway-client @ git+https://github.com/brunovicco/governed-llm-gateway.git#subdirectory=packages/gateway-client"
```

Seu projeto consumidor precisa só de duas variáveis de ambiente — nunca de uma chave de provider:

```dotenv
GOVERNED_LLM_GATEWAY_URL=http://127.0.0.1:8000
GOVERNED_LLM_GATEWAY_API_KEY=<o mesmo GATEWAY_DEMO_API_KEY do passo 2>
```

```python
import asyncio

from governed_llm_gateway_client import GatewayClient
from governed_llm_gateway_contracts import DataClassification, Message, MessageRole, RiskLevel


async def main() -> None:
    async with GatewayClient.from_env() as gateway:
        response = await gateway.generate(
            workload="rag.answer",
            messages=(
                Message(role=MessageRole.USER, content="Explique roteamento determinístico em uma frase."),
            ),
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            context_tokens_estimated=128,
            max_output_tokens=2000,
            provider_timeout_seconds=30.0,
        )

    print(response.content)
    # Decidido pelo ranking do Gateway, não pelo seu código — NVIDIA em condições normais,
    # com fallback automático para outro provider autorizado caso contrário.
    print(response.execution.provider, response.execution.model, response.execution.deployment)


asyncio.run(main())
```

O `max_output_tokens: 2000` não é arbitrário: os deployments de NVIDIA, Gemini e Groq aqui gastam uma
parte variável, às vezes grande, do orçamento "pensando" internamente antes de qualquer texto visível
— um orçamento apertado como `128` retorna `response.content` vazio numa fração real das vezes
(reproduzido de fato, não teórico). Dê espaço real de tokens para modelos com "reasoning".

Nenhum SDK de provider, nenhuma API key e nenhum `if provider == ...` pertence ao seu projeto. Veja
[o README dele](config/profiles/personal-default/README.md) para o runbook completo, o escopo atual
(`rag.answer` em `balanced`) e o status de prova por provider.

## Validar o repositório

O quality path padrão é determinístico e não exige credenciais:

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Frontend, observabilidade e provas de integração também ficam isolados em workflows específicos do GitHub Actions. Testes com providers reais permanecem opt-in por design.

## Mapa do repositório

| Caminho | Responsabilidade |
| --- | --- |
| `apps/gateway-api/` | Composition root FastAPI e processos executáveis do Gateway |
| `apps/gateway-console/` | Console operacional read-only em React/TypeScript |
| `packages/gateway-contracts/` | Contratos públicos provider-neutral |
| `packages/gateway-core/` | Domínio, serviços de aplicação e adapters de provider/runtime |
| `packages/gateway-client/` | SDK consumidor fino e tipado |
| `config/` | Registry e artefatos secret-free de provider, cliente, policy e routing |
| `benchmarks/` | Avaliação determinística e evidência |
| `Dockerfile`, `compose.gateway.yml` | Imagem de container e deployment da Gateway API |
| `deploy/observability/` | Provisioning local de Collector, Tempo e Grafana |
| `scripts/` | Ferramentas de quality, evidência e demo local determinística |
| `tests/` | Testes de contrato mais provas de integração opt-in contra servidores reais |
| `docs/` | Arquitetura, fronteiras de segurança, roadmap e contratos de evidência |

## Leitura recomendada

Se você está avaliando o projeto, comece por:

- [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) — checkpoint atual autoritativo;
- [`docs/project/CHECKPOINT_LOG.md`](docs/project/CHECKPOINT_LOG.md) — o histórico datado, prova por prova, por trás dele;
- [`docs/project/OPERATIONAL_READINESS.md`](docs/project/OPERATIONAL_READINESS.md) — sequência de readiness/demo operacional;
- [`config/profiles/live-development/README.md`](config/profiles/live-development/README.md) — runbook de live development governado;
- [`config/profiles/personal-default/README.md`](config/profiles/personal-default/README.md) — como chamar o Gateway a partir do seu próprio projeto, ranking com preferência de custo do NVIDIA;
- [`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) — fronteira de autorização;
- [`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) — modelo de providers e secrets;
- [`docs/project/CONTAINER_DEPLOYMENT.md`](docs/project/CONTAINER_DEPLOYMENT.md) — imagem de container e deployment;
- [`docs/project/OPENAI_COMPATIBLE_INGRESS.md`](docs/project/OPENAI_COMPATIBLE_INGRESS.md) — ingresso compatível com OpenAI;
- [`docs/project/SHARED_RUNTIME_STATE.md`](docs/project/SHARED_RUNTIME_STATE.md) — estado de health e circuito compartilhado;
- [`docs/project/SPEND_ACCOUNTING.md`](docs/project/SPEND_ACCOUNTING.md) — gasto estimado e orçamentos;
- [`docs/project/GATEWAY_CONSOLE.md`](docs/project/GATEWAY_CONSOLE.md) — fronteira do Console;
- [`docs/project/GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) — prova local real com Grafana/Tempo;
- [`docs/project/EVALUATION.md`](docs/project/EVALUATION.md) — arquitetura de benchmarks/evidência;
- [`CHANGELOG.md`](CHANGELOG.md) — o que cada versão inclui.

## Licença

Licenciado sob a [Apache License, Version 2.0](LICENSE).
