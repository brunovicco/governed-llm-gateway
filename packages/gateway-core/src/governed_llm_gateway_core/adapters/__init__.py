"""Infrastructure adapters owned by gateway-core."""

from .anthropic import AnthropicMessagesAdapter
from .gemini import GeminiAdapter
from .model_registry_yaml import load_model_registry, load_model_registry_text
from .openai_compatible import OpenAICompatibleAdapter
from .openai_responses import OpenAIResponsesAdapter
from .policy_router import PolicyRouterHttpAdapter, StdlibPolicyTransport

__all__ = [
    "AnthropicMessagesAdapter",
    "GeminiAdapter",
    "OpenAICompatibleAdapter",
    "OpenAIResponsesAdapter",
    "PolicyRouterHttpAdapter",
    "StdlibPolicyTransport",
    "load_model_registry",
    "load_model_registry_text",
]
