"""Contract tests for fail-closed provider-runtime process composition."""

import json
from pathlib import Path

import pytest
from governed_llm_gateway_api import (
    ProviderRuntimeBootstrapPaths,
    bootstrap_provider_runtime,
)
from governed_llm_gateway_core.adapters import (
    ProviderRuntimeDocumentError,
    ProviderRuntimeRegistryMismatchError,
)
from governed_llm_gateway_core.domain import ModelRegistryError

_ROOT = Path(__file__).resolve().parents[2]


class RecordingSecretResolver:
    """Record credential-reference access without exposing provider values."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        return "server-side-provider-token"


def _registry_yaml(*, enabled: bool = True) -> str:
    enabled_text = "true" if enabled else "false"
    return f"""schema_version: "1.0"
catalog_version: "pc2-test"
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
      snapshot_version: "pc2-pricing"
    max_data_classification: internal
    allowed_environments: [development]
    enabled: {enabled_text}
    source_date: "2026-09-07"
    catalog_version: "pc2-test"
"""


def _runtime_json(*, include_binding: bool = True) -> str:
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
            "config_version": "pc2-test",
            "bindings": bindings,
        }
    )


def _paths(
    tmp_path: Path,
    *,
    registry_text: str,
    runtime_text: str,
) -> ProviderRuntimeBootstrapPaths:
    registry_path = tmp_path / "model_registry.yaml"
    runtime_path = tmp_path / "runtime.json"
    registry_path.write_text(registry_text, encoding="utf-8")
    runtime_path.write_text(runtime_text, encoding="utf-8")
    return ProviderRuntimeBootstrapPaths(
        model_registry_path=registry_path,
        provider_runtime_path=runtime_path,
    )


def test_checked_in_empty_artifacts_bootstrap_without_secret_access() -> None:
    secrets = RecordingSecretResolver()

    bundle = bootstrap_provider_runtime(
        ProviderRuntimeBootstrapPaths(
            model_registry_path=_ROOT / "config/model_registry.yaml",
            provider_runtime_path=_ROOT / "config/providers/runtime.json",
        ),
        secrets,
    )

    assert bundle.registry.deployments == ()
    assert bundle.provider_runtime_config_version == "pc1-empty"
    assert len(bundle.model_registry_digest) == 64
    assert len(bundle.provider_runtime_digest) == 64
    assert secrets.calls == []


def test_malformed_registry_fails_before_secret_resolution(tmp_path: Path) -> None:
    secrets = RecordingSecretResolver()
    paths = _paths(
        tmp_path,
        registry_text='schema_version: "2.0"\ncatalog_version: bad\nsource_date: "2026-09-07"\ndeployments: {}\n',
        runtime_text=_runtime_json(),
    )

    with pytest.raises(ModelRegistryError):
        bootstrap_provider_runtime(paths, secrets)

    assert secrets.calls == []


def test_malformed_runtime_fails_before_secret_resolution(tmp_path: Path) -> None:
    secrets = RecordingSecretResolver()
    malformed_runtime = json.dumps({"schema_version": "1.0", "bindings": []})
    paths = _paths(
        tmp_path,
        registry_text=_registry_yaml(enabled=False),
        runtime_text=malformed_runtime,
    )

    with pytest.raises(ProviderRuntimeDocumentError):
        bootstrap_provider_runtime(paths, secrets)

    assert secrets.calls == []


@pytest.mark.parametrize(
    ("registry_text", "runtime_text", "expected_detail"),
    (
        (_registry_yaml(), _runtime_json(include_binding=False), "missing=openai/openai-responses"),
        (
            _registry_yaml(enabled=False),
            _runtime_json(include_binding=True),
            "extra=openai/openai-responses",
        ),
    ),
)
def test_registry_runtime_mismatch_fails_before_secret_resolution(
    tmp_path: Path,
    registry_text: str,
    runtime_text: str,
    expected_detail: str,
) -> None:
    secrets = RecordingSecretResolver()
    paths = _paths(
        tmp_path,
        registry_text=registry_text,
        runtime_text=runtime_text,
    )

    with pytest.raises(ProviderRuntimeRegistryMismatchError, match=expected_detail):
        bootstrap_provider_runtime(paths, secrets)

    assert secrets.calls == []


def test_matched_pair_resolves_only_configured_reference_after_cross_check(tmp_path: Path) -> None:
    secrets = RecordingSecretResolver()
    paths = _paths(
        tmp_path,
        registry_text=_registry_yaml(),
        runtime_text=_runtime_json(),
    )

    bundle = bootstrap_provider_runtime(paths, secrets)
    deployment = bundle.registry.by_id("openai-primary")
    resolved = bundle.resolver.resolve(deployment)

    assert resolved is not None
    assert secrets.calls == ["OPENAI_API_KEY"]
    assert bundle.provider_runtime_config_version == "pc2-test"
    assert len(bundle.model_registry_digest) == 64
    assert len(bundle.provider_runtime_digest) == 64
