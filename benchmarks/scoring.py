"""Deterministic offline scorers for the reviewed benchmark workloads."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol

from .contracts import BenchmarkCase, BenchmarkQualityMetric, JsonValue
from .workloads.agent_orchestration import (
    AGENT_ORCHESTRATION_SCORER_ID,
    assess_agent_orchestration,
)
from .workloads.classification import CLASSIFICATION_SCORER_ID, score_classification
from .workloads.code_generation import CODE_GENERATION_SCORER_ID, score_code_generation
from .workloads.code_review import CODE_REVIEW_SCORER_ID, score_code_review
from .workloads.json_schema_compliance import (
    JSON_SCHEMA_COMPLIANCE_SCORER_ID,
    assess_json_schema_compliance,
)
from .workloads.long_context import LONG_CONTEXT_SCORER_ID, score_long_context
from .workloads.multi_step_tool_use import (
    MULTI_STEP_TOOL_USE_SCORER_ID,
    assess_multi_step_tool_use,
)
from .workloads.multimodal_analysis import (
    MULTIMODAL_ANALYSIS_SCORER_ID,
    score_multimodal_analysis,
)
from .workloads.rag_answer import RAG_ANSWER_SCORER_ID, assess_rag_answer
from .workloads.rag_ptbr import RAG_PTBR_SCORER_ID, score_rag_ptbr
from .workloads.rag_ptbr_v2 import (
    RAG_PTBR_V2_SCORER_ID,
    assess_rag_ptbr_v2,
)
from .workloads.reasoning import REASONING_SCORER_ID, score_reasoning
from .workloads.security_analysis import (
    SECURITY_ANALYSIS_SCORER_ID,
    score_security_analysis,
)
from .workloads.structured_extraction import (
    STRUCTURED_EXTRACTION_SCORER_ID,
    score_structured_extraction,
)
from .workloads.structured_extraction_v2 import (
    STRUCTURED_EXTRACTION_V2_SCORER_ID,
    assess_structured_extraction_v2,
)
from .workloads.tool_argument_generation import (
    TOOL_ARGUMENT_GENERATION_SCORER_ID,
    assess_tool_argument_generation,
)
from .workloads.tool_selection import (
    TOOL_SELECTION_SCORER_ID,
    assess_tool_selection,
)
from .workloads.tool_use import TOOL_USE_SCORER_ID, assess_tool_use


class DeterministicScorer(Protocol):
    """Score normalized provider output without another model or network dependency."""

    def __call__(self, case: BenchmarkCase, output: JsonValue) -> Decimal:
        """Return a deterministic quality score from 0 through 1."""
        ...


@dataclass(frozen=True, slots=True)
class QualityMeasurement:
    """Scalar quality plus optional reviewed component evidence for one completed call."""

    score: Decimal
    metrics: Mapping[BenchmarkQualityMetric, Decimal]

    def __post_init__(self) -> None:
        """Validate and freeze bounded quality evidence."""
        if not Decimal("0") <= self.score <= Decimal("1"):
            raise ValueError("quality measurement score must be between 0 and 1")
        metrics: dict[BenchmarkQualityMetric, Decimal] = {}
        for metric, value in self.metrics.items():
            if not isinstance(metric, BenchmarkQualityMetric):
                raise ValueError("quality measurement keys must use BenchmarkQualityMetric")
            if not isinstance(value, Decimal) or not Decimal("0") <= value <= Decimal("1"):
                raise ValueError("quality measurement values must be Decimal values from 0 to 1")
            metrics[metric] = value
        object.__setattr__(self, "metrics", MappingProxyType(metrics))


class ComponentScorer:
    """Backward-compatible scalar scorer that can also expose reviewed component evidence."""

    def __init__(
        self,
        evaluator: Callable[[BenchmarkCase, JsonValue], QualityMeasurement],
    ) -> None:
        """Bind one deterministic component-aware evaluator."""
        self._evaluator = evaluator

    def __call__(self, case: BenchmarkCase, output: JsonValue) -> Decimal:
        """Preserve the historical scalar scorer callable contract."""
        return self.evaluate(case, output).score

    def evaluate(self, case: BenchmarkCase, output: JsonValue) -> QualityMeasurement:
        """Return scalar and reviewed component evidence together."""
        return self._evaluator(case, output)


def evaluate_scorer(
    scorer: DeterministicScorer,
    case: BenchmarkCase,
    output: JsonValue,
) -> QualityMeasurement:
    """Evaluate a scorer without requiring every historical scorer to expose components."""
    if isinstance(scorer, ComponentScorer):
        return scorer.evaluate(case, output)
    return QualityMeasurement(score=scorer(case, output), metrics={})


def _exact_json(case: BenchmarkCase, output: JsonValue) -> Decimal:
    return Decimal("1") if output == case.expected else Decimal("0")


def _contains_all(case: BenchmarkCase, output: JsonValue) -> Decimal:
    if not isinstance(case.expected, list):
        raise ValueError("contains_all scorer expects a list of required strings")
    required: list[str] = []
    for item in case.expected:
        if not isinstance(item, str):
            raise ValueError("contains_all scorer expects a list of required strings")
        required.append(item.casefold())
    if not isinstance(output, str):
        return Decimal("0")
    if not required:
        return Decimal("1")
    normalized = output.casefold()
    matches = sum(1 for item in required if item in normalized)
    return Decimal(matches) / Decimal(len(required))


def _mapping_fields(case: BenchmarkCase, output: JsonValue) -> Decimal:
    if not isinstance(case.expected, dict):
        raise ValueError("mapping_fields scorer expects an object")
    if not isinstance(output, dict):
        return Decimal("0")
    if not case.expected:
        return Decimal("1")
    matches = sum(1 for key, expected in case.expected.items() if output.get(key) == expected)
    return Decimal(matches) / Decimal(len(case.expected))


def _ordered_sequence(case: BenchmarkCase, output: JsonValue) -> Decimal:
    if not isinstance(case.expected, list):
        raise ValueError("ordered_sequence scorer expects a list")
    if not isinstance(output, list):
        return Decimal("0")
    if not case.expected:
        return Decimal("1")
    matches = sum(
        1
        for index, expected in enumerate(case.expected)
        if index < len(output) and output[index] == expected
    )
    return Decimal(matches) / Decimal(len(case.expected))


def _structured_extraction_v2_measurement(
    case: BenchmarkCase,
    output: JsonValue,
) -> QualityMeasurement:
    assessment = assess_structured_extraction_v2(case, output)
    return QualityMeasurement(
        score=assessment.score,
        metrics={BenchmarkQualityMetric.SCHEMA_VALIDITY: assessment.schema_score},
    )


def _json_schema_compliance_measurement(
    case: BenchmarkCase,
    output: JsonValue,
) -> QualityMeasurement:
    assessment = assess_json_schema_compliance(case, output)
    return QualityMeasurement(
        score=assessment.score,
        metrics={BenchmarkQualityMetric.SCHEMA_VALIDITY: assessment.score},
    )


def _tool_use_measurement(case: BenchmarkCase, output: JsonValue) -> QualityMeasurement:
    assessment = assess_tool_use(case, output)
    return QualityMeasurement(
        score=assessment.score,
        metrics={
            BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: assessment.selection_score,
            BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: assessment.arguments_score,
        },
    )


def _tool_selection_measurement(case: BenchmarkCase, output: JsonValue) -> QualityMeasurement:
    assessment = assess_tool_selection(case, output)
    return QualityMeasurement(
        score=assessment.score,
        metrics={BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: assessment.score},
    )


def _tool_argument_measurement(case: BenchmarkCase, output: JsonValue) -> QualityMeasurement:
    assessment = assess_tool_argument_generation(case, output)
    return QualityMeasurement(
        score=assessment.score,
        metrics={BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: assessment.score},
    )


def _multi_step_tool_measurement(case: BenchmarkCase, output: JsonValue) -> QualityMeasurement:
    assessment = assess_multi_step_tool_use(case, output)
    trajectory = Decimal("1") if assessment.trajectory_success else Decimal("0")
    return QualityMeasurement(
        score=assessment.score,
        metrics={
            BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: assessment.selection_score,
            BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: assessment.arguments_score,
            BenchmarkQualityMetric.TRAJECTORY_SUCCESS: trajectory,
        },
    )


def _agent_orchestration_measurement(
    case: BenchmarkCase,
    output: JsonValue,
) -> QualityMeasurement:
    assessment = assess_agent_orchestration(case, output)
    trajectory = Decimal("1") if assessment.trajectory_success else Decimal("0")
    return QualityMeasurement(
        score=assessment.score,
        metrics={BenchmarkQualityMetric.TRAJECTORY_SUCCESS: trajectory},
    )


def _rag_answer_measurement(case: BenchmarkCase, output: JsonValue) -> QualityMeasurement:
    assessment = assess_rag_answer(case, output)
    return QualityMeasurement(
        score=assessment.score,
        metrics={BenchmarkQualityMetric.GROUNDING: assessment.score},
    )


def _rag_ptbr_v2_measurement(case: BenchmarkCase, output: JsonValue) -> QualityMeasurement:
    assessment = assess_rag_ptbr_v2(case, output)
    return QualityMeasurement(
        score=assessment.score,
        metrics={
            BenchmarkQualityMetric.GROUNDING: assessment.grounding_score,
            BenchmarkQualityMetric.PT_BR_QUALITY: assessment.pt_br_quality_score,
        },
    )


def build_default_scorers() -> Mapping[str, DeterministicScorer]:
    """Return the bounded credential-free scorer registry used by benchmark datasets."""
    scorers: dict[str, DeterministicScorer] = {
        "exact_json": _exact_json,
        "contains_all": _contains_all,
        "mapping_fields": _mapping_fields,
        "ordered_sequence": _ordered_sequence,
        STRUCTURED_EXTRACTION_SCORER_ID: score_structured_extraction,
        STRUCTURED_EXTRACTION_V2_SCORER_ID: ComponentScorer(_structured_extraction_v2_measurement),
        JSON_SCHEMA_COMPLIANCE_SCORER_ID: ComponentScorer(_json_schema_compliance_measurement),
        RAG_PTBR_SCORER_ID: score_rag_ptbr,
        RAG_PTBR_V2_SCORER_ID: ComponentScorer(_rag_ptbr_v2_measurement),
        RAG_ANSWER_SCORER_ID: ComponentScorer(_rag_answer_measurement),
        CODE_GENERATION_SCORER_ID: score_code_generation,
        CODE_REVIEW_SCORER_ID: score_code_review,
        SECURITY_ANALYSIS_SCORER_ID: score_security_analysis,
        TOOL_ARGUMENT_GENERATION_SCORER_ID: ComponentScorer(_tool_argument_measurement),
        TOOL_SELECTION_SCORER_ID: ComponentScorer(_tool_selection_measurement),
        TOOL_USE_SCORER_ID: ComponentScorer(_tool_use_measurement),
        MULTI_STEP_TOOL_USE_SCORER_ID: ComponentScorer(_multi_step_tool_measurement),
        AGENT_ORCHESTRATION_SCORER_ID: ComponentScorer(_agent_orchestration_measurement),
        MULTIMODAL_ANALYSIS_SCORER_ID: score_multimodal_analysis,
        LONG_CONTEXT_SCORER_ID: score_long_context,
        CLASSIFICATION_SCORER_ID: score_classification,
        REASONING_SCORER_ID: score_reasoning,
    }
    return scorers


def require_scorer(
    scorers: Mapping[str, DeterministicScorer], scorer_id: str
) -> DeterministicScorer:
    """Resolve a scorer by versioned dataset identifier and fail closed if unknown."""
    scorer = scorers.get(scorer_id)
    if scorer is None:
        raise ValueError(f"unknown deterministic scorer: {scorer_id}")
    return scorer


def ensure_supported_scorers(
    cases: Sequence[BenchmarkCase], scorers: Mapping[str, DeterministicScorer]
) -> None:
    """Validate all dataset scorer references before any provider call is attempted."""
    unknown = sorted({case.scorer for case in cases if case.scorer not in scorers})
    if unknown:
        raise ValueError(f"dataset references unknown deterministic scorers: {', '.join(unknown)}")
