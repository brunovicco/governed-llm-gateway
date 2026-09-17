"""Private ADR-0021 cost-evidence shapes, not a tokenizer or provider finality proof.

These values correlate declared metadata and price an explicitly limited two-rate model.
Trusted adapters must resolve retained prepared requests/reports, verify exact supported
dimensions and issue evidence independently. Constructors cannot authenticate that evidence.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from .spend_admission import (
    MAX_SPEND_MICROS,
    SpendAdmissionContractError,
    SpendAttemptAllocation,
    SpendDispatchReceipt,
    SpendSettlement,
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class SpendCostShape(StrEnum):
    """Version-one supported dimension vocabulary, not an approved API-family list."""

    TEXT_INPUT_OUTPUT = "text_input_output_v1"


@dataclass(frozen=True, slots=True)
class SpendPreparedTextBinding:
    """Gateway-local opaque preparation handle and declared immutable provenance.

    The handle is not a payload hash, provider request ID or caller idempotency key.
    Its issuer must bind exact native preparation/model/configuration, including all
    charge-affecting options; a self-constructed handle proves none of those facts.
    """

    prepared_request_id: str = field(repr=False)
    deployment_id: str = field(repr=False)
    api_family: str = field(repr=False)
    policy_epoch: int
    policy_digest: str = field(repr=False)
    plan_digest: str = field(repr=False)
    registry_digest: str = field(repr=False)
    retry_policy_digest: str = field(repr=False)
    max_output_tokens: int
    shape: SpendCostShape
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Require exact version, closed shape and bounded private correlation metadata."""
        _version(self.schema_version)
        for value in (self.prepared_request_id, self.deployment_id, self.api_family):
            _identifier(value)
        for value in (
            self.policy_digest,
            self.plan_digest,
            self.registry_digest,
            self.retry_policy_digest,
        ):
            _digest(value)
        _integer(self.policy_epoch, minimum=1)
        _integer(self.max_output_tokens, minimum=1)
        if self.shape is not SpendCostShape.TEXT_INPUT_OUTPUT:
            raise SpendAdmissionContractError("spend cost needs a closed supported shape")


@dataclass(frozen=True, slots=True)
class SpendTextCostModel:
    """Pinned declared USD-per-million rates for input/output-only estimated cost.

    No cache tiers, reasoning, media, server tools, flat fees or implicit dimensions.
    Rates are exact plain Decimals with at most 12 fractional places, bounded encoding
    and magnitude. Unsupported precision is refused, never rounded into another price.
    Digest shape does not prove these rates match a trusted versioned configuration.
    """

    api_family: str = field(repr=False)
    pricing_digest: str = field(repr=False)
    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Reject missing, implicit, nonfinite, negative or unbounded pricing."""
        _version(self.schema_version)
        _identifier(self.api_family)
        _digest(self.pricing_digest)
        _rate(self.input_usd_per_million_tokens)
        _rate(self.output_usd_per_million_tokens)


@dataclass(frozen=True, slots=True)
class SpendTextCostBound:
    """Declared all-input bound plus enforceable total-output limit and pinned evidence.

    A trusted adapter must prove expansion/tokenization and that max_output_tokens
    caps every charged output unit for this exact request/API/model/configuration.
    No fallback multiplier or caller token projection establishes that proof here.
    """

    binding: SpendPreparedTextBinding = field(repr=False)
    model: SpendTextCostModel = field(repr=False)
    input_token_bound: int
    estimator_digest: str = field(repr=False)
    usage_contract_digest: str = field(repr=False)
    bound_evidence_id: str = field(repr=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Correlate declared model/preparation and require representable upward cost."""
        _version(self.schema_version)
        _value(self.binding, SpendPreparedTextBinding)
        _value(self.model, SpendTextCostModel)
        _integer(self.input_token_bound)
        for value in (self.estimator_digest, self.usage_contract_digest):
            _digest(value)
        _identifier(self.bound_evidence_id)
        if self.model.api_family != self.binding.api_family:
            raise SpendAdmissionContractError("spend cost model must match preparation")
        _integer(self.bound_micros)

    @property
    def bound_micros(self) -> int:
        """Exactly price supplied bounds and ceil once, independently of Decimal context."""
        return _priced_micros(self.model, self.input_token_bound, self.binding.max_output_tokens)

    def allocation(self, *, fallback_index: int, attempt_number: int) -> SpendAttemptAllocation:
        """Project one slot's correlation; do not verify authorization or retry coverage."""
        return SpendAttemptAllocation(
            self.binding.deployment_id,
            fallback_index,
            attempt_number,
            self.bound_micros,
            self.model.pricing_digest,
            self.bound_evidence_id,
        )


@dataclass(frozen=True, slots=True)
class SpendUsageFinalityRequest:
    """Exact issued attempt plus an opaque, privately retained usage-report handle.

    Shape/equality cannot prove receipt/report issuance, ownership, finality or completeness.
    Issuers must correlate the retained source with this owner/dispatch fence, not trust
    normalized usage defaults, a public response ID or another attempt's report.
    """

    bound: SpendTextCostBound = field(repr=False)
    dispatch: SpendDispatchReceipt = field(repr=False)
    usage_report_id: str = field(repr=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Reject changed plan/policy/registry/retry, deployment, pricing, evidence or bound."""
        _version(self.schema_version)
        _value(self.bound, SpendTextCostBound)
        _value(self.dispatch, SpendDispatchReceipt)
        _identifier(self.usage_report_id)
        binding = self.bound.binding
        intent = self.dispatch.reservation.request
        allocation = self.dispatch.allocation
        if (
            intent.policy_epoch,
            intent.policy_digest,
            intent.plan_digest,
            intent.registry_digest,
            intent.retry_policy_digest,
        ) != (
            binding.policy_epoch,
            binding.policy_digest,
            binding.plan_digest,
            binding.registry_digest,
            binding.retry_policy_digest,
        ) or (
            allocation.deployment_id,
            allocation.bound_micros,
            allocation.pricing_digest,
            allocation.bound_evidence_id,
        ) != (
            binding.deployment_id,
            self.bound.bound_micros,
            self.bound.model.pricing_digest,
            self.bound.bound_evidence_id,
        ):
            raise SpendAdmissionContractError("spend usage must match the exact cost intent")


@dataclass(frozen=True, slots=True)
class SpendTextUsageFinality:
    """Declared complete final counts under the bound's same pinned cost/usage model.

    All counts are mandatory, including measured zero. Unknown/provisional/missing
    usage has no instance of this value. A usage-evidence handle is not a settlement
    acknowledgement; neither construction nor projection implements a journal write.
    """

    request: SpendUsageFinalityRequest = field(repr=False)
    input_tokens: int
    output_tokens: int
    usage_evidence_id: str = field(repr=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Keep truthful representable excess, reject missing counts or arithmetic overflow."""
        _version(self.schema_version)
        _value(self.request, SpendUsageFinalityRequest)
        _integer(self.input_tokens)
        _integer(self.output_tokens)
        _identifier(self.usage_evidence_id)
        _integer(self.estimated_micros)

    @property
    def estimated_micros(self) -> int:
        """Use exact pinned two-rate pricing, never a provider-reported total cost."""
        return _priced_micros(self.request.bound.model, self.input_tokens, self.output_tokens)

    @property
    def token_bound_exceeded(self) -> bool:
        """Expose violated dimension assumptions even when free pricing hides cost excess."""
        return (
            self.input_tokens > self.request.bound.input_token_bound
            or self.output_tokens > self.request.bound.binding.max_output_tokens
        )

    @property
    def cost_bound_exceeded(self) -> bool:
        """Do not clamp a truthful cost to the reserved bound."""
        return self.estimated_micros > self.request.bound.bound_micros

    def settlement(self) -> SpendSettlement:
        """Project the exact outcome; no finality verification, acknowledgement or release."""
        return SpendSettlement(self.request.dispatch, self.estimated_micros, self.usage_evidence_id)


def _version(value: object) -> None:
    if type(value) is not str or value != "1.0":
        raise SpendAdmissionContractError("spend cost needs the exact supported version")


def _identifier(value: object) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise SpendAdmissionContractError("spend cost identity must be a bounded opaque identifier")


def _digest(value: object) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise SpendAdmissionContractError("spend cost provenance needs a canonical digest")


def _integer(value: int, *, minimum: int = 0) -> None:
    if type(value) is not int or not minimum <= value <= MAX_SPEND_MICROS:
        raise SpendAdmissionContractError("spend cost count or amount must be a bounded integer")


def _value(value: object, expected: type[object]) -> None:
    if type(value) is not expected:
        raise SpendAdmissionContractError("spend cost needs an exact immutable value")


def _rate(value: Decimal) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise SpendAdmissionContractError("spend cost price must be an exact finite Decimal")
    parts = value.as_tuple()
    if (
        not isinstance(parts.exponent, int)
        or not -12 <= parts.exponent <= 18
        or len(parts.digits) > 31
        or value < 0
        or value > Decimal(MAX_SPEND_MICROS)
    ):
        raise SpendAdmissionContractError("spend cost price must have bounded nonnegative encoding")


def _priced_micros(model: SpendTextCostModel, input_tokens: int, output_tokens: int) -> int:
    # USD/million tokens times tokens is already micro-USD: the factors cancel exactly.
    amount = (
        Fraction(model.input_usd_per_million_tokens) * input_tokens
        + Fraction(model.output_usd_per_million_tokens) * output_tokens
    )
    result = (amount.numerator + amount.denominator - 1) // amount.denominator
    _integer(result)
    return result
