# Governed LLM Gateway

[English](README.md) | **Português (Brasil)**

Gateway reutilizável e neutro em relação a provedores de LLM para **resolução e execução governada de modelos**.

Status: **Phase 8 — Streaming implementado; em revisão**.

O projeto separa autorização, seleção operacional determinística, resiliência de runtime,
normalização de recursos do provedor e transporte streaming:

```text
Aplicação / Agente
       │ workload + requisitos + metadados de política
       │ mensagens + schema/tools opcionais
       ▼
Policy Model Router (PDP)
       │ grupo lógico de modelos autorizado + proveniência
       ▼
Governed LLM Gateway (PEP + seleção operacional)
       │ candidatos autorizados
       ├─ elegibilidade + ranking determinístico
       ├─ saúde de runtime / circuit breaker
       ├─ retry limitado / fallback seguro
       ├─ structured output / normalização de tool calls
       └─ streaming normalizado / cancelamento
       ▼
Provedor de LLM
       │ texto / structured output / ToolCall / eventos streaming
       ▼
Aplicação / Agente / runtime MCP
       └─ autoriza e executa business tools
```

Invariante central:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

O gateway pode restringir a autorização por capacidade, política de ambiente/dados, custo, latência,
saúde, estado do circuito ou outras restrições operacionais. Ele nunca pode ampliar a autorização do
PDP, inclusive durante retry, fallback, tradução de provedor ou streaming.

## Implementação atual

As Phases 0–4 estabeleceram o workspace e os gates de arquitetura, model registry estrito, fundação de
execução de provedores e a fronteira determinística de autorização com o Policy Model Router. A Phase
5 adicionou elegibilidade/ranking determinístico e o `POST /v1/route/explain` autenticado. A Phase 6
adicionou saúde por deployment, circuit breaker, retry limitado, fallback seguro e regras de segurança
de replay. A Phase 7 adicionou validação limitada de structured output e normalização provider-neutral
de tool calls, mantendo a execução de business tools fora do gateway.

A Phase 8 adiciona streaming normalizado:

- ADR-0011 define lifecycle, replay, cancelamento, usage e semântica de transporte;
- `Capability.STREAMING` participa da elegibilidade determinística;
- adapters também precisam comprovar separadamente `native_streaming` e suporte a `streaming_usage`;
- existem adapters streaming nativos para OpenAI Responses, Anthropic Messages e Gemini
  `streamGenerateContent`;
- streaming OpenAI-compatible genérico continua sendo opt-in explícito, nunca inferido;
- um transporte SSE-over-HTTPS assíncrono dedicado oferece parsing limitado e fechamento explícito do
  upstream;
- `POST /v1/generate` autentica, consulta o PDP, captura health de runtime e ranqueia antes de iniciar
  a resposta SSE;
- retry/fallback só pode ocorrer antes de output semântico ficar visível;
- após conteúdo/tool call ficar visível, falha do provedor termina como
  `response.failed(partial=true, retryable=false)` sem replay entre provedores;
- streams bem-sucedidos finalizam usage exatamente uma vez antes de completar;
- disconnect/cancelamento do cliente fecha o generator de execução e o stream upstream do provedor;
- structured output e tool calls em streaming preservam a validação local da Phase 7;
- o gateway nunca executa business tools nem fabrica estado de continuação/correlação ausente.

## Eventos streaming canônicos

`POST /v1/generate` emite somente:

```text
response.started
content.delta
tool_call.started
tool_call.arguments.delta
tool_call.completed
usage.completed
response.completed
response.failed
```

Os números de sequência são positivos e monotônicos. `response.started` só se torna público quando o
primeiro output semântico está prestes a ser exposto; um evento de start interno do provedor sozinho
não cruza a fronteira de retry/fallback.

Exemplo de frame SSE:

```text
event: content.delta
id: 2
data: {"delta":"hello","event_type":"content.delta","request_id":"...","sequence_number":2}

```

Veja `docs/project/STREAMING.md` e `docs/adr/ADR-0011-streaming-normalization.md`.

## Structured output e tools

Structured output é tratado como uma **capacidade nativa do modelo/API**, e não como convenção de
prompt. A fronteira da Phase 7 usa um subconjunto limitado do Draft 2020-12, limite serializado de
64 KiB, profundidade limitada, sem `$ref`/`$dynamicRef` remoto, sem keywords regex controlados pelo
caller e sem `format` aceito silenciosamente. O output é validado localmente depois do enforcement
nativo do provedor.

A autoridade sobre business tools permanece fora do gateway:

```text
Gateway → normaliza ToolCall
Aplicação / Agente / runtime MCP → autoriza + executa tool → é dono do ToolResult
```

O gateway nunca transforma output do modelo em permissão para executar uma ação externa.

## Retry e fallback seguros

A resiliência da Phase 6 permanece limitada à sequência já autorizada e ranqueada na Phase 5:

- retry usa o mesmo deployment concreto;
- fallback só pode avançar para alternativa já ranqueada e autorizada;
- falhas transitórias incluem rate limit, timeout, unavailable/5xx e transporte;
- falhas permanentes de validação/autenticação/autorização/configuração não fazem fallback automático;
- circuitos abertos e deployments unhealthy só restringem elegibilidade;
- output do provedor, side effects externos ou estado opaco de continuação encerram replay automático.

A Phase 8 torna essa fronteira ainda mais rígida: após output semântico streaming ficar visível,
retry/fallback é desabilitado de forma terminal para aquele request.

## Explicação determinística de rota

`POST /v1/route/explain` é metadata-only e não executa inferência. Resolve contexto confiável, obtém a
decisão do PDP, avalia apenas candidatos do registry já autorizados e retorna deployment selecionado,
alternativas, motivos de rejeição e proveniência.

O endpoint intencionalmente não aceita `messages`.

## Segurança do transporte streaming

`HttpxSseTransport` é separado do transporte JSON não-streaming e exige:

- endpoint HTTPS absoluto;
- ausência de userinfo e fragments na URL;
- timeout positivo e limitado;
- máximo de 1 MiB por evento SSE;
- normalização de timeout/falha de rede na abertura e leitura;
- allowlist de headers de resposta limitada a `content-type` e `retry-after`;
- fechamento upstream explícito e idempotente.

Credenciais do provedor, headers arbitrários e corpos brutos de erro não são expostos no stream
normalizado.

## Notas sobre o Policy Router

`GatewayRequest.requirements.min_context_tokens` é requisito de capacidade do modelo, não uma
estimativa de tokens de entrada, portanto não é traduzido silenciosamente para
`context_tokens_estimated`.

A API 1.0 do Policy Model Router não possui campo `tool_calling_required` por request. O gateway não
inventa esse campo.

Deployments que exigem autorização runtime assinada falham fechado até a futura integração com
Verifiable AI Governance.

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

Baseline atual da Phase 8: **181 testes PASS, 80,40% de cobertura total, mypy em 71 arquivos fonte,
Ruff/Bandit/pip-audit/arquitetura/secret scan/Phase 0 todos PASS**. O CI não exige credenciais e o
workflow normal usa `contents: read`.

Coverage é aplicado em duas camadas: pytest-cov usa `--cov-fail-under=80` e, em seguida, um comando
independente `coverage report --fail-under=80` valida novamente o arquivo de cobertura.

O warning conhecido do Starlette TestClient sobre `httpx`/`httpx2` continua não bloqueante.

## Fonte de verdade

Comece por:

- `docs/project/CURRENT_STATE.md` — checkpoint atual;
- `docs/project/STREAMING.md` e `docs/adr/ADR-0011-streaming-normalization.md` — Phase 8;
- `docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md` e ADR-0013 — Phase 7;
- `docs/project/FALLBACK_AND_RETRY.md` e ADR-0007 — Phase 6;
- ADR-0006 — ranking determinístico da Phase 5;
- `docs/architecture/PDP_PEP_CONTRACT_DRAFT.md` — autorização da Phase 4;
- `docs/project/SOURCE_ROADMAP.txt` — especificação original do projeto.
