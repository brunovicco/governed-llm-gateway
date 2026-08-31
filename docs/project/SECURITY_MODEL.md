# Security Model

## Assets

Provider credentials, authorization decisions, model registry/ranking policy, workload identity,
prompt/customer payload, routing provenance, operational health, and cost budgets.

## Trust boundaries

1. consumer → gateway authentication;
2. gateway → Policy Model Router;
3. gateway configuration/registry supply chain;
4. gateway → provider;
5. gateway telemetry/evidence sinks;
6. future admin/explain/catalog surfaces.

## Authorization

Identity and policy failures fail closed. Operational availability failures may fail over only inside
already-authorized groups/deployments.

Caller metadata can request stricter constraints but cannot downgrade authoritative classification,
risk, environment, or policy authorization.

## Secrets

Consumers receive only gateway credentials. Provider keys never enter request contracts, registry,
ranking policy, logs, traces, benchmark artifacts, or error responses.

## Runtime privacy

Metadata-only evidence is the default. Payload capture is out of the Phase 0 design and must not be
introduced implicitly by SDK logging, exception serialization, middleware, or telemetry exporters.
