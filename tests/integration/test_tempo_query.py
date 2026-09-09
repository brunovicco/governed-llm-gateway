"""End-to-end queryability proof for Gateway metadata traces in local Tempo."""

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

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
    _require_reviewed_tempo_endpoint(tempo_endpoint)

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
    span_clause = f'span:name = "{_EXPECTED_SPAN}"'
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


def _require_reviewed_tempo_endpoint(endpoint: str) -> None:
    if endpoint != _EXPECTED_TEMPO_ENDPOINT:
        pytest.fail("Tempo query integration endpoint must use the reviewed loopback address")

    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 3200
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        pytest.fail("Tempo query integration endpoint must remain strict loopback HTTP")


def _require_reviewed_tempo_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 3200
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/api/")
        or parsed.fragment
    ):
        pytest.fail("Tempo query request URL must remain inside the reviewed loopback boundary")


def _tempo_trace_by_id(endpoint: str, trace_id: str) -> dict[str, Any] | None:
    url = _reviewed_tempo_url(endpoint, f"/api/v2/traces/{trace_id}")
    payload = _tempo_get_json(url, "Tempo trace-by-ID", allow_not_found=True)
    if payload is None:
        return None

    trace = payload.get("trace")
    if trace == {}:
        return None
    if not isinstance(trace, dict):
        pytest.fail("Tempo trace-by-ID response must contain a trace object")
    return payload


def _tempo_search(endpoint: str, traceql: str) -> dict[str, Any]:
    url = _reviewed_tempo_url(endpoint, "/api/search", params={"q": traceql})
    payload = _tempo_get_json(url, "Tempo search")
    if payload is None:
        pytest.fail("Tempo search unexpectedly returned no response payload")

    traces = payload.get("traces")
    if not isinstance(traces, list):
        pytest.fail("Tempo search response must contain a traces array")
    for trace in traces:
        if not isinstance(trace, dict):
            pytest.fail("Tempo search trace entries must be JSON objects")
    return payload


def _reviewed_tempo_url(
    endpoint: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
) -> str:
    _require_reviewed_tempo_endpoint(endpoint)
    query = urlencode(params or {})
    suffix = f"?{query}" if query else ""
    url = f"{endpoint}{path}{suffix}"
    _require_reviewed_tempo_url(url)
    return url


def _tempo_get_json(
    url: str,
    boundary: str,
    *,
    allow_not_found: bool = False,
) -> dict[str, Any] | None:
    _require_reviewed_tempo_url(url)
    request = Request(  # noqa: S310  # nosec B310
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        # Both the base endpoint and complete URL are validated as loopback HTTP above.
        with urlopen(  # noqa: S310  # nosec B310
            request,
            timeout=_HTTP_TIMEOUT_SECONDS,
        ) as response:
            status = response.getcode()
            body = response.read()
    except HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return None
        pytest.fail(f"{boundary} returned HTTP {exc.code}")
    except URLError:
        pytest.fail(f"{boundary} request failed before a valid HTTP response")

    if status != 200:
        pytest.fail(f"{boundary} returned HTTP {status}")
    return _json_object(body, boundary)


def _json_object(body: bytes, boundary: str) -> dict[str, Any]:
    try:
        payload: object = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pytest.fail(f"{boundary} returned malformed JSON")

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
