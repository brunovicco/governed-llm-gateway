# Agent Orchestration Benchmark v1

`agent-orchestration-v1` is the fifth workload in the gateway's initial benchmark set.

It evaluates whether a model can propose the reviewed **observable orchestration trajectory** for a synthetic support scenario. It does not evaluate hidden reasoning and it does not execute agents, tools, business operations, or human handoffs.

## Contract

Each case is public and synthetic and uses:

- `workload: agent_orchestration`;
- `scorer: agent_orchestration_v1`;
- `contract_version: "1.0"`;
- `synthetic: true`;
- `execute_steps: false`;
- an explicit `allowed_agents` list;
- an `allowed_actions` mapping covering every allowed agent.

The expected and observed outputs have one top-level field:

```json
{
  "steps": [
    {
      "agent": "router",
      "action": "classify_request",
      "handoff_to": "knowledge"
    },
    {
      "agent": "knowledge",
      "action": "answer_public_knowledge",
      "handoff_to": null
    }
  ]
}
```

Every step contains exactly `agent`, `action`, and `handoff_to`.

The reviewed expected trajectory must be internally consistent: every non-terminal `handoff_to` names the next step's agent and the final step terminates with a null handoff.

## Deterministic scoring

The scorer exposes:

- `sequence_score`: fraction of expected positions whose `agent` and `action` both match;
- `handoff_score`: fraction of expected positions whose `handoff_to` matches;
- `score = (sequence_score + handoff_score) / 2`;
- `trajectory_success`: true only for an exact reviewed trajectory with no issues.

The denominator is the larger of expected and observed step count, so missing and extra steps are penalized.

Malformed outputs, undeclared agents, undeclared agent/action combinations, and handoffs to undeclared agents fail closed with score zero. JSON text is not permissively parsed into a trajectory.

Stable issue codes identify invalid shapes, step-count differences, missing or extra steps, wrong agents/actions/handoffs, broken handoff chains, and unterminated trajectories.

## Authority boundary

This workload measures model quality only.

It has no authority to:

- execute an agent or tool;
- authorize a business operation;
- create a `ToolResult`;
- widen the Policy Model Router authorized set;
- change active routing;
- promote its own benchmark snapshot.

The gateway continues to satisfy the project invariant that it may only further restrict policy authorization. Promotion remains explicit, versioned, and reversible through the existing benchmark evidence pipeline.

## Deliberate v1 boundary

v1 evaluates one bounded reviewed trajectory per case.

It does not score:

- hidden chain-of-thought;
- framework-specific state machines;
- autonomous replanning;
- parallel agent execution;
- long-running workflows;
- real human escalation;
- side effects.

Those behaviors require separate contracts and execution authority. Keeping them out of v1 preserves deterministic, credential-free CI and prevents the benchmark layer from becoming an orchestration runtime.
