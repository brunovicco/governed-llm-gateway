"""Provider-neutral execution-plan materialization for multimodal benchmark cases."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    ImageInput,
    ImageMediaType,
    Message,
    MessageRole,
    RiskLevel,
    WorkloadRequirements,
)

from benchmarks.contracts import BenchmarkCase
from benchmarks.fixture_publication import BenchmarkFixturePublication
from benchmarks.workloads.multimodal_analysis import validate_multimodal_analysis_case


@dataclass(frozen=True, slots=True)
class MultimodalGatewayExecutionPlan:
    """Gateway request plus immutable benchmark fixture provenance."""

    case_id: str
    fixture_id: str
    fixture_digest: str
    publication_revision: str
    request: GatewayRequest


def build_multimodal_gateway_execution_plan(
    case: BenchmarkCase,
    publication: BenchmarkFixturePublication,
    *,
    request_id: UUID,
    workload_identity: str,
) -> MultimodalGatewayExecutionPlan:
    """Materialize one validated visual case without bypassing workload authorization."""
    validate_multimodal_analysis_case(case)

    fixture_id = _required_metadata_string(case, "fixture_id")
    fixture_digest = _required_metadata_string(case, "fixture_digest")
    fixture_media_type = _required_metadata_string(case, "fixture_media_type")

    if publication.fixture_id != fixture_id:
        raise ValueError("multimodal execution publication fixture_id does not match benchmark case")
    if publication.digest != fixture_digest:
        raise ValueError("multimodal execution publication digest does not match benchmark case")

    request = GatewayRequest(
        schema_version="1.0",
        request_id=request_id,
        workload=workload_identity,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(vision=True),
        messages=(
            Message(
                role=MessageRole.USER,
                content=case.prompt,
                images=(
                    ImageInput(
                        media_type=ImageMediaType(fixture_media_type),
                        url=publication.url,
                    ),
                ),
            ),
        ),
    )

    return MultimodalGatewayExecutionPlan(
        case_id=case.case_id,
        fixture_id=fixture_id,
        fixture_digest=fixture_digest,
        publication_revision=publication.source_revision,
        request=request,
    )


def _required_metadata_string(case: BenchmarkCase, key: str) -> str:
    value = case.metadata.get(key)
    if not isinstance(value, str):
        raise ValueError(f"multimodal execution requires string metadata field: {key}")
    return value
