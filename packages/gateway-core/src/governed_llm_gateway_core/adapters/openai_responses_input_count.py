"""Private, pure Responses text count projection; not trusted cost evidence.

No transport, issuance, pricing, admission or finality capability is provided.
Native bytes stay private and must never enter public responses or telemetry.
"""

import json
import re
from dataclasses import dataclass, field
from typing import cast

from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostEvidenceError,
    SpendCostEvidenceErrorCode,
)

from .http_sse import PreparedSseRequest

_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
# Parser allocation ceilings, not context capacity, token bounds or budget limits.
_MAX_NATIVE_BYTES = 8 * 1024 * 1024
_MAX_COUNT_BYTES = 64 * 1024
_MAX_INTEGER = 2**63 - 1
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", re.ASCII)
_REQUIRED = frozenset({"model", "store", "max_output_tokens", "input"})
_OPTIONAL = frozenset({"instructions", "stream", "reasoning", "service_tier", "truncation"})


@dataclass(frozen=True, slots=True)
class OpenAIResponsesTextCountProjection:
    """Retain exact generation bytes and derive a closed text-only count body.

    Construction validates wire shape only, not model/pricing qualification,
    transport provenance, count-to-dispatch validity or provider acceptance.
    Omitted native options remain omitted; their server defaults are unqualified.
    """

    native_body: bytes = field(repr=False)
    count_body: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate the native wire shape and freeze its count projection."""
        native = _load_object(self.native_body, limit=_MAX_NATIVE_BYTES)
        _validate_native(native)
        count = {key: native[key] for key in ("model", "input")}
        for key in ("instructions", "reasoning", "truncation"):
            if key in native:
                count[key] = native[key]
        try:
            body = json.dumps(count, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            encoded = body.encode("utf-8")
        except (ValueError, RecursionError):
            raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
        object.__setattr__(self, "count_body", encoded)


@dataclass(frozen=True, slots=True)
class OpenAIResponsesInputCountObservation:
    """Explicit parsed count paired with its projection, not an issued receipt.

    Pairing supplied facts does not authenticate a remote response or authorize
    admission. No raw count report, credentials, price or dispatch rights remain.
    """

    projection: OpenAIResponsesTextCountProjection = field(repr=False)
    input_tokens: int = field(repr=False)

    def __post_init__(self) -> None:
        """Reject foreign projections and absent or unrepresentable counts."""
        if type(self.projection) is not OpenAIResponsesTextCountProjection:
            raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
        if not _bounded_integer(self.input_tokens, minimum=0):
            raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None


def prepare_openai_responses_text_count(
    source: PreparedSseRequest,
) -> OpenAIResponsesTextCountProjection:
    """Project the retained native SSE preparation without reading its headers.

    The literal route check is a shape restriction, not endpoint authentication.
    No canonical request is translated again and no count HTTP request is issued.
    """
    if type(source) is not PreparedSseRequest:
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    if type(source.url) is not str or source.url != _RESPONSES_ENDPOINT:
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    projection = OpenAIResponsesTextCountProjection(native_body=source.body)
    native = _load_object(projection.native_body, limit=_MAX_NATIVE_BYTES)
    if native.get("stream") is not True:
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    return projection


def parse_openai_responses_input_count(
    projection: OpenAIResponsesTextCountProjection,
    *,
    body: bytes,
) -> OpenAIResponsesInputCountObservation:
    """Parse mandatory explicit counters; absence never becomes zero or None."""
    if type(projection) is not OpenAIResponsesTextCountProjection:
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    report = _load_object(body, limit=_MAX_COUNT_BYTES)
    if set(report) != {"object", "input_tokens"} or report["object"] != "response.input_tokens":
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    count = report["input_tokens"]
    if not _bounded_integer(count, minimum=0):
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    return OpenAIResponsesInputCountObservation(
        projection=projection, input_tokens=cast(int, count)
    )


def _validate_native(native: dict[str, object]) -> None:
    if not _REQUIRED.issubset(native):
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    if set(native) - (_REQUIRED | _OPTIONAL):
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    model = native["model"]
    if type(model) is not str or _MODEL.fullmatch(model) is None:
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    if native["store"] is not False:
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    if not _bounded_integer(native["max_output_tokens"], minimum=1):
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    if "stream" in native and type(native["stream"]) is not bool:
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    if "instructions" in native and type(native["instructions"]) is not str:
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    if "reasoning" in native and native["reasoning"] != {"effort": "none"}:
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    if "service_tier" in native and native["service_tier"] != "default":
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    if "truncation" in native and native["truncation"] != "disabled":
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    messages = native["input"]
    if type(messages) is not list or not messages:
        raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
    for message in cast(list[object], messages):
        if type(message) is not dict:
            raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
        item = cast(dict[str, object], message)
        if set(item) != {"role", "content"} or item["role"] not in ("user", "assistant"):
            raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
        content = item["content"]
        if type(content) is not list or not content:
            raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
        for block in cast(list[object], content):
            if type(block) is not dict:
                raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None
            text = cast(dict[str, object], block)
            if (
                set(text) != {"type", "text"}
                or text["type"] != "input_text"
                or type(text["text"]) is not str
            ):
                raise _error(SpendCostEvidenceErrorCode.UNSUPPORTED) from None


def _bounded_integer(value: object, *, minimum: int) -> bool:
    return type(value) is int and minimum <= value <= _MAX_INTEGER


def _load_object(body: bytes, *, limit: int) -> dict[str, object]:
    if type(body) is not bytes or not body or len(body) > limit:
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    try:
        parsed: object = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError):
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    if type(parsed) is not dict:
        raise _error(SpendCostEvidenceErrorCode.INVALID_STATE) from None
    return cast(dict[str, object], parsed)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("nonfinite JSON constant")


def _error(code: SpendCostEvidenceErrorCode) -> SpendCostEvidenceError:
    return SpendCostEvidenceError(code=code)
