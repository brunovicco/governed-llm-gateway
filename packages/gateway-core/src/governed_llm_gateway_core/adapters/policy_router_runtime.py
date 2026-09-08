"""Deployment-owned Policy Router runtime configuration and secret composition."""

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypeGuard
from urllib.parse import urlsplit

from .policy_router import PolicyRouterHttpAdapter
from .policy_router_loopback import LoopbackHttpPolicyTransport, is_literal_loopback_host

_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ENV_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_MAX_CREDENTIAL_REFERENCE_LENGTH = 256
_MAX_CREDENTIAL_LENGTH = 4096
_MAX_TIMEOUT_SECONDS = 300.0


class PolicyRouterRuntimeConfigurationError(ValueError):
    """Raised when deployment-owned Policy Router runtime configuration is invalid."""


class PolicyRouterSecretResolutionError(RuntimeError):
    """Raised when a configured Policy Router credential cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class PolicyRouterCredentialBinding:
    """Secret-free mapping from one trusted Gateway client to one PDP credential reference."""

    client_id: str
    credential_reference: str

    def __post_init__(self) -> None:
        """Validate identity and secret reference without resolving credential material."""
        if not isinstance(self.client_id, str) or _IDENTIFIER.fullmatch(self.client_id) is None:
            raise PolicyRouterRuntimeConfigurationError(
                "Policy Router client_id must be a normalized identifier"
            )
        _validate_credential_reference(self.credential_reference)


@dataclass(frozen=True, slots=True)
class PolicyRouterRuntimeConfig:
    """Validated secret-free configuration for the Policy Router HTTP adapter."""

    enabled: bool
    endpoint: str | None
    timeout_seconds: float
    bindings: tuple[PolicyRouterCredentialBinding, ...]

    def __post_init__(self) -> None:
        """Fail closed on incoherent activation, endpoint, timeout, or client bindings."""
        if not isinstance(self.enabled, bool):
            raise PolicyRouterRuntimeConfigurationError("enabled must be boolean")
        _validate_timeout(self.timeout_seconds)
        _validate_bindings(self.bindings)

        if self.enabled:
            if self.endpoint is None:
                raise PolicyRouterRuntimeConfigurationError(
                    "enabled Policy Router runtime requires an endpoint"
                )
            _validate_endpoint(self.endpoint)
            if not self.bindings:
                raise PolicyRouterRuntimeConfigurationError(
                    "enabled Policy Router runtime requires at least one client binding"
                )
            return

        if self.endpoint is not None:
            raise PolicyRouterRuntimeConfigurationError(
                "disabled Policy Router runtime must not configure an endpoint"
            )
        if self.bindings:
            raise PolicyRouterRuntimeConfigurationError(
                "disabled Policy Router runtime must not configure client bindings"
            )


class PolicyRouterSecretResolver(Protocol):
    """Resolve one server-side Policy Router credential reference."""

    def resolve(self, reference: str) -> str:
        """Return one raw Policy Router credential or fail with sanitized metadata."""
        ...


class EnvironmentPolicyRouterSecretResolver:
    """Resolve Policy Router credentials from the Gateway process environment."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        """Bind an explicit mapping for tests or use the current process environment."""
        self._environ = os.environ if environ is None else environ

    def resolve(self, reference: str) -> str:
        """Resolve one environment reference without exposing key material."""
        if not isinstance(reference, str) or _ENV_REFERENCE.fullmatch(reference) is None:
            raise PolicyRouterSecretResolutionError(
                "Policy Router credential environment reference is invalid"
            )
        value = self._environ.get(reference)
        if not _valid_credential(value):
            raise PolicyRouterSecretResolutionError(
                "Policy Router credential environment value is unavailable or malformed"
            )
        return value


def build_policy_router_adapter(
    config: PolicyRouterRuntimeConfig,
    secrets: PolicyRouterSecretResolver,
) -> PolicyRouterHttpAdapter | None:
    """Resolve server-side credentials only after a complete runtime config is validated."""
    if not isinstance(config, PolicyRouterRuntimeConfig):
        raise TypeError("config must use PolicyRouterRuntimeConfig")
    if not config.enabled:
        return None

    endpoint = config.endpoint
    if endpoint is None:
        raise PolicyRouterRuntimeConfigurationError(
            "enabled Policy Router runtime is missing its validated endpoint"
        )

    credentials: dict[str, str] = {}
    for binding in config.bindings:
        try:
            credential = secrets.resolve(binding.credential_reference)
        except PolicyRouterSecretResolutionError:
            raise
        except Exception:
            raise PolicyRouterSecretResolutionError(
                "Policy Router credential resolution failed"
            ) from None
        if not _valid_credential(credential):
            raise PolicyRouterSecretResolutionError(
                "Policy Router credential resolution returned a malformed value"
            )
        credentials[binding.client_id] = credential

    transport = LoopbackHttpPolicyTransport() if urlsplit(endpoint).scheme == "http" else None
    return PolicyRouterHttpAdapter(
        endpoint=endpoint,
        api_keys_by_client=credentials,
        transport=transport,
        timeout_seconds=config.timeout_seconds,
    )


def _validate_bindings(bindings: object) -> None:
    if not isinstance(bindings, tuple):
        raise PolicyRouterRuntimeConfigurationError("Policy Router bindings must be a tuple")
    client_ids: set[str] = set()
    references: set[str] = set()
    previous_client_id: str | None = None
    for binding in bindings:
        if not isinstance(binding, PolicyRouterCredentialBinding):
            raise PolicyRouterRuntimeConfigurationError(
                "Policy Router bindings must contain PolicyRouterCredentialBinding values"
            )
        if binding.client_id in client_ids:
            raise PolicyRouterRuntimeConfigurationError(
                "Policy Router client_id values must be unique"
            )
        if binding.credential_reference in references:
            raise PolicyRouterRuntimeConfigurationError(
                "Policy Router credential references must be unique"
            )
        if previous_client_id is not None and binding.client_id < previous_client_id:
            raise PolicyRouterRuntimeConfigurationError(
                "Policy Router bindings must use deterministic client_id order"
            )
        client_ids.add(binding.client_id)
        references.add(binding.credential_reference)
        previous_client_id = binding.client_id


def _validate_credential_reference(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > _MAX_CREDENTIAL_REFERENCE_LENGTH
        or any(char.isspace() for char in value)
    ):
        raise PolicyRouterRuntimeConfigurationError(
            "credential_reference must be a normalized bounded reference"
        )


def _validate_endpoint(value: object) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise PolicyRouterRuntimeConfigurationError(
            "Policy Router endpoint must be an absolute HTTPS URL or literal loopback HTTP URL"
        )
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise PolicyRouterRuntimeConfigurationError("Policy Router endpoint is invalid") from exc
    if not parsed.hostname:
        raise PolicyRouterRuntimeConfigurationError(
            "Policy Router endpoint must be an absolute HTTPS URL or literal loopback HTTP URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise PolicyRouterRuntimeConfigurationError(
            "Policy Router endpoint must not contain userinfo"
        )
    if parsed.query or parsed.fragment:
        raise PolicyRouterRuntimeConfigurationError(
            "Policy Router endpoint must not contain query or fragment"
        )
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and is_literal_loopback_host(parsed.hostname):
        return
    raise PolicyRouterRuntimeConfigurationError(
        "Policy Router endpoint must use HTTPS unless HTTP targets a literal loopback address"
    )


def _validate_timeout(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
        or float(value) <= 0
        or float(value) > _MAX_TIMEOUT_SECONDS
    ):
        raise PolicyRouterRuntimeConfigurationError(
            "timeout_seconds must be finite, positive, and at most 300 seconds"
        )


def _valid_credential(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and 0 < len(value) <= _MAX_CREDENTIAL_LENGTH
        and value.isascii()
        and value.strip() == value
    )
