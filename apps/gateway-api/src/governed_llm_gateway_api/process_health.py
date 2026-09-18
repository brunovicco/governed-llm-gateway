"""Bootstrap-derived process liveness and readiness HTTP surfaces."""

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict


class ProcessHealthCompositionError(RuntimeError):
    """Raised when process-health routes cannot be attached deterministically."""


class ProcessLiveResponse(BaseModel):
    """Bounded liveness response for an already-serving Gateway process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["live"] = "live"


class ProcessReadyResponse(BaseModel):
    """Bounded readiness response proving successful pre-server bootstrap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready"] = "ready"


def attach_process_health_routes(
    app: FastAPI, *, readiness: Callable[[], bool] | None = None
) -> None:
    """Attach process-only health routes exactly once without dependency probing."""
    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI application")
    existing_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    conflicts = sorted(existing_paths & {"/livez", "/readyz"})
    if conflicts:
        raise ProcessHealthCompositionError(
            f"process health route already attached: {', '.join(conflicts)}"
        )

    @app.get("/livez", response_model=ProcessLiveResponse, tags=["health"])
    async def live() -> ProcessLiveResponse:
        return ProcessLiveResponse()

    @app.get("/readyz", response_model=ProcessReadyResponse, tags=["health"])
    async def ready() -> ProcessReadyResponse:
        if readiness is not None and not readiness():
            raise HTTPException(status_code=503, detail={"code": "policy_transport_not_ready"})
        return ProcessReadyResponse()
