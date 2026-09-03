"""Small async JSON-over-HTTPS transport used by provider adapters."""

import asyncio
import http.client
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

from a2a_otel_kit import inject_trace_context

_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_SAFE_RESPONSE_HEADERS = frozenset({"retry-after"})


class TransportFailureKind(StrEnum):
    """Infrastructure failure categories before provider-level normalization."""

    TIMEOUT = "timeout"
    NETWORK = "network"
    INVALID_RESPONSE = "invalid_response"


class TransportFailure(RuntimeError):
    """Sanitized transport failure that never stores request secrets or response bodies."""

    def __init__(self, kind: TransportFailureKind, message: str) -> None:
        """Create a sanitized transport failure with a stable category."""
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class JsonHttpResponse:
    """Bounded HTTP response metadata and parsed successful JSON body."""

    status_code: int
    headers: Mapping[str, str]
    payload: Mapping[str, object] | None


class JsonTransport(Protocol):
    """Injectable transport boundary used by adapter contract tests."""

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        """POST one JSON object and return bounded response metadata."""
        ...


class StdlibJsonTransport:
    """Credential-agnostic stdlib HTTPS transport with bounded response reads."""

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        """Execute blocking stdlib HTTP I/O outside the event-loop thread."""
        return await asyncio.to_thread(
            self._post_json_sync,
            url=url,
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _post_json_sync(
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("provider endpoint must be an absolute HTTPS URL")

        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        request_headers = dict(headers)
        inject_trace_context(request_headers)
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            port=port,
            timeout=timeout_seconds,
        )
        try:
            connection.request("POST", path, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            response_headers = {
                normalized_name: value
                for name, value in response.getheaders()
                if (normalized_name := name.lower()) in _SAFE_RESPONSE_HEADERS
            }
        except TimeoutError as exc:
            raise TransportFailure(
                TransportFailureKind.TIMEOUT,
                "provider request timed out",
            ) from exc
        except (OSError, http.client.HTTPException) as exc:
            raise TransportFailure(
                TransportFailureKind.NETWORK,
                "provider transport failed",
            ) from exc
        finally:
            connection.close()

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise TransportFailure(
                TransportFailureKind.INVALID_RESPONSE,
                "provider response exceeded the bounded response size",
            )

        if response.status < 200 or response.status >= 300:
            return JsonHttpResponse(
                status_code=response.status,
                headers=response_headers,
                payload=None,
            )

        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportFailure(
                TransportFailureKind.INVALID_RESPONSE,
                "provider returned invalid JSON",
            ) from exc
        if not isinstance(decoded, dict):
            raise TransportFailure(
                TransportFailureKind.INVALID_RESPONSE,
                "provider response must be a JSON object",
            )
        return JsonHttpResponse(
            status_code=response.status,
            headers=response_headers,
            payload=decoded,
        )
