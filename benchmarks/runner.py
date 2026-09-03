"""Provider-neutral deterministic benchmark runner and aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Protocol

from .contracts import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
    Scorecard,
)
from .scoring import DeterministicScorer, ensure_supported_scorers, require_scorer


@dataclass(frozen=True, slots=True)
class BenchmarkProviderFailure(Exception):
    """Stable availability evidence for a failed provider call."""

    code: str
    status_code: int | None = None
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        """Validate stable provider-failure evidence."""
        if not self.code or self.code.strip() != self.code:
            raise ValueError("provider failure code must be non-empty and normalized")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("provider failure latency_ms must be non-negative")


class BenchmarkExecutor(Protocol):
    """Execute one benchmark case against one fully identified provider/model target."""

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        """Return normalized call evidence or raise BenchmarkProviderFailure."""
        ...


class BenchmarkRunner:
    """Run deterministic scorers while preserving provider failures as availability evidence."""

    def __init__(
        self,
        executor: BenchmarkExecutor,
        scorers: Mapping[str, DeterministicScorer],
        *,
        quality_success_threshold: Decimal = Decimal("1"),
    ) -> None:
        """Configure the executor, scorer registry, and deterministic quality threshold."""
        if not Decimal("0") <= quality_success_threshold <= Decimal("1"):
            raise ValueError("quality_success_threshold must be between 0 and 1")
        self._executor = executor
        self._scorers = scorers
        self._quality_success_threshold = quality_success_threshold

    async def run(
        self,
        cases: Sequence[BenchmarkCase],
        targets: Sequence[BenchmarkTarget],
    ) -> tuple[tuple[BenchmarkObservation, ...], tuple[Scorecard, ...]]:
        """Evaluate all case/target pairs in stable input order."""
        if not cases:
            raise ValueError("benchmark dataset must contain at least one case")
        if not targets:
            raise ValueError("benchmark run must contain at least one target")
        ensure_supported_scorers(cases, self._scorers)
        _ensure_unique_ids(cases, targets)

        observations: list[BenchmarkObservation] = []
        for target in targets:
            for case in cases:
                observations.append(await self._run_one(case, target))

        return tuple(observations), build_scorecards(observations)

    async def _run_one(self, case: BenchmarkCase, target: BenchmarkTarget) -> BenchmarkObservation:
        try:
            call = await self._executor.execute(case, target)
        except BenchmarkProviderFailure as exc:
            return BenchmarkObservation(
                target_id=target.target_id,
                case_id=case.case_id,
                workload=case.workload,
                status=ObservationStatus.PROVIDER_FAILURE,
                quality_score=None,
                latency_ms=exc.latency_ms,
                ttft_ms=None,
                input_units=None,
                output_units=None,
                cost_usd=None,
                fallback_count=0,
                provider_error_code=exc.code,
                provider_error_status=exc.status_code,
            )

        score = require_scorer(self._scorers, case.scorer)(case, call.output)
        status = (
            ObservationStatus.SUCCEEDED
            if score >= self._quality_success_threshold
            else ObservationStatus.QUALITY_FAILURE
        )
        return BenchmarkObservation(
            target_id=target.target_id,
            case_id=case.case_id,
            workload=case.workload,
            status=status,
            quality_score=score,
            latency_ms=call.latency_ms,
            ttft_ms=call.ttft_ms,
            input_units=call.input_units,
            output_units=call.output_units,
            cost_usd=call.cost_usd,
            fallback_count=call.fallback_count,
        )


def _ensure_unique_ids(cases: Sequence[BenchmarkCase], targets: Sequence[BenchmarkTarget]) -> None:
    case_ids = [case.case_id for case in cases]
    target_ids = [target.target_id for target in targets]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark case IDs must be unique")
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("benchmark target IDs must be unique")


def build_scorecards(observations: Sequence[BenchmarkObservation]) -> tuple[Scorecard, ...]:
    """Aggregate observations without conflating quality failure with provider outage."""
    grouped: dict[tuple[str, BenchmarkWorkload], list[BenchmarkObservation]] = defaultdict(list)
    for observation in observations:
        grouped[(observation.target_id, observation.workload)].append(observation)

    return tuple(
        _build_scorecard(target_id, workload, grouped[(target_id, workload)])
        for target_id, workload in sorted(grouped, key=lambda item: (item[0], item[1].value))
    )


def _build_scorecard(
    target_id: str,
    workload: BenchmarkWorkload,
    observations: Sequence[BenchmarkObservation],
) -> Scorecard:
    total = len(observations)
    provider_failures = [
        item for item in observations if item.status is ObservationStatus.PROVIDER_FAILURE
    ]
    completed = [
        item for item in observations if item.status is not ObservationStatus.PROVIDER_FAILURE
    ]
    quality_successes = [item for item in completed if item.status is ObservationStatus.SUCCEEDED]
    quality_failures = [
        item for item in completed if item.status is ObservationStatus.QUALITY_FAILURE
    ]
    quality_scores = [item.quality_score for item in completed if item.quality_score is not None]
    latencies = [item.latency_ms for item in completed if item.latency_ms is not None]
    ttfts = [item.ttft_ms for item in completed if item.ttft_ms is not None]
    provider_error_counts = Counter(
        item.provider_error_code
        for item in provider_failures
        if item.provider_error_code is not None
    )

    total_cost = sum(
        (item.cost_usd or Decimal("0") for item in completed),
        start=Decimal("0"),
    )
    return Scorecard(
        target_id=target_id,
        workload=workload,
        total_cases=total,
        completed_calls=len(completed),
        provider_failures=len(provider_failures),
        quality_successes=len(quality_successes),
        quality_failures=len(quality_failures),
        availability_rate=_ratio(len(completed), total),
        quality_success_rate=_ratio(len(quality_successes), len(completed)) if completed else None,
        mean_quality_score=(
            sum(quality_scores, start=Decimal("0")) / Decimal(len(quality_scores))
            if quality_scores
            else None
        ),
        latency_p50_ms=_percentile(latencies, Decimal("0.50")),
        latency_p95_ms=_percentile(latencies, Decimal("0.95")),
        ttft_p50_ms=_percentile(ttfts, Decimal("0.50")),
        ttft_p95_ms=_percentile(ttfts, Decimal("0.95")),
        total_input_units=sum(item.input_units or 0 for item in completed),
        total_output_units=sum(item.output_units or 0 for item in completed),
        total_cost_usd=total_cost,
        rate_limit_errors=provider_error_counts.get("rate_limit", 0),
        fallback_frequency=(
            _ratio(sum(1 for item in completed if item.fallback_count > 0), len(completed))
            if completed
            else Decimal("0")
        ),
        provider_error_counts=dict(sorted(provider_error_counts.items())),
    )


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        raise ValueError("ratio denominator must be positive")
    return Decimal(numerator) / Decimal(denominator)


def _percentile(values: Sequence[int], percentile: Decimal) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    raw_rank = percentile * Decimal(len(ordered))
    rank = max(1, int(raw_rank.to_integral_value(rounding=ROUND_CEILING)))
    return ordered[rank - 1]
