import type {
  CircuitState,
  EvidenceState,
  HealthStatus,
  OperationsDeployment,
  OperationsDeployments,
  OperationsOverview,
} from "./types";

export class OperationsResponseValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OperationsResponseValidationError";
  }
}

const HEALTH_STATUSES = ["healthy", "degraded", "unhealthy"] as const;
const CIRCUIT_STATES = ["closed", "open", "half_open"] as const;
const EVIDENCE_STATES = ["not_supplied", "available"] as const;

export function decodeOverview(value: unknown): OperationsOverview {
  const root = asObject(value, "overview");
  assertExactKeys(root, ["registry", "ranking", "health", "operational_evidence"], "overview");

  const registry = asObject(root.registry, "overview.registry");
  assertExactKeys(
    registry,
    ["schema_version", "catalog_version", "source_date", "digest", "deployment_count"],
    "overview.registry",
  );

  const ranking = asObject(root.ranking, "overview.ranking");
  assertExactKeys(
    ranking,
    [
      "schema_version",
      "policy_version",
      "source_date",
      "digest",
      "score_snapshot_id",
      "score_provenance_mode",
      "benchmark_snapshot_id",
      "promotion_evidence_id",
      "manual_override_id",
    ],
    "overview.ranking",
  );

  const health = asObject(root.health, "overview.health");
  assertExactKeys(
    health,
    ["scope", "deployment_count", "healthy", "degraded", "unhealthy"],
    "overview.health",
  );

  const evidence = asObject(root.operational_evidence, "overview.operational_evidence");
  assertExactKeys(evidence, ["state"], "overview.operational_evidence");

  const deploymentCount = nonNegativeInteger(registry.deployment_count, "overview.registry.deployment_count");
  const healthDeploymentCount = nonNegativeInteger(
    health.deployment_count,
    "overview.health.deployment_count",
  );
  const healthy = nonNegativeInteger(health.healthy, "overview.health.healthy");
  const degraded = nonNegativeInteger(health.degraded, "overview.health.degraded");
  const unhealthy = nonNegativeInteger(health.unhealthy, "overview.health.unhealthy");

  if (deploymentCount !== healthDeploymentCount || healthy + degraded + unhealthy !== deploymentCount) {
    throw new OperationsResponseValidationError("overview deployment counts are inconsistent");
  }

  return {
    registry: {
      schema_version: nonEmptyString(registry.schema_version, "overview.registry.schema_version"),
      catalog_version: nonEmptyString(registry.catalog_version, "overview.registry.catalog_version"),
      source_date: isoDate(registry.source_date, "overview.registry.source_date"),
      digest: nonEmptyString(registry.digest, "overview.registry.digest"),
      deployment_count: deploymentCount,
    },
    ranking: {
      schema_version: nonEmptyString(ranking.schema_version, "overview.ranking.schema_version"),
      policy_version: nonEmptyString(ranking.policy_version, "overview.ranking.policy_version"),
      source_date: isoDate(ranking.source_date, "overview.ranking.source_date"),
      digest: nonEmptyString(ranking.digest, "overview.ranking.digest"),
      score_snapshot_id: nonEmptyString(ranking.score_snapshot_id, "overview.ranking.score_snapshot_id"),
      score_provenance_mode: nullableString(
        ranking.score_provenance_mode,
        "overview.ranking.score_provenance_mode",
      ),
      benchmark_snapshot_id: nullableString(
        ranking.benchmark_snapshot_id,
        "overview.ranking.benchmark_snapshot_id",
      ),
      promotion_evidence_id: nullableString(
        ranking.promotion_evidence_id,
        "overview.ranking.promotion_evidence_id",
      ),
      manual_override_id: nullableString(
        ranking.manual_override_id,
        "overview.ranking.manual_override_id",
      ),
    },
    health: {
      scope: exactLiteral(health.scope, ["process_local"] as const, "overview.health.scope"),
      deployment_count: healthDeploymentCount,
      healthy,
      degraded,
      unhealthy,
    },
    operational_evidence: {
      state: exactLiteral(
        evidence.state,
        EVIDENCE_STATES,
        "overview.operational_evidence.state",
      ) satisfies EvidenceState,
    },
  };
}

export function decodeDeployments(value: unknown): OperationsDeployments {
  const root = asObject(value, "deployments");
  assertExactKeys(root, ["health_scope", "deployments"], "deployments");
  if (!Array.isArray(root.deployments)) {
    throw new OperationsResponseValidationError("deployments.deployments must be an array");
  }

  return {
    health_scope: exactLiteral(root.health_scope, ["process_local"] as const, "deployments.health_scope"),
    deployments: root.deployments.map((entry, index) => decodeDeployment(entry, index)),
  };
}

function decodeDeployment(value: unknown, index: number): OperationsDeployment {
  const path = `deployments.deployments[${index}]`;
  const deployment = asObject(value, path);
  assertExactKeys(
    deployment,
    [
      "deployment_id",
      "provider",
      "model_id",
      "model_group",
      "api_family",
      "enabled",
      "capabilities",
      "modalities",
      "context_tokens",
      "max_data_classification",
      "allowed_environments",
      "pricing_snapshot_version",
      "health",
    ],
    path,
  );

  const health = asObject(deployment.health, `${path}.health`);
  assertExactKeys(health, ["status", "circuit_state"], `${path}.health`);

  return {
    deployment_id: nonEmptyString(deployment.deployment_id, `${path}.deployment_id`),
    provider: nonEmptyString(deployment.provider, `${path}.provider`),
    model_id: nonEmptyString(deployment.model_id, `${path}.model_id`),
    model_group: nonEmptyString(deployment.model_group, `${path}.model_group`),
    api_family: nonEmptyString(deployment.api_family, `${path}.api_family`),
    enabled: booleanValue(deployment.enabled, `${path}.enabled`),
    capabilities: stringArray(deployment.capabilities, `${path}.capabilities`),
    modalities: stringArray(deployment.modalities, `${path}.modalities`),
    context_tokens: positiveInteger(deployment.context_tokens, `${path}.context_tokens`),
    max_data_classification: nonEmptyString(
      deployment.max_data_classification,
      `${path}.max_data_classification`,
    ),
    allowed_environments: stringArray(deployment.allowed_environments, `${path}.allowed_environments`),
    pricing_snapshot_version: nullableString(
      deployment.pricing_snapshot_version,
      `${path}.pricing_snapshot_version`,
    ),
    health: {
      status: exactLiteral(health.status, HEALTH_STATUSES, `${path}.health.status`) satisfies HealthStatus,
      circuit_state: exactLiteral(
        health.circuit_state,
        CIRCUIT_STATES,
        `${path}.health.circuit_state`,
      ) satisfies CircuitState,
    },
  };
}

function asObject(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new OperationsResponseValidationError(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function assertExactKeys(object: Record<string, unknown>, expected: readonly string[], path: string): void {
  const actual = Object.keys(object).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new OperationsResponseValidationError(`${path} contains an unexpected response shape`);
  }
}

function nonEmptyString(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new OperationsResponseValidationError(`${path} must be a non-empty string`);
  }
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  if (value === null) {
    return null;
  }
  return nonEmptyString(value, path);
}

function isoDate(value: unknown, path: string): string {
  const date = nonEmptyString(value, path);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    throw new OperationsResponseValidationError(`${path} must be an ISO date`);
  }

  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(5, 7));
  const day = Number(date.slice(8, 10));
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  ) {
    throw new OperationsResponseValidationError(`${path} must be a valid calendar date`);
  }
  return date;
}

function nonNegativeInteger(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new OperationsResponseValidationError(`${path} must be a non-negative integer`);
  }
  return value;
}

function positiveInteger(value: unknown, path: string): number {
  const integer = nonNegativeInteger(value, path);
  if (integer === 0) {
    throw new OperationsResponseValidationError(`${path} must be greater than zero`);
  }
  return integer;
}

function booleanValue(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    throw new OperationsResponseValidationError(`${path} must be a boolean`);
  }
  return value;
}

function stringArray(value: unknown, path: string): readonly string[] {
  if (!Array.isArray(value)) {
    throw new OperationsResponseValidationError(`${path} must be an array`);
  }
  return value.map((entry, index) => nonEmptyString(entry, `${path}[${index}]`));
}

function exactLiteral<const T extends readonly string[]>(
  value: unknown,
  allowed: T,
  path: string,
): T[number] {
  if (typeof value !== "string" || !allowed.includes(value)) {
    throw new OperationsResponseValidationError(`${path} contains an unsupported value`);
  }
  return value;
}
