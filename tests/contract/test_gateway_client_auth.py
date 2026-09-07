"""Contract tests for Gateway client authentication and trust reconciliation."""

import asyncio
from collections.abc import Sequence
from typing import cast
from uuid import UUID

import pytest
from governed_llm_gateway_api import (
    ClientAuthenticationError,
    EnvironmentGatewayClientSecretResolver,
    GatewayClientAuthBinding,
    GatewayClientAuthenticationConfigurationError,
    GatewayClientAuthorizationError,
    GatewayClientSecretResolutionError,
    build_static_gateway_client_context_resolver,
)
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.domain import EffectivePolicyContext

_REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_KEY_A = "unit-test-gateway-key-a"
_KEY_B = "unit-test-gateway-key-b"


class RecordingSecrets:
    """Record reference access while returning configured test credentials."""

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        return self.values[reference]


class ExplodingSecrets:
    def resolve(self, reference: str) -> str:
        del reference
        raise RuntimeError("backend details must not escape")


def _binding(
    *,
    client_id: str = "service-a",
    reference: str = "GATEWAY_CLIENT_A_KEY",
    workloads: tuple[str, ...] = ("rag.answer",),
    minimum_risk: RiskLevel = RiskLevel.HIGH,
    minimum_classification: DataClassification = DataClassification.CONFIDENTIAL,
) -> GatewayClientAuthBinding:
    return GatewayClientAuthBinding(
        client_id=client_id,
        environment="development",
        credential_reference=reference,
        allowed_workloads=workloads,
        minimum_risk_level=minimum_risk,
        minimum_data_classification=minimum_classification,
    )


def _request(
    *,
    workload: str = "rag.answer",
    risk: RiskLevel = RiskLevel.LOW,
    classification: DataClassification = DataClassification.PUBLIC,
    agent_identity: str | None = "spoofed-client",
) -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=_REQUEST_ID,
        workload=workload,
        risk_level=risk,
        data_classification=classification,
        requirements=WorkloadRequirements(),
        messages=(),
        agent_identity=agent_identity,
    )


def _resolve(
    api_key: str,
    request: GatewayRequest,
    *,
    binding: GatewayClientAuthBinding | None = None,
) -> EffectivePolicyContext:
    secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": _KEY_A})
    resolver = build_static_gateway_client_context_resolver(
        (binding or _binding(),),
        secrets,
    )
    return asyncio.run(resolver.resolve(api_key=api_key, request=request))


def test_authenticated_context_raises_caller_downgrades_to_authoritative_minima() -> None:
    context = _resolve(_KEY_A, _request())

    assert context.client_id == "service-a"
    assert context.environment == "development"
    assert context.workload == "rag.answer"
    assert context.risk_level is RiskLevel.HIGH
    assert context.data_classification is DataClassification.CONFIDENTIAL


def test_authenticated_context_preserves_stricter_caller_claims() -> None:
    context = _resolve(
        _KEY_A,
        _request(
            risk=RiskLevel.CRITICAL,
            classification=DataClassification.RESTRICTED,
        ),
    )

    assert context.risk_level is RiskLevel.CRITICAL
    assert context.data_classification is DataClassification.RESTRICTED


def test_agent_identity_cannot_spoof_authenticated_client() -> None:
    context = _resolve(
        _KEY_A,
        _request(agent_identity="attacker-controlled-agent"),
    )

    assert context.client_id == "service-a"


@pytest.mark.parametrize(
    "api_key",
    (
        "wrong-key",
        " leading-space",
        "trailing-space ",
        "não-ascii",
    ),
)
def test_invalid_gateway_credentials_fail_with_sanitized_authentication_error(
    api_key: str,
) -> None:
    with pytest.raises(ClientAuthenticationError, match="gateway credential rejected"):
        _resolve(api_key, _request())


def test_authenticated_client_outside_workload_scope_gets_distinct_403() -> None:
    secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": _KEY_A})
    resolver = build_static_gateway_client_context_resolver((_binding(),), secrets)

    with pytest.raises(GatewayClientAuthorizationError) as captured:
        asyncio.run(
            resolver.resolve(
                api_key=_KEY_A,
                request=_request(workload="code.review"),
            )
        )

    assert captured.value.status_code == 403
    assert captured.value.detail == {"code": "gateway_client_not_authorized"}


def test_duplicate_client_ids_fail_before_secret_backend_access() -> None:
    secrets = RecordingSecrets(
        {
            "GATEWAY_CLIENT_A_KEY": _KEY_A,
            "GATEWAY_CLIENT_B_KEY": _KEY_B,
        }
    )
    bindings = (
        _binding(),
        _binding(
            client_id="service-a",
            reference="GATEWAY_CLIENT_B_KEY",
            workloads=("code.review",),
        ),
    )

    with pytest.raises(
        GatewayClientAuthenticationConfigurationError,
        match="client_id values must be unique",
    ):
        build_static_gateway_client_context_resolver(bindings, secrets)

    assert secrets.calls == []


def test_duplicate_credential_references_fail_before_secret_backend_access() -> None:
    secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": _KEY_A})
    bindings = (
        _binding(),
        _binding(
            client_id="service-b",
            workloads=("code.review",),
        ),
    )

    with pytest.raises(
        GatewayClientAuthenticationConfigurationError,
        match="credential references must be unique",
    ):
        build_static_gateway_client_context_resolver(bindings, secrets)

    assert secrets.calls == []


def test_non_binding_value_fails_before_secret_backend_access() -> None:
    secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": _KEY_A})
    malformed = cast(
        Sequence[GatewayClientAuthBinding],
        (_binding(), object()),
    )

    with pytest.raises(
        GatewayClientAuthenticationConfigurationError,
        match="must contain GatewayClientAuthBinding",
    ):
        build_static_gateway_client_context_resolver(malformed, secrets)

    assert secrets.calls == []


def test_duplicate_resolved_credentials_fail_closed() -> None:
    secrets = RecordingSecrets(
        {
            "GATEWAY_CLIENT_A_KEY": _KEY_A,
            "GATEWAY_CLIENT_B_KEY": _KEY_A,
        }
    )
    bindings = (
        _binding(),
        _binding(
            client_id="service-b",
            reference="GATEWAY_CLIENT_B_KEY",
            workloads=("code.review",),
        ),
    )

    with pytest.raises(
        GatewayClientAuthenticationConfigurationError,
        match="credentials must resolve uniquely",
    ):
        build_static_gateway_client_context_resolver(bindings, secrets)

    assert secrets.calls == ["GATEWAY_CLIENT_A_KEY", "GATEWAY_CLIENT_B_KEY"]


def test_arbitrary_secret_backend_exception_is_sanitized_without_chain() -> None:
    with pytest.raises(GatewayClientSecretResolutionError) as captured:
        build_static_gateway_client_context_resolver((_binding(),), ExplodingSecrets())

    assert str(captured.value) == "gateway client credential resolution failed"
    assert captured.value.__cause__ is None
    assert "backend details" not in str(captured.value)


def test_resolved_secret_is_hidden_from_resolver_repr() -> None:
    secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": _KEY_A})
    resolver = build_static_gateway_client_context_resolver((_binding(),), secrets)

    assert _KEY_A not in repr(resolver.__dict__)


@pytest.mark.parametrize(
    "kwargs",
    (
        {"client_id": " Service-A"},
        {"reference": "bad secret reference"},
        {"workloads": ()},
        {"workloads": ("rag.answer", "rag.answer")},
        {"workloads": ("rag.answer", "code.review")},
        {"workloads": ("not-dotted",)},
    ),
)
def test_binding_validation_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(GatewayClientAuthenticationConfigurationError):
        _binding(
            client_id=cast(str, kwargs.get("client_id", "service-a")),
            reference=cast(str, kwargs.get("reference", "GATEWAY_CLIENT_A_KEY")),
            workloads=cast(tuple[str, ...], kwargs.get("workloads", ("rag.answer",))),
        )


def test_environment_secret_resolver_is_backend_specific_and_sanitized() -> None:
    resolver = EnvironmentGatewayClientSecretResolver(
        {
            "GATEWAY_CLIENT_A_KEY": _KEY_A,
            "GATEWAY_CLIENT_BAD_KEY": " malformed ",
        }
    )

    assert resolver.resolve("GATEWAY_CLIENT_A_KEY") == _KEY_A
    with pytest.raises(GatewayClientSecretResolutionError, match="reference is invalid"):
        resolver.resolve("vault://clients/a")
    with pytest.raises(GatewayClientSecretResolutionError, match="unavailable or malformed"):
        resolver.resolve("GATEWAY_CLIENT_MISSING_KEY")
    with pytest.raises(GatewayClientSecretResolutionError, match="unavailable or malformed"):
        resolver.resolve("GATEWAY_CLIENT_BAD_KEY")


def test_generic_binding_can_hold_non_environment_secret_reference() -> None:
    binding = _binding(reference="vault://clients/service-a")

    assert binding.credential_reference == "vault://clients/service-a"
