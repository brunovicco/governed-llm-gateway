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


@pytest.mark.integration
def test_gateway_metadata_trace_is_queryable_from_tempo() -> None:
    """Require Tempo trace-by-ID and TraceQL evidence after Collector export."""
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
        trace_id = span.get_span_context().trace_id
        if trace_id == 0:
            pytest.fail("enabled observability produced an invalid zero trace ID")
        expected_trace_id = f"{trace_id:032x}"
    try:
        assert observability.flush(5), "OTLP exporter did not flush within five seconds"
    finally:
        observability.shutdown(5)

    trace_deadline = time.monotonic() + _QUERY_TIMEOUT_SECONDS
    while time.monotonic() < trace_deadline:
        trace_payload = _tempo_trace_by_id(tempo_endpoint, expected_trace_id)
        if trace_payload is not None:
            _require_expected_span(trace_payload)
            break
        time.sleep(0.1)
    else:
        pytest.fail(
            "Tempo did not return the emitted trace ID within the bounded polling window; "
            f"trace_id={expected_trace_id}"
        )

    service_clause = f'resource.service.name = "{_EXPECTED_SERVICE}"'
    span_clause = f'name = "{_EXPECTED_SPAN}"'
    traceql = f"{{ {service_clause} && {span_clause} }}"
    search_deadline = time.monotonic() + _QUERY_TIMEOUT_SECONDS
    last_payload: dict[str, Any] | None = None

    while time.monotonic() < search_deadline:
        last_payload = _tempo_search(tempo_endpoint, traceql)
        if _contains_expected_root(last_payload, expected_trace_id):
            return
        time.sleep(0.1)

    pytest.fail(
        "Tempo trace was retrievable by ID but not discoverable through the reviewed TraceQL "
        f"search within the bounded polling window; trace_id={expected_trace_id}; "
        f"last_payload={last_payload!r}"
    )


def _tempo_trace_by_id(endpoint: str, trace_id: str) -> dict[str, Any] | None:
    response = httpx.get(
        f"{endpoint}/api/v2/traces/{trace_id}",
        headers={"Accept": "application/json"},
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        pytest.fail(f"Tempo trace-by-ID returned HTTP {response.status_code}")
    return _json_object(response, "Tempo trace-by-ID")


def _tempo_search(endpoint: str, traceql: str) -> dict[str, Any]:
    response = httpx.get(
        f"{endpoint}/api/search",
        params={"q": traceql},
        headers={"Accept": "application/json"},
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        pytest.fail(f"Tempo search returned HTTP {response.status_code}")

    payload = _json_object(response, "Tempo search")
    traces = payload.get("traces")
    if not isinstance(traces, list):
        pytest.fail("Tempo search response must contain a traces array")
    for trace in traces:
        if not isinstance(trace, dict):
            pytest.fail("Tempo search trace entries must be JSON objects")
    return payload


def _json_object(response: httpx.Response, boundary: str) -> dict[str, Any]:
    try:
        payload: object = json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        pytest.fail(f"{boundary} returned malformed JSON: {exc}")

    if not isinstance(payload, dict):
        pytest.fail(f"{boundary} response must be a JSON object")
    return payload


def _require_expected_span(payload: dict[str, Any]) -> None:
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        pytest.fail("Tempo trace-by-ID response must contain a trace object")
    resource_spans = trace.get("resourceSpans")
    if not isinstance(resource_spans, list):
        pytest.fail("Tempo trace-by-ID response must contain resourceSpans")

    for resource_span in resource_spans:
        if not isinstance(resource_span, dict):
            pytest.fail("Tempo resourceSpans entries must be JSON objects")
        if _resource_span_contains_expected_span(resource_span):
            return
    pytest.fail("Tempo returned the trace ID without the expected service/span metadata")


def _resource_span_contains_expected_span(resource_span: dict[str, Any]) -> bool:
    resource = resource_span.get("resource")
    if not isinstance(resource, dict):
        return False
    attributes = resource.get("attributes")
    if not isinstance(attributes, list) or not _has_expected_service(attributes):
        return False

    scope_spans = resource_span.get("scopeSpans")
    if not isinstance(scope_spans, list):
        return False
    for scope_span in scope_spans:
        if not isinstance(scope_span, dict):
            continue
        spans = scope_span.get("spans")
        if isinstance(spans, list) and any(
            isinstance(span, dict) and span.get("name") == _EXPECTED_SPAN for span in spans
        ):
            return True
    return False


def _has_expected_service(attributes: list[Any]) -> bool:
    for attribute in attributes:
        if not isinstance(attribute, dict) or attribute.get("key") != "service.name":
            continue
        value = attribute.get("value")
        if isinstance(value, dict) and value.get("stringValue") == _EXPECTED_SERVICE:
            return True
    return False


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
