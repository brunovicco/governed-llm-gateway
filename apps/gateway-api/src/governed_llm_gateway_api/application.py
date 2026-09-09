"""Explicit FastAPI application composition for governed Gateway HTTP surfaces."""

from a2a_otel_kit import Observability
from fastapi import FastAPI

from .complexity_generate import ComplexityGenerateCoordinator
from .generation_content_type_security import GenerationContentTypeMiddleware
from .generation_response_security import GenerationNoStoreMiddleware
from .generation_security import GenerationRequestBodyLimitMiddleware
from .route_explain import (
    ComplexityRouteExplainCoordinator,
    RouteExplainCoordinator,
    create_app,
)
from .route_explain_request_security import RouteExplainRequestBodyLimitMiddleware
from .route_explain_security import RouteExplainNoStoreMiddleware
from .stream_generate import GenerateCoordinator, attach_generate_route


def create_gateway_app(
    route_explain_coordinator: RouteExplainCoordinator,
    generate_coordinator: GenerateCoordinator,
    *,
    complexity_route_explain_coordinator: ComplexityRouteExplainCoordinator | None = None,
    complexity_generate_coordinator: ComplexityGenerateCoordinator | None = None,
    observability: Observability | None = None,
) -> FastAPI:
    """Compose existing governed HTTP routes without resolving config, secrets, or providers."""
    app = create_app(
        route_explain_coordinator,
        complexity_coordinator=complexity_route_explain_coordinator,
        observability=observability,
    )
    app.add_middleware(RouteExplainRequestBodyLimitMiddleware)
    app.add_middleware(RouteExplainNoStoreMiddleware)
    app.add_middleware(GenerationRequestBodyLimitMiddleware)
    app.add_middleware(GenerationContentTypeMiddleware)
    app.add_middleware(GenerationNoStoreMiddleware)
    attach_generate_route(
        app,
        generate_coordinator,
        complexity_coordinator=complexity_generate_coordinator,
        observability=observability,
    )
    return app
