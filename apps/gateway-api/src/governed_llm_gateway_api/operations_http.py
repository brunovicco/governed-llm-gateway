"""Authenticated bounded HTTP projection for read-only Gateway operations metadata."""

from datetime import date
from typing import Annotated, Literal, Protocol

from fastapi import FastAPI, Header, HTTPException
from fastapi.routing import APIRoute
from governed_llm_gateway_core.application import OperationsSnapshot
from governed_llm_gateway_core.domain.resilience import HealthStatus
from pydantic import BaseModel, ConfigDict, Field

from .client_auth import GatewayClientIdentity
from .operations_access import OperationsReadAuthorizationError
from .route_explain import ClientAuthenticationError

_OPERATIONS_OVERVIEW_PATH = "/v1/ops/overview"


class OperationsHttpCompositionError(RuntimeError):
    """Raised when the operations HTTP surface cannot be attached deterministically."""


class OperationsReadAuthorizer(Protocol):
    """Authorize one Gateway credential for descriptive operations visibility."""

    async def authorize(self, *, api_key: str) -> GatewayClientIdentity:
        """Return the authenticated granted principal or fail closed."""
        ...


class OperationsSnapshotReader(Protocol):
    """Read one already-composed immutable operations snapshot."""

    def snapshot(self) -> OperationsSnapshot:
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
    """First bounded read-only operations API response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registry: OperationsRegistryOverviewModel
    ranking: OperationsRankingOverviewModel
    health: OperationsHealthOverviewModel
    operational_evidence: OperationsEvidenceOverviewModel


def attach_operations_routes(
    app: FastAPI,
    *,
    access: OperationsReadAuthorizer,
    read_model: OperationsSnapshotReader,
) -> None:
    """Attach the authenticated operations overview exactly once."""
    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI application")
    existing_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    if _OPERATIONS_OVERVIEW_PATH in existing_paths:
        raise OperationsHttpCompositionError("operations overview route already attached")

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
            snapshot = read_model.snapshot()
            return _overview_response(snapshot)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "operations_snapshot_unavailable"},
            ) from exc


def _invalid_gateway_credential() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"code": "invalid_gateway_credential"},
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
