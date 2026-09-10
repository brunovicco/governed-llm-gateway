"""Authenticated bounded HTTP projections for read-only Gateway operations metadata."""

from datetime import date
from typing import Annotated, Literal, Protocol

from fastapi import FastAPI, Header, HTTPException
from fastapi.routing import APIRoute
from governed_llm_gateway_core.application import OperationsSnapshot
from governed_llm_gateway_core.domain.resilience import HealthStatus
from pydantic import BaseModel, ConfigDict, Field

from .client_auth import GatewayClientIdentity
from .operations_access import OperationsReadAuthorizationError
from .operations_security import OperationsNoStoreMiddleware
from .route_explain import ClientAuthenticationError

_OPERATIONS_OVERVIEW_PATH = "/v1/ops/overview"
_OPERATIONS_DEPLOYMENTS_PATH = "/v1/ops/deployments"


class OperationsHttpCompositionError(RuntimeError):
    """Raised when the operations HTTP surface cannot be attached deterministically."""


class OperationsReadAuthorizer(Protocol):
    """Authorize one Gateway credential for descriptive operations visibility."""

    async def authorize(self, *, api_key: str) -> GatewayClientIdentity:
        """Return the authenticated granted principal or fail closed."""
        ...


class OperationsSnapshotReader(Protocol):
    """Read one already-composed immutable operations snapshot."""

    async def snapshot(self) -> OperationsSnapshot:
        """Return descriptive operations state without I/O or mutation."""
        ...


class OperationsRegistryOverviewModel(BaseModel):
    """Bounded provenance for the active validated registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    catalog_version: str
    source_date: date
    digest: str
    deployment_count: int = Field(ge=0)


class OperationsRankingOverviewModel(BaseModel):
    """Bounded provenance for the active deterministic ranking policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    policy_version: str
    source_date: date
    digest: str
    score_snapshot_id: str
    score_provenance_mode: str | None
    benchmark_snapshot_id: str | None
    promotion_evidence_id: str | None
    manual_override_id: str | None


class OperationsHealthOverviewModel(BaseModel):
    """Aggregate process-local health counts without deployment identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: Literal["process_local"] = "process_local"
    deployment_count: int = Field(ge=0)
    healthy: int = Field(ge=0)
    degraded: int = Field(ge=0)
    unhealthy: int = Field(ge=0)


class OperationsEvidenceOverviewModel(BaseModel):
    """Expose only whether reviewed operational evidence is currently supplied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["not_supplied", "available"]


class OperationsOverviewResponseModel(BaseModel):
    """Bounded aggregate read-only operations API response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registry: OperationsRegistryOverviewModel
    ranking: OperationsRankingOverviewModel
    health: OperationsHealthOverviewModel
    operational_evidence: OperationsEvidenceOverviewModel


class OperationsDeploymentHealthModel(BaseModel):
    """Coarse process-local health without mutable execution counters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["healthy", "degraded", "unhealthy"]
    circuit_state: Literal["closed", "open", "half_open"]


class OperationsDeploymentModel(BaseModel):
    """Bounded operator-visible metadata for one active registry deployment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deployment_id: str
    provider: str
    model_id: str
    model_group: str
    api_family: str
    enabled: bool
    capabilities: tuple[str, ...]
    modalities: tuple[str, ...]
    context_tokens: int = Field(gt=0)
    max_data_classification: str
    allowed_environments: tuple[str, ...]
    pricing_snapshot_version: str | None
    health: OperationsDeploymentHealthModel


class OperationsDeploymentsResponseModel(BaseModel):
    """Authenticated deterministic deployment catalog for operator visibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    health_scope: Literal["process_local"] = "process_local"
    deployments: tuple[OperationsDeploymentModel, ...]


def attach_operations_routes(
    app: FastAPI,
    *,
    access: OperationsReadAuthorizer,
    read_model: OperationsSnapshotReader,
) -> None:
    """Attach the owned authenticated Operations routes atomically and exactly once."""
    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI application")
    existing_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    owned_paths = {_OPERATIONS_OVERVIEW_PATH, _OPERATIONS_DEPLOYMENTS_PATH}
    conflicts = sorted(existing_paths & owned_paths)
    if conflicts:
        raise OperationsHttpCompositionError(
            f"operations route already attached: {', '.join(conflicts)}"
        )

    app.add_middleware(OperationsNoStoreMiddleware)

    @app.get(
        _OPERATIONS_OVERVIEW_PATH,
        response_model=OperationsOverviewResponseModel,
        tags=["operations"],
    )
    async def operations_overview(
        gateway_api_key: Annotated[
            str | None,
            Header(alias="X-Gateway-API-Key"),
        ] = None,
    ) -> OperationsOverviewResponseModel:
        snapshot = await _authorize_and_read_snapshot(
            gateway_api_key=gateway_api_key,
            access=access,
            read_model=read_model,
        )
        try:
            return _overview_response(snapshot)
        except RuntimeError as exc:
            raise _snapshot_unavailable() from exc

    @app.get(
        _OPERATIONS_DEPLOYMENTS_PATH,
        response_model=OperationsDeploymentsResponseModel,
        tags=["operations"],
    )
    async def operations_deployments(
        gateway_api_key: Annotated[
            str | None,
            Header(alias="X-Gateway-API-Key"),
        ] = None,
    ) -> OperationsDeploymentsResponseModel:
        snapshot = await _authorize_and_read_snapshot(
            gateway_api_key=gateway_api_key,
            access=access,
            read_model=read_model,
        )
        return _deployments_response(snapshot)


async def _authorize_and_read_snapshot(
    *,
    gateway_api_key: str | None,
    access: OperationsReadAuthorizer,
    read_model: OperationsSnapshotReader,
) -> OperationsSnapshot:
    if gateway_api_key is None:
        raise _invalid_gateway_credential()
    try:
        await access.authorize(api_key=gateway_api_key)
    except ClientAuthenticationError as exc:
        raise _invalid_gateway_credential() from exc
    except OperationsReadAuthorizationError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "operations_read_access_denied"},
        ) from exc

    try:
        return await read_model.snapshot()
    except RuntimeError as exc:
        raise _snapshot_unavailable() from exc


def _invalid_gateway_credential() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"code": "invalid_gateway_credential"},
    )


def _snapshot_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "operations_snapshot_unavailable"},
    )


def _overview_response(snapshot: OperationsSnapshot) -> OperationsOverviewResponseModel:
    counts = {
        HealthStatus.HEALTHY: 0,
        HealthStatus.DEGRADED: 0,
        HealthStatus.UNHEALTHY: 0,
    }
    for deployment in snapshot.deployments:
        counts[deployment.health.status] += 1

    counted = sum(counts.values())
    if counted != snapshot.registry.deployment_count:
        raise RuntimeError("operations overview health count does not match registry")

    return OperationsOverviewResponseModel(
        registry=OperationsRegistryOverviewModel(
            schema_version=snapshot.registry.schema_version,
            catalog_version=snapshot.registry.catalog_version,
            source_date=snapshot.registry.source_date,
            digest=snapshot.registry.digest,
            deployment_count=snapshot.registry.deployment_count,
        ),
        ranking=OperationsRankingOverviewModel(
            schema_version=snapshot.ranking.schema_version,
            policy_version=snapshot.ranking.policy_version,
            source_date=snapshot.ranking.source_date,
            digest=snapshot.ranking.digest,
            score_snapshot_id=snapshot.ranking.score_snapshot_id,
            score_provenance_mode=snapshot.ranking.score_provenance_mode,
            benchmark_snapshot_id=snapshot.ranking.benchmark_snapshot_id,
            promotion_evidence_id=snapshot.ranking.promotion_evidence_id,
            manual_override_id=snapshot.ranking.manual_override_id,
        ),
        health=OperationsHealthOverviewModel(
            scope=snapshot.health_scope.value,
            deployment_count=counted,
            healthy=counts[HealthStatus.HEALTHY],
            degraded=counts[HealthStatus.DEGRADED],
            unhealthy=counts[HealthStatus.UNHEALTHY],
        ),
        operational_evidence=OperationsEvidenceOverviewModel(
            state=snapshot.operational_evidence.state.value,
        ),
    )


def _deployments_response(snapshot: OperationsSnapshot) -> OperationsDeploymentsResponseModel:
    deployments = tuple(
        OperationsDeploymentModel(
            deployment_id=deployment.deployment_id,
            provider=deployment.provider,
            model_id=deployment.model_id,
            model_group=deployment.model_group,
            api_family=deployment.api_family,
            enabled=deployment.enabled,
            capabilities=deployment.capabilities,
            modalities=deployment.modalities,
            context_tokens=deployment.context_tokens,
            max_data_classification=deployment.max_data_classification,
            allowed_environments=deployment.allowed_environments,
            pricing_snapshot_version=deployment.pricing_snapshot_version,
            health=OperationsDeploymentHealthModel(
                status=deployment.health.status.value,
                circuit_state=deployment.health.circuit_state.value,
            ),
        )
        for deployment in snapshot.deployments
    )
    return OperationsDeploymentsResponseModel(
        health_scope=snapshot.health_scope.value,
        deployments=deployments,
    )
