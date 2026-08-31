"""Explicit OpenAI-compatible chat-completions adapter for compatible providers."""

from collections.abc import Mapping

from governed_llm_gateway_core.adapters.http_json import (
    JsonTransport,
    StdlibJsonTransport,
    TransportFailure,
)
from governed_llm_gateway_core.adapters.provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
)
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)


class OpenAICompatibleAdapter:
    """Execute explicitly configured OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        endpoint: str,
        max_tokens_field: str = "max_tokens",
        transport: JsonTransport | None = None,
    ) -> None:
        """Configure one explicit OpenAI-compatible provider endpoint."""
        if not provider.strip():
            raise ValueError("provider must not be empty")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if max_tokens_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("unsupported max_tokens_field")
        self._provider = provider
        self._api_key = api_key
        self._endpoint = endpoint
        self._max_tokens_field = max_tokens_field
        self._transport = transport or StdlibJsonTransport()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate text through one explicitly configured compatible endpoint."""
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            self._max_tokens_field: request.max_output_tokens,
        }
        try:
            response = await self._transport.post_json(
                url=self._endpoint,
                headers={
                    "authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                payload=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except TransportFailure as exc:
            raise normalize_transport_failure(self._provider, exc) from exc

        data = require_success_payload(self._provider, response)
        text, finish_reason = self._extract_choice(data)
        usage = self._extract_usage(data)
        return ProviderResponse(
            text=text,
            usage=usage,
            response_id=_optional_string(data.get("id")),
            finish_reason=finish_reason,
        )

    def _extract_choice(self, data: Mapping[str, object]) -> tuple[str, str | None]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise self._invalid_response("response did not contain a valid first choice")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise self._invalid_response("response choice did not contain a message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise self._invalid_response("response message did not contain text")
        return content.strip(), _optional_string(choice.get("finish_reason"))

    def _extract_usage(self, data: Mapping[str, object]) -> ProviderUsage:
        usage = data.get("usage")
        if usage is None:
            return ProviderUsage()
        if not isinstance(usage, dict):
            raise self._invalid_response("response contained invalid usage metadata")
        return ProviderUsage(
            input_tokens=require_non_negative_int(
                usage.get("prompt_tokens", 0),
                provider=self._provider,
                field="prompt_tokens",
            ),
            output_tokens=require_non_negative_int(
                usage.get("completion_tokens", 0),
                provider=self._provider,
                field="completion_tokens",
            ),
        )

    def _invalid_response(self, detail: str) -> ProviderError:
        return ProviderError(
            provider=self._provider,
            code=ProviderErrorCode.INVALID_RESPONSE,
            message=f"{self._provider} {detail}",
            retryable=False,
        )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
