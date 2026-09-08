"""Contract tests for the deployment-owned operations-read access artifact."""

import json

import pytest
from governed_llm_gateway_api import (
    DuplicateOperationsReadAccessKeyError,
    GatewayClientAuthBinding,
    GatewayClientAuthDocument,
    OperationsReadAccessDocumentError,
    load_operations_read_access_document_text,
    validate_operations_access_client_auth,
)
from governed_llm_gateway_contracts import DataClassification, RiskLevel


def _client_auth_document() -> GatewayClientAuthDocument:
    return GatewayClientAuthDocument(
        schema_version="1.0",
        config_version="ops-test-clients",
        bindings=(
            GatewayClientAuthBinding(
                client_id="service-a",
                environment="development",
                credential_reference="GATEWAY_CLIENT_A_KEY",
                allowed_workloads=("rag.answer",),
                minimum_risk_level=RiskLevel.HIGH,
                minimum_data_classification=DataClassification.CONFIDENTIAL,
            ),
            GatewayClientAuthBinding(
                client_id="service-b",
                environment="staging",
                credential_reference="GATEWAY_CLIENT_B_KEY",
                allowed_workloads=("code.review",),
                minimum_risk_level=RiskLevel.MEDIUM,
                minimum_data_classification=DataClassification.INTERNAL,
            ),
        ),
    )


def _document_text() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "ops-read-v1",
            "principals": [
                {"client_id": "service-a", "environment": "development"},
                {"client_id": "service-b", "environment": "staging"},
            ],
        }
    )


def test_valid_document_has_deterministic_canonical_digest_and_cross_validates() -> None:
    first = load_operations_read_access_document_text(_document_text())
    second = load_operations_read_access_document_text(
        '{"principals":[{"environment":"development","client_id":"service-a"},'
        '{"environment":"staging","client_id":"service-b"}],'
        '"config_version":"ops-read-v1","schema_version":"1.0"}'
    )

    validate_operations_access_client_auth(first, _client_auth_document())

    assert first.digest == second.digest
    assert first.canonical_payload() == {
        "schema_version": "1.0",
        "config_version": "ops-read-v1",
        "principals": [
            {"client_id": "service-a", "environment": "development"},
            {"client_id": "service-b", "environment": "staging"},
        ],
    }


def test_empty_document_is_explicit_deny_all() -> None:
    document = load_operations_read_access_document_text(
        '{"schema_version":"1.0","config_version":"deny-all","principals":[]}'
    )

    validate_operations_access_client_auth(document, _client_auth_document())

    assert document.policy.principals == ()


def test_duplicate_json_key_is_rejected() -> None:
    with pytest.raises(DuplicateOperationsReadAccessKeyError):
        load_operations_read_access_document_text(
            '{"schema_version":"1.0","schema_version":"1.0",'
            '"config_version":"ops-read-v1","principals":[]}'
        )


@pytest.mark.parametrize(
    "text,match",
    (
        (
            '{"schema_version":"1.0","config_version":"ops-read-v1",'
            '"principals":[],"unexpected":true}',
            "unknown fields",
        ),
        (
            '{"schema_version":"2.0","config_version":"ops-read-v1","principals":[]}',
            "schema_version",
        ),
        (
            '{"schema_version":"1.0","config_version":"bad version","principals":[]}',
            "normalized identifier",
        ),
        (
            '{"schema_version":"1.0","config_version":"ops-read-v1",'
            '"principals":[{"client_id":"service-b","environment":"staging"},'
            '{"client_id":"service-a","environment":"development"}]}',
            "deterministic",
        ),
        (
            '{"schema_version":"1.0","config_version":"ops-read-v1",'
            '"principals":[{"client_id":"service-a","environment":"development"},'
            '{"client_id":"service-a","environment":"development"}]}',
            "duplicates",
        ),
    ),
)
def test_closed_document_rejects_malformed_or_non_deterministic_content(
    text: str,
    match: str,
) -> None:
    with pytest.raises(OperationsReadAccessDocumentError, match=match):
        load_operations_read_access_document_text(text)


def test_unknown_client_or_environment_fails_cross_artifact_validation() -> None:
    unknown_client = load_operations_read_access_document_text(
        '{"schema_version":"1.0","config_version":"ops-read-v1",'
        '"principals":[{"client_id":"service-z","environment":"development"}]}'
    )
    wrong_environment = load_operations_read_access_document_text(
        '{"schema_version":"1.0","config_version":"ops-read-v1",'
        '"principals":[{"client_id":"service-a","environment":"staging"}]}'
    )

    with pytest.raises(OperationsReadAccessDocumentError, match="configured Gateway client"):
        validate_operations_access_client_auth(unknown_client, _client_auth_document())
    with pytest.raises(OperationsReadAccessDocumentError, match="configured Gateway client"):
        validate_operations_access_client_auth(wrong_environment, _client_auth_document())
