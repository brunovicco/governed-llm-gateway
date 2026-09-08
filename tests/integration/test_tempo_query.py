"""End-to-end queryability proof for Gateway metadata traces in local Tempo."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest
from a2a_otel_kit import Observability, ObservabilitySettings

_COLLECTOR_ENDPOINT_ENV = "GATEWAY_TEMPO_QUERY_COLLECTOR_ENDPOINT"
_TEMPO_ENDPOINT_ENV = "GATEWAY_TEMPO_QUERY_ENDPOINT"
_EXPECTED_SERVICE = "governed-llm-gateway-tempo-query-integration"
_EXPECTED_SPAN = "llm.gateway.request"
_QUERY_TIMEOUT_SECONDS = 10.0
_HTTP_TIMEOUT_SECONDS = 2.0


@pytest.mark.integration
def test_gateway_metadata_trace_is_queryable_from_tempo() -> None:
    """Require Tempo query evidence after export through the real local Collector."""
    collector_endpoint = os.environ.get(_COLLECTOR_ENDPOINT_ENV)
    tempo_endpoint = os.environ.get(_TEMPO_ENDPOINT_ENV)
    if collector_endpoint is None or tempo_endpoint is None:
        pytest.skip(
            f"set {_COLLECTOR_ENDPOINT_ENV} and {_TEMPO_ENDPOINT_ENV} to run Tempo query integration"
        )

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
    with observability.start_span(_EXPECTED_SPAN):
        pass
    try:
        assert observability.flush(5), "OTLP exporter did not flush within five seconds"
    finally:
        observability.shutdown(5)

    traceql = (
        f'{{ resource.service.name = "{_EXPECTED_SERVICE}" && name = "{_EXPECTED_SPAN}" }}'
    )
    deadline = time.monotonic() + _QUERY_TIMEOUT_SECONDS
    last_payload: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        last_payload = _tempo_search(tempo_endpoint, traceql)
        if _contains_expected_root(last_payload):
            return
        time.sleep(0.1)

    pytest.fail(
        "Tempo did not return the expected Gateway metadata trace within the bounded polling window; "
        f"last_payload={last_payload!r}"
    )


def _tempo_search(endpoint: str, traceql: str) -> dict[str, Any]:
    url = f"{endpoint.rstrip('/')}/api/search?{urlencode({'q': traceql})}"
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    with urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 - loopback test endpoint
        if response.status != 200:
            pytest.fail(f"Tempo search returned HTTP {response.status}")
        raw = response.read()

    try:
        payload: object = json.loads(raw)
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


def _contains_expected_root(payload: dict[str, Any]) -> bool:
    traces = payload["traces"]
    assert isinstance(traces, list)
    for trace in traces:
        assert isinstance(trace, dict)
        if (
            trace.get("rootServiceName") == _EXPECTED_SERVICE
            and trace.get("rootTraceName") == _EXPECTED_SPAN
            and isinstance(trace.get("traceID"), str)
            and bool(trace["traceID"])
        ):
            return True
    return False
