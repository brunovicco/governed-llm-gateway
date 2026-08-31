"""Infrastructure adapters owned by gateway-core."""

from .model_registry_yaml import load_model_registry, load_model_registry_text

__all__ = ["load_model_registry", "load_model_registry_text"]
