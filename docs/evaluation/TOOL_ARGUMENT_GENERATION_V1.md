# Tool Argument Generation Benchmark v1

Status: COMPLETE — merged in PR #52.

## Purpose

`tool-argument-generation-v1` adds the roadmap-listed `tool argument generation` benchmark as a narrow deterministic diagnostic workload.

The tool identity is already reviewed and fixed by the case. The model generates only the argument object. This prevents argument quality from being conflated with tool-selection quality.

The diagnostic chain is therefore explicit:

- `tool-selection-v1` measures which tool should be used;
- `tool-argument-generation-v1` measures arguments for a fixed selected tool;
- `tool-use-v1` remains the complete single-call benchmark that measures selection plus arguments together;
- multi-step tool use remains a separate future workload.

## Reviewed catalog

The immutable v1 catalog matches `support-tools-v1`:

- `account_lookup`;
- `knowledge_search`;
- `send_notification`;
- `weather_forecast`.

The dataset contains exactly one reviewed argument-generation case for every tool. Cases cover strings, integers, booleans, arrays, and multi-field objects.

## Response contract

Every case returns exactly:

```json
{
  "arguments": {
    "query": "synthetic export feature",
    "limit": 5
  }
}
```

The response must not contain a `tool` field. Tool identity is input context, not output to be selected again.

## Deterministic scoring

Scoring is binary after recursive exact, type-sensitive comparison:

- exact argument object: `1`;
- any missing or extra argument: `0`;
- wrong scalar type or value: `0`;
- wrong array length or nested value: `0`;
- malformed output shape: `0`.

Stable issue codes include:

- `invalid_output_shape`
- `wrong_arguments_type`
- `missing_argument`
- `extra_argument`
- `wrong_type`
- `wrong_value`
- `wrong_array_length`

Boolean and integer values are deliberately type-sensitive, so `false` is not accepted as integer `0` and vice versa.

No model-as-judge or semantic similarity is used.

## Dataset and execution boundary

Each case carries an explicit reviewed `selected_tool`. The prompt must bind that exact value. Changing metadata without changing the prompt fails closed.

All cases are public/synthetic and set `execute_tool=false`. The benchmark never executes tools, starts an MCP server, performs network calls, invokes side effects, or treats the reviewed catalog as a runtime allowlist.

Default CI requires no provider credentials, tool credentials, network access, agent runtime, or external service.

## Authorization boundary

Tool-argument evidence is evaluation evidence, not authorization. The fixed `selected_tool` is benchmark ground truth only; it does not authorize that tool in a production agent or gateway request.

Any future gateway-backed benchmark execution must still traverse ordinary policy authorization, model-registry eligibility, operational ranking/resilience, tool restrictions, and terminal provenance validation.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`

This increment does not change runtime policy, registry data, ranking, promotion, provider adapters, tool execution, API/SDK behavior, or consumer repositories.

Issue #18 continues to defer OpsLens reconciliation and blocks RAGForge unless the normative Phase 14 order is explicitly revised.
