# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

Gateway reutilizável e neutro em relação a provedores de LLM, cuja responsabilidade é a **resolução e execução governada de modelos**.

Status: **Phase 6 — Saúde de Runtime, Retry e Fallback Seguro implementados; em revisão**.

O projeto separa autorização, seleção operacional e resiliência de execução:

```text
Aplicação / Agente
       │ workload + requisitos + metadados de política
       ▼
Policy Model Router (PDP)
       │ grupo lógico de modelos autorizado + proveniência
       ▼
Governed LLM Gateway (PEP + seleção operacional)
       │ candidatos autorizados
       ├─ elegibilidade + ranking determinístico
       ├─ saúde de runtime / circuit breaker
       └─ retry limitado / fallback seguro
       ▼
Provedor de LLM
```

Invariante central:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

O gateway pode tornar a autorização mais restritiva por capacidade, política de ambiente/dados, custo,
latência, saúde, estado do circuito ou outras restrições operacionais. Ele nunca pode ampliar a
autorização, inclusive durante fallback.

## Implementação atual

A Phase 0 estabeleceu o workspace com uv, os limites de arquitetura e segurança, o contrato
provider-neutral inicial, os ADRs 0001 a 0005 e o invariante de autorização fail-closed.

A Phase 1 foi concluída no `policy-model-router`, generalizando identificadores de workload e grupos
lógicos de modelos, preservando decisões de política determinísticas e proveniência.

A Phase 2 concluiu o model registry estrito, com parsing seguro de YAML, validação de schema e
semântica, metadados de preço versionados e proveniência determinística do registry via SHA-256.

A Phase 3, incorporada pelo PR #2, adicionou a fundação de execução de provedores:

- ports provider-neutral para requests, responses e erros;
- adapters nativos para OpenAI Responses, Anthropic Messages e Google Gemini `generateContent`;
- adapter explicitamente configurado para chat completions compatíveis com OpenAI;
- transporte HTTPS/JSON limitado, normalização de uso, timeout por tentativa e erros tipados;
- nenhuma exposição de corpo bruto de erro não-2xx, credenciais ou headers arbitrários do provedor.

A Phase 4, incorporada pelo PR #3, adicionou a fronteira determinística com o Policy Model Router:

- contrato `PolicyRequestMetadata` sem prompt;
- projeção de política baseada em `EffectivePolicyContext` confiável, e não em claims do caller;
- adapter para o schema wire `1.0` do `POST /route`;
- validação estrita de decisões e proveniência;
- interseção do registry com o grupo lógico autorizado pelo PDP;
- prova de que rejeição do PDP ou seleção fora da autorização produz zero chamadas ao provedor.

A Phase 5, incorporada pelo PR #4, adicionou seleção operacional determinística:

- ADR-0006 para semântica de ranking determinístico;
- política de ranking estrita/versionada com digest SHA-256;
- elegibilidade antes do scoring para estado habilitado, ambiente/classificação confiáveis,
  capacidades, contexto, evidência estática de ranking, preço, limite de custo e latência esperada;
- scoring determinístico com `Decimal` e desempate por `deployment_id` crescente;
- proveniência de PDP, registry e ranking, além de motivos de rejeição legíveis por máquina;
- `POST /v1/route/explain` autenticado, que executa autorização + elegibilidade + ranking sem invocar
  um provedor.

Os scores estáticos da Phase 5 são explicitamente **não** considerados evidência de benchmark.
`benchmark_snapshot_id` permanece vazio até as fases posteriores de avaliação/ranking por evidências.

A Phase 6 adiciona resiliência de runtime estritamente dentro da sequência já autorizada e ranqueada:

- ADR-0007 para semântica de retry/fallback e segurança de replay;
- retry limitado contra o mesmo deployment concreto;
- fallback limitado apenas para o próximo deployment já ranqueado e autorizado;
- classes transitórias normalizadas: rate limit, timeout, unavailable/5xx e falha de transporte;
- erros permanentes de validação/autenticação/autorização/configuração falham de forma fechada sem
  fallback automático para outro provedor;
- backoff exponencial limitado, jitter reconstruível e `Retry-After` do provedor também limitado;
- saúde de runtime e circuit breaker por processo e por deployment;
- ciclo do circuito `CLOSED → OPEN → HALF_OPEN → CLOSED`;
- circuito aberto e estado unhealthy removem o deployment da elegibilidade operacional;
- quando o filtro de saúde está ativo, snapshot ausente torna o deployment inelegível em vez de
  tratá-lo como saudável;
- `FallbackSafetyState` bloqueia replay automático após output do modelo, side effect externo ou
  estado opaco de continuação/raciocínio do provedor;
- execução resiliente bem-sucedida registra a progressão real de deployments em `fallback_sequence`
  e os retries do mesmo deployment como evidência metadata-only de tentativas.

A camada de resiliência nunca reenumera o registry nem solicita ao PDP uma autorização mais ampla após
falha de provedor. Todos os candidatos bounded de fallback são verificados contra o grupo lógico
autorizado antes da primeira chamada ao provedor.

## Limites de escopo da resiliência

Saúde de runtime é estado operacional mutável. Ela não altera os scores estáticos da Phase 5 nem é
apresentada como evidência de benchmark.

O timeout do provedor permanece um limite **por tentativa** na Phase 6. O gateway não reutiliza
silenciosamente `max_latency_ms` de política/ranking como deadline total entre retries. Um orçamento
total de execução exige contrato explícito.

O circuit breaker inicial é por processo. Estado compartilhado em Redis e probes ativos mais ricos
ficam adiados até haver evidência operacional de necessidade.

A Phase 6 cobre resiliência de geração de texto. Semântica de replay para tools/structured output começa
na Phase 7; streaming, output parcial e cancelamento começam na Phase 8.

## Explicação determinística de rota

`POST /v1/route/explain` é uma superfície metadata-only e sem inferência. Ela resolve contexto
confiável, obtém a decisão do PDP, avalia somente candidatos já autorizados e retorna deployment,
alternativas, rejeições e proveniência.

O endpoint não aceita `messages`. Claims de `risk_level`, `data_classification` ou `agent_identity` do
caller não se tornam fatos autoritativos de política.

## Notas sobre o Policy Router

`GatewayRequest.requirements.min_context_tokens` é requisito de capacidade do modelo, não uma
estimativa de tokens de entrada, e não é traduzido silenciosamente para
`context_tokens_estimated`.

A API 1.0 do Policy Model Router expressa requisito de tool calling pela regra de workload, não por um
campo `tool_calling_required` por request. O gateway não inventa esse campo.

Deployments do Policy Model Router que exigem autorização runtime assinada falham com 403 até a futura
integração com Verifiable AI Governance; o gateway falha fechado sem chamar provedor.

## Nota sobre Gemini

O Google recomenda a Interactions API para novos projetos desde junho de 2026, enquanto
`generateContent` continua suportada. O adapter inicial usa deliberadamente `generateContent` porque
o request provider-neutral atual possui mensagens canônicas, mas não os passos exatos de Interaction
gerados pelo modelo necessários para reconstrução stateless sem perda.

## Estrutura do repositório

```text
apps/gateway-api/           composition root HTTP
packages/gateway-contracts contratos provider-neutral
packages/gateway-core/     fronteira domain/application/adapters
packages/gateway-client/   fronteira fina de SDK
config/                    configuração de modelos/ranking/provedores
benchmarks/                futuro framework de benchmark
examples/                  futuros consumidores/exemplos
tests/                     suítes contract/integration/e2e
docs/                      fontes duráveis e ADRs
```

## Validação

```bash
uv sync --frozen
uv run python scripts/quality_gate.py
```

O quality gate inclui Ruff, mypy, pytest/coverage, Bandit, pip-audit, validação de arquitetura,
secret scanning e o regression gate congelado da Phase 0.

Validação atual da Phase 6: **111 testes, 84,11% de cobertura total, mypy em 54 arquivos fonte e todos
os gates de qualidade/segurança PASS**. O CI não exige credenciais e usa `contents: read`.

## Fonte de verdade

Comece por `docs/project/CURRENT_STATE.md` para continuidade,
`docs/adr/ADR-0007-fallback-safety-semantics.md` e `docs/project/FALLBACK_AND_RETRY.md` para a Phase 6,
`docs/adr/ADR-0006-deterministic-candidate-ranking.md` para a Phase 5,
`docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` para a autorização da Phase 4 e
`docs/project/SOURCE_ROADMAP.txt` para a especificação original.
