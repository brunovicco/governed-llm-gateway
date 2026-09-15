# ADR-0016: Pull a pinned external Policy Router for governed Compose

- Status: Accepted
- Date: 2026-09-15

## Context

The previous governed Compose profile required a separately running or sibling checkout of Policy
Model Router. That was useful for cross-repository development but made the normal operator path
require two clones. Copying Router code into this repository would violate the authority boundary.

## Decision

The normal `governed` profile pulls Policy Model Router `0.5.0` by its multi-platform manifest digest
and mounts deployment-owned policy configuration. The Gateway still builds locally. The services
share one network namespace so the Gateway reaches the Router over literal loopback without
weakening the runtime's HTTPS-or-loopback transport rule. Both run read-only, without Linux
capabilities, with loopback-only host ports and readiness ordering.

The sibling-source `compose.pdp-composition.yml` remains the development/composition-test workflow.
No Router implementation or authorization logic is imported or copied into the Gateway.

## Consequences

- Operators clone only the Gateway repository for normal local governed startup.
- Updating the Router requires an explicit reviewed version and digest change.
- The local policy file is configuration owned by the deployment; Policy Model Router remains the
  external PDP and sole authority over the model groups it returns.
