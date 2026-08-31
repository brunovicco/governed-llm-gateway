"""Trust-boundary types for caller claims and authoritative workload context."""

from dataclasses import dataclass

from governed_llm_gateway_contracts import DataClassification, RiskLevel


@dataclass(frozen=True, slots=True)
class AuthenticatedWorkloadIdentity:
    """Identity facts established by the gateway authentication boundary."""

    client_id: str
    environment: str
    minimum_data_classification: DataClassification
    maximum_risk_level: RiskLevel
    allowed_workloads: frozenset[str]


@dataclass(frozen=True, slots=True)
class EffectivePolicyContext:
    """Authoritative policy context after validating caller-declared metadata."""

    client_id: str
    environment: str
    workload: str
    risk_level: RiskLevel
    data_classification: DataClassification
