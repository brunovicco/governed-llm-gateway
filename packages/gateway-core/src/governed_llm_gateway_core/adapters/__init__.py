"""Infrastructure adapters owned by gateway-core."""

from .anthropic import AnthropicMessagesAdapter
from .gemini import GeminiAdapter
from .governance_authorization import (
    GovernanceAuthorizationVerificationError,
    StaticGovernanceKeyResolver,
    verify_governance_authorization_text,
)
from .model_registry_yaml import load_model_registry, load_model_registry_text
from .openai_compatible import OpenAICompatibleAdapter
from .openai_responses import OpenAIResponsesAdapter
from .policy_router import PolicyRouterHttpAdapter, StdlibPolicyTransport
from .ranking_policy_yaml import load_ranking_policy, load_ranking_policy_text

__all__ = [
    "AnthropicMessagesAdapter",
    "GeminiAdapter",
    "GovernanceAuthorizationVerificationError",
    "OpenAICompatibleAdapter",
    "OpenAIResponsesAdapter",
    "PolicyRouterHttpAdapter",
    "StaticGovernanceKeyResolver",
    "StdlibPolicyTransport",
    "load_model_registry",
    "load_model_registry_text",
    "load_ranking_policy",
    "load_ranking_policy_text",
    "verify_governance_authorization_text",
]
