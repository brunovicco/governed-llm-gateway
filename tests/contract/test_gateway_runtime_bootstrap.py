"""Contract tests for fail-closed full Gateway runtime composition."""

import asyncio
import json
from pathlib import Path

import pytest
from governed_llm_gateway_api import (
    GatewayClientAuthDocumentError,
    GatewayRuntimeBootstrapPaths,
    bootstrap_gateway_runtime,
)
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.adapters import ProviderRuntimeRegistryMismatchError

_ROOT = Path(__file__).resolve().parents[2]


class RecordingSecrets:
    """Record server-side secret-reference access while returning configured values."""

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        return self.values[reference]


def _registry_yaml(*, enabled: bool = True) -> str:
    enabled_text = "true" if enabled else "false"
    return f"""schema_version: "1.0"
catalog_version: "pc5-test"
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
      snapshot_version: "pc5-pricing"
    max_data_classification: internal
    allowed_environments: [development]
    enabled: {enabled_text}
    source_date: "2026-09-07"
    catalog_version: "pc5-test"
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
            "config_version": "pc5-test",
            "bindings": bindings,
        }
    )


def _client_auth_json(*, include_binding: bool = True) -> str:
    bindings: list[dict[str, object]] = []
    if include_binding:
        bindings.append(
            {
                "client_id": "service-a",
                "environment": "development",
                "credential_reference": "GATEWAY_CLIENT_A_KEY",
                "allowed_workloads": ["rag.answer"],
                "minimum_risk_level": "high",
                "minimum_data_classification": "confidential",
            }
        )
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc5-test",
            "bindings": bindings,
        }
    )


def _paths(
    tmp_path: Path,
    *,
    registry_text: str,
    provider_runtime_text: str,
    client_auth_text: str,
) -> GatewayRuntimeBootstrapPaths:
    registry_path = tmp_path / "model_registry.yaml"
    provider_runtime_path = tmp_path / "provider_runtime.json"
    client_auth_path = tmp_path / "client_auth.json"
    registry_path.write_text(registry_text, encoding="utf-8")
    provider_runtime_path.write_text(provider_runtime_text, encoding="utf-8")
    client_auth_path.write_text(client_auth_text, encoding="utf-8")
    return GatewayRuntimeBootstrapPaths(
        model_registry_path=registry_path,
        provider_runtime_path=provider_runtime_path,
        client_auth_path=client_auth_path,
    )


def test_checked_in_empty_artifacts_bootstrap_without_secret_access() -> None:
    provider_secrets = RecordingSecrets({})
    client_secrets = RecordingSecrets({})

    bundle = bootstrap_gateway_runtime(
        GatewayRuntimeBootstrapPaths(
            model_registry_path=_ROOT / "config/model_registry.yaml",
            provider_runtime_path=_ROOT / "config/providers/runtime.json",
            client_auth_path=_ROOT / "config/clients/auth.json",
        ),
        provider_secrets=provider_secrets,
        client_secrets=client_secrets,
    )

    assert bundle.registry.deployments == ()
    assert bundle.provider_runtime_document.bindings == ()
    assert bundle.client_auth_document.bindings == ()
    assert bundle.provider_runtime_config_version == "pc1-empty"
    assert bundle.client_auth_config_version == "pc4-empty"
    assert len(bundle.model_registry_digest) == 64
    assert len(bundle.provider_runtime_digest) == 64
    assert len(bundle.client_auth_digest) == 64
    assert provider_secrets.calls == []
    assert client_secrets.calls == []


def test_malformed_client_auth_fails_before_any_secret_access(tmp_path: Path) -> None:
    provider_secrets = RecordingSecrets({"OPENAI_API_KEY": "server-side-provider-token"})
    client_secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": "server-side-client-key"})
    malformed_client_auth = json.dumps(
        {
            "schema_version": "1.0",
            "bindings": [],
        }
    )
    paths = _paths(
        tmp_path,
        registry_text=_registry_yaml(),
        provider_runtime_text=_provider_runtime_json(),
        client_auth_text=malformed_client_auth,
    )

    with pytest.raises(GatewayClientAuthDocumentError):
        bootstrap_gateway_runtime(
            paths,
            provider_secrets=provider_secrets,
            client_secrets=client_secrets,
        )

    assert provider_secrets.calls == []
    assert client_secrets.calls == []


def test_provider_registry_mismatch_fails_before_any_secret_access(tmp_path: Path) -> None:
    provider_secrets = RecordingSecrets({"OPENAI_API_KEY": "server-side-provider-token"})
    client_secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": "server-side-client-key"})
    paths = _paths(
        tmp_path,
        registry_text=_registry_yaml(),
        provider_runtime_text=_provider_runtime_json(include_binding=False),
        client_auth_text=_client_auth_json(),
    )

    with pytest.raises(
        ProviderRuntimeRegistryMismatchError,
        match="missing=openai/openai-responses",
    ):
        bootstrap_gateway_runtime(
            paths,
            provider_secrets=provider_secrets,
            client_secrets=client_secrets,
        )

    assert provider_secrets.calls == []
    assert client_secrets.calls == []


def test_valid_runtime_resolves_each_secret_once_after_validation(tmp_path: Path) -> None:
    provider_secrets = RecordingSecrets({"OPENAI_API_KEY": "server-side-provider-token"})
    client_secrets = RecordingSecrets({"GATEWAY_CLIENT_A_KEY": "server-side-client-key"})
    paths = _paths(
        tmp_path,
        registry_text=_registry_yaml(),
        provider_runtime_text=_provider_runtime_json(),
        client_auth_text=_client_auth_json(),
    )

    bundle = bootstrap_gateway_runtime(
        paths,
        provider_secrets=provider_secrets,
        client_secrets=client_secrets,
    )

    deployment = bundle.registry.by_id("openai-primary")
    assert bundle.provider_resolver.resolve(deployment) is not None
    request = GatewayRequest(
        schema_version="1.0",
        request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        workload="rag.answer",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(),
        messages=(),
    )
    context = asyncio.run(
        bundle.client_context_resolver.resolve(
            api_key="server-side-client-key",
            request=request,
        )
    )

    assert context.client_id == "service-a"
    assert context.environment == "development"
    assert context.risk_level is RiskLevel.HIGH
    assert context.data_classification is DataClassification.CONFIDENTIAL
    assert provider_secrets.calls == ["OPENAI_API_KEY"]
    assert client_secrets.calls == ["GATEWAY_CLIENT_A_KEY"]
    assert bundle.provider_runtime_config_version == "pc5-test"
    assert bundle.client_auth_config_version == "pc5-test"
    assert len(bundle.model_registry_digest) == 64
    assert len(bundle.provider_runtime_digest) == 64
    assert len(bundle.client_auth_digest) == 64
