"""Contract tests for explicit composition of the complete Gateway HTTP application."""

from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID

from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    ClientAuthenticationError,
    ComplexityGenerateCoordinator,
    ComplexityRouteExplainCoordinator,
    GenerateCoordinator,
    GenerateRequestModel,
    PreparedStreamingExecution,
    RouteExplainCoordinator,
    RouteExplainRequestModel,
    RouteExplainResponseModel,
    create_gateway_app,
)
from governed_llm_gateway_api.stream_generate import NoEligibleStreamingDeploymentError
from governed_llm_gateway_contracts import GatewayStreamEvent

_API_KEY = "gateway-test-key"
_REQUEST_ID = UUID("00000000-0000-4000-8000-000000000906")


class RejectingRouteExplainCoordinator:
    """Record dispatch by failing with the established sanitized authentication boundary."""

    async def explain(
        self,
        *,
        api_key: str,
        payload: RouteExplainRequestModel,
    ) -> RouteExplainResponseModel:
        assert api_key == _API_KEY
        assert payload.request_id == _REQUEST_ID
        raise ClientAuthenticationError("test rejection")


class RejectingGenerateCoordinator:
    """Record generation dispatch by failing before provider execution can begin."""

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        assert api_key == _API_KEY
        assert payload.request_id == _REQUEST_ID
        raise NoEligibleStreamingDeploymentError("test rejection")

    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        del prepared
        raise AssertionError("stream must not start after preflight rejection")
        yield cast(GatewayStreamEvent, object())


def _route_payload() -> dict[str, object]:
    return {
        "request_id": str(_REQUEST_ID),
        "workload": "demo.routing",
        "risk_level": "low",
        "data_classification": "public",
        "context_tokens_estimated": 32,
        "max_output_tokens_estimated": 16,
    }


def _generate_payload() -> dict[str, object]:
    return {
        "request_id": str(_REQUEST_ID),
        "workload": "demo.routing",
        "risk_level": "low",
        "data_classification": "public",
        "messages": [{"role": "user", "content": "test message"}],
        "context_tokens_estimated": 32,
        "max_output_tokens": 16,
    }


def _operational_route() -> RouteExplainCoordinator:
    return cast(RouteExplainCoordinator, RejectingRouteExplainCoordinator())


def _operational_generate() -> GenerateCoordinator:
    return cast(GenerateCoordinator, RejectingGenerateCoordinator())


def test_factory_mounts_each_governed_http_surface_exactly_once() -> None:
    app = create_gateway_app(_operational_route(), _operational_generate())
    paths = [getattr(route, "path", None) for route in app.routes]

    assert paths.count("/v1/route/explain") == 1
    assert paths.count("/v1/generate") == 1


def test_default_modes_continue_to_dispatch_operational_coordinators() -> None:
    app = create_gateway_app(_operational_route(), _operational_generate())
    client = TestClient(app)
    headers = {"X-Gateway-API-Key": _API_KEY}

    route_response = client.post("/v1/route/explain", json=_route_payload(), headers=headers)
    generate_response = client.post("/v1/generate", json=_generate_payload(), headers=headers)

    assert route_response.status_code == 401
    assert route_response.json()["detail"]["code"] == "invalid_gateway_credential"
    assert generate_response.status_code == 503
    assert generate_response.json()["detail"]["code"] == "no_eligible_streaming_deployment"


def test_complexity_modes_fail_closed_when_optional_coordinators_are_absent() -> None:
    app = create_gateway_app(_operational_route(), _operational_generate())
    client = TestClient(app)
    headers = {"X-Gateway-API-Key": _API_KEY}

    route_response = client.post(
        "/v1/route/explain?mode=complexity",
        json=_route_payload(),
        headers=headers,
    )
    generate_response = client.post(
        "/v1/generate?mode=complexity",
        json=_generate_payload(),
        headers=headers,
    )

    assert route_response.status_code == 503
    assert route_response.json()["detail"]["code"] == "complexity_routing_unavailable"
    assert generate_response.status_code == 503
    assert generate_response.json()["detail"]["code"] == "complexity_routing_unavailable"


def test_complexity_coordinators_are_wired_independently_when_explicitly_supplied() -> None:
    route = RejectingRouteExplainCoordinator()
    generate = RejectingGenerateCoordinator()
    app = create_gateway_app(
        cast(RouteExplainCoordinator, route),
        cast(GenerateCoordinator, generate),
        complexity_route_explain_coordinator=cast(ComplexityRouteExplainCoordinator, route),
        complexity_generate_coordinator=cast(ComplexityGenerateCoordinator, generate),
    )
    client = TestClient(app)
    headers = {"X-Gateway-API-Key": _API_KEY}

    route_response = client.post(
        "/v1/route/explain?mode=complexity",
        json=_route_payload(),
        headers=headers,
    )
    generate_response = client.post(
        "/v1/generate?mode=complexity",
        json=_generate_payload(),
        headers=headers,
    )

    assert route_response.status_code == 401
    assert route_response.json()["detail"]["code"] == "invalid_gateway_credential"
    assert generate_response.status_code == 503
    assert generate_response.json()["detail"]["code"] == "no_eligible_streaming_deployment"
