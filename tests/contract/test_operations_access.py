"""Contract tests for the authenticated read-only operations access boundary."""

import asyncio
from collections.abc import Sequence
from typing import cast

import pytest
from governed_llm_gateway_api import (
    ClientAuthenticationError,
    GatewayClientAuthBinding,
    GatewayClientAuthorizationError,
    GatewayClientIdentity,
    OperationsReadAccessConfigurationError,
    OperationsReadAccessPolicy,
    OperationsReadAccessService,
    OperationsReadAuthorizationError,
    build_static_gateway_client_context_resolver,
)
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    RiskLevel,
    WorkloadRequirements,
)

_KEY_A = "unit-test-operations-key-a"
_KEY_B = "unit-test-operations-key-b"


class RecordingSecrets:
    """Record the one-time materialization reads used by the existing auth boundary."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.values = {
            "GATEWAY_CLIENT_A_KEY": _KEY_A,
            "GATEWAY_CLIENT_B_KEY": _KEY_B,
        }

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        return self.values[reference]


def _binding(
    *,
    client_id: str,
    environment: str,
    reference: str,
    workload: str,
) -> GatewayClientAuthBinding:
    return GatewayClientAuthBinding(
        client_id=client_id,
        environment=environment,
        credential_reference=reference,
        allowed_workloads=(workload,),
        minimum_risk_level=RiskLevel.HIGH,
        minimum_data_classification=DataClassification.CONFIDENTIAL,
    )


def _resolver() -> tuple[object, RecordingSecrets]:
    secrets = RecordingSecrets()
    resolver = build_static_gateway_client_context_resolver(
        (
            _binding(
                client_id="service-a",
                environment="development",
                reference="GATEWAY_CLIENT_A_KEY",
                workload="rag.answer",
            ),
            _binding(
                client_id="service-b",
                environment="staging",
                reference="GATEWAY_CLIENT_B_KEY",
                workload="code.review",
            ),
        ),
        secrets,
    )
    return resolver, secrets


def _request(workload: str) -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        workload=workload,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(),
        messages=(),
    )


def test_authenticate_returns_identity_without_synthetic_workload_request() -> None:
    resolver, secrets = _resolver()
    typed_resolver = cast("StaticGatewayClientContextResolver", resolver)
    before = tuple(secrets.calls)

    identity = asyncio.run(typed_resolver.authenticate(api_key=_KEY_A))

    assert identity == GatewayClientIdentity(client_id="service-a", environment="development")
    assert tuple(secrets.calls) == before


def test_operations_read_grant_reuses_materialized_authenticator_without_secret_reads() -> None:
    resolver, secrets = _resolver()
    typed_resolver = cast("StaticGatewayClientContextResolver", resolver)
    policy = OperationsReadAccessPolicy(
        principals=(GatewayClientIdentity(client_id="service-a", environment="development"),)
    )
    service = OperationsReadAccessService(authenticator=typed_resolver, policy=policy)
    before = tuple(secrets.calls)

    identity = asyncio.run(service.authorize(api_key=_KEY_A))

    assert identity.client_id == "service-a"
    assert identity.environment == "development"
    assert tuple(secrets.calls) == before


def test_valid_gateway_credential_without_operations_grant_fails_sanitized() -> None:
    resolver, _ = _resolver()
    typed_resolver = cast("StaticGatewayClientContextResolver", resolver)
    policy = OperationsReadAccessPolicy(
        principals=(GatewayClientIdentity(client_id="service-a", environment="development"),)
    )
    service = OperationsReadAccessService(authenticator=typed_resolver, policy=policy)

    with pytest.raises(OperationsReadAuthorizationError) as captured:
        asyncio.run(service.authorize(api_key=_KEY_B))

    assert str(captured.value) == "operations read access denied"
    assert "service-a" not in str(captured.value)
    assert "service-b" not in str(captured.value)
    assert "staging" not in str(captured.value)


def test_empty_operations_policy_denies_every_authenticated_client() -> None:
    resolver, _ = _resolver()
    typed_resolver = cast("StaticGatewayClientContextResolver", resolver)
    service = OperationsReadAccessService(
        authenticator=typed_resolver,
        policy=OperationsReadAccessPolicy(),
    )

    with pytest.raises(OperationsReadAuthorizationError, match="operations read access denied"):
        asyncio.run(service.authorize(api_key=_KEY_A))


def test_invalid_gateway_credential_preserves_authentication_failure() -> None:
    resolver, _ = _resolver()
    typed_resolver = cast("StaticGatewayClientContextResolver", resolver)
    service = OperationsReadAccessService(
        authenticator=typed_resolver,
        policy=OperationsReadAccessPolicy(
            principals=(GatewayClientIdentity(client_id="service-a", environment="development"),)
        ),
    )

    with pytest.raises(ClientAuthenticationError, match="gateway credential rejected"):
        asyncio.run(service.authorize(api_key="wrong-key"))


def test_operations_grant_does_not_replace_workload_authorization() -> None:
    resolver, _ = _resolver()
    typed_resolver = cast("StaticGatewayClientContextResolver", resolver)
    service = OperationsReadAccessService(
        authenticator=typed_resolver,
        policy=OperationsReadAccessPolicy(
            principals=(GatewayClientIdentity(client_id="service-a", environment="development"),)
        ),
    )

    assert asyncio.run(service.authorize(api_key=_KEY_A)).client_id == "service-a"
    with pytest.raises(GatewayClientAuthorizationError):
        asyncio.run(
            typed_resolver.resolve(
                api_key=_KEY_A,
                request=_request("code.review"),
            )
        )


@pytest.mark.parametrize(
    "principals",
    (
        (
            GatewayClientIdentity(client_id="service-a", environment="development"),
            GatewayClientIdentity(client_id="service-a", environment="development"),
        ),
        (
            GatewayClientIdentity(client_id="service-b", environment="staging"),
            GatewayClientIdentity(client_id="service-a", environment="development"),
        ),
    ),
)
def test_operations_policy_rejects_duplicate_or_unsorted_principals(
    principals: tuple[GatewayClientIdentity, ...],
) -> None:
    with pytest.raises(OperationsReadAccessConfigurationError):
        OperationsReadAccessPolicy(principals=principals)


def test_operations_policy_rejects_non_tuple_or_non_identity_values() -> None:
    with pytest.raises(OperationsReadAccessConfigurationError, match="must use a tuple"):
        OperationsReadAccessPolicy(
            principals=cast(tuple[GatewayClientIdentity, ...], [GatewayClientIdentity("a", "dev")])
        )

    malformed = cast(
        Sequence[GatewayClientIdentity],
        (GatewayClientIdentity("service-a", "development"), object()),
    )
    with pytest.raises(OperationsReadAccessConfigurationError, match="GatewayClientIdentity"):
        OperationsReadAccessPolicy(
            principals=cast(tuple[GatewayClientIdentity, ...], malformed)
        )
