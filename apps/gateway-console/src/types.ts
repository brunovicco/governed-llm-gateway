export type HealthStatus = "healthy" | "degraded" | "unhealthy";
export type CircuitState = "closed" | "open" | "half_open";
export type EvidenceState = "not_supplied" | "available";

export interface OperationsRegistryOverview {
  schema_version: string;
  catalog_version: string;
  source_date: string;
  digest: string;
  deployment_count: number;
}

export interface OperationsRankingOverview {
  schema_version: string;
  policy_version: string;
  source_date: string;
  digest: string;
  score_snapshot_id: string;
  score_provenance_mode: string | null;
  benchmark_snapshot_id: string | null;
  promotion_evidence_id: string | null;
  manual_override_id: string | null;
}

export interface OperationsHealthOverview {
  scope: "process_local";
  deployment_count: number;
  healthy: number;
  degraded: number;
  unhealthy: number;
}

export interface OperationsOverview {
  registry: OperationsRegistryOverview;
  ranking: OperationsRankingOverview;
  health: OperationsHealthOverview;
  operational_evidence: {
    state: EvidenceState;
  };
}

export interface OperationsDeployment {
  deployment_id: string;
  provider: string;
  model_id: string;
  model_group: string;
  api_family: string;
  enabled: boolean;
  capabilities: readonly string[];
  modalities: readonly string[];
  context_tokens: number;
  max_data_classification: string;
  allowed_environments: readonly string[];
  pricing_snapshot_version: string | null;
  health: {
    status: HealthStatus;
    circuit_state: CircuitState;
  };
}

export interface OperationsDeployments {
  health_scope: "process_local";
  deployments: readonly OperationsDeployment[];
}

export interface OperationsConsoleSnapshot {
  overview: OperationsOverview;
  deployments: OperationsDeployments;
}
