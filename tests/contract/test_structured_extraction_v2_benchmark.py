"""Structured-extraction v2 benchmark contract, scoring, and evidence tests."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkSnapshot,
    BenchmarkTarget,
    BenchmarkWorkload,
    JsonValue,
    ObservationStatus,
    ProviderCall,
    Scorecard,
)
from benchmarks.promotion import PromotionError, PromotionMapping, promote_snapshot
from benchmarks.runner import BenchmarkProviderFailure, BenchmarkRunner
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import build_snapshot, dataset_digest
from benchmarks.workloads.structured_extraction_v2 import (
    STRUCTURED_EXTRACTION_V2_BENCHMARK_VERSION,
    STRUCTURED_EXTRACTION_V2_SCORER_ID,
    StructuredExtractionIssue,
    assess_structured_extraction_v2,
    load_structured_extraction_v2_dataset,
    score_structured_extraction_v2,
)

_DATASET = Path("benchmarks/datasets/structured-extraction-v2.json")
_RUN_DATE = date(2026, 9, 4)


class _OutputExecutor:
    """Credential-free executor with deterministic per-case outputs or failures."""

    def __init__(self, outcomes: dict[str, JsonValue | BenchmarkProviderFailure]) -> None:
        self._outcomes = outcomes

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        assert target.target_id == "fixture-structured-v2"
        outcome = self._outcomes[case.case_id]
        if isinstance(outcome, BenchmarkProviderFailure):
            raise outcome
        return ProviderCall(
            output=outcome,
            latency_ms=30,
            ttft_ms=10,
            input_units=25,
            output_units=10,
            cost_usd=Decimal("0.001"),
        )


def _target() -> BenchmarkTarget:
    return BenchmarkTarget(
        target_id="fixture-structured-v2",
        provider="fixture",
        model="structured-model-v2",
        api="fixture/v2",
        configuration="temperature=0;structured_output=true",
        source_date=_RUN_DATE,
    )


def _dataset_cases() -> tuple[BenchmarkCase, ...]:
    return load_structured_extraction_v2_dataset(_DATASET).cases


def _exact_outcomes(
    cases: tuple[BenchmarkCase, ...],
) -> dict[str, JsonValue | BenchmarkProviderFailure]:
    return {case.case_id: case.expected for case in cases}


def _snapshot_for(
    cases: tuple[BenchmarkCase, ...],
    outcomes: dict[str, JsonValue | BenchmarkProviderFailure],
) -> tuple[tuple[BenchmarkObservation, ...], tuple[Scorecard, ...], BenchmarkSnapshot]:
    observations, scorecards = asyncio.run(
        BenchmarkRunner(_OutputExecutor(outcomes), build_default_scorers()).run(cases, (_target(),))
    )
    snapshot = build_snapshot(
        benchmark_version=STRUCTURED_EXTRACTION_V2_BENCHMARK_VERSION,
        runner_version="structured-extraction-runner-v2",
        run_date=_RUN_DATE,
        cases=cases,
        targets=(_target(),),
        observations=observations,
        scorecards=scorecards,
    )
    return observations, scorecards, snapshot


def test_v2_dataset_is_public_versioned_synthetic_and_reproducible() -> None:
    first = load_structured_extraction_v2_dataset(_DATASET)
    second = load_structured_extraction_v2_dataset(_DATASET)

    assert first.schema_version == "1.0"
    assert first.benchmark_version == STRUCTURED_EXTRACTION_V2_BENCHMARK_VERSION
    assert first.data_classification == "public"
    assert len(first.cases) == 6
    assert all(case.workload is BenchmarkWorkload.STRUCTURED_EXTRACTION for case in first.cases)
    assert all(case.scorer == STRUCTURED_EXTRACTION_V2_SCORER_ID for case in first.cases)
    assert all(case.metadata["synthetic"] is True for case in first.cases)
    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_v2_dataset_rejects_malformed_nested_schema(tmp_path: Path) -> None:
    payload = json.loads(_DATASET.read_text(encoding="utf-8"))
    ticket_schema = payload["cases"][1]["metadata"]["output_schema"]
    ticket_schema["properties"]["affected_service"]["additionalProperties"] = True
    path = tmp_path / "malformed-structured-v2.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="reject additional properties"):
        load_structured_extraction_v2_dataset(path)


def test_v2_dataset_rejects_expected_value_that_violates_schema(tmp_path: Path) -> None:
    payload = json.loads(_DATASET.read_text(encoding="utf-8"))
    payload["cases"][0]["expected"]["line_count"] = 3.0
    path = tmp_path / "invalid-expected-structured-v2.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="expected output does not satisfy output_schema"):
        load_structured_extraction_v2_dataset(path)


def test_exact_extraction_scores_one_without_issues() -> None:
    invoice = _dataset_cases()[0]

    assessment = assess_structured_extraction_v2(invoice, invoice.expected)

    assert assessment.schema_valid is True
    assert assessment.schema_score == Decimal("1")
    assert assessment.value_score == Decimal("1")
    assert assessment.score == Decimal("1")
    assert assessment.issues == ()
    assert score_structured_extraction_v2(invoice, invoice.expected) == Decimal("1")


def test_partial_and_missing_extraction_is_explained() -> None:
    invoice = _dataset_cases()[0]
    assert isinstance(invoice.expected, dict)
    partial = dict(invoice.expected)
    partial.pop("currency")

    assessment = assess_structured_extraction_v2(invoice, partial)

    assert assessment.schema_valid is False
    assert assessment.value_score == Decimal(5) / Decimal(6)
    assert assessment.score < Decimal("1")
    assert ("missing_required_field", "/currency") in {
        (issue.code, issue.path) for issue in assessment.issues
    }
    assert ("missing_expected_field", "/currency") in {
        (issue.code, issue.path) for issue in assessment.issues
    }


def test_extra_field_is_rejected_without_permissive_parsing() -> None:
    invoice = _dataset_cases()[0]
    assert isinstance(invoice.expected, dict)
    extra = dict(invoice.expected)
    extra["internal_note"] = "must not be extracted"

    assessment = assess_structured_extraction_v2(invoice, extra)

    assert assessment.schema_valid is False
    assert assessment.value_score == Decimal(6) / Decimal(7)
    assert ("unexpected_field", "/internal_note") in {
        (issue.code, issue.path) for issue in assessment.issues
    }
    assert score_structured_extraction_v2(invoice, '{"invoice_id":"INV-204"}') == Decimal("0")


def test_wrong_integer_type_is_schema_and_value_failure() -> None:
    invoice = _dataset_cases()[0]
    assert isinstance(invoice.expected, dict)
    wrong_type = dict(invoice.expected)
    wrong_type["line_count"] = 3.0

    assessment = assess_structured_extraction_v2(invoice, wrong_type)

    assert assessment.schema_valid is False
    assert assessment.value_score == Decimal(5) / Decimal(6)
    assert ("wrong_type", "/line_count") in {
        (issue.code, issue.path) for issue in assessment.issues
    }


def test_wrong_nested_value_can_be_schema_valid_but_semantically_wrong() -> None:
    ticket = _dataset_cases()[1]
    assert isinstance(ticket.expected, dict)
    wrong_nested = dict(ticket.expected)
    service = wrong_nested["affected_service"]
    assert isinstance(service, dict)
    wrong_nested["affected_service"] = {**service, "tier": "silver"}

    assessment = assess_structured_extraction_v2(ticket, wrong_nested)

    assert assessment.schema_valid is True
    assert assessment.schema_score == Decimal("1")
    assert assessment.value_score == Decimal(5) / Decimal(6)
    assert assessment.score == (Decimal("1") + Decimal(5) / Decimal(6)) / Decimal("2")
    assert assessment.issues == (
        StructuredExtractionIssue("wrong_value", "/affected_service/tier"),
    )


def test_allowed_enum_value_can_still_be_semantically_incorrect() -> None:
    invoice = _dataset_cases()[0]
    assert isinstance(invoice.expected, dict)
    wrong_currency = {**invoice.expected, "currency": "USD"}

    assessment = assess_structured_extraction_v2(invoice, wrong_currency)

    assert assessment.schema_valid is True
    assert assessment.value_score == Decimal(5) / Decimal(6)
    assert [(issue.code, issue.path) for issue in assessment.issues] == [
        ("wrong_value", "/currency")
    ]


def test_array_mismatch_is_deterministic_and_path_explained() -> None:
    purchase_order = _dataset_cases()[2]
    assert isinstance(purchase_order.expected, dict)
    items = purchase_order.expected["items"]
    assert isinstance(items, list)
    truncated = {**purchase_order.expected, "items": items[:1]}

    assessment = assess_structured_extraction_v2(purchase_order, truncated)

    assert assessment.schema_valid is True
    assert assessment.value_score < Decimal("1")
    assert ("array_length_mismatch", "/items") in {
        (issue.code, issue.path) for issue in assessment.issues
    }


def test_optional_absent_field_is_expected_to_remain_absent() -> None:
    purchase_order = _dataset_cases()[2]
    assert isinstance(purchase_order.expected, dict)
    with_absent_field_materialized = {**purchase_order.expected, "discount_code": None}

    assessment = assess_structured_extraction_v2(purchase_order, with_absent_field_materialized)

    assert assessment.schema_valid is True
    assert assessment.value_score < Decimal("1")
    assert ("unexpected_extracted_field", "/discount_code") in {
        (issue.code, issue.path) for issue in assessment.issues
    }


def test_runner_keeps_provider_failure_separate_from_quality_failure() -> None:
    cases = _dataset_cases()[:3]
    first, second, third = cases
    assert isinstance(second.expected, dict)
    quality_failure = {**second.expected, "priority": "low"}
    outcomes: dict[str, JsonValue | BenchmarkProviderFailure] = {
        first.case_id: first.expected,
        second.case_id: quality_failure,
        third.case_id: BenchmarkProviderFailure(
            code="rate_limit",
            status_code=429,
            latency_ms=15,
        ),
    }

    observations, scorecards = asyncio.run(
        BenchmarkRunner(_OutputExecutor(outcomes), build_default_scorers()).run(cases, (_target(),))
    )

    assert [item.status for item in observations] == [
        ObservationStatus.SUCCEEDED,
        ObservationStatus.QUALITY_FAILURE,
        ObservationStatus.PROVIDER_FAILURE,
    ]
    assert observations[1].quality_score is not None
    assert observations[1].quality_score < Decimal("1")
    assert observations[2].quality_score is None
    assert observations[2].provider_error_code == "rate_limit"

    scorecard = scorecards[0]
    assert scorecard.total_cases == 3
    assert scorecard.completed_calls == 2
    assert scorecard.provider_failures == 1
    assert scorecard.quality_successes == 1
    assert scorecard.quality_failures == 1
    assert scorecard.availability_rate == Decimal(2) / Decimal(3)


def test_scorecard_snapshot_and_explicit_promotion_are_deterministic() -> None:
    cases = _dataset_cases()
    outcomes = _exact_outcomes(cases)

    observations, scorecards, first = _snapshot_for(cases, outcomes)
    _, _, second = _snapshot_for(cases, outcomes)

    assert all(item.status is ObservationStatus.SUCCEEDED for item in observations)
    assert all(item.quality_score == Decimal("1") for item in observations)
    assert len(scorecards) == 1
    scorecard = scorecards[0]
    assert scorecard.total_cases == 6
    assert scorecard.completed_calls == 6
    assert scorecard.provider_failures == 0
    assert scorecard.mean_quality_score == Decimal("1")
    assert scorecard.availability_rate == Decimal("1")
    assert first.dataset_digest == dataset_digest(cases)
    assert first.dataset_digest.startswith("sha256:")
    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_id.startswith("sha256:")

    promoted = promote_snapshot(
        first,
        promotion_version="structured-extraction-promotion-v2",
        approval_date=_RUN_DATE,
        approved_by="benchmark-review",
        mappings=(
            PromotionMapping(
                target_id=_target().target_id,
                benchmark_workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
                deployment_id="fixture-deployment",
                runtime_workload="benchmark.structured_extraction",
            ),
        ),
    )

    assert promoted.benchmark_snapshot_id == first.snapshot_id
    assert promoted.dataset_digest == first.dataset_digest
    assert promoted.records[0].quality_score == Decimal("1")
    assert promoted.records[0].availability_rate == Decimal("1")


def test_promotion_fails_closed_without_quality_evidence_or_consistent_mapping() -> None:
    cases = _dataset_cases()
    failures = {
        case.case_id: BenchmarkProviderFailure(code="unavailable", status_code=503)
        for case in cases
    }
    _, _, failed_snapshot = _snapshot_for(cases, failures)

    mapping = PromotionMapping(
        target_id=_target().target_id,
        benchmark_workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        deployment_id="fixture-deployment",
        runtime_workload="benchmark.structured_extraction",
    )
    with pytest.raises(PromotionError, match="at least one completed call"):
        promote_snapshot(
            failed_snapshot,
            promotion_version="structured-extraction-promotion-v2",
            approval_date=_RUN_DATE,
            approved_by="benchmark-review",
            mappings=(mapping,),
        )

    _, _, good_snapshot = _snapshot_for(cases, _exact_outcomes(cases))
    inconsistent = PromotionMapping(
        target_id="missing-target",
        benchmark_workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        deployment_id="fixture-deployment",
        runtime_workload="benchmark.structured_extraction",
    )
    with pytest.raises(PromotionError, match="has no scorecard"):
        promote_snapshot(
            good_snapshot,
            promotion_version="structured-extraction-promotion-v2",
            approval_date=_RUN_DATE,
            approved_by="benchmark-review",
            mappings=(inconsistent,),
        )
