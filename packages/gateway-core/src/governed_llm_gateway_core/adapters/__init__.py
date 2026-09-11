"""Infrastructure adapters owned by gateway-core."""

from .anthropic import AnthropicMessagesAdapter
from .approved_ranking_artifact_json import (
    ApprovedRankingArtifactDocumentError,
    DuplicateApprovedRankingArtifactKeyError,
    dump_approved_ranking_artifact_text,
    load_approved_ranking_artifact,
    load_approved_ranking_artifact_text,
)
from .complexity_routing_json import (
    ComplexityRoutingDocument,
    ComplexityRoutingDocumentError,
    DuplicateComplexityRoutingKeyError,
    load_complexity_routing_document,
    load_complexity_routing_document_text,
)
from .gemini import GeminiAdapter
from .governance_authorization import (
    GovernanceAuthorizationVerificationError,
    StaticGovernanceKeyResolver,
    verify_governance_authorization_envelope,
    verify_governance_authorization_text,
)
from .model_registry_yaml import load_model_registry, load_model_registry_text
from .openai_compatible import OpenAICompatibleAdapter
from .openai_responses import OpenAIResponsesAdapter
from .policy_router import PolicyRouterHttpAdapter, StdlibPolicyTransport
from .policy_router_runtime import (
    EnvironmentPolicyRouterSecretResolver,
    PolicyRouterCredentialBinding,
    PolicyRouterRuntimeConfig,
    PolicyRouterRuntimeConfigurationError,
    PolicyRouterSecretResolutionError,
    PolicyRouterSecretResolver,
    build_policy_router_adapter,
)
from .policy_router_runtime_json import (
    DuplicatePolicyRouterRuntimeKeyError,
    PolicyRouterRuntimeDocument,
    PolicyRouterRuntimeDocumentError,
    load_policy_router_runtime_document,
    load_policy_router_runtime_document_text,
)
from .provider_runtime import (
    EnvironmentProviderSecretResolver,
    OpenAICompatibleRuntimeOptions,
    ProviderApiFamily,
    ProviderRuntimeConfig,
    ProviderRuntimeConfigurationError,
    ProviderSecretResolutionError,
    ProviderSecretResolver,
    build_static_provider_resolver,
)
from .provider_runtime_json import (
    DuplicateProviderRuntimeKeyError,
    ProviderRuntimeDocument,
    ProviderRuntimeDocumentError,
    ProviderRuntimeRegistryMismatchError,
    load_provider_runtime_document,
    load_provider_runtime_document_text,
    validate_provider_runtime_registry,
)
from .ranking_policy_yaml import load_ranking_policy, load_ranking_policy_text

__all__ = [
    "AnthropicMessagesAdapter",
    "ApprovedRankingArtifactDocumentError",
    "ComplexityRoutingDocument",
    "ComplexityRoutingDocumentError",
    "DuplicateApprovedRankingArtifactKeyError",
    "DuplicateComplexityRoutingKeyError",
    "DuplicatePolicyRouterRuntimeKeyError",
    "DuplicateProviderRuntimeKeyError",
    "EnvironmentPolicyRouterSecretResolver",
    "EnvironmentProviderSecretResolver",
    "GeminiAdapter",
    "GovernanceAuthorizationVerificationError",
    "OpenAICompatibleAdapter",
    "OpenAICompatibleRuntimeOptions",
    "OpenAIResponsesAdapter",
    "PolicyRouterCredentialBinding",
    "PolicyRouterHttpAdapter",
    "PolicyRouterRuntimeConfig",
    "PolicyRouterRuntimeConfigurationError",
    "PolicyRouterRuntimeDocument",
    "PolicyRouterRuntimeDocumentError",
    "PolicyRouterSecretResolutionError",
    "PolicyRouterSecretResolver",
    "ProviderApiFamily",
    "ProviderRuntimeConfig",
    "ProviderRuntimeConfigurationError",
    "ProviderRuntimeDocument",
    "ProviderRuntimeDocumentError",
    "ProviderRuntimeRegistryMismatchError",
    "ProviderSecretResolutionError",
    "ProviderSecretResolver",
    "StaticGovernanceKeyResolver",
    "StdlibPolicyTransport",
    "build_policy_router_adapter",
    "build_static_provider_resolver",
    "dump_approved_ranking_artifact_text",
    "load_approved_ranking_artifact",
    "load_approved_ranking_artifact_text",
    "load_complexity_routing_document",
    "load_complexity_routing_document_text",
    "load_model_registry",
    "load_model_registry_text",
    "load_policy_router_runtime_document",
    "load_policy_router_runtime_document_text",
    "load_provider_runtime_document",
    "load_provider_runtime_document_text",
    "load_ranking_policy",
    "load_ranking_policy_text",
    "validate_provider_runtime_registry",
    "verify_governance_authorization_envelope",
    "verify_governance_authorization_text",
]
