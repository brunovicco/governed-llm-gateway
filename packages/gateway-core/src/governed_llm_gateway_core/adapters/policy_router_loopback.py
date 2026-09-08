"""Explicit HTTP transport for a Policy Router bound to a literal loopback address."""

import http.client
import ipaddress
import json
from collections.abc import Mapping
from typing import TypeGuard, cast
from urllib.parse import urlsplit

from .policy_router import (
    PolicyHttpResponse,
    PolicyTransportFailure,
    PolicyTransportFailureKind,
    StdlibPolicyTransport,
)

_MAX_RESPONSE_BYTES = 512 * 1024


def is_literal_loopback_host(hostname: object) -> TypeGuard[str]:
    """Return whether a hostname is an IP literal in a loopback network."""
    if not isinstance(hostname, str):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_loopback


class LoopbackHttpPolicyTransport(StdlibPolicyTransport):
    """HTTP transport allowed only for a literal loopback Policy Router endpoint."""

    @staticmethod
    def _post_json_sync(
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        parsed = urlsplit(url)
        try:
            parsed_port = parsed.port
        except ValueError as exc:
            raise ValueError("policy router loopback endpoint is invalid") from exc

        hostname = parsed.hostname
        if parsed.scheme != "http":
            raise ValueError("policy router loopback endpoint must use HTTP")
        if not is_literal_loopback_host(hostname):
            raise ValueError("policy router HTTP endpoint must use a literal loopback address")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "policy router HTTP endpoint must not contain userinfo, query, or fragment"
            )
        if timeout_seconds <= 0:
            raise ValueError("policy router timeout_seconds must be positive")

        port = parsed_port or 80
        path = parsed.path or "/"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        connection = http.client.HTTPConnection(
            hostname,
            port=port,
            timeout=timeout_seconds,
        )
        try:
            connection.request("POST", path, body=body, headers=dict(headers))
            response = connection.getresponse()
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            retry_after = response.getheader("Retry-After")
        except TimeoutError as exc:
            raise PolicyTransportFailure(
                PolicyTransportFailureKind.TIMEOUT,
                "policy router request timed out",
            ) from exc
        except (OSError, http.client.HTTPException) as exc:
            raise PolicyTransportFailure(
                PolicyTransportFailureKind.NETWORK,
                "policy router transport failed",
            ) from exc
        finally:
            connection.close()

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise PolicyTransportFailure(
                PolicyTransportFailureKind.INVALID_RESPONSE,
                "policy router response exceeded the bounded response size",
            )

        payload_out: Mapping[str, object] | None = None
        if response.status in {200, 422}:
            try:
                decoded = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PolicyTransportFailure(
                    PolicyTransportFailureKind.INVALID_RESPONSE,
                    "policy router returned invalid JSON",
                ) from exc
            if not isinstance(decoded, dict):
                raise PolicyTransportFailure(
                    PolicyTransportFailureKind.INVALID_RESPONSE,
                    "policy router response must be a JSON object",
                )
            payload_out = cast(dict[str, object], decoded)

        return PolicyHttpResponse(
            status_code=response.status,
            retry_after=retry_after,
            payload=payload_out,
        )
