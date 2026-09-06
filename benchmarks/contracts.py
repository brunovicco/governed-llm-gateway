"""Provider-neutral contracts for deterministic benchmark execution."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class BenchmarkWorkload(StrEnum):
    """Versioned benchmark workload vocabulary."""

    CLASSIFICATION = "classification"
    REASONING = "reasoning"
    STRUCTURED_EXTRACTION = "structured_extraction"
    JSON_SCHEMA_COMPLIANCE = "json_schema_compliance"
    RAG_PTBR = "rag_ptbr"
    RAG_ANSWER = "rag_answer"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    SECURITY_ANALYSIS = "security_analysis"
    TOOL_SELECTION = "tool_selection"
    TOOL_ARGUMENT_GENERATION = "tool_argument_generation"
    TOOL_USE = "tool_use"
    MULTI_STEP_TOOL_USE = "multi_step_tool_use"
    AGENT_ORCHESTRATION = "agent_orchestration"
    MULTIMODAL_ANALYSIS = "multimodal_analysis"
    LONG_CONTEXT = "long_context"


class BenchmarkQualityMetric(StrEnum):
    """Bounded reviewed offline-quality metric vocabulary."""

    SCHEMA_VALIDITY = "schema_validity"
    TOOL_SELECTION_ACCURACY = "tool_selection_accuracy"
    TOOL_ARGUMENT_ACCURACY = "tool_argument_accuracy"
    TRAJECTORY_SUCCESS = "trajectory_success"
    GROUNDING = "grounding"


class ObservationStatus(StrEnum):
    """Separate model-quality evidence from provider-availability evidence."""

    SUCCEEDED = "succeeded"
    QUALITY_FAILURE = "quality_failure"
    PROVIDER_FAILURE = "provider_failure"


@dataclass(frozen=True, slots=True)
class BenchmarkTarget:
    """Fully identified provider/model/API/configuration benchmark target."""

    target_id: str
    provider: str
    model: str
    api: str
    configuration: str
    source_date: date
    api_family: str | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        """Validate normalized target provenance fields."""
        for field_name in ("target_id", "provider", "model", "api", "configuration"):
            value = getattr(self, field_name)
            if not value or value.strip() != value:
                raise ValueError(f"{field_name} must be non-empty and normalized")
        if self.api_family is not None and (
            not self.api_family or self.api_family.strip() != self.api_family
        ):
            raise ValueError("api_family must be normalized when present")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive when present")


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One public/synthetic deterministic benchmark case."""

    case_id: str
    workload: BenchmarkWorkload
    scorer: str
    prompt: str
    expected: JsonValue
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate case identity and freeze metadata."""
        if not self.case_id or self.case_id.strip() != self.case_id:
            raise ValueError("case_id must be non-empty and normalized")
        if not self.scorer or self.scorer.strip() != self.scorer:
            raise ValueError("scorer must be non-empty and normalized")
        if not self.prompt:
            raise ValueError("prompt must not be empty")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    """Versioned public/synthetic dataset with explicit data classification."""

    schema_version: str
    benchmark_version: str
    data_classification: str
    cases: tuple[BenchmarkCase, ...]

    def __post_init__(self) -> None:
        """Require the Phase 10 dataset schema and public classification."""
        if self.schema_version != "1.0":
            raise ValueError("unsupported benchmark dataset schema_version")
        if not self.benchmark_version or self.benchmark_version.strip() != self.benchmark_version:
            raise ValueError("benchmark_version must be non-empty and normalized")
        if self.data_classification != "public":
            raise ValueError("Phase 10 credential-free datasets must be explicitly public")
        if not self.cases:
            raise ValueError("benchmark dataset must contain at least one case")


@dataclass(frozen=True, slots=True)
class ProviderCall:
    """Normalized successful provider call evidence used by deterministic scorers."""

    output: JsonValue
    latency_ms: int
    ttft_ms: int | None = None
    input_units: int | None = None
    output_units: int | None = None
    cost_usd: Decimal | None = None
    fallback_count: int = 0
    provider: str | None = None
    model: str | None = None
    deployment: str | None = None
    api_family: str | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        """Validate normalized metrics and optional terminal execution identity."""
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        if self.ttft_ms is not None and self.ttft_ms < 0:
            raise ValueError("ttft_ms must be non-negative")
        for name in ("input_units", "output_units"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.cost_usd is not None and self.cost_usd < 0:
            raise ValueError("cost_usd must be non-negative")
        if self.fallback_count < 0:
            raise ValueError("fallback_count must be non-negative")

        identity = (
            ("provider", self.provider),
            ("model", self.model),
            ("deployment", self.deployment),
        )
        if not all(value is None for _, value in identity):
            for name, value in identity:
                if value is None or not value or value.strip() != value:
                    raise ValueError(
                        f"provider call {name} must be present and normalized "
                        "when execution identity is set"
                    )
        if self.api_family is not None:
            if self.provider is None:
                raise ValueError("provider call api_family requires execution identity")
            if not self.api_family or self.api_family.strip() != self.api_family:
                raise ValueError("provider call api_family must be normalized when present")
        if self.max_output_tokens is not None:
            if self.provider is None:
                raise ValueError("provider call max_output_tokens requires execution identity")
            if self.max_output_tokens <= 0:
                raise ValueError("provider call max_output_tokens must be positive when present")


@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    """One target/case result with quality, availability, and execution evidence separated."""

    target_id: str
    case_id: str
    workload: BenchmarkWorkload
    status: ObservationStatus
    quality_score: Decimal | None
    latency_ms: int | None
    ttft_ms: int | None
    input_units: int | None
    output_units: int | None
    cost_usd: Decimal | None
    fallback_count: int
    provider_error_code: str | None = None
    provider_error_status: int | None = None
    provider: str | None = None
    model: str | None = None
    deployment: str | None = None
    api_family: str | None = None
    max_output_tokens: int | None = None
    quality_metrics: Mapping[BenchmarkQualityMetric, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce quality/failure semantics and normalized optional execution identity."""
        quality_metrics = _validated_quality_metrics(self.quality_metrics)
        object.__setattr__(self, "quality_metrics", MappingProxyType(quality_metrics))

        if self.status is ObservationStatus.PROVIDER_FAILURE:
            if self.quality_score is not None:
                raise ValueError("provider failures must not carry a quality score")
            if quality_metrics:
                raise ValueError("provider failures must not carry quality component metrics")
            if not self.provider_error_code:
                raise ValueError("provider failures require a stable provider_error_code")
        elif self.provider_error_code is not None or self.provider_error_status is not None:
            raise ValueError("quality observations must not carry provider failure metadata")

        valid_quality = self.quality_score is None or Decimal("0") <= self.quality_score <= Decimal(
            "1"
        )
        if not valid_quality:
            raise ValueError("quality_score must be between 0 and 1")

        identity = (
            ("provider", self.provider),
            ("model", self.model),
            ("deployment", self.deployment),
        )
        if not all(value is None for _, value in identity):
            for name, value in identity:
                if value is None or not value or value.strip() != value:
                    raise ValueError(
                        f"benchmark observation {name} must be present and normalized "
                        "when execution identity is set"
                    )
        if self.api_family is not None:
            if self.provider is None:
                raise ValueError("benchmark observation api_family requires execution identity")
            if not self.api_family or self.api_family.strip() != self.api_family:
                raise ValueError("benchmark observation api_family must be normalized when present")
        if self.max_output_tokens is not None:
            if self.provider is None:
                raise ValueError(
                    "benchmark observation max_output_tokens requires execution identity"
                )
            if self.max_output_tokens <= 0:
                raise ValueError(
                    "benchmark observation max_output_tokens must be positive when present"
                )


@dataclass(frozen=True, slots=True)
class Scorecard:
    """Aggregated offline quality and provider availability evidence for one target/workload."""

    target_id: str
    workload: BenchmarkWorkload
    total_cases: int
    completed_calls: int
    provider_failures: int
    quality_successes: int
    quality_failures: int
    availability_rate: Decimal
    quality_success_rate: Decimal | None
    mean_quality_score: Decimal | None
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    ttft_p50_ms: int | None
    ttft_p95_ms: int | None
    total_input_units: int
    total_output_units: int
    total_cost_usd: Decimal
    rate_limit_errors: int
    fallback_frequency: Decimal
    provider_error_counts: Mapping[str, int]
    mean_quality_metrics: Mapping[BenchmarkQualityMetric, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze mappings to keep aggregated benchmark evidence immutable."""
        object.__setattr__(
            self,
            "provider_error_counts",
            MappingProxyType(dict(self.provider_error_counts)),
        )
        metrics = _validated_quality_metrics(self.mean_quality_metrics)
        object.__setattr__(self, "mean_quality_metrics", MappingProxyType(metrics))


@dataclass(frozen=True, slots=True)
class BenchmarkSnapshot:
    """Versioned immutable benchmark result snapshot."""

    schema_version: str
    benchmark_version: str
    runner_version: str
    run_date: date
    dataset_digest: str
    snapshot_id: str
    targets: tuple[BenchmarkTarget, ...]
    observations: tuple[BenchmarkObservation, ...]
    scorecards: tuple[Scorecard, ...]
    target_matrix_version: str | None = None
    target_matrix_digest: str | None = None

    def __post_init__(self) -> None:
        """Validate historical and component-evidence snapshot schema boundaries."""
        has_components = any(item.quality_metrics for item in self.observations) or any(
            item.mean_quality_metrics for item in self.scorecards
        )
        if self.schema_version == "1.0":
            if self.target_matrix_version is not None or self.target_matrix_digest is not None:
                raise ValueError("snapshot schema 1.0 must not carry target matrix provenance")
            if has_components:
                raise ValueError("snapshot schema 1.0 must not carry quality component metrics")
            return
        if self.schema_version == "1.1":
            if has_components:
                raise ValueError("snapshot schema 1.1 must not carry quality component metrics")
            if (
                self.target_matrix_version is None
                or not self.target_matrix_version
                or self.target_matrix_version.strip() != self.target_matrix_version
            ):
                raise ValueError("snapshot schema 1.1 requires normalized target_matrix_version")
            digest = self.target_matrix_digest
            if digest is None or not _is_sha256_digest(digest):
                raise ValueError("snapshot schema 1.1 requires canonical target_matrix_digest")
            return
        if self.schema_version != "1.2":
            raise ValueError("unsupported benchmark snapshot schema_version")
        if not has_components:
            raise ValueError("snapshot schema 1.2 requires quality component metrics")
        if (self.target_matrix_version is None) != (self.target_matrix_digest is None):
            raise ValueError("snapshot schema 1.2 target matrix provenance must be complete")
        if self.target_matrix_version is not None:
            _require_target_matrix_provenance(
                self.target_matrix_version,
                self.target_matrix_digest,
            )


def _validated_quality_metrics(
    value: Mapping[BenchmarkQualityMetric, Decimal],
) -> dict[BenchmarkQualityMetric, Decimal]:
    metrics: dict[BenchmarkQualityMetric, Decimal] = {}
    for metric, score in value.items():
        if not isinstance(metric, BenchmarkQualityMetric):
            raise ValueError("benchmark quality metric keys must use BenchmarkQualityMetric")
        if not isinstance(score, Decimal) or not Decimal("0") <= score <= Decimal("1"):
            raise ValueError("benchmark quality metric values must be Decimal values from 0 to 1")
        metrics[metric] = score
    return metrics


def _require_target_matrix_provenance(
    version: str | None,
    digest: str | None,
) -> None:
    if version is None or not version or version.strip() != version:
        raise ValueError("snapshot target matrix provenance requires normalized version")
    if digest is None or not _is_sha256_digest(digest):
        raise ValueError("snapshot target matrix provenance requires canonical digest")


def _is_sha256_digest(value: str) -> bool:
    prefix = "sha256:"
    if not value.startswith(prefix):
        return False
    digest = value.removeprefix(prefix)
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)
