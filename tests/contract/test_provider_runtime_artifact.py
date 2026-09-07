"""Contract tests for the versioned provider runtime configuration artifact."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from governed_llm_gateway_contracts import Capability, DataClassification, Modality
from governed_llm_gateway_core.adapters import (
    DuplicateProviderRuntimeKeyError,
    ProviderApiFamily,
    ProviderRuntimeDocumentError,
    ProviderRuntimeRegistryMismatchError,
    load_model_registry,
    load_provider_runtime_document,
    load_provider_runtime_document_text,
    validate_provider_runtime_registry,
)
from governed_llm_gateway_core.domain import ModelDeployment, ModelRegistry, PricingMetadata

_TODAY = date(2026, 9, 7)
_ROOT = Path(__file__).resolve().parents[2]


def _binding(
    *,
    provider: str = "openai",
    api_family: str = "openai-responses",
    credential_reference: str = "OPENAI_API_KEY",
    endpoint: str = "https://api.openai.example/v1/responses",
) -> dict[str, object]:
    return {
        "provider": provider,
        "api_family": api_family,
        "credential_reference": credential_reference,
        "endpoint": endpoint,
    }


def _compatible_binding(provider: str = "nvidia") -> dict[str, object]:
    return {
        "provider": provider,
        "api_family": "openai-compatible",
        "credential_reference": f"{provider.upper()}_API_KEY",
        "endpoint": f"https://{provider}.example/v1/chat/completions",
        "openai_compatible": {
            "max_tokens_field": "max_tokens",
            "supports_native_structured_output": False,
            "supports_native_tool_calling": False,
            "supports_streaming": True,
            "supports_stream_usage": True,
        },
    }


def _document(bindings: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "runtime-v1",
            "bindings": bindings,
        }
    )


def _deployment(
    provider: str,
    api_family: str,
    *,
    deployment_id: str,
    enabled: bool = True,
) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group="general",
        api_family=api_family,
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=_TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"prod"}),
        enabled=enabled,
        source_date=_TODAY,
        catalog_version="catalog-v1",
    )


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=_TODAY,
        deployments=tuple(deployments),
    )


def test_empty_document_matches_empty_registry() -> None:
    document = load_provider_runtime_document_text(_document([]))

    validate_provider_runtime_registry(document, _registry())

    assert document.schema_version == "1.0"
    assert document.config_version == "runtime-v1"
    assert document.bindings == ()


def test_committed_provider_runtime_artifact_matches_committed_registry() -> None:
    document = load_provider_runtime_document(_ROOT / "config/providers/runtime.json")
    registry = load_model_registry(_ROOT / "config/model_registry.yaml")

    validate_provider_runtime_registry(document, registry)

    assert document.schema_version == "1.0"
    assert document.config_version == "phase2-empty"
    assert document.bindings == ()


def test_document_digest_is_independent_of_json_format_and_binding_order() -> None:
    first = {
        "schema_version": "1.0",
        "config_version": "runtime-v1",
        "bindings": [_binding(), _compatible_binding()],
    }
    second = {
        "bindings": [_compatible_binding(), _binding()],
        "config_version": "runtime-v1",
        "schema_version": "1.0",
    }

    compact = load_provider_runtime_document_text(json.dumps(first, separators=(",", ":")))
    formatted = load_provider_runtime_document_text(json.dumps(second, indent=4))

    assert compact.digest == formatted.digest
    assert compact.canonical_payload() == formatted.canonical_payload()


def test_duplicate_json_key_fails_closed() -> None:
    payload = (
        '{"schema_version":"1.0","config_version":"runtime-v1",'
        '"config_version":"runtime-v2","bindings":[]}'
    )

    with pytest.raises(DuplicateProviderRuntimeKeyError, match="duplicate"):
        load_provider_runtime_document_text(payload)


@pytest.mark.parametrize(
    "payload",
    (
        {"schema_version": "1.0", "bindings": []},
        {
            "schema_version": "1.0",
            "config_version": "runtime-v1",
            "bindings": [],
            "secret": "forbidden-shape",
        },
        {
            "schema_version": "2.0",
            "config_version": "runtime-v1",
            "bindings": [],
        },
    ),
)
def test_document_rejects_missing_unknown_and_unsupported_root_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ProviderRuntimeDocumentError):
        load_provider_runtime_document_text(json.dumps(payload))


def test_binding_reuses_pc0_endpoint_and_family_validation() -> None:
    invalid = _binding(
        provider="nvidia",
        api_family=ProviderApiFamily.OPENAI_RESPONSES.value,
        endpoint="http://caller-controlled.example/v1",
    )

    with pytest.raises(ProviderRuntimeDocumentError):
        load_provider_runtime_document_text(_document([invalid]))


def test_compatible_options_are_closed_and_explicit() -> None:
    binding = _compatible_binding()
    options = binding["openai_compatible"]
    assert isinstance(options, dict)
    options.pop("supports_stream_usage")

    with pytest.raises(ProviderRuntimeDocumentError, match="missing required fields"):
        load_provider_runtime_document_text(_document([binding]))


def test_raw_secret_value_field_is_not_part_of_artifact_schema() -> None:
    binding = _binding()
    binding["api_key"] = "opaque-value"

    with pytest.raises(ProviderRuntimeDocumentError, match="unknown fields"):
        load_provider_runtime_document_text(_document([binding]))


def test_duplicate_provider_api_family_binding_fails_closed() -> None:
    with pytest.raises(ProviderRuntimeDocumentError, match="duplicate provider runtime binding"):
        load_provider_runtime_document_text(_document([_binding(), _binding()]))


def test_registry_cross_check_accepts_shared_binding_for_multiple_deployments() -> None:
    document = load_provider_runtime_document_text(_document([_binding()]))
    registry = _registry(
        _deployment("openai", "openai-responses", deployment_id="openai-a"),
        _deployment("openai", "openai-responses", deployment_id="openai-b"),
    )

    validate_provider_runtime_registry(document, registry)


def test_registry_cross_check_rejects_missing_runtime_binding() -> None:
    document = load_provider_runtime_document_text(_document([]))
    registry = _registry(
        _deployment("openai", "openai-responses", deployment_id="openai-a"),
    )

    with pytest.raises(
        ProviderRuntimeRegistryMismatchError,
        match="missing=openai/openai-responses",
    ):
        validate_provider_runtime_registry(document, registry)


def test_registry_cross_check_rejects_extra_runtime_binding() -> None:
    document = load_provider_runtime_document_text(_document([_binding()]))

    with pytest.raises(ProviderRuntimeRegistryMismatchError, match="extra=openai/openai-responses"):
        validate_provider_runtime_registry(document, _registry())


def test_registry_cross_check_ignores_disabled_deployment_requirement() -> None:
    document = load_provider_runtime_document_text(_document([]))
    registry = _registry(
        _deployment(
            "openai",
            "openai-responses",
            deployment_id="openai-disabled",
            enabled=False,
        ),
    )

    validate_provider_runtime_registry(document, registry)


def test_loader_does_not_require_or_resolve_secret_values() -> None:
    document = load_provider_runtime_document_text(
        _document(
            [
                _binding(
                    credential_reference="vault://providers/openai",
                )
            ]
        )
    )

    assert document.bindings[0].credential_reference == "vault://providers/openai"
    assert "vault://providers/openai" in json.dumps(document.canonical_payload())
