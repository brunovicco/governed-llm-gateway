# Tool Selection Benchmark v1

Status: COMPLETE — merged in PR #51.

## Purpose

`tool-selection-v1` adds the roadmap-listed `tool selection` benchmark class as a narrow deterministic diagnostic workload.

It measures only whether a model selects the reviewed tool that matches a synthetic request, or correctly selects no tool. It does not evaluate tool arguments and never executes a tool.

This is intentionally narrower than `tool-use-v1`, which scores both selection and arguments in one complete call. Keeping the diagnostic separate makes failures attributable: selection quality can be measured independently before `tool-argument-generation` and multi-step tool-use workloads are evaluated.

## Reviewed catalog

The immutable v1 catalog is:

- `account_lookup` — read a synthetic account profile;
- `knowledge_search` — search synthetic product documentation;
- `send_notification` — send a synthetic user notification;
- `weather_forecast` — read a synthetic weather forecast.

The dataset contains exactly one reviewed case for every catalog tool plus exactly two cases where no tool is required.

## Response contract

Every case returns exactly:

```json
{"tool": "knowledge_search"}
```

or:

```json
{"tool": null}
```

No `arguments` field is allowed in this workload. Producing arguments changes the output shape and scores zero.

## Deterministic scoring

Scoring is binary and exact:

- exact reviewed tool: `1`;
- exact reviewed no-tool decision: `1`;
- wrong, missing, unexpected, unknown, or wrongly typed tool: `0`;
- any extra output field: `0`.

Stable issue codes include:

- `invalid_output_shape`
- `wrong_tool_type`
- `unknown_tool`
- `missing_tool`
- `unexpected_tool`
- `wrong_tool`

No LLM judge or semantic similarity is used.

## Dataset and execution boundary

`load_tool_selection_dataset(...)` fails closed on benchmark-version drift, duplicate case IDs, unknown metadata, prompt/catalog drift, execution enablement, malformed expected output, missing reviewed-tool coverage, or an incorrect number of no-tool cases.

All cases are public/synthetic and set `execute_tool=false`. Default CI needs no provider credentials, network calls, MCP server, tool runtime, agent framework, sandbox, or external service.

## Authorization boundary

Tool-selection evidence is evaluation evidence, not authorization. A reviewed benchmark catalog does not authorize those tools for runtime use, and a benchmark result cannot widen an agent or gateway tool allowlist.

Any future gateway-backed execution must still follow normal policy authorization, registry eligibility, ranking/resilience, tool restrictions, and terminal provenance rules.

The permanent invariant remains:

`Gateway allowed set ⊆ Policy Router authorized set`

This increment does not change policy, registry data, ranking, promotion, provider adapters, runtime tool execution, API/SDK behavior, or consumer repositories.

Issue #18 continues to defer OpsLens reconciliation and blocks RAGForge unless the normative Phase 14 order is explicitly revised.
