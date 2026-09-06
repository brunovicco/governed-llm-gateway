# Multi-Step Tool Use Benchmark v1

Status: COMPLETE — merged in PR #55.

## Purpose

`multi-step-tool-use-v1` measures whether a model can propose a short reviewed sequence of tool calls while keeping tool selection and arguments bound to the correct step.

The benchmark is deliberately non-executing. It evaluates model output only; it is not a tool runtime, agent runtime, MCP client, or authorization layer.

## Versioned contract

- workload: `multi_step_tool_use`
- benchmark version: `multi-step-tool-use-v1`
- contract version: `1.0`
- scorer: `multi_step_tool_use_v1`
- response format: `multi_step_tool_calls_v1`
- tool catalog: `support-tools-v1`
- data classification: `public`
- cases: synthetic only
- tool execution: always disabled

The reviewed catalog is intentionally identical to the smaller tool diagnostics:

- `account_lookup`
- `knowledge_search`
- `send_notification`
- `weather_forecast`

## Boundary relative to existing workloads

The workload adds one diagnostic dimension without replacing the existing contracts:

- `tool-selection-v1` measures only the choice of one reviewed tool or explicit no-tool choice;
- `tool-argument-generation-v1` fixes the reviewed tool identity and measures only arguments;
- `tool-use-v1` measures one proposed tool call as a composite of selection and arguments;
- `multi-step-tool-use-v1` measures an ordered proposal of two or three reviewed tool calls;
- `agent-orchestration-v1` measures agents, actions, and handoffs rather than a tool-call sequence.

Keeping these boundaries separate makes failures attributable instead of collapsing selection, argument generation, multi-step planning, and agent handoff quality into one score.

## Synthetic intermediate context

A real multi-step runtime would normally execute one tool and feed its result into later reasoning. This benchmark does **not** do that.

Each checked-in case supplies reviewed immutable synthetic intermediate-result context directly in the prompt. The model therefore proposes the complete trajectory against known public/synthetic evidence without any tool, MCP server, network call, or side effect being invoked by the benchmark.

This is intentionally quality evidence rather than operational tool-execution evidence.

## Expected output

The model must return only:

```json
{
  "steps": [
    {
      "tool": "account_lookup",
      "arguments": {
        "account_id": "A-104",
        "include_history": false
      }
    },
    {
      "tool": "send_notification",
      "arguments": {
        "user_id": "U-7",
        "message": "Account A-104 is locked",
        "channels": ["email"]
      }
    }
  ]
}
```

Every step must contain exactly `tool` and `arguments`. Reviewed expected trajectories contain two or three steps.

## Deterministic scoring

The scorer produces two explainable components:

1. `selection_score` — positional exact tool matches divided by the larger of expected and observed trajectory length;
2. `arguments_score` — positional exact, recursive, type-sensitive argument matches for steps whose tool selection is correct, using the same denominator.

The scalar quality score is:

```text
(selection_score + arguments_score) / 2
```

Arguments on a step with the wrong tool are not rewarded. This prevents argument coincidence from masking an incorrect tool decision.

The recursive argument comparison rejects drift in:

- JSON type;
- scalar value;
- missing keys;
- extra keys;
- array length;
- nested objects and arrays.

No embeddings, fuzzy matching, repair path, external judge, or LLM-as-judge is used.

## Fail-closed validation

Dataset loading rejects, among other things:

- the wrong benchmark version;
- duplicate case IDs;
- any workload other than `multi_step_tool_use`;
- a scorer other than `multi_step_tool_use_v1`;
- prompt instruction drift;
- unknown metadata;
- contract/catalog/response-format drift;
- non-synthetic cases;
- `execute_tools` other than `false`;
- expected trajectories outside the reviewed two-to-three-step bound;
- undeclared tools;
- a case count different from exactly four;
- failure to cover every reviewed tool;
- failure to include both reviewed two-step and three-step trajectories.

Malformed provider output produces deterministic zero or partial quality evidence with stable issue codes; it never causes a tool to execute.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

The expected trajectory is benchmark ground truth only. It cannot:

- authorize a tool or side effect;
- expand the policy-router authorized model set;
- force a provider, model, deployment, or API family;
- bypass gateway eligibility, ranking, retry, or fallback;
- turn synthetic intermediate context into runtime tool evidence;
- mutate policy or ranking configuration;
- promote itself automatically.

Benchmark scores may become ranking evidence only through the existing explicit, attributable promotion process and only among candidates already authorized and eligible.

## Quality evidence vs operational evidence

`multi-step-tool-use-v1` answers a narrow offline question: did the model propose the reviewed tool sequence and arguments?

It does not measure whether those tools are available, authorized for a user, fast, reliable, or successfully executed. Those would be separate operational/runtime facts owned by the appropriate execution system. Model-provider execution provenance carried by `ProviderCall` also must not be confused with business-tool execution provenance.

## CI boundary

Default CI remains:

- credential-free;
- deterministic;
- replayable;
- free of live provider and tool dependencies for contract tests;
- free of tool/MCP execution;
- free of LLM-as-judge dependencies.

The checked-in dataset and deterministic scorer are sufficient to validate the contract and dataset digest offline.

## Non-goals

Version 1 does not introduce:

- live tool or MCP execution;
- dynamic ingestion of observed tool results;
- an agent loop;
- provider-specific function/tool semantics;
- parallel tool execution;
- arbitrary-length trajectories;
- runtime tool authorization;
- benchmark-side provider/model forcing;
- adaptive or self-modifying policy.
