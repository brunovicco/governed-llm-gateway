# Routing

## Stage A — deterministic authorization

The Policy Model Router receives policy metadata and returns authorized logical model group(s) with
decision provenance. It does not receive prompt/message payloads and performs no inference.

## Stage B — operational selection

The gateway considers only deployments inside authorization, then filters by enabled state,
capabilities, context, environment/data policy, health/circuit state, cost, and latency constraints.
Only eligible deployments are ranked.

## Determinism

Initial ranking is deterministic and explainable. Ties must have a stable explicit tie-breaker.
Benchmark and ranking-policy versions are evidence inputs.

## Explainability

Future explain output includes authorized group, selected deployment, policy provenance, score inputs,
and machine-readable rejection reasons. Explainability does not invoke an LLM and is itself an
authorized surface.
