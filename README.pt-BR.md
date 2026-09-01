# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

Gateway reutilizável e neutro em relação a provedores de LLM, cuja responsabilidade é a **resolução e execução governada de modelos**.

Status: **Phase 5 — Ranking Operacional Determinístico e Explicabilidade implementados; em revisão**.

O projeto separa autorização de seleção operacional:

```text
Aplicação / Agente
       │ workload + requisitos + metadados de política
       ▼
Policy Model Router (PDP)
       │ grupo lógico de modelos autorizado + proveniência
       ▼
Governed LLM Gateway (PEP + seleção operacional)
       │ deployment elegível e ranqueado
       ▼
Provedor de LLM
```

Invariante central:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

O gateway pode tornar a autorização mais restritiva por capacidade, política de ambiente/dados, custo,
latência, saúde operacional ou outras restrições. Ele nunca pode ampliar a autorização.

## Implementação atual

A Phase 0 estabeleceu o workspace com uv, os limites de arquitetura e segurança, o contrato
provider-neutral inicial, os ADRs 0001 a 0005 e o invariante de autorização fail-closed.

A Phase 1 foi concluída no `policy-model-router`, generalizando identificadores de workload e de grupos
lógicos de modelos, preservando decisões de política determinísticas e proveniência.

A Phase 2 concluiu o model registry estrito, com parsing seguro de YAML, validação de schema e
semântica, metadados de preço versionados e proveniência determinística do registry via SHA-256.

A Phase 3, incorporada pelo PR #2, adicionou a fundação de execução de provedores:

- ports provider-neutral para requests, responses e erros de provedores;
- adapters nativos para OpenAI Responses, Anthropic Messages e Google Gemini `generateContent`;
- adapter explicitamente configurado para chat completions compatíveis com OpenAI;
- transporte HTTPS/JSON limitado, normalização de uso, timeouts de request e erros tipados;
- nenhuma exposição de corpo bruto de erro não-2xx, credenciais ou headers arbitrários do provedor.

A Phase 4, incorporada pelo PR #3, adicionou a fronteira determinística com o Policy Model Router:

- contrato de aplicação `PolicyRequestMetadata` sem prompt;
- projeção de política baseada em `EffectivePolicyContext` confiável, e não em claims de segurança do caller;
- adapter para o schema wire `1.0` do `POST /route` do Policy Model Router;
- validação estrita de decisões aceitas/rejeitadas e de proveniência;
- interseção do registry com o grupo lógico de modelos autorizado pelo PDP;
- prova de que rejeição pelo PDP ou tentativa de selecionar um deployment fora da autorização resulta em zero chamadas ao provedor;
- nenhum metadado exclusivo do PDP é copiado para payloads de execução do provedor.

A Phase 5 adiciona seleção operacional determinística dentro desse conjunto de candidatos da Phase 4:

- ADR-0006 para a semântica de ranking determinístico;
- `ranking_policy.yaml` estrito e versionado, com rejeição de chaves duplicadas/campos desconhecidos e digest SHA-256;
- pesos `Decimal` específicos por workload para qualidade, confiabilidade, latência, custo e disponibilidade;
- elegibilidade antes do scoring: deployment habilitado, ambiente/classificação de dados confiáveis,
  capacidades, capacidade de contexto, evidência estática de ranking, evidência de preço, limite de custo
  e limite de latência esperada;
- preço desconhecido e ausência de evidência de ranking falham de forma fechada;
- score ponderado determinístico e desempate por `deployment_id` em ordem crescente;
- proveniência de roteamento inclui proveniência da política do PDP, digest do registry, versão/digest da
  política de ranking, ID do snapshot de scores, provedor/modelo/deployment selecionado e motivos de
  rejeição legíveis por máquina;
- mudança do registry após a autorização, ampliação indevida do conjunto autorizado e autorização
  ambígua com múltiplos grupos falham de forma fechada;
- `POST /v1/route/explain` autenticado, que executa apenas autorização + elegibilidade + ranking e nunca
  invoca um provedor;
- requests de explain rejeitam prompt/messages, versões de schema não suportadas e workload IDs inválidos.

Os scores estáticos da Phase 5 são explicitamente **não** considerados evidência de benchmark.
`benchmark_snapshot_id` permanece vazio até as fases de avaliação e ranking orientado por evidências.

## Explicação determinística de rota

`POST /v1/route/explain` é uma superfície metadata-only e sem inferência. Ela resolve o contexto confiável
do cliente, obtém a decisão do PDP, avalia apenas os candidatos do registry já autorizados e retorna o
deployment selecionado, alternativas, motivos de rejeição e proveniência da seleção.

O endpoint não aceita `messages`. `risk_level`, `data_classification` e `agent_identity` enviados pelo
caller não são promovidos a fatos autoritativos de política; o resolver de contexto confiável injetado
e a fronteira com o PDP permanecem como autoridades.

## Notas sobre o contrato com o Policy Router

`GatewayRequest.requirements.min_context_tokens` é um requisito de capacidade do modelo, e não uma
estimativa de tokens de entrada. Por isso, ele não é traduzido silenciosamente para
`context_tokens_estimated` do Policy Model Router.

A API 1.0 do Policy Model Router expressa requisitos de tool calling por meio da regra de política do
workload, e não por um campo `tool_calling_required` por request. O gateway não inventa esse campo.

Alguns deployments do Policy Model Router podem exigir autorização de runtime assinada. Isso pertence
à futura integração com Verifiable AI Governance. Até lá, esse tipo de deployment retorna 403 e o
gateway falha de forma fechada sem chamar um provedor.

## Nota sobre a API Gemini

O Google recomenda a Interactions API para novos projetos desde junho de 2026, enquanto
`generateContent` continua suportada. O adapter inicial do Gemini usa deliberadamente `generateContent`
porque o request provider-neutral atual possui o histórico canônico de mensagens, mas não os passos
exatos de Interaction produzidos pelo modelo, necessários para reconstrução stateless sem perda. O
gateway não fabrica estado/raciocínio específico do provedor apenas para traduzir entre APIs.

## Estrutura do repositório

```text
apps/gateway-api/           composition root HTTP
packages/gateway-contracts contratos provider-neutral
packages/gateway-core/     fronteira domain/application/adapters
packages/gateway-client/   fronteira de SDK fina para consumidores
config/                    configuração de modelos/ranking/provedores
benchmarks/                framework futuro de benchmark
examples/                  futuros consumidores/exemplos
tests/                     suítes contract/integration/e2e
docs/                      fontes duráveis do projeto e ADRs
```

## Validação

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

O quality gate inclui Ruff, mypy, pytest/coverage, Bandit, pip-audit, validação de arquitetura,
secret scanning e o regression gate congelado da Phase 0.

Validação atual da implementação da Phase 5: **94 testes, 83,43% de cobertura total, mypy em 49 arquivos
fonte e todos os gates de qualidade/segurança PASS**. O CI não exige credenciais e usa `contents: read`.

## Fonte de verdade

Comece por `docs/project/CURRENT_STATE.md` para continuidade,
`docs/adr/ADR-0006-deterministic-candidate-ranking.md` para a semântica de ranking da Phase 5,
`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` para o binding de autorização da Phase 4 e
`docs/project/SOURCE_ROADMAP.txt` para a especificação original do projeto.
