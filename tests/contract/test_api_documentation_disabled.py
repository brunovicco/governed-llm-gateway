from typing import cast

from fastapi.testclient import TestClient
from governed_llm_gateway_api.route_explain import RouteExplainCoordinator, create_app


def test_implicit_api_documentation_surfaces_are_disabled() -> None:
    client = TestClient(create_app(cast(RouteExplainCoordinator, object())))

    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
