"""Fail-closed Gateway client authentication and trusted-context reconciliation."""

import hmac
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import HTTPException
from governed_llm_gateway_contracts import DataClassification, GatewayRequest, RiskLevel
from governed_llm_gateway_core.domain import EffectivePolicyContext

from .route_explain import ClientAuthenticationError

_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_WORKLOAD = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
_SECRET_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_ENV_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_MAX_API_KEY_LENGTH = 4096
_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}
_CLASSIFICATION_ORDER = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 1,
    DataClassification.CONFIDENTIAL: 2,
    DataClassification.RESTRICTED: 3,
}


class GatewayClientAuthenticationConfigurationError(ValueError):
    """Raised when deployment-owned Gateway client authentication config is invalid."""


class GatewayClientSecretResolutionError(RuntimeError):
    """Raised when a configured Gateway client credential cannot be resolved safely."""


class GatewayClientAuthorizationError(HTTPException):
    """Sanitized HTTP rejection for an authenticated client outside its workload scope."""

    def __init__(self) -> None:
        super().__init__(
            status_code=403,
            detail={"code": "gateway_client_not_authorized"},
        )


class GatewayClientSecretResolver(Protocol):
    """Resolve one server-side Gateway client credential reference."""

    def resolve(self, reference: str) -> str:
        """Return a raw Gateway credential or fail with sanitized metadata."""
        ...


@dataclass(frozen=True, slots=True)
class GatewayClientAuthBinding:
    """Secret-free authoritative identity and workload trust configuration."""

    client_id: str
    environment: str
    credential_reference: str
    allowed_workloads: tuple[str, ...]
    minimum_risk_level: RiskLevel
    minimum_data_classification: DataClassification

    def __post_init__(self) -> None:
        """Validate trust metadata before any secret backend access."""
        _require_identifier(self.client_id, "client_id")
        _require_identifier(self.environment, "environment")
        if (
            not isinstance(self.credential_reference, str)
            or _SECRET_REFERENCE.fullmatch(self.credential_reference) is None
        ):
            raise GatewayClientAuthenticationConfigurationError(
                "credential_reference must be a normalized secret reference"
            )
        if not isinstance(self.allowed_workloads, tuple) or not self.allowed_workloads:
            raise GatewayClientAuthenticationConfigurationError(
                "allowed_workloads must be a non-empty tuple"
            )
        for workload in self.allowed_workloads:
            if not isinstance(workload, str) or _WORKLOAD.fullmatch(workload) is None:
                raise GatewayClientAuthenticationConfigurationError(
                    "allowed_workloads must contain normalized dotted workloads"
                )
        if len(set(self.allowed_workloads)) != len(self.allowed_workloads):
            raise GatewayClientAuthenticationConfigurationError(
                "allowed_workloads must not contain duplicates"
            )
        if self.allowed_workloads != tuple(sorted(self.allowed_workloads)):
            raise GatewayClientAuthenticationConfigurationError(
                "allowed_workloads must use deterministic sorted order"
            )
        if not isinstance(self.minimum_risk_level, RiskLevel):
            raise GatewayClientAuthenticationConfigurationError(
                "minimum_risk_level must use RiskLevel"
            )
        if not isinstance(self.minimum_data_classification, DataClassification):
            raise GatewayClientAuthenticationConfigurationError(
                "minimum_data_classification must use DataClassification"
            )


class EnvironmentGatewayClientSecretResolver:
    """Resolve Gateway client credentials from the Gateway process environment."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def resolve(self, reference: str) -> str:
        """Resolve one environment reference without surfacing key material."""
        if not isinstance(reference, str) or _ENV_REFERENCE.fullmatch(reference) is None:
            raise GatewayClientSecretResolutionError(
                "gateway client credential environment reference is invalid"
            )
        value = self._environ.get(reference)
        if not _valid_api_key(value):
            raise GatewayClientSecretResolutionError(
                "gateway client credential environment value is unavailable or malformed"
            )
        return value


@dataclass(frozen=True, slots=True)
class _ResolvedGatewayClientBinding:
    binding: GatewayClientAuthBinding
    credential: str = field(repr=False)


class StaticGatewayClientContextResolver:
    """Authenticate one Gateway key and produce authoritative policy context."""

    def __init__(self, bindings: tuple[_ResolvedGatewayClientBinding, ...]) -> None:
        self._bindings = bindings

    async def resolve(
        self,
        *,
        api_key: str,
        request: GatewayRequest,
    ) -> EffectivePolicyContext:
        """Authenticate, authorize workload scope, and reconcile stricter caller claims."""
        if not _valid_api_key(api_key):
            raise ClientAuthenticationError("gateway credential rejected")

        matches = tuple(
            item
            for item in self._bindings
            if hmac.compare_digest(api_key, item.credential)
        )
        if len(matches) != 1:
            raise ClientAuthenticationError("gateway credential rejected")

        binding = matches[0].binding
        if request.workload not in binding.allowed_workloads:
            raise GatewayClientAuthorizationError()

        return EffectivePolicyContext(
            client_id=binding.client_id,
            environment=binding.environment,
            workload=request.workload,
            risk_level=_stricter_risk(request.risk_level, binding.minimum_risk_level),
            data_classification=_stricter_classification(
                request.data_classification,
                binding.minimum_data_classification,
            ),
        )


def build_static_gateway_client_context_resolver(
    bindings: Sequence[GatewayClientAuthBinding],
    secrets: GatewayClientSecretResolver,
) -> StaticGatewayClientContextResolver:
    """Validate all identities, then resolve server-side Gateway credentials exactly once."""
    validated = _validate_bindings(bindings)
    resolved: list[_ResolvedGatewayClientBinding] = []
    credentials: set[str] = set()
    for binding in validated:
        try:
            credential = secrets.resolve(binding.credential_reference)
        except GatewayClientSecretResolutionError:
            raise
        except Exception:
            raise GatewayClientSecretResolutionError(
                "gateway client credential resolution failed"
            ) from None
        if not _valid_api_key(credential):
            raise GatewayClientSecretResolutionError(
                "gateway client credential resolution returned a malformed value"
            )
        if credential in credentials:
            raise GatewayClientAuthenticationConfigurationError(
                "gateway client credentials must resolve uniquely"
            )
        credentials.add(credential)
        resolved.append(
            _ResolvedGatewayClientBinding(
                binding=binding,
                credential=credential,
            )
        )
    return StaticGatewayClientContextResolver(tuple(resolved))


def _validate_bindings(
    bindings: Sequence[GatewayClientAuthBinding],
) -> tuple[GatewayClientAuthBinding, ...]:
    if isinstance(bindings, (str, bytes)):
        raise GatewayClientAuthenticationConfigurationError(
            "gateway client bindings must be a sequence of binding objects"
        )
    validated: list[GatewayClientAuthBinding] = []
    client_ids: set[str] = set()
    references: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, GatewayClientAuthBinding):
            raise GatewayClientAuthenticationConfigurationError(
                "gateway client bindings must contain GatewayClientAuthBinding values"
            )
        if binding.client_id in client_ids:
            raise GatewayClientAuthenticationConfigurationError(
                "gateway client_id values must be unique"
            )
        if binding.credential_reference in references:
            raise GatewayClientAuthenticationConfigurationError(
                "gateway client credential references must be unique"
            )
        client_ids.add(binding.client_id)
        references.add(binding.credential_reference)
        validated.append(binding)
    return tuple(validated)


def _require_identifier(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise GatewayClientAuthenticationConfigurationError(
            f"{field_name} must be a normalized identifier"
        )


def _valid_api_key(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= _MAX_API_KEY_LENGTH
        and value.isascii()
        and value.strip() == value
    )


def _stricter_risk(caller: RiskLevel, minimum: RiskLevel) -> RiskLevel:
    return caller if _RISK_ORDER[caller] >= _RISK_ORDER[minimum] else minimum


def _stricter_classification(
    caller: DataClassification,
    minimum: DataClassification,
) -> DataClassification:
    return (
        caller
        if _CLASSIFICATION_ORDER[caller] >= _CLASSIFICATION_ORDER[minimum]
        else minimum
    )
