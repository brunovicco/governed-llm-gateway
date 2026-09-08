"""End-to-end queryability proof for Gateway metadata traces in local Tempo."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import pytest
from a2a_otel_kit import Observability, ObservabilitySettings

_COLLECTOR_ENDPOINT_ENV = "GATEWAY_TEMPO_QUERY_COLLECTOR_ENDPOINT"
_TEMPO_ENDPOINT_ENV = "GATEWAY_TEMPO_QUERY_ENDPOINT"
_EXPECTED_COLLECTOR_ENDPOINT = "http://127.0.0.1:4318/v1/traces"
_EXPECTED_TEMPO_ENDPOINT = "http://127.0.0.1:3200"
_EXPECTED_SERVICE = "governed-llm-gateway-tempo-query-integration"
_EXPECTED_SPAN = "llm.gateway.request"
_QUERY_TIMEOUT_SECONDS = 10.0
_HTTP_TIMEOUT_SECONDS = 2.0
_SEARCH_LOOKBACK_SECONDS = 30


@pytest.mark.integration
def test_gateway_metadata_trace_is_queryable_from_tempo() -> None:
    """Require Tempo query evidence after export through the real local Collector."""
    collector_endpoint = os.environ.get(_COLLECTOR_ENDPOINT_ENV)
    tempo_endpoint = os.environ.get(_TEMPO_ENDPOINT_ENV)
    if collector_endpoint is None or tempo_endpoint is None:
        pytest.skip(
            "set the explicit Collector and Tempo loopback endpoints to run Tempo query integration"
        )

    if collector_endpoint != _EXPECTED_COLLECTOR_ENDPOINT:
        pytest.fail(
            "Tempo query integration Collector endpoint must use the reviewed loopback address"
        )
    if tempo_endpoint != _EXPECTED_TEMPO_ENDPOINT:
        pytest.fail("Tempo query integration endpoint must use the reviewed loopback address")

    search_start = int(time.time()) - _SEARCH_LOOKBACK_SECONDS
    observability = Observability.configure(
        ObservabilitySettings(
            service_name=_EXPECTED_SERVICE,
            service_version="0.1.0",
            environment="integration",
            enabled=True,
            otlp_endpoint=collector_endpoint,
            otlp_timeout_seconds=5,
        )
    )
    with observability.start_span(_EXPECTED_SPAN) as span:
        expected_trace_id = format(span.get_span_context().trace_id, "032x")
    try:
        assert observability.flush(5), "OTLP exporter did not flush within five seconds"
    finally:
        observability.shutdown(5)

    service_clause = f'resource.service.name = "{_EXPECTED_SERVICE}"'
    span_clause = f'span:name = "{_EXPECTED_SPAN}"'
    traceql = f"{{ {service_clause} && {span_clause} }}"
    deadline = time.monotonic() + _QUERY_TIMEOUT_SECONDS
    last_payload: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        last_payload = _tempo_search(
            tempo_endpoint,
            traceql,
            start_epoch_seconds=search_start,
            end_epoch_seconds=int(time.time()) + 1,
        )
        if _contains_expected_root(last_payload, expected_trace_id):
            return
        time.sleep(0.1)

    pytest.fail(
        "Tempo did not return the expected Gateway metadata trace within the bounded polling "
        f"window; trace_id={expected_trace_id}; last_payload={last_payload!r}"
    )


def _tempo_search(
    endpoint: str,
    traceql: str,
    *,
    start_epoch_seconds: int,
    end_epoch_seconds: int,
) -> dict[str, Any]:
    response = httpx.get(
        f"{endpoint}/api/search",
        params={
            "q": traceql,
            "start": start_epoch_seconds,
            "end": end_epoch_seconds,
        },
        headers={"Accept": "application/json"},
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        pytest.fail(f"Tempo search returned HTTP {response.status_code}")

    try:
        payload: object = json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        pytest.fail(f"Tempo search returned malformed JSON: {exc}")

    if not isinstance(payload, dict):
        pytest.fail("Tempo search response must be a JSON object")
    traces = payload.get("traces")
    if not isinstance(traces, list):
        pytest.fail("Tempo search response must contain a traces array")
    for trace in traces:
        if not isinstance(trace, dict):
            pytest.fail("Tempo search trace entries must be JSON objects")
    return payload


def _contains_expected_root(payload: dict[str, Any], expected_trace_id: str) -> bool:
    traces = payload["traces"]
    assert isinstance(traces, list)
    for trace in traces:
        assert isinstance(trace, dict)
        if (
            trace.get("rootServiceName") == _EXPECTED_SERVICE
            and trace.get("rootTraceName") == _EXPECTED_SPAN
            and trace.get("traceID") == expected_trace_id
        ):
            return True
    return False
