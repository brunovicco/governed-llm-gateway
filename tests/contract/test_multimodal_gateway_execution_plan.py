from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    DataClassification,
    ImageMediaType,
    MessageRole,
    RiskLevel,
)

from benchmarks.contracts import BenchmarkCase
from benchmarks.fixture_publication import (
    BenchmarkFixturePublication,
    load_fixture_publication_manifest,
)
from benchmarks.multimodal_execution import build_multimodal_gateway_execution_plan
from benchmarks.workloads.multimodal_analysis import load_multimodal_analysis_dataset

_REQUEST_ID = UUID("11111111-2222-3333-4444-555555555555")
_WORKLOAD_IDENTITY = "benchmarks.multimodal-analysis-v1"


def _inputs() -> tuple[BenchmarkCase, BenchmarkFixturePublication]:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = repo_root / "benchmarks" / "fixtures" / "multimodal-v1"
    dataset = load_multimodal_analysis_dataset(
        repo_root / "benchmarks" / "datasets" / "multimodal-analysis-v1.json",
        fixture_root / "manifest.json",
        fixture_root / "publication.json",
    )
    publications = load_fixture_publication_manifest(fixture_root / "publication.json")
    case = dataset.cases[0]
    publication = publications.require(str(case.metadata["fixture_id"]))
    return case, publication


def test_execution_plan_materializes_provider_neutral_visual_request() -> None:
    case, publication = _inputs()

    plan = build_multimodal_gateway_execution_plan(
        case,
        publication,
        request_id=_REQUEST_ID,
        workload_identity=_WORKLOAD_IDENTITY,
    )

    assert plan.case_id == case.case_id
    assert plan.fixture_id == case.metadata["fixture_id"]
    assert plan.fixture_digest == case.metadata["fixture_digest"]
    assert plan.publication_revision == publication.source_revision

    request = plan.request
    assert request.request_id == _REQUEST_ID
    assert request.workload == _WORKLOAD_IDENTITY
    assert request.risk_level is RiskLevel.LOW
    assert request.data_classification is DataClassification.PUBLIC
    assert request.requirements.vision is True
    assert request.requirements.structured_output is False
    assert request.structured_output is None
    assert len(request.messages) == 1

    message = request.messages[0]
    assert message.role is MessageRole.USER
    assert message.content == case.prompt
    assert len(message.images) == 1
    assert message.images[0].media_type is ImageMediaType.PNG
    assert message.images[0].url == publication.url


def test_execution_plan_does_not_invent_authorized_workload_identity() -> None:
    case, publication = _inputs()

    with pytest.raises(ValueError, match="workload must be a dotted policy-defined identifier"):
        build_multimodal_gateway_execution_plan(
            case,
            publication,
            request_id=_REQUEST_ID,
            workload_identity="multimodal-analysis-v1",
        )


def test_execution_plan_rejects_publication_identity_drift() -> None:
    case, publication = _inputs()
    changed_publication = BenchmarkFixturePublication(
        fixture_id="multimodal.other",
        digest=publication.digest,
        source=publication.source,
        source_revision=publication.source_revision,
        url=publication.url,
    )

    with pytest.raises(ValueError, match="fixture_id does not match benchmark case"):
        build_multimodal_gateway_execution_plan(
            case,
            changed_publication,
            request_id=_REQUEST_ID,
            workload_identity=_WORKLOAD_IDENTITY,
        )


def test_execution_plan_rejects_publication_digest_drift() -> None:
    case, publication = _inputs()
    changed_publication = BenchmarkFixturePublication(
        fixture_id=publication.fixture_id,
        digest="sha256:" + "0" * 64,
        source=publication.source,
        source_revision=publication.source_revision,
        url=publication.url,
    )

    with pytest.raises(ValueError, match="digest does not match benchmark case"):
        build_multimodal_gateway_execution_plan(
            case,
            changed_publication,
            request_id=_REQUEST_ID,
            workload_identity=_WORKLOAD_IDENTITY,
        )
