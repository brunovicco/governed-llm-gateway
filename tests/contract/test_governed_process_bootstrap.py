"""Contract tests for all-artifact validation before governed process secret access."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from governed_llm_gateway_api import (
    GovernedProcessArtifacts,
    GovernedProcessBootstrapPaths,
    OperationsReadAccessDocumentError,
    OperationsReadAuthorizationError,
    PolicyRouterClientAuthMismatchError,
    bootstrap_governed_process_runtime,
    load_gateway_client_auth_document_text,
    load_governed_process_artifacts,
    materialize_governed_process_runtime,
)
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.adapters import (
    PolicyRouterHttpAdapter,
    ProviderRuntimeRegistryMismatchError,
    load_model_registry_text,
    load_policy_router_runtime_document_text,
    load_provider_runtime_document_text,
)

_ROOT = Path(__file__).resolve().parents[2]


class RecordingSecrets:
    """Record secret-reference access while returning only test-owned opaque values."""

    def __init__(
        self,
        *,
        label: str,
        values: dict[str, str],
        events: list[str],
    ) -> None:
        self._label = label
        self._values = values
        self._events = events
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        self._events.append(f"{self._label}:{reference}")
        return self._values[reference]


def _registry_yaml() -> str:
    return """schema_version: "1.0"
catalog_version: "pc8-test"
source_date: "2026-09-07"
deployments:
  openai-primary:
    provider: openai
    model_id: openai/test-model
    model_group: general
    api_family: openai-responses
    capabilities:
      text: true
      vision: false
      tool_calling: true
      structured_output: true
      streaming: true
    context_tokens: 128000
    modalities: [text]
    pricing:
      input_usd_per_million_tokens: "1.00"
      output_usd_per_million_tokens: "2.00"
      source_date: "2026-09-07"
      snapshot_version: "pc8-pricing"
    max_data_classification: internal
    allowed_environments: [development]
    enabled: true
    source_date: "2026-09-07"
    catalog_version: "pc8-test"
"""


def _provider_runtime_json(*, include_binding: bool = True) -> str:
    bindings: list[dict[str, object]] = []
    if include_binding:
        bindings.append(
            {
                "provider": "openai",
                "api_family": "openai-responses",
                "credential_reference": "OPENAI_API_KEY",
                "endpoint": "https://api.openai.example/v1/responses",
            }
        )
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc8-test",
            "bindings": bindings,
        }
    )


def _client_auth_json(*, client_id: str = "service-a") -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc8-test",
            "bindings": [
                {
                    "client_id": client_id,
                    "environment": "development",
                    "credential_reference": "GATEWAY_CLIENT_A_KEY",
                    "allowed_workloads": ["rag.answer"],
                    "minimum_risk_level": "high",
                    "minimum_data_classification": "confidential",
                }
            ],
        }
    )


def _policy_router_json(*, client_id: str = "service-a") -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc8-test",
            "enabled": True,
            "endpoint": "https://policy-router.example/route",
            "timeout_seconds": 5.0,
            "bindings": [
                {
                    "client_id": client_id,
                    "credential_reference": "POLICY_SERVICE_A_KEY",
                }
            ],
        }
    )


def _operations_access_json(*, environment: str = "development") -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc21-test",
            "principals": [
                {
                    "client_id": "service-a",
                    "environment": environment,
                }
            ],
        }
    )


def _paths(
    tmp_path: Path,
    *,
    provider_runtime_text: str | None = None,
    client_auth_text: str | None = None,
    policy_router_text: str | None = None,
    operations_access_text: str | None = None,
) -> GovernedProcessBootstrapPaths:
    registry_path = tmp_path / "model_registry.yaml"
    provider_runtime_path = tmp_path / "provider_runtime.json"
    client_auth_path = tmp_path / "client_auth.json"
    policy_router_path = tmp_path / "policy_router.json"
    registry_path.write_text(_registry_yaml(), encoding="utf-8")
    provider_runtime_path.write_text(
        provider_runtime_text or _provider_runtime_json(),
        encoding="utf-8",
    )
    client_auth_path.write_text(client_auth_text or _client_auth_json(), encoding="utf-8")
    policy_router_path.write_text(
        policy_router_text or _policy_router_json(),
        encoding="utf-8",
    )
    operations_access_path: Path | None = None
    if operations_access_text is not None:
        operations_access_path = tmp_path / "operations_access.json"
        operations_access_path.write_text(operations_access_text, encoding="utf-8")
    return GovernedProcessBootstrapPaths(
        model_registry_path=registry_path,
        provider_runtime_path=provider_runtime_path,
        client_auth_path=client_auth_path,
        policy_router_path=policy_router_path,
        operations_access_path=operations_access_path,
    )


def _secrets() -> tuple[RecordingSecrets, RecordingSecrets, RecordingSecrets, list[str]]:
    events: list[str] = []
    client = RecordingSecrets(
        label="client",
        values={"GATEWAY_CLIENT_A_KEY": "pc8-client-opaque"},
        events=events,
    )
    policy = RecordingSecrets(
        label="policy",
        values={"POLICY_SERVICE_A_KEY": "pc8-policy-opaque"},
        events=events,
    )
    provider = RecordingSecrets(
        label="provider",
        values={"OPENAI_API_KEY": "pc8-provider-opaque"},
        events=events,
    )
    return client, policy, provider, events


def test_checked_in_defaults_finish_both_stages_without_secret_reads() -> None:
    client, policy, provider, events = _secrets()
    paths = GovernedProcessBootstrapPaths(
        model_registry_path=_ROOT / "config/model_registry.yaml",
        provider_runtime_path=_ROOT / "config/providers/runtime.json",
        client_auth_path=_ROOT / "config/clients/auth.json",
        policy_router_path=_ROOT / "config/policy/router.json",
    )

    artifacts = load_governed_process_artifacts(paths)
    bundle = materialize_governed_process_runtime(
        artifacts,
        client_secrets=client,
        policy_router_secrets=policy,
        provider_secrets=provider,
    )

    assert artifacts.registry.deployments == ()
    assert artifacts.provider_runtime_document.bindings == ()
    assert artifacts.client_auth_document.bindings == ()
    assert artifacts.policy_router_runtime_document.runtime.enabled is False
    assert artifacts.operations_access_document is None
    assert artifacts.operations_access_policy.principals == ()
    assert artifacts.operations_access_digest is None
    assert artifacts.operations_access_config_version is None
    assert bundle.policy_router_adapter is None
    assert bundle.operations_access_digest is None
    assert events == []
    assert artifacts.provider_runtime_config_version == "pc1-empty"
    assert artifacts.client_auth_config_version == "pc4-empty"
    assert artifacts.policy_router_runtime_config_version == "pc7-empty"
    assert len(bundle.model_registry_digest) == 64
    assert len(bundle.provider_runtime_digest) == 64
    assert len(bundle.client_auth_digest) == 64
    assert len(bundle.policy_router_runtime_digest) == 64


def test_policy_client_mismatch_fails_before_all_secret_resolvers(tmp_path: Path) -> None:
    client, policy, provider, events = _secrets()
    paths = _paths(
        tmp_path,
        policy_router_text=_policy_router_json(client_id="service-b"),
    )

    with pytest.raises(PolicyRouterClientAuthMismatchError):
        bootstrap_governed_process_runtime(
            paths,
            client_secrets=client,
            policy_router_secrets=policy,
            provider_secrets=provider,
        )

    assert events == []
    assert client.calls == []
    assert policy.calls == []
    assert provider.calls == []


def test_provider_registry_mismatch_fails_before_all_secret_resolvers(tmp_path: Path) -> None:
    client, policy, provider, events = _secrets()
    paths = _paths(
        tmp_path,
        provider_runtime_text=_provider_runtime_json(include_binding=False),
    )

    with pytest.raises(ProviderRuntimeRegistryMismatchError):
        bootstrap_governed_process_runtime(
            paths,
            client_secrets=client,
            policy_router_secrets=policy,
            provider_secrets=provider,
        )

    assert events == []
    assert client.calls == []
    assert policy.calls == []
    assert provider.calls == []


def test_operations_access_mismatch_fails_before_all_secret_resolvers(tmp_path: Path) -> None:
    client, policy, provider, events = _secrets()
    paths = _paths(
        tmp_path,
        operations_access_text=_operations_access_json(environment="production"),
    )

    with pytest.raises(
        OperationsReadAccessDocumentError,
        match="must reference configured Gateway client identities",
    ):
        bootstrap_governed_process_runtime(
            paths,
            client_secrets=client,
            policy_router_secrets=policy,
            provider_secrets=provider,
        )

    assert events == []
    assert client.calls == []
    assert policy.calls == []
    assert provider.calls == []


def test_valid_staged_runtime_resolves_once_in_least_privilege_order(tmp_path: Path) -> None:
    client, policy, provider, events = _secrets()
    artifacts = load_governed_process_artifacts(_paths(tmp_path))

    assert events == []

    bundle = materialize_governed_process_runtime(
        artifacts,
        client_secrets=client,
        policy_router_secrets=policy,
        provider_secrets=provider,
    )

    assert events == [
        "client:GATEWAY_CLIENT_A_KEY",
        "policy:POLICY_SERVICE_A_KEY",
        "provider:OPENAI_API_KEY",
    ]
    assert isinstance(bundle.policy_router_adapter, PolicyRouterHttpAdapter)
    assert bundle.provider_resolver.resolve(artifacts.registry.by_id("openai-primary")) is not None

    request = GatewayRequest(
        schema_version="1.0",
        request_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        workload="rag.answer",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(),
        messages=(),
    )
    context = asyncio.run(
        bundle.client_context_resolver.resolve(
            api_key="pc8-client-opaque",
            request=request,
        )
    )

    assert context.client_id == "service-a"
    assert context.environment == "development"
    assert context.risk_level is RiskLevel.HIGH
    assert context.data_classification is DataClassification.CONFIDENTIAL
    with pytest.raises(OperationsReadAuthorizationError):
        asyncio.run(bundle.operations_read_access.authorize(api_key="pc8-client-opaque"))
    assert client.calls == ["GATEWAY_CLIENT_A_KEY"]
    assert policy.calls == ["POLICY_SERVICE_A_KEY"]
    assert provider.calls == ["OPENAI_API_KEY"]


def test_configured_operations_access_reuses_materialized_client_authenticator(
    tmp_path: Path,
) -> None:
    client, policy, provider, events = _secrets()
    artifacts = load_governed_process_artifacts(
        _paths(tmp_path, operations_access_text=_operations_access_json())
    )

    assert events == []
    bundle = materialize_governed_process_runtime(
        artifacts,
        client_secrets=client,
        policy_router_secrets=policy,
        provider_secrets=provider,
    )

    identity = asyncio.run(
        bundle.operations_read_access.authorize(api_key="pc8-client-opaque")
    )

    assert identity.client_id == "service-a"
    assert identity.environment == "development"
    assert artifacts.operations_access_document is not None
    assert artifacts.operations_access_config_version == "pc21-test"
    assert artifacts.operations_access_digest == bundle.operations_access_digest
    assert artifacts.operations_access_digest is not None
    assert len(artifacts.operations_access_digest) == 64
    assert events == [
        "client:GATEWAY_CLIENT_A_KEY",
        "policy:POLICY_SERVICE_A_KEY",
        "provider:OPENAI_API_KEY",
    ]
    assert client.calls == ["GATEWAY_CLIENT_A_KEY"]


def test_artifact_bundle_direct_construction_revalidates_policy_client_boundary() -> None:
    registry = load_model_registry_text(_registry_yaml())
    provider_runtime = load_provider_runtime_document_text(_provider_runtime_json())
    client_auth = load_gateway_client_auth_document_text(_client_auth_json(client_id="service-a"))
    policy_router = load_policy_router_runtime_document_text(
        _policy_router_json(client_id="service-b")
    )

    with pytest.raises(PolicyRouterClientAuthMismatchError):
        GovernedProcessArtifacts(
            registry=registry,
            provider_runtime_document=provider_runtime,
            client_auth_document=client_auth,
            policy_router_runtime_document=policy_router,
        )
