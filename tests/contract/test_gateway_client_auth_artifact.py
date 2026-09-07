"""Contract tests for the versioned Gateway client-auth configuration artifact."""

import json
from pathlib import Path

import pytest
from governed_llm_gateway_api import (
    DuplicateGatewayClientAuthKeyError,
    GatewayClientAuthDocumentError,
    load_gateway_client_auth_document,
    load_gateway_client_auth_document_text,
)

_ROOT = Path(__file__).resolve().parents[2]


def _binding(
    *,
    client_id: str = "service-a",
    credential_reference: str = "GATEWAY_CLIENT_A_KEY",
    allowed_workloads: list[str] | None = None,
    minimum_risk_level: str = "high",
    minimum_data_classification: str = "confidential",
) -> dict[str, object]:
    return {
        "client_id": client_id,
        "environment": "development",
        "credential_reference": credential_reference,
        "allowed_workloads": ["rag.answer"] if allowed_workloads is None else allowed_workloads,
        "minimum_risk_level": minimum_risk_level,
        "minimum_data_classification": minimum_data_classification,
    }


def _document(bindings: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "client-auth-v1",
            "bindings": bindings,
        }
    )


def test_committed_client_auth_artifact_is_empty_and_fail_closed() -> None:
    document = load_gateway_client_auth_document(_ROOT / "config/clients/auth.json")

    assert document.schema_version == "1.0"
    assert document.config_version == "pc4-empty"
    assert document.bindings == ()
    assert len(document.digest) == 64


def test_document_digest_is_independent_of_json_format_and_binding_order() -> None:
    first_binding = _binding(
        client_id="service-a",
        credential_reference="GATEWAY_CLIENT_A_KEY",
        allowed_workloads=["code.review", "rag.answer"],
    )
    second_binding = _binding(
        client_id="service-b",
        credential_reference="vault://clients/service-b",
        allowed_workloads=["ops.analyze"],
        minimum_risk_level="critical",
        minimum_data_classification="restricted",
    )
    first = {
        "schema_version": "1.0",
        "config_version": "client-auth-v1",
        "bindings": [second_binding, first_binding],
    }
    second = {
        "bindings": [first_binding, second_binding],
        "config_version": "client-auth-v1",
        "schema_version": "1.0",
    }

    compact = load_gateway_client_auth_document_text(json.dumps(first, separators=(",", ":")))
    formatted = load_gateway_client_auth_document_text(json.dumps(second, indent=4))

    assert compact.digest == formatted.digest
    assert compact.canonical_payload() == formatted.canonical_payload()
    assert tuple(binding.client_id for binding in compact.bindings) == ("service-a", "service-b")


def test_duplicate_json_key_fails_closed() -> None:
    payload = (
        '{"schema_version":"1.0","config_version":"client-auth-v1",'
        '"config_version":"client-auth-v2","bindings":[]}'
    )

    with pytest.raises(DuplicateGatewayClientAuthKeyError, match="duplicate"):
        load_gateway_client_auth_document_text(payload)


@pytest.mark.parametrize(
    "payload",
    (
        {"schema_version": "1.0", "bindings": []},
        {
            "schema_version": "1.0",
            "config_version": "client-auth-v1",
            "bindings": [],
            "secret": "forbidden-shape",
        },
        {
            "schema_version": "2.0",
            "config_version": "client-auth-v1",
            "bindings": [],
        },
        {
            "schema_version": "1.0",
            "config_version": "invalid version",
            "bindings": [],
        },
    ),
)
def test_document_rejects_missing_unknown_and_unsupported_root_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(GatewayClientAuthDocumentError):
        load_gateway_client_auth_document_text(json.dumps(payload))


@pytest.mark.parametrize("field_name", ("api_key", "credential", "secret_value"))
def test_raw_secret_value_fields_are_not_part_of_artifact_schema(field_name: str) -> None:
    binding = _binding()
    binding[field_name] = "opaque-value"

    with pytest.raises(GatewayClientAuthDocumentError, match="unknown fields"):
        load_gateway_client_auth_document_text(_document([binding]))


def test_duplicate_client_id_fails_closed() -> None:
    bindings = [
        _binding(),
        _binding(
            client_id="service-a",
            credential_reference="GATEWAY_CLIENT_B_KEY",
            allowed_workloads=["code.review"],
        ),
    ]

    with pytest.raises(GatewayClientAuthDocumentError, match="duplicate.*client_id"):
        load_gateway_client_auth_document_text(_document(bindings))


def test_duplicate_credential_reference_fails_closed() -> None:
    bindings = [
        _binding(),
        _binding(
            client_id="service-b",
            credential_reference="GATEWAY_CLIENT_A_KEY",
            allowed_workloads=["code.review"],
        ),
    ]

    with pytest.raises(
        GatewayClientAuthDocumentError,
        match="credential references must be unique",
    ):
        load_gateway_client_auth_document_text(_document(bindings))


@pytest.mark.parametrize(
    ("risk", "classification"),
    (
        ("urgent", "confidential"),
        ("high", "secret"),
    ),
)
def test_unsupported_trust_vocabulary_fails_closed(risk: str, classification: str) -> None:
    binding = _binding(
        minimum_risk_level=risk,
        minimum_data_classification=classification,
    )

    with pytest.raises(GatewayClientAuthDocumentError, match="unsupported"):
        load_gateway_client_auth_document_text(_document([binding]))


@pytest.mark.parametrize(
    "workloads",
    (
        [],
        ["not-dotted"],
        ["rag.answer", "rag.answer"],
        ["rag.answer", "code.review"],
    ),
)
def test_artifact_reuses_pc3_workload_validation(workloads: list[str]) -> None:
    binding = _binding(allowed_workloads=workloads)

    with pytest.raises(GatewayClientAuthDocumentError):
        load_gateway_client_auth_document_text(_document([binding]))


def test_loader_preserves_generic_secret_reference_without_resolving_it() -> None:
    document = load_gateway_client_auth_document_text(
        _document(
            [
                _binding(
                    credential_reference="vault://clients/service-a",
                )
            ]
        )
    )

    assert document.bindings[0].credential_reference == "vault://clients/service-a"
    assert "vault://clients/service-a" in json.dumps(document.canonical_payload())


@pytest.mark.parametrize(
    "payload",
    (
        [],
        {"schema_version": "1.0", "config_version": "client-auth-v1", "bindings": {}},
        {
            "schema_version": "1.0",
            "config_version": "client-auth-v1",
            "bindings": ["not-an-object"],
        },
    ),
)
def test_non_object_or_non_array_shapes_fail_closed(payload: object) -> None:
    with pytest.raises(GatewayClientAuthDocumentError):
        load_gateway_client_auth_document_text(json.dumps(payload))
