"""FastAPI composition-root surfaces for the Governed LLM Gateway."""

from .client_auth import (
    EnvironmentGatewayClientSecretResolver,
    GatewayClientAuthBinding,
    GatewayClientAuthenticationConfigurationError,
    GatewayClientAuthorizationError,
    GatewayClientSecretResolutionError,
    GatewayClientSecretResolver,
    StaticGatewayClientContextResolver,
    build_static_gateway_client_context_resolver,
)
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
    "EnvironmentGatewayClientSecretResolver",
    "GatewayClientAuthBinding",
    "GatewayClientAuthenticationConfigurationError",
    "GatewayClientAuthorizationError",
    "GatewayClientSecretResolutionError",
    "GatewayClientSecretResolver",
    "GenerateCoordinator",
    "GenerateRequestModel",
    "PreparedStreamingExecution",
    "ProviderRuntimeBootstrapBundle",
    "ProviderRuntimeBootstrapPaths",
    "RouteExplainCoordinator",
    "RouteExplainRequestModel",
    "RouteExplainResponseModel",
    "StaticGatewayClientContextResolver",
    "attach_generate_route",
    "bootstrap_provider_runtime",
    "build_static_gateway_client_context_resolver",
    "complexity_evidence_from_decision",
    "create_app",
]
