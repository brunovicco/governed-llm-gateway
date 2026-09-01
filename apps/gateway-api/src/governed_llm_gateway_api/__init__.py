"""FastAPI composition-root surfaces for the Governed LLM Gateway."""

from .route_explain import (
    ClientAuthenticationError,
    EffectiveContextResolver,
    RouteExplainCoordinator,
    RouteExplainRequestModel,
    RouteExplainResponseModel,
    create_app,
)
from .stream_generate import (
    GenerateCoordinator,
    GenerateRequestModel,
    PreparedStreamingExecution,
    attach_generate_route,
)

__all__ = [
    "ClientAuthenticationError",
    "EffectiveContextResolver",
    "GenerateCoordinator",
    "GenerateRequestModel",
    "PreparedStreamingExecution",
    "RouteExplainCoordinator",
    "RouteExplainRequestModel",
    "RouteExplainResponseModel",
    "attach_generate_route",
    "create_app",
]
