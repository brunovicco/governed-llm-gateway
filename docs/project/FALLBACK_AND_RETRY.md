# Fallback and Retry

Retry and fallback are different operations.

- retry: same deployment, transient failure only;
- fallback: different eligible deployment, still inside already-authorized policy boundaries.

Default safety model:

- transport/rate-limit failure before model output: fallback may be allowed;
- schema failure without side effect: bounded repair/retry may be allowed;
- tool call generated but not executed: conservative explicit policy;
- external side effect executed: no automatic cross-provider fallback;
- opaque provider reasoning/state established: no cross-provider continuation unless an explicit,
  tested replay strategy supports it.

Idempotency/execution state must be represented by the orchestration layer before runtime fallback is
implemented. Availability never grants additional authorization.
