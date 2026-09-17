"""Private partitioned-cache v2 declarations, not trusted issuance or finality.

Pure values price supplied qualified facts only. No configuration loading, clock
lookup, provider I/O, budget transition, suspension, release or replay is provided.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from .spend_admission import (
    SpendAdmissionContractError,
    SpendAttemptAllocation,
    SpendDispatchReceipt,
    SpendSettlement,
)
from .spend_cost_evidence import _digest, _identifier, _integer, _rate, _value


def _check(condition: bool) -> None:
    if not condition:
        raise SpendAdmissionContractError("spend cache cost needs consistent private values")


def _version(value: object) -> None:
    _check(type(value) is str and value == "2.0")


def _window(start: datetime, end: datetime) -> None:
    _check(type(start) is datetime and type(end) is datetime)
    _check(start.tzinfo is UTC and end.tzinfo is UTC)
    _check(start < end)


def _ceil_micros(amount: Fraction) -> int:
    # USD/million tokens times tokens is already micro-USD; ceil the whole sum once.
    result = (amount.numerator + amount.denominator - 1) // amount.denominator
    _integer(result)
    return result


class SpendCacheCostShape(StrEnum):
    """Separate closed dimension vocabulary, never an approved family/model list."""

    TEXT_CACHE_PARTITIONED = "text_cache_partitioned_v2"


@dataclass(frozen=True, slots=True)
class SpendCachePreparedBinding:
    """Declared exact native preparation/provenance; an ID does not prove issuance."""

    prepared_request_id: str = field(repr=False)
    deployment_id: str = field(repr=False)
    api_family: str = field(repr=False)
    model_id: str = field(repr=False)
    pricing_profile_id: str = field(repr=False)
    configuration_digest: str = field(repr=False)
    policy_epoch: int = field(repr=False)
    policy_digest: str = field(repr=False)
    plan_digest: str = field(repr=False)
    registry_digest: str = field(repr=False)
    retry_policy_digest: str = field(repr=False)
    max_output_tokens: int = field(repr=False)
    shape: SpendCacheCostShape = field(repr=False)
    schema_version: str = field(default="2.0", repr=False)

    def __post_init__(self) -> None:
        """Require closed shape, bounded private identities and immutable provenance."""
        _version(self.schema_version)
        for value in (
            self.prepared_request_id,
            self.deployment_id,
            self.api_family,
            self.model_id,
            self.pricing_profile_id,
        ):
            _identifier(value)
        for value in (
            self.configuration_digest,
            self.policy_digest,
            self.plan_digest,
            self.registry_digest,
            self.retry_policy_digest,
        ):
            _digest(value)
        _integer(self.policy_epoch, minimum=1)
        _integer(self.max_output_tokens, minimum=1)
        _check(self.shape is SpendCacheCostShape.TEXT_CACHE_PARTITIONED)


@dataclass(frozen=True, slots=True)
class SpendCacheRates:
    """Four explicit exact rates for one whole-request band, including free rates."""

    ordinary_input_usd_per_million: Decimal = field(repr=False)
    cache_read_usd_per_million: Decimal = field(repr=False)
    cache_write_usd_per_million: Decimal = field(repr=False)
    output_usd_per_million: Decimal = field(repr=False)
    schema_version: str = field(default="2.0", repr=False)

    def __post_init__(self) -> None:
        """Use v1 precision/range rules without changing v1 pricing semantics."""
        _version(self.schema_version)
        for rate in (
            self.ordinary_input_usd_per_million,
            self.cache_read_usd_per_million,
            self.cache_write_usd_per_million,
            self.output_usd_per_million,
        ):
            _rate(rate)


@dataclass(frozen=True, slots=True)
class SpendCacheCostModel:
    """Declared complete pinned two-band schedule, not verified provider prices.

    Validity/epoch are fixed declarations, not current-time/configuration checks.
    Model/profile identity and qualification digests prove no external guarantees.
    """

    api_family: str = field(repr=False)
    model_id: str = field(repr=False)
    pricing_profile_id: str = field(repr=False)
    configuration_digest: str = field(repr=False)
    pricing_digest: str = field(repr=False)
    input_threshold: int = field(repr=False)
    short_context: SpendCacheRates = field(repr=False)
    long_context: SpendCacheRates = field(repr=False)
    qualification_digest: str = field(repr=False)
    qualification_epoch: int = field(repr=False)
    valid_from: datetime = field(repr=False)
    valid_until: datetime = field(repr=False)
    schema_version: str = field(default="2.0", repr=False)

    def __post_init__(self) -> None:
        """Reject absent bands, invalid thresholds, provenance and UTC windows."""
        _version(self.schema_version)
        for value in (self.api_family, self.model_id, self.pricing_profile_id):
            _identifier(value)
        for value in (self.configuration_digest, self.pricing_digest, self.qualification_digest):
            _digest(value)
        _integer(self.input_threshold, minimum=1)
        _integer(self.qualification_epoch, minimum=1)
        _value(self.short_context, SpendCacheRates)
        _value(self.long_context, SpendCacheRates)
        _window(self.valid_from, self.valid_until)


@dataclass(frozen=True, slots=True)
class SpendCacheCostBound:
    """Declared input cap and inclusive output cap under the same fixed schedule."""

    binding: SpendCachePreparedBinding = field(repr=False)
    model: SpendCacheCostModel = field(repr=False)
    input_token_bound: int = field(repr=False)
    estimator_digest: str = field(repr=False)
    usage_contract_digest: str = field(repr=False)
    bound_evidence_id: str = field(repr=False)
    valid_from: datetime = field(repr=False)
    valid_until: datetime = field(repr=False)
    schema_version: str = field(default="2.0", repr=False)

    def __post_init__(self) -> None:
        """Correlate declared configuration and a window contained in the schedule."""
        _version(self.schema_version)
        _value(self.binding, SpendCachePreparedBinding)
        _value(self.model, SpendCacheCostModel)
        _integer(self.input_token_bound)
        _digest(self.estimator_digest)
        _digest(self.usage_contract_digest)
        _identifier(self.bound_evidence_id)
        _window(self.valid_from, self.valid_until)
        _check(
            self.model.valid_from <= self.valid_from < self.valid_until <= self.model.valid_until
        )
        for name in ("api_family", "model_id", "pricing_profile_id", "configuration_digest"):
            _check(getattr(self.binding, name) == getattr(self.model, name))
        _integer(self.bound_micros)

    @property
    def bound_micros(self) -> int:
        """Use independent rate maxima across both bands, never a cache prediction."""
        bands = (self.model.short_context, self.model.long_context)
        input_rate = max(
            Fraction(rate)
            for band in bands
            for rate in (
                band.ordinary_input_usd_per_million,
                band.cache_read_usd_per_million,
                band.cache_write_usd_per_million,
            )
        )
        output_rate = max(Fraction(band.output_usd_per_million) for band in bands)
        return _ceil_micros(
            input_rate * self.input_token_bound + output_rate * self.binding.max_output_tokens
        )

    def allocation(self, *, fallback_index: int, attempt_number: int) -> SpendAttemptAllocation:
        """Project declared correlation only, not admission or dispatch permission."""
        return SpendAttemptAllocation(
            self.binding.deployment_id,
            fallback_index,
            attempt_number,
            self.bound_micros,
            self.model.pricing_digest,
            self.bound_evidence_id,
        )


@dataclass(frozen=True, slots=True)
class SpendCacheUsageFinalityRequest:
    """Exact declared dispatch/report correlation, not authenticated report issuance."""

    bound: SpendCacheCostBound = field(repr=False)
    dispatch: SpendDispatchReceipt = field(repr=False)
    usage_report_id: str = field(repr=False)
    schema_version: str = field(default="2.0", repr=False)

    def __post_init__(self) -> None:
        """Reject changed original plan/policy/registry/retry and allocated cost facts."""
        _version(self.schema_version)
        _value(self.bound, SpendCacheCostBound)
        _value(self.dispatch, SpendDispatchReceipt)
        _identifier(self.usage_report_id)
        binding = self.bound.binding
        intent = self.dispatch.reservation.request
        for name in (
            "policy_epoch",
            "policy_digest",
            "plan_digest",
            "registry_digest",
            "retry_policy_digest",
        ):
            _check(getattr(intent, name) == getattr(binding, name))
        allocation = self.dispatch.allocation
        _check(
            (
                allocation.deployment_id,
                allocation.bound_micros,
                allocation.pricing_digest,
                allocation.bound_evidence_id,
            )
            == (
                binding.deployment_id,
                self.bound.bound_micros,
                self.bound.model.pricing_digest,
                self.bound.bound_evidence_id,
            )
        )


@dataclass(frozen=True, slots=True)
class SpendCacheUsageFinality:
    """Declared complete partitioned usage; explicit zero still needs trusted issuance."""

    request: SpendCacheUsageFinalityRequest = field(repr=False)
    input_tokens: int = field(repr=False)
    cache_read_input_tokens: int = field(repr=False)
    cache_write_input_tokens: int = field(repr=False)
    output_tokens: int = field(repr=False)
    reasoning_output_tokens: int = field(repr=False)
    total_tokens: int = field(repr=False)
    usage_evidence_id: str = field(repr=False)
    schema_version: str = field(default="2.0", repr=False)

    def __post_init__(self) -> None:
        """Keep truthful excess, but reject invalid partitions and unrepresentable cost."""
        _version(self.schema_version)
        _value(self.request, SpendCacheUsageFinalityRequest)
        for count in (
            self.input_tokens,
            self.cache_read_input_tokens,
            self.cache_write_input_tokens,
            self.output_tokens,
            self.reasoning_output_tokens,
            self.total_tokens,
        ):
            _integer(count)
        _identifier(self.usage_evidence_id)
        _check(self.cache_read_input_tokens + self.cache_write_input_tokens <= self.input_tokens)
        _check(self.reasoning_output_tokens <= self.output_tokens)
        _check(self.total_tokens == self.input_tokens + self.output_tokens)
        _integer(self.estimated_micros)

    @property
    def estimated_micros(self) -> int:
        """Select the whole-request band from observed input and ceil the sum once."""
        model = self.request.bound.model
        band = (
            model.long_context if self.input_tokens > model.input_threshold else model.short_context
        )
        ordinary = self.input_tokens - self.cache_read_input_tokens - self.cache_write_input_tokens
        return _ceil_micros(
            ordinary * Fraction(band.ordinary_input_usd_per_million)
            + self.cache_read_input_tokens * Fraction(band.cache_read_usd_per_million)
            + self.cache_write_input_tokens * Fraction(band.cache_write_usd_per_million)
            + self.output_tokens * Fraction(band.output_usd_per_million)
        )

    @property
    def input_bound_exceeded(self) -> bool:
        """Expose input violations independently of free/discounted cost."""
        return self.input_tokens > self.request.bound.input_token_bound

    @property
    def output_bound_exceeded(self) -> bool:
        """Inclusive output includes reasoning, never a visible-output-only comparison."""
        return self.output_tokens > self.request.bound.binding.max_output_tokens

    @property
    def token_bound_exceeded(self) -> bool:
        """Keep token-model invalidation obligations visible before projection."""
        return self.input_bound_exceeded or self.output_bound_exceeded

    @property
    def cost_bound_exceeded(self) -> bool:
        """Preserve truthful cost excess without clamping to the allocation."""
        return self.estimated_micros > self.request.bound.bound_micros

    def settlement(self) -> "SpendCacheSettlementProjection":
        """Retain the full finality/violation state, not a flag-losing generic settlement."""
        return SpendCacheSettlementProjection(self)


@dataclass(frozen=True, slots=True)
class SpendCacheSettlementProjection:
    """Keep finality and its token/cost flags alongside the generic outcome.

    Future consumers must inspect finality and invalidate affected qualification
    before new admissions/claims; this value suspends nothing and writes no journal.
    """

    finality: SpendCacheUsageFinality = field(repr=False)
    settlement: SpendSettlement = field(init=False, repr=False)
    schema_version: str = field(default="2.0", repr=False)

    def __post_init__(self) -> None:
        """Derive the outcome internally; flags cannot be supplied separately."""
        _version(self.schema_version)
        _value(self.finality, SpendCacheUsageFinality)
        finality = self.finality
        object.__setattr__(
            self,
            "settlement",
            SpendSettlement(
                finality.request.dispatch,
                finality.estimated_micros,
                finality.usage_evidence_id,
            ),
        )
