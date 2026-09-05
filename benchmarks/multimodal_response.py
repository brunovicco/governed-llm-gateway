"""Normalize terminal gateway responses into benchmark call evidence."""

from __future__ import annotations

import json
from json import JSONDecodeError

from governed_llm_gateway_contracts import ExecutionStatus, GatewayResponse

from benchmarks.contracts import JsonValue, ProviderCall
from benchmarks.runner import BenchmarkProviderFailure


def normalize_multimodal_gateway_response(response: GatewayResponse) -> ProviderCall:
    """Convert one terminal gateway response without conflating quality and availability."""
    if response.status is ExecutionStatus.FAILED:
        _raise_provider_failure(response)
    if response.status is not ExecutionStatus.SUCCEEDED:
        raise ValueError("multimodal benchmark requires a terminal gateway response")

    execution = response.execution
    if execution is None:
        raise ValueError("successful multimodal benchmark response requires execution evidence")
    if execution.status is not ExecutionStatus.SUCCEEDED:
        raise ValueError("successful gateway response has inconsistent execution status")

    usage = execution.usage
    output = _normalized_output(response)
    return ProviderCall(
        output=output,
        latency_ms=execution.latency_ms,
        ttft_ms=None,
        input_units=usage.input_tokens if usage is not None else None,
        output_units=usage.output_tokens if usage is not None else None,
        cost_usd=usage.total_cost_usd if usage is not None else None,
        fallback_count=execution.fallback_index,
    )


def _raise_provider_failure(response: GatewayResponse) -> None:
    error = response.error
    if error is None:
        raise ValueError("failed multimodal benchmark response requires gateway error evidence")
    execution = response.execution
    latency_ms = execution.latency_ms if execution is not None else None
    raise BenchmarkProviderFailure(code=error.code, latency_ms=latency_ms)


def _normalized_output(response: GatewayResponse) -> JsonValue:
    if response.structured_output is not None:
        return _require_json_value(response.structured_output)

    content = response.content
    if content is None:
        return None
    try:
        decoded: object = json.loads(content)
    except JSONDecodeError:
        return content
    return _require_json_value(decoded)


def _require_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_require_json_value(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("gateway structured output object keys must be strings")
            normalized[key] = _require_json_value(item)
        return normalized
    raise ValueError("gateway structured output must contain only JSON-compatible values")
