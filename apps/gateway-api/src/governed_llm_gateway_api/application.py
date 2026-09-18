"""Explicit FastAPI application composition for governed Gateway HTTP surfaces."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from governed_llm_gateway_core.application.observability import ObservabilityPort

from .anthropic_messages_ingress import attach_anthropic_messages_route
from .claude_code_compat import ClaudeCodeCompatibilityMiddleware
from .complexity_generate import ComplexityGenerateCoordinator
from .content_type_security import GovernedJsonContentTypeMiddleware
from .credential_header_security import GatewayCredentialHeaderMiddleware
from .generation_response_security import GenerationNoStoreMiddleware
from .generation_security import GenerationRequestBodyLimitMiddleware
from .openai_compatible_ingress import attach_openai_compatible_route
from .openai_responses_ingress import attach_openai_responses_route
from .protocol_validation import attach_protocol_validation_handler
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
    observability: ObservabilityPort | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """Compose existing governed HTTP routes without resolving config, secrets, or providers."""
    app = create_app(
        route_explain_coordinator,
        complexity_coordinator=complexity_route_explain_coordinator,
        observability=observability,
        lifespan=lifespan,
    )
    app.add_middleware(RouteExplainRequestBodyLimitMiddleware)
    app.add_middleware(GenerationRequestBodyLimitMiddleware)
    app.add_middleware(GovernedJsonContentTypeMiddleware)
    app.add_middleware(GatewayCredentialHeaderMiddleware)
    app.add_middleware(RouteExplainNoStoreMiddleware)
    app.add_middleware(GenerationNoStoreMiddleware)
    app.add_middleware(ClaudeCodeCompatibilityMiddleware)
    attach_generate_route(
        app,
        generate_coordinator,
        complexity_coordinator=complexity_generate_coordinator,
        observability=observability,
    )
    attach_openai_compatible_route(app, generate_coordinator)
    attach_anthropic_messages_route(app, generate_coordinator)
    attach_openai_responses_route(app, generate_coordinator)
    attach_protocol_validation_handler(app)
    return app
