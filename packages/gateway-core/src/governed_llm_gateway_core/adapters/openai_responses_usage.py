"""Private, pure native Responses usage counters, not trusted cost evidence.

Only the usage fragment is parsed. No transport, pricing, provenance, admission
or lifecycle/finality capability is provided; no provider report is retained.
"""

from dataclasses import dataclass, field
from typing import cast

from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostEvidenceErrorCode,
)

from .openai_responses_input_count import _bounded_integer, _error, _load_object

# Allocation ceiling only, not a context, output or budget bound.
_MAX_USAGE_BYTES = 64 * 1024
_USAGE_KEYS = frozenset(
    {
        "input_tokens",
        "input_tokens_details",
        "output_tokens",
        "output_tokens_details",
        "total_tokens",
    }
)
_INPUT_DETAIL_KEYS = frozenset({"cached_tokens", "cache_write_tokens"})
_OUTPUT_DETAIL_KEYS = frozenset({"reasoning_tokens"})


@dataclass(frozen=True, slots=True)
class OpenAIResponsesUsageCounters:
    """Explicit bounded counters in a closed subset, without evidence authority.

    Every count is mandatory, including explicit zero. Output includes reasoning;
    cache categories are preserved, not priced or subtracted to derive uncached
    input. Overlapping cache categories are outside this conservative subset.
    """

    input_tokens: int = field(repr=False)
    cached_input_tokens: int = field(repr=False)
    cache_write_input_tokens: int = field(repr=False)
    output_tokens: int = field(repr=False)
    reasoning_output_tokens: int = field(repr=False)
    total_tokens: int = field(repr=False)

    def __post_init__(self) -> None:
        """Reject invalid counts even when constructed without the parser."""
        values = (
            self.input_tokens,
            self.cached_input_tokens,
            self.cache_write_input_tokens,
            self.output_tokens,
            self.reasoning_output_tokens,
            self.total_tokens,
        )
        if any(not _bounded_integer(value, minimum=0) for value in values):
            raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
        if (
            self.total_tokens != self.input_tokens + self.output_tokens
            or self.cached_input_tokens > self.input_tokens
            or self.cache_write_input_tokens > self.input_tokens
            or self.reasoning_output_tokens > self.output_tokens
        ):
            raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
        if self.cached_input_tokens + self.cache_write_input_tokens > self.input_tokens:
            raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None


def parse_openai_responses_usage_counters(*, body: bytes) -> OpenAIResponsesUsageCounters:
    """Parse only a native usage JSON object, without defaults or authentication.

    Full responses, SSE events and normalized usage are not accepted. Even six
    explicit zero counters do not prove complete zero usage or remote finality.
    """
    usage = _closed_object(_load_object(body, limit=_MAX_USAGE_BYTES), _USAGE_KEYS)
    input_details = _closed_object(usage["input_tokens_details"], _INPUT_DETAIL_KEYS)
    output_details = _closed_object(usage["output_tokens_details"], _OUTPUT_DETAIL_KEYS)
    return OpenAIResponsesUsageCounters(
        input_tokens=cast(int, usage["input_tokens"]),
        cached_input_tokens=cast(int, input_details["cached_tokens"]),
        cache_write_input_tokens=cast(int, input_details["cache_write_tokens"]),
        output_tokens=cast(int, usage["output_tokens"]),
        reasoning_output_tokens=cast(int, output_details["reasoning_tokens"]),
        total_tokens=cast(int, usage["total_tokens"]),
    )


def _closed_object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    obj = cast(dict[str, object], value)
    if not keys <= obj.keys():
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    if obj.keys() != keys:
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    return obj
