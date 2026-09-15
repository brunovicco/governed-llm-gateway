"""Protocol-aware safe errors for ASGI middleware that runs before route translation."""

from starlette.responses import JSONResponse


def boundary_error_response(path: str, *, status_code: int, code: str) -> JSONResponse:
    """Return the compatible envelope when the route protocol is already known."""
    if path == "/v1/messages":
        if status_code == 401:
            error_type = "authentication_error"
        elif status_code == 429:
            error_type = "rate_limit_error"
        elif status_code < 500:
            error_type = "invalid_request_error"
        else:
            error_type = "api_error"
        return JSONResponse(
            status_code=status_code,
            content={
                "type": "error",
                "error": {
                    "type": error_type,
                    "message": f"governed gateway rejected the request: {code}",
                },
            },
        )
    if path == "/v1/responses":
        if status_code == 401:
            error_type = "authentication_error"
        elif status_code == 429:
            error_type = "rate_limit_error"
        elif status_code < 500:
            error_type = "invalid_request_error"
        else:
            error_type = "api_error"
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "message": f"governed gateway rejected the request: {code}",
                    "type": error_type,
                    "param": None,
                    "code": code,
                }
            },
        )
    return JSONResponse(status_code=status_code, content={"detail": {"code": code}})
