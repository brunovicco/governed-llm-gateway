"""FastAPI composition-root surfaces for the Governed LLM Gateway."""

from .complexity_evidence import (
    ComplexityAssessmentExplainModel,
    ComplexityExplainModel,
    ComplexityHttpEvidenceInvariantViolation,
    ComplexityNarrowingExplainModel,
    complexity_evidence_from_decision,
)
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
    "ComplexityAssessmentExplainModel",
    "ComplexityExplainModel",
    "ComplexityHttpEvidenceInvariantViolation",
    "ComplexityNarrowingExplainModel",
    "EffectiveContextResolver",
    "GenerateCoordinator",
    "GenerateRequestModel",
    "PreparedStreamingExecution",
    "RouteExplainCoordinator",
    "RouteExplainRequestModel",
    "RouteExplainResponseModel",
    "attach_generate_route",
    "complexity_evidence_from_decision",
    "create_app",
]
