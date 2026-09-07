"""FastAPI composition-root surfaces for the Governed LLM Gateway."""

from .application import create_gateway_app
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
from .client_auth_json import (
    DuplicateGatewayClientAuthKeyError,
    GatewayClientAuthDocument,
    GatewayClientAuthDocumentError,
    load_gateway_client_auth_document,
    load_gateway_client_auth_document_text,
)
from .complexity_evidence import (
    ComplexityAssessmentExplainModel,
    ComplexityExplainModel,
    ComplexityHttpEvidenceInvariantViolation,
    ComplexityNarrowingExplainModel,
    complexity_evidence_from_decision,
)
from .complexity_generate import ComplexityGenerateCoordinator
from .gateway_runtime_bootstrap import (
    GatewayRuntimeBootstrapBundle,
    GatewayRuntimeBootstrapPaths,
    bootstrap_gateway_runtime,
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
    "ComplexityGenerateCoordinator",
    "ComplexityHttpEvidenceInvariantViolation",
    "ComplexityNarrowingExplainModel",
    "ComplexityRouteExplainCoordinator",
    "ComplexityRouteExplainResponseModel",
    "DuplicateGatewayClientAuthKeyError",
    "EffectiveContextResolver",
    "EnvironmentGatewayClientSecretResolver",
    "GatewayClientAuthBinding",
    "GatewayClientAuthDocument",
    "GatewayClientAuthDocumentError",
    "GatewayClientAuthenticationConfigurationError",
    "GatewayClientAuthorizationError",
    "GatewayClientSecretResolutionError",
    "GatewayClientSecretResolver",
    "GatewayRuntimeBootstrapBundle",
    "GatewayRuntimeBootstrapPaths",
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
    "bootstrap_gateway_runtime",
    "bootstrap_provider_runtime",
    "build_static_gateway_client_context_resolver",
    "complexity_evidence_from_decision",
    "create_app",
    "create_gateway_app",
    "load_gateway_client_auth_document",
    "load_gateway_client_auth_document_text",
]
