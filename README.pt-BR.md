# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

[![quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/quality.yml)
[![console-quality](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/console-quality.yml)
[![observability-compose](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml/badge.svg)](https://github.com/brunovicco/governed-llm-gateway/actions/workflows/observability-compose.yml)

> Um gateway de execução de LLM provider-neutral que mantém **autorização, seleção de modelo, credenciais de provider, resiliência e evidência de runtime** fora do código das aplicações.

A aplicação declara um workload e seus requisitos. O Gateway decide qual modelo autorizado atende, chama
o provider e devolve a resposta com a evidência de como ela foi escolhida. Nenhum SDK de provider,
nenhuma API key e nenhum `if provider == ...` no consumidor.

```text
Aplicação / Agente
        │
        │ workload + requisitos + credencial do Gateway
        ▼
Policy Model Router (PDP)
        │ grupos lógicos de modelo autorizados
        ▼
Governed LLM Gateway (PEP)
        ├─ elegibilidade + ranking determinístico
        ├─ health / circuit breaker
        ├─ retry limitado + fallback seguro
        ├─ tradução de provider
        └─ proveniência + OpenTelemetry
        ▼
Providers de LLM
```

```text
conjunto permitido pelo Gateway ⊆ conjunto autorizado pelo Policy Router
```

O Gateway pode estreitar um conjunto autorizado. Nunca pode ampliá-lo.

[Uma requisição governada real](#uma-requisição-governada-real) · [O que você ganha](#o-que-você-ganha) · [Como funciona](#como-funciona) · [Executando](#executando) · [Chamando a partir do seu projeto](#chamando-a-partir-do-seu-projeto) · [Mapa do repositório](#mapa-do-repositório) · [Escopo](#escopo) · [Por onde continuar](#por-onde-continuar)

## Uma requisição governada real

O chamador declarou apenas `workload`, `risk_level` e `data_classification`. A política autorizou o grupo
`balanced`, o ranking determinístico selecionou o deployment dentro dele, e a chamada ao provider, o
orçamento de retry/fallback e a emissão do trace ficaram todos do lado do servidor.

![Gateway Console após uma requisição governada real: grupo autorizado "balanced" sob a policy 1.0.0, provider selecionado nvidia, modelo nvidia/nemotron-3-super-120b-a12b, deployment nvidia-nemotron-3-super-dev na tentativa 1 com fallback 0, 1644 ms e 149 tokens normalizados, além de decisão de rota, decisão de política, digest do registry, ranking policy, score snapshot, sequência de fallback e trace ID](docs/assets/screenshots/console-trace-evidence.png)

Uma execução local real do perfil [`personal-default`](config/profiles/personal-default/README.md) com
credenciais. Cada campo é evidência terminal de execução: IDs de decisão de
rota e de política, digests de registry e ranking, o score snapshot que ranqueou os candidatos, a
sequência de fallback efetivamente percorrida e o trace ID emitido. O link *View this request's trace in
Grafana* do próprio Console resolve exatamente aquele trace — o waterfall correspondente está em
[`docs/project/GATEWAY_CONSOLE.md`](docs/project/GATEWAY_CONSOLE.md).

## O que você ganha

| Capacidade | O que significa na prática |
| --- | --- |
| **Um único ponto de integração** | Os consumidores falam um contrato provider-neutral. Adicionar, trocar ou desabilitar um provider é mudança de registry, não edição em cada serviço que chama um modelo. |
| **Credenciais em um lugar só** | As chaves de provider pertencem ao deployment do Gateway. Rotacionar uma é uma mudança única, em um lugar único, sem redeploy de consumidor e sem chave espalhada por repositórios. |
| **Autorização que se sustenta** | A política decide quais grupos de modelo um workload pode usar. O Gateway só consegue estreitar esse conjunto, nunca ampliá-lo, e falha fechado quando a política está inacessível. |
| **Seleção determinística** | O ranking dentro do conjunto autorizado é reproduzível e explicável: mesmas entradas, mesmo deployment, com os motivos e os digests que o produziram anexados. |
| **Resiliência sem surpresa** | Health, circuit breaker, retry limitado e fallback — todos restritos a deployments já autorizados, e compartilháveis entre réplicas para que o comportamento continue determinístico ao escalar. |
| **Teto de custo** | Contabilização de gasto por cliente e por workload, a partir do pricing fixado e do uso reportado, com orçamentos que recusam a requisição ao atingir o teto. |
| **Evidência em toda requisição** | Proveniência terminal de execução mais OpenTelemetry metadata-only: o que foi autorizado, o que foi selecionado, o que de fato executou e o trace emitido. |
| **Interoperabilidade nos dois sentidos** | Adapters nativos de OpenAI Responses, Anthropic Messages e Gemini, adapters explicitamente compatíveis com OpenAI, e um ingresso no formato OpenAI para que um cliente existente apenas reaponte seu `base_url`. |

## Como funciona

1. O consumidor se autentica no Gateway e declara um workload, não um modelo.
2. O Policy Model Router determina quais grupos lógicos de modelo aquele workload pode usar.
3. O Gateway intersecta essa autoridade com capability do registry, ambiente, dado/risco e elegibilidade de runtime.
4. O ranking determinístico seleciona dentro do que restou; retry e fallback só podem ir para outro deployment já autorizado e elegível.
5. Requisições e respostas específicas de provider são normalizadas atrás de adapters.
6. Proveniência terminal e telemetria metadata-safe descrevem o que aconteceu. Elas nunca autorizam uma requisição futura.

Uma autoridade opcional de governança pode estreitar ainda mais o que a política autorizou; nunca pode
expandir. O contrato de fio exato está em
[`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md).

O Gateway deliberadamente não é framework de agentes, framework de RAG, executor de ferramentas MCP,
plataforma de gestão de prompts nem produto de API management. Ele normaliza uma tool call, mas o
runtime da aplicação continua dono da autorização e dos efeitos colaterais da ferramenta.

### Credenciais de provider em um lugar só

Credencial de provider é assunto do deployment. Um binding de provider-runtime referencia a credencial
por nome, e um resolver server-side transforma essa referência no valor real apenas dentro do processo
do Gateway — um `.env` carregado localmente, ou as mesmas referências injetadas por AWS Secrets Manager,
Azure Key Vault, GCP Secret Manager ou Vault em um deployment real. Rotacionar uma chave de provider é,
portanto, uma mudança em um lugar só: nenhum consumidor publica build novo e nenhum repositório guarda
segredo de provider.

Uma aplicação consumidora recebe exatamente duas variáveis — `GOVERNED_LLM_GATEWAY_URL` e
`GOVERNED_LLM_GATEWAY_API_KEY` — e não é dona de política de provider, modelo, retry ou fallback. A
fronteira de confiança está especificada em
[`docs/project/PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md) e
[`docs/project/GATEWAY_CLIENT_AUTHENTICATION.md`](docs/project/GATEWAY_CLIENT_AUTHENTICATION.md).

## Executando

Três configurações, em ordem crescente do que exigem:

| Configuração | Exige | O que mostra |
| --- | --- | --- |
| **Demo local de operações** | Nada além do toolchain | A Operations API read-only, o Console e a cadeia Collector → Tempo → Grafana. Não expõe rota de inferência, então não precisa de credencial. |
| [**`live-development`**](config/profiles/live-development/README.md) | Um policy router externo e credenciais de provider | Um consumidor revisado, ranking determinístico, dois deployments nativos em um grupo autorizado. |
| [**`personal-default`**](config/profiles/personal-default/README.md) | O mesmo, mais suas próprias chaves | Seis providers (NVIDIA, Gemini, OpenAI, Anthropic, Groq, OpenRouter) em um grupo autorizado, NVIDIA preferido por custo; é o perfil para chamar a partir das suas aplicações. |

O baseline versionado é fail-closed: nenhum deployment habilitado, nenhum binding de provider, política
desabilitada, nenhum principal ativo. Adicionar uma chave de provider por si só não habilita inferência —
um perfil precisa ser ativado explicitamente, de modo que disponibilidade operacional nunca vira
autorização por acidente.

### Pré-requisitos

Python **3.13+** (3.13–3.14 suportados), [uv](https://docs.astral.sh/uv/), Docker com Compose e
Node.js 24 com npm.

### Demo local de operações

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
cd governed-llm-gateway
cp .env.example .env
```

Defina `GATEWAY_LOCAL_DEMO_API_KEY` no `.env` com qualquer valor local aleatório. O runtime Python não
carrega `.env` sozinho, então exporte antes:

```bash
set -a; source .env; set +a
uv run --frozen python scripts/local_demo.py
```

| Superfície | URL |
| --- | --- |
| Gateway Console | `http://127.0.0.1:5173` |
| Readiness do Gateway | `http://127.0.0.1:8000/readyz` |
| Operations API | `http://127.0.0.1:8000/v1/ops/overview` |
| Grafana | `http://127.0.0.1:3000` |

`Ctrl+C` encerra; o launcher é dono da limpeza dos processos filhos e do seu projeto Compose. Para uma
prova automatizada de startup/readiness/teardown, adicione `--smoke-test`.

| Console — antes de conectar | Console — conectado, baseline operations-only |
| --- | --- |
| ![Gateway Console, desconectado](docs/assets/screenshots/gateway-console-disconnected.png) | ![Gateway Console, conectado, mostrando o baseline operations-only real: registry phase2-empty, 0 deployments, 0 processos rastreados](docs/assets/screenshots/gateway-console-connected.png) |

![Dashboard local de traces no Grafana, provisionado por esta demo](docs/assets/screenshots/grafana-trace-dashboard.png)

Screenshots reais desta demo: a visão conectada é o baseline fail-closed genuíno (registry
`phase2-empty`, zero deployments), e o dashboard não tem linhas porque este modo não expõe rota de
inferência capaz de produzir um trace.

## Chamando a partir do seu projeto

Dois processos rodam: o Policy Model Router (repositório separado) e o Gateway. Sua aplicação aponta
para a URL e a credencial do Gateway.

```bash
git clone https://github.com/brunovicco/governed-llm-gateway.git
git clone https://github.com/brunovicco/policy-model-router.git
(cd policy-model-router && uv sync --frozen)
cd governed-llm-gateway && uv sync --frozen
```

Coloque no `.env` os dois segredos locais compartilhados que você inventa, mais as chaves de provider
que você realmente tem:

```dotenv
GATEWAY_DEMO_API_KEY=valor-local-aleatorio
POLICY_ROUTER_DEMO_API_KEY=valor-local-aleatorio
NVIDIA_API_KEY=...
GEMINI_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
```

Uma chave faltando para um deployment **habilitado** derruba o processo fechado no startup. Com menos de
seis providers, desabilite os demais no `model_registry.yaml` (`enabled: false`) e remova seus bindings
do `provider_runtime.json` antes. A NVIDIA tem tier gratuito em [build.nvidia.com](https://build.nvidia.com).

```bash
set -a; source .env; set +a
uv run --frozen python scripts/personal_default_launcher.py
```

Isso sobe e derruba os dois serviços juntos (assume `../policy-model-router`; sobrescreva com
`POLICY_MODEL_ROUTER_ROOT`). Depois adicione o client fino ao seu projeto — não publicado no PyPI,
instale direto deste repositório:

```bash
uv add "governed-llm-gateway-client @ git+https://github.com/brunovicco/governed-llm-gateway.git#subdirectory=packages/gateway-client"
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
    # Escolhido pelo ranking do Gateway, não pelo seu código.
    print(response.execution.provider, response.execution.model, response.execution.deployment)


asyncio.run(main())
```

`max_output_tokens=2000` não é arbitrário: os deployments de NVIDIA, Gemini e Groq aqui gastam uma
fatia variável, às vezes grande, do orçamento em raciocínio interno antes de qualquer texto visível —
com um orçamento apertado, o conteúdo volta vazio numa fração mensurável das vezes. O runbook completo,
o escopo atual (`rag.answer` em `balanced`) e o status de prova por provider estão no
[README do perfil](config/profiles/personal-default/README.md).

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
| `docs/` | Arquitetura, fronteiras de segurança e contratos de evidência — comece por [`docs/project/README.md`](docs/project/README.md) |

O caminho padrão de qualidade é determinístico e não exige credencial:

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

Provas de frontend, observabilidade, container e integração contra servidores reais rodam em workflows
dedicados do GitHub Actions. Testes com provider real continuam opt-in por design.

## Escopo

Uma implementação de referência feita para ser executada e lida, não um produto hospedado:

- **Não é infraestrutura de produção.** Sem terminação TLS, IAM/SSO de produção, gestão de sessão de browser, rate limiting ou política de CSRF. Todo caminho demonstrado roda como processos loopback locais.
- **Não é SLA sobre nenhum provider.** Entradas de pricing e catálogo são metadados fixados, revisados em uma data, e podem se distanciar do catálogo real do provider.
- **Benchmarks são fixtures, não tráfego de produção.** Eles informam elegibilidade de ranking dentro de um conjunto já autorizado — nunca autorização, e nunca substituto para feedback real de usuários.
- **As provas com provider são reais.** Toda prova de inferência governada citada no checkpoint log é uma requisição real, com credenciais fornecidas pelo operador, pela cadeia completa política → Gateway → provider, com a evidência terminal inspecionada. Não é mock, não é stub, não é simulação sem credencial.

Status de fase, escopo adiado e a evidência datada por trás de cada afirmação vivem em
[`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) e
[`docs/project/CHECKPOINT_LOG.md`](docs/project/CHECKPOINT_LOG.md).

## Por onde continuar

Todo documento em `docs/project/` está agrupado e explicado no
[índice da documentação](docs/project/README.md). Os caminhos mais curtos:

- **Arquitetura** — [`ARCHITECTURE.md`](docs/project/ARCHITECTURE.md), o contrato de autorização em [`PDP_PEP_CONTRACT_DRAFT.md`](docs/architecture/PDP_PEP_CONTRACT_DRAFT.md) e as decisões por trás de ambos em [`docs/adr/`](docs/adr/);
- **Segurança e secrets** — [`SECURITY_MODEL.md`](docs/project/SECURITY_MODEL.md) e [`PROVIDER_RUNTIME_CONFIGURATION.md`](docs/project/PROVIDER_RUNTIME_CONFIGURATION.md);
- **Deployment** — [`CONTAINER_DEPLOYMENT.md`](docs/project/CONTAINER_DEPLOYMENT.md), [`SHARED_RUNTIME_STATE.md`](docs/project/SHARED_RUNTIME_STATE.md) e [`SPEND_ACCOUNTING.md`](docs/project/SPEND_ACCOUNTING.md);
- **Evidência** — [`GRAFANA_TRACE_DASHBOARD.md`](docs/project/GRAFANA_TRACE_DASHBOARD.md) e [`EVALUATION.md`](docs/project/EVALUATION.md);
- **Histórico de releases** — [`CHANGELOG.md`](CHANGELOG.md).

## Licença

Licenciado sob a [Apache License, Version 2.0](LICENSE).
