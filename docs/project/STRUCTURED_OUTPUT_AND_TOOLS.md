# Structured Output and Tool Normalization

## Scope

Phase 7 adds provider-neutral structured-output and business-tool contracts while preserving the
existing authorization and replay-safety boundaries.

The gateway remains responsible for governed model execution. It does not execute business tools.

## Canonical contracts

### StructuredOutputSchema

A caller may request native structured output by supplying a named JSON Schema together with
`WorkloadRequirements.structured_output=True`.

Provider-neutral validation requires:

- normalized schema name;
- non-empty schema;
- valid Draft 2020-12 JSON Schema syntax;
- maximum serialized schema size of 64 KiB;
- bounded schema depth;
- no remote `$ref` or `$dynamicRef` resolution;
- no `pattern` or `patternProperties` keyword in Phase 7;
- no `format` keyword in Phase 7.

Only local fragment references are accepted.

Phase 7 intentionally implements a safe subset of Draft 2020-12. Caller-controlled regex keywords are
rejected rather than evaluated, avoiding unbounded regular-expression work inside the validation
boundary. `format` is rejected rather than silently accepted without an explicit format checker.

The keyword restriction is schema-aware: an ordinary object property named `pattern` is still valid.

### ToolDefinition

A declared tool contains:

- normalized tool name;
- normalized non-empty description;
- object-root input schema.

Tool schemas pass through the same bounded JSON Schema subset before provider execution. Duplicate
tool names are rejected.

### ToolCall

Provider tool calls normalize to:

- `call_id`;
- tool `name`;
- object-valued `arguments`.

The gateway validates that:

- the tool was declared by the caller;
- the provider correlation ID is present;
- the arguments satisfy the declared tool schema.

Unknown tools and invalid arguments become typed `invalid_tool_call` failures.

### ToolResult

`ToolResult` represents a business-tool result supplied by the application/agent/MCP runtime. The
gateway does not produce it by executing a tool.

Phase 7 does not yet round-trip `ToolResult` into provider-native continuation transcripts when exact
provider-generated continuation or reasoning state would be required. The gateway fails closed rather
than reconstructing opaque state.

## Structured output semantics

Structured output is treated as a provider-native capability, not as a prompt convention.

Prompted JSON is not equivalent to native schema enforcement.

Even after a provider reports native schema enforcement, the gateway parses and validates the final
JSON locally. A malformed document or schema mismatch produces `invalid_structured_output`.

No automatic repair loop is implemented in Phase 7.

## Provider mappings

### OpenAI Responses

The native Responses adapter maps the canonical structured-output contract to the Responses text
format JSON Schema configuration and maps canonical tools to function tools.

Provider-produced function calls are normalized and schema-validated before being returned.

### Anthropic Messages

The native Messages adapter maps structured output to the provider output-format configuration and
maps canonical tools to Anthropic tool definitions.

`tool_use` blocks are normalized to canonical `ToolCall` values and validated locally.

### Google Gemini generateContent

The Gemini adapter maps structured output to `responseJsonSchema` and canonical tools to
`functionDeclarations`.

A provider `functionCall` must contain a correlation ID for normalization. If the selected model/API
omits the ID, the gateway fails closed rather than synthesizing one.

### OpenAI-compatible chat completions

The generic compatibility adapter assumes neither structured output nor tool calling.

Each capability must be explicitly enabled for a configured endpoint. When enabled, the adapter uses
the documented OpenAI-style JSON Schema/function-call shapes and still applies local validation.

This preserves the rule that OpenAI-compatible does not mean behaviorally identical.

## Resilience interaction

Phase 6 resilience forwards the structured-output/tool contracts unchanged to every selected attempt.

The following normalized failures are permanent:

- `invalid_structured_output`;
- `invalid_tool_call`.

They cause zero automatic retry and zero automatic fallback.

This is intentional: semantic output validation failure is not treated as an availability incident.

Automatic replay remains allowed only for the transient categories already defined by ADR-0007:

- rate limit;
- timeout;
- unavailable/server failure;
- transport failure.

## Authority boundary

The execution chain remains:

```text
Application / Agent
  │ declares schema/tools
  ▼
Policy Model Router
  │ authorizes logical model group
  ▼
Gateway eligibility/ranking/resilience
  │ chooses only inside authorization
  ▼
Provider adapter
  │ generates text / structured output / tool call
  ▼
Application / Agent / MCP runtime
  │ authorizes and executes business tool
  └─ owns side effects and ToolResult
```

No tool schema, tool call, or tool result grants additional model authorization.

## Privacy and evidence

Tool arguments, tool results, prompts, and completions are payload data and are not included in
metadata-only evidence by default.

Operational evidence may record bounded facts such as provider/deployment, outcome category, retry or
fallback progression, and normalized error code without storing business payloads.

## Acceptance evidence

Phase 7 contract tests prove:

- native structured-output payload mapping for supported adapters;
- invalid JSON and schema mismatch fail closed;
- unsafe external schema references are rejected before provider execution;
- Phase 7 rejects regex/format schema keywords whose local enforcement is not safely bounded;
- property names are not confused with schema keywords during subset validation;
- tool schemas use the same bounded schema policy as structured output;
- declared tool calls are normalized and arguments validated;
- unknown tools and invalid arguments fail closed;
- missing provider tool-call correlation fails closed where required by the canonical contract;
- generic OpenAI-compatible endpoints do not receive optional capabilities without explicit opt-in;
- structured-output/tool contracts survive the resilience boundary unchanged;
- structured/tool semantic failures do not trigger retry or fallback;
- gateway contracts expose no business-tool execution hook.

See ADR-0013 for the architectural decision record.
