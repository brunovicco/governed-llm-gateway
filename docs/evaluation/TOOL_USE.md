# Tool Use Benchmark

`tool_use` measures whether a model proposes the reviewed business-tool call, or correctly abstains from calling a tool, without executing any tool:

`dataset -> runner -> deterministic scorer -> scorecard -> immutable snapshot -> explicit promotion`

The benchmark is public, synthetic, credential-free, and offline-first. The scorer performs no network access and no model-as-judge evaluation.

## Phase 7 alignment

The benchmark follows the Phase 7 authority boundary rather than extending it.

A model may propose a normalized tool name and object-valued arguments. The gateway may normalize and validate provider tool calls, but the gateway does not authorize or execute the underlying business action. Business-tool authorization, side effects, and `ToolResult` ownership remain with the application, agent, or MCP runtime.

For the same reason, the benchmark never executes a proposed tool and cannot turn benchmark evidence into business-tool authority.

## Version 1 contract

`tool-use-v1` and scorer `tool_use_v1` evaluate one normalized decision per case:

- a single tool proposal represented as `{"name": ..., "arguments": {...}}`; or
- `null` when the reviewed behavior is to abstain from tool use.

Every case declares a non-empty `allowed_tools` list. A proposed tool outside that list scores zero. The version deliberately evaluates a single tool decision; multi-step tool workflows belong to a later contract or the `agent_orchestration` workload rather than being inferred inside this scorer.

The dataset covers exact tool selection, exact type-sensitive arguments, nested arguments, scalar arrays, and explicit no-tool behavior.

## Deterministic scoring

`assess_tool_use()` exposes two equal components:

- `selection_score`: `1` when the selected tool matches the reviewed tool, otherwise `0`;
- `arguments_score`: `1` when arguments match exactly and type-sensitively, otherwise `0`.

The scalar score consumed by `BenchmarkRunner` is:

`score = (selection_score + arguments_score) / 2`

Correct abstention receives `1`. An unexpected tool call receives `0`. An undeclared tool always receives `0`, even if its arguments happen to resemble the expected values.

The default runner threshold remains `1`, so partial credit is evidence for diagnosis and comparison, not a successful quality result.

## Explainability

`assess_tool_use()` returns stable issue codes and JSON-pointer-like paths. Current codes include:

- `missing_tool_call`;
- `unexpected_tool_call`;
- `undeclared_tool`;
- `wrong_tool`;
- `invalid_output_shape`;
- `wrong_tool_type`;
- `wrong_arguments_type`;
- `missing_argument`;
- `unexpected_argument`;
- `wrong_argument_type`;
- `wrong_argument_value`;
- `argument_array_length_mismatch`.

The generic snapshot contract continues to persist only the scalar quality score. Workload-specific issue evidence is additive and does not require a benchmark framework migration.

## Quality, availability, and promotion

Completed model outputs are quality evidence. Timeouts, rate limits, transport errors, and provider outages remain provider-availability evidence with `quality_score = None`.

Snapshots remain content-addressed and promotion remains explicit. Neither raw benchmark results nor promoted benchmark evidence can widen Policy Router authorization, enable a deployment, execute a tool, or mutate active runtime routing by themselves.
