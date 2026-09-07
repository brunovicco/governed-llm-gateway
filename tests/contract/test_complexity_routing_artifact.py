"""Contract tests for the versioned complexity-routing operational artifact."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from governed_llm_gateway_contracts import TaskComplexity
from governed_llm_gateway_core.adapters import (
    ComplexityRoutingDocumentError,
    DuplicateComplexityRoutingKeyError,
    load_complexity_routing_document,
    load_complexity_routing_document_text,
)

_DEFAULT_PATH = Path("config/routing/complexity.json")
_EXPECTED_DIGEST = "d0af20218d6670dbfd1fbe58685eb46f57cd5b56a02e2afd57c8fefaa064e42d"


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "config_version": "complexity-routing-v1",
        "assessment_policy": {
            "policy_id": "deterministic-complexity",
            "version": "v1",
            "medium_context_tokens": 8_000,
            "high_context_tokens": 32_000,
            "medium_output_tokens": 2_000,
            "high_output_tokens": 8_000,
            "tool_calling_floor": "medium",
            "structured_output_floor": "medium",
            "vision_floor": "high",
            "workload_floors": [],
        },
        "quality_policy": {
            "policy_id": "complexity-quality",
            "version": "v1",
            "low_min_quality": "0.50",
            "medium_min_quality": "0.75",
            "high_min_quality": "0.90",
        },
    }


def _dump(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=True)


def test_default_artifact_loads_existing_immutable_domain_policies() -> None:
    document = load_complexity_routing_document(_DEFAULT_PATH)

    assert document.schema_version == "1.0"
    assert document.config_version == "complexity-routing-v1"
    assert document.assessment_policy.policy_id == "deterministic-complexity"
    assert document.assessment_policy.medium_context_tokens == 8_000
    assert document.assessment_policy.high_context_tokens == 32_000
    assert document.assessment_policy.tool_calling_floor is TaskComplexity.MEDIUM
    assert document.assessment_policy.vision_floor is TaskComplexity.HIGH
    assert document.assessment_policy.workload_floors == ()
    assert document.quality_policy.low_min_quality == Decimal("0.50")
    assert document.quality_policy.medium_min_quality == Decimal("0.75")
    assert document.quality_policy.high_min_quality == Decimal("0.90")
    assert document.digest == _EXPECTED_DIGEST


def test_digest_is_semantic_and_independent_of_json_field_order_or_decimal_scale() -> None:
    first = load_complexity_routing_document_text(_dump(_payload()))
    payload = _payload()
    quality = payload["quality_policy"]
    assert isinstance(quality, dict)
    quality["low_min_quality"] = "0.5"
    quality["high_min_quality"] = "0.9"
    reordered = json.dumps(payload, sort_keys=True, indent=4)

    second = load_complexity_routing_document_text(reordered)

    assert first.canonical_payload() == second.canonical_payload()
    assert first.digest == second.digest == _EXPECTED_DIGEST


def test_default_artifact_contains_no_authority_provider_or_secret_fields() -> None:
    document = load_complexity_routing_document(_DEFAULT_PATH)
    serialized = json.dumps(document.canonical_payload(), sort_keys=True)

    forbidden = (
        "authorized_model_group",
        "provider",
        "model_id",
        "deployment_id",
        "credential",
        "secret",
        "api_key",
        "endpoint",
        "messages",
        "prompt",
        "completion",
    )
    assert all(token not in serialized for token in forbidden)


def test_duplicate_json_key_fails_closed() -> None:
    text = _dump(_payload()).replace(
        '"schema_version": "1.0"',
        '"schema_version": "1.0", "schema_version": "1.0"',
        1,
    )

    with pytest.raises(DuplicateComplexityRoutingKeyError):
        load_complexity_routing_document_text(text)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("root", "provider", "openai"),
        ("assessment_policy", "model_group", "general"),
        ("quality_policy", "ranking_weight", "0.5"),
    ],
)
def test_unknown_fields_fail_closed(section: str, field: str, value: object) -> None:
    payload = _payload()
    target: dict[str, object]
    if section == "root":
        target = payload
    else:
        raw_target = payload[section]
        assert isinstance(raw_target, dict)
        target = raw_target
    target[field] = value

    with pytest.raises(ComplexityRoutingDocumentError, match="fields are invalid"):
        load_complexity_routing_document_text(_dump(payload))


def test_threshold_ordering_is_delegated_to_domain_policy_and_fails_closed() -> None:
    payload = _payload()
    assessment = payload["assessment_policy"]
    assert isinstance(assessment, dict)
    assessment["high_context_tokens"] = 8_000

    with pytest.raises(
        ComplexityRoutingDocumentError,
        match="high context token threshold must exceed medium threshold",
    ):
        load_complexity_routing_document_text(_dump(payload))


def test_workload_floors_must_be_sorted_unique_and_provider_neutral() -> None:
    payload = _payload()
    assessment = payload["assessment_policy"]
    assert isinstance(assessment, dict)
    assessment["workload_floors"] = [
        {"workload": "zeta.reasoning", "minimum": "high"},
        {"workload": "alpha.extraction", "minimum": "medium"},
    ]

    with pytest.raises(ComplexityRoutingDocumentError, match="must be sorted by workload"):
        load_complexity_routing_document_text(_dump(payload))

    duplicate_payload = _payload()
    duplicate_assessment = duplicate_payload["assessment_policy"]
    assert isinstance(duplicate_assessment, dict)
    duplicate_assessment["workload_floors"] = [
        {"workload": "demo.reasoning", "minimum": "medium"},
        {"workload": "demo.reasoning", "minimum": "high"},
    ]
    with pytest.raises(ComplexityRoutingDocumentError, match="must not contain duplicate"):
        load_complexity_routing_document_text(_dump(duplicate_payload))


def test_workload_floor_rejects_unknown_fields_and_invalid_complexity() -> None:
    payload = _payload()
    assessment = payload["assessment_policy"]
    assert isinstance(assessment, dict)
    assessment["workload_floors"] = [
        {"workload": "demo.reasoning", "minimum": "critical", "provider": "x"}
    ]

    with pytest.raises(ComplexityRoutingDocumentError, match="fields are invalid"):
        load_complexity_routing_document_text(_dump(payload))

    clean = deepcopy(payload)
    clean_assessment = clean["assessment_policy"]
    assert isinstance(clean_assessment, dict)
    clean_assessment["workload_floors"] = [{"workload": "demo.reasoning", "minimum": "critical"}]
    with pytest.raises(
        ComplexityRoutingDocumentError,
        match="provider-neutral complexity vocabulary",
    ):
        load_complexity_routing_document_text(_dump(clean))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("low_min_quality", 0.5, "normalized decimal string"),
        ("low_min_quality", "-0.1", "finite Decimal between 0 and 1"),
        ("high_min_quality", "1.1", "finite Decimal between 0 and 1"),
    ],
)
def test_quality_floors_reject_ambiguous_or_out_of_range_values(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _payload()
    quality = payload["quality_policy"]
    assert isinstance(quality, dict)
    quality[field] = value

    with pytest.raises(ComplexityRoutingDocumentError, match=message):
        load_complexity_routing_document_text(_dump(payload))


def test_quality_floors_must_remain_monotonic() -> None:
    payload = _payload()
    quality = payload["quality_policy"]
    assert isinstance(quality, dict)
    quality["medium_min_quality"] = "0.95"
    quality["high_min_quality"] = "0.90"

    with pytest.raises(ComplexityRoutingDocumentError, match="must be monotonic"):
        load_complexity_routing_document_text(_dump(payload))


def test_invalid_schema_version_and_malformed_root_fail_closed() -> None:
    payload = _payload()
    payload["schema_version"] = "2.0"
    with pytest.raises(ComplexityRoutingDocumentError, match="schema_version"):
        load_complexity_routing_document_text(_dump(payload))

    with pytest.raises(ComplexityRoutingDocumentError, match="root must be an object"):
        load_complexity_routing_document_text("[]")
