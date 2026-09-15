"""Protocol-aware sanitization of FastAPI request-validation failures."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from .protocol_error import boundary_error_response

_PROTOCOL_PATHS = frozenset({"/v1/messages", "/v1/responses"})


def attach_protocol_validation_handler(app: FastAPI) -> None:
    """Preserve existing validation behavior except on provider-compatible protocols."""

    @app.exception_handler(RequestValidationError)
    async def protocol_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> Response:
        if request.url.path in _PROTOCOL_PATHS:
            return boundary_error_response(
                request.url.path,
                status_code=422,
                code="invalid_request",
            )
        return await request_validation_exception_handler(request, exc)
