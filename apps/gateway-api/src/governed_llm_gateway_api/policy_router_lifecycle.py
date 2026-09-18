"""Explicit deployment selection and single-lifetime ASGI ownership of the PDP pool."""

import asyncio
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyHttpResponse,
    PolicyTransportFailure,
    PolicyTransportFailureKind,
)
from governed_llm_gateway_core.adapters.policy_router_httpx import (
    HttpxPolicyTransport,
    validate_policy_https_endpoint,
    validate_policy_pool_limits,
)
from governed_llm_gateway_core.adapters.policy_router_runtime import PolicyRouterRuntimeConfig


@dataclass(frozen=True, slots=True)
class PolicyRouterHttpPoolSettings:
    """Secret-free, explicit deployment opt-in; omission preserves existing transports."""

    max_connections: int = 8
    max_keepalive_connections: int = 8
    keepalive_expiry_seconds: float = 30.0

    def __post_init__(self) -> None:
        """Validate limits without creating a backend, opening sockets or reading secrets."""
        validate_policy_pool_limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive_connections,
            keepalive_expiry_seconds=self.keepalive_expiry_seconds,
        )


class PolicyRouterPoolLifecycleError(RuntimeError):
    """Sanitized lifecycle failure with no secret, target or raw infrastructure detail."""


class PolicyRouterPoolLifecycle:
    """Prepare one stateless policy boundary, then own its backend on the serving loop."""

    def __init__(self, *, endpoint: str, settings: PolicyRouterHttpPoolSettings) -> None:
        """Validate trusted inputs without constructing any asynchronous resource."""
        if not isinstance(settings, PolicyRouterHttpPoolSettings):
            raise TypeError("pool settings must use PolicyRouterHttpPoolSettings")
        validate_policy_https_endpoint(endpoint)
        self._endpoint = endpoint
        self._settings = settings
        self._backend: HttpxPolicyTransport | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False
        self._active = False

    def ready(self) -> bool:
        """Report local lifetime readiness only, never upstream availability."""
        if not self._active:
            return False
        try:
            return self._loop is asyncio.get_running_loop()
        except RuntimeError:
            return False

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        """Own one application lifetime, closing partial startup and active work safely."""
        del app
        if self._started:
            raise PolicyRouterPoolLifecycleError("PDP pool requires a new application lifetime")
        self._started = True
        self._loop = asyncio.get_running_loop()
        try:
            try:
                self._backend = HttpxPolicyTransport(
                    endpoint=self._endpoint,
                    max_connections=self._settings.max_connections,
                    max_keepalive_connections=self._settings.max_keepalive_connections,
                    keepalive_expiry_seconds=self._settings.keepalive_expiry_seconds,
                )
                await self._backend.__aenter__()
            except Exception:
                raise PolicyRouterPoolLifecycleError("PDP transport startup failed") from None
            self._active = True
            yield
        finally:
            self._active = False
            primary_failure = sys.exception() is not None
            if self._backend is not None:
                try:
                    await self._backend.aclose()
                except Exception:
                    if not primary_failure:
                        raise PolicyRouterPoolLifecycleError(
                            "PDP transport shutdown failed"
                        ) from None

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        """Forward a fresh exchange only while this app's serving loop owns the pool."""
        if not self.ready() or self._backend is None:
            raise PolicyTransportFailure(
                PolicyTransportFailureKind.NETWORK, "PDP transport is not active"
            )
        return await self._backend.post_json(
            url=url, headers=headers, payload=payload, timeout_seconds=timeout_seconds
        )


def prepare_policy_router_pool(
    config: PolicyRouterRuntimeConfig, settings: PolicyRouterHttpPoolSettings | None
) -> PolicyRouterPoolLifecycle | None:
    """Reject incompatible explicit selection before any credential materialization."""
    if settings is None:
        return None
    if not isinstance(settings, PolicyRouterHttpPoolSettings):
        raise TypeError("pool settings must use PolicyRouterHttpPoolSettings or None")
    if not config.enabled or config.endpoint is None:
        raise ValueError("PDP pool requires an enabled HTTPS PDP")
    return PolicyRouterPoolLifecycle(endpoint=config.endpoint, settings=settings)
