"""Contract tests for fail-closed Policy Router runtime configuration and bootstrap."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from governed_llm_gateway_api import (
    PolicyRouterClientAuthMismatchError,
    PolicyRouterRuntimeBootstrapPaths,
    bootstrap_policy_router_runtime,
)
from governed_llm_gateway_core.adapters import (
    DuplicatePolicyRouterRuntimeKeyError,
    EnvironmentPolicyRouterSecretResolver,
    PolicyRouterHttpAdapter,
    PolicyRouterRuntimeDocumentError,
    PolicyRouterSecretResolutionError,
    load_policy_router_runtime_document_text,
)

_ROOT = Path(__file__).resolve().parents[2]
_OPAQUE_VALUE = "pc7-opaque-runtime-value"


class RecordingPolicyRouterSecretResolver:
    """Record attempted secret reads without exposing deployment credentials."""

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self.calls: list[str] = []
        self._values = dict(values or {})

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        if reference not in self._values:
            raise AssertionError("unexpected Policy Router secret read")
        return self._values[reference]


def _policy_runtime_text(*, client_ids: tuple[str, ...]) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc7-test",
            "enabled": True,
            "endpoint": "https://policy-router.example/route",
            "timeout_seconds": 5.0,
            "bindings": [
                {
                    "client_id": client_id,
                    "credential_reference": f"POLICY_{client_id.upper().replace('-', '_')}_KEY",
                }
                for client_id in client_ids
            ],
        }
    )


def _client_auth_text(*, client_ids: tuple[str, ...]) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc7-test-clients",
            "bindings": [
                {
                    "client_id": client_id,
                    "environment": "development",
                    "credential_reference": f"GATEWAY_{client_id.upper().replace('-', '_')}_KEY",
                    "allowed_workloads": ["demo.routing"],
                    "minimum_risk_level": "low",
                    "minimum_data_classification": "public",
                }
                for client_id in client_ids
            ],
        }
    )


def test_policy_router_document_canonicalizes_client_order_and_digest() -> None:
    unsorted = load_policy_router_runtime_document_text(
        _policy_runtime_text(client_ids=("client-b", "client-a"))
    )
    sorted_document = load_policy_router_runtime_document_text(
        _policy_runtime_text(client_ids=("client-a", "client-b"))
    )

    assert tuple(binding.client_id for binding in unsorted.runtime.bindings) == (
        "client-a",
        "client-b",
    )
    assert unsorted.canonical_payload() == sorted_document.canonical_payload()
    assert unsorted.digest == sorted_document.digest
    assert len(unsorted.digest) == 64


def test_policy_router_document_rejects_duplicate_json_keys() -> None:
    text = """{
      "schema_version": "1.0",
      "config_version": "pc7-test",
      "enabled": false,
      "enabled": true,
      "endpoint": null,
      "timeout_seconds": 5.0,
      "bindings": []
    }"""

    with pytest.raises(DuplicatePolicyRouterRuntimeKeyError):
        load_policy_router_runtime_document_text(text)


def test_policy_router_document_rejects_non_https_endpoint() -> None:
    payload = json.loads(_policy_runtime_text(client_ids=("client-a",)))
    assert isinstance(payload, dict)
    payload["endpoint"] = "http://policy-router.example/route"

    with pytest.raises(PolicyRouterRuntimeDocumentError, match="HTTPS"):
        load_policy_router_runtime_document_text(json.dumps(payload))


def test_disabled_policy_router_document_rejects_active_configuration() -> None:
    payload = {
        "schema_version": "1.0",
        "config_version": "pc7-test",
        "enabled": False,
        "endpoint": "https://policy-router.example/route",
        "timeout_seconds": 5.0,
        "bindings": [],
    }

    with pytest.raises(PolicyRouterRuntimeDocumentError, match="must not configure an endpoint"):
        load_policy_router_runtime_document_text(json.dumps(payload))


def test_default_policy_router_runtime_is_disabled_and_reads_no_secrets() -> None:
    secrets = RecordingPolicyRouterSecretResolver()
    bundle = bootstrap_policy_router_runtime(
        PolicyRouterRuntimeBootstrapPaths(
            policy_router_path=_ROOT / "config" / "policy" / "router.json",
            client_auth_path=_ROOT / "config" / "clients" / "auth.json",
        ),
        secrets,
    )

    assert bundle.runtime_document.config_version == "pc7-empty"
    assert bundle.runtime_document.runtime.enabled is False
    assert bundle.client_auth_document.bindings == ()
    assert bundle.adapter is None
    assert secrets.calls == []
    assert len(bundle.policy_router_runtime_digest) == 64
    assert len(bundle.client_auth_digest) == 64


def test_enabled_bootstrap_requires_exact_client_match_then_resolves_once(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "policy.json"
    client_path = tmp_path / "clients.json"
    policy_path.write_text(
        _policy_runtime_text(client_ids=("client-b", "client-a")),
        encoding="utf-8",
    )
    client_path.write_text(
        _client_auth_text(client_ids=("client-a", "client-b")),
        encoding="utf-8",
    )
    secrets = RecordingPolicyRouterSecretResolver(
        {
            "POLICY_CLIENT_A_KEY": _OPAQUE_VALUE,
            "POLICY_CLIENT_B_KEY": _OPAQUE_VALUE,
        }
    )

    bundle = bootstrap_policy_router_runtime(
        PolicyRouterRuntimeBootstrapPaths(
            policy_router_path=policy_path,
            client_auth_path=client_path,
        ),
        secrets,
    )

    assert isinstance(bundle.adapter, PolicyRouterHttpAdapter)
    assert secrets.calls == ["POLICY_CLIENT_A_KEY", "POLICY_CLIENT_B_KEY"]
    assert _OPAQUE_VALUE not in repr(bundle.runtime_document)
    assert _OPAQUE_VALUE not in repr(bundle)


def test_client_mismatch_fails_before_any_policy_router_secret_read(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "policy.json"
    client_path = tmp_path / "clients.json"
    policy_path.write_text(
        _policy_runtime_text(client_ids=("client-a",)),
        encoding="utf-8",
    )
    client_path.write_text(
        _client_auth_text(client_ids=("client-b",)),
        encoding="utf-8",
    )
    secrets = RecordingPolicyRouterSecretResolver()

    with pytest.raises(PolicyRouterClientAuthMismatchError):
        bootstrap_policy_router_runtime(
            PolicyRouterRuntimeBootstrapPaths(
                policy_router_path=policy_path,
                client_auth_path=client_path,
            ),
            secrets,
        )

    assert secrets.calls == []


def test_disabled_policy_router_rejects_active_gateway_clients_before_secret_read(
    tmp_path: Path,
) -> None:
    client_path = tmp_path / "clients.json"
    client_path.write_text(
        _client_auth_text(client_ids=("client-a",)),
        encoding="utf-8",
    )
    secrets = RecordingPolicyRouterSecretResolver()

    with pytest.raises(PolicyRouterClientAuthMismatchError):
        bootstrap_policy_router_runtime(
            PolicyRouterRuntimeBootstrapPaths(
                policy_router_path=_ROOT / "config" / "policy" / "router.json",
                client_auth_path=client_path,
            ),
            secrets,
        )

    assert secrets.calls == []


def test_environment_policy_router_secret_resolver_fails_closed() -> None:
    resolver = EnvironmentPolicyRouterSecretResolver({"POLICY_CLIENT_A_KEY": _OPAQUE_VALUE})

    assert resolver.resolve("POLICY_CLIENT_A_KEY") == _OPAQUE_VALUE
    with pytest.raises(PolicyRouterSecretResolutionError):
        resolver.resolve("policy-client-a-key")
    with pytest.raises(PolicyRouterSecretResolutionError):
        resolver.resolve("POLICY_MISSING_KEY")
