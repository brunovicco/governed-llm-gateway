"""FastAPI composition-root surfaces for the Governed LLM Gateway."""

from .complexity_evidence import (
    ComplexityAssessmentExplainModel,
    ComplexityExplainModel,
    ComplexityHttpEvidenceInvariantViolation,
    ComplexityNarrowingExplainModel,
    complexity_evidence_from_decision,
)
from .provider_bootstrap import (
    ProviderRuntimeBootstrapBundle,
    ProviderRuntimeBootstrapPaths,
    bootstrap_provider_runtime,
)
from .route_explain import (
    ClientAuthenticationError,
    ComplexityRouteExplainCoordinator,
    ComplexityRouteExplainResponseModel,
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
    "ComplexityAssessmentExplainModel",
    "ComplexityExplainModel",
    "ComplexityHttpEvidenceInvariantViolation",
    "ComplexityNarrowingExplainModel",
    "ComplexityRouteExplainCoordinator",
    "ComplexityRouteExplainResponseModel",
    "EffectiveContextResolver",
    "GenerateCoordinator",
    "GenerateRequestModel",
    "PreparedStreamingExecution",
    "ProviderRuntimeBootstrapBundle",
    "ProviderRuntimeBootstrapPaths",
    "RouteExplainCoordinator",
    "RouteExplainRequestModel",
    "RouteExplainResponseModel",
    "attach_generate_route",
    "bootstrap_provider_runtime",
    "complexity_evidence_from_decision",
    "create_app",
]
