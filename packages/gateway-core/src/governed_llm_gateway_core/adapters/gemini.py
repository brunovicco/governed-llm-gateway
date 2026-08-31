"""Native Google Gemini generateContent adapter for Phase 3 text generation."""

from collections.abc import Mapping
from urllib.parse import quote

from governed_llm_gateway_contracts import MessageRole

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

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiAdapter:
    """Execute native Gemini generateContent requests with header-based API-key auth."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        transport: JsonTransport | None = None,
    ) -> None:
        """Configure the native Gemini endpoint and credential."""
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport or StdlibJsonTransport()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate one text response through Gemini generateContent."""
        system = "\n\n".join(
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        )
        contents = [
            {
                "role": "model" if message.role is MessageRole.ASSISTANT else "user",
                "parts": [{"text": message.content}],
            }
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        if not contents:
            raise ProviderError(
                provider="google",
                code=ProviderErrorCode.INVALID_REQUEST,
                message="google request requires at least one non-system message",
                retryable=False,
            )

        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": request.max_output_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        model_path = quote(request.model.removeprefix("models/"), safe="-._")
        endpoint = f"{self._base_url}/{model_path}:generateContent"
        try:
            response = await self._transport.post_json(
                url=endpoint,
                headers={
                    "x-goog-api-key": self._api_key,
                    "content-type": "application/json",
                },
                payload=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except TransportFailure as exc:
            raise normalize_transport_failure("google", exc) from exc

        data = require_success_payload("google", response)
        text, finish_reason = _extract_text_and_finish_reason(data)
        return ProviderResponse(
            text=text,
            usage=_extract_usage(data),
            response_id=_optional_string(data.get("responseId")),
            finish_reason=finish_reason,
        )


def _extract_text_and_finish_reason(data: Mapping[str, object]) -> tuple[str, str | None]:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise _invalid_response("google response did not contain a candidate")
    candidate = candidates[0]
    content = candidate.get("content")
    if not isinstance(content, dict):
        raise _invalid_response("google candidate did not contain content")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise _invalid_response("google candidate content did not contain parts")
    text_parts = [
        part["text"].strip()
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip()
    ]
    if not text_parts:
        raise _invalid_response("google response did not contain text")
    return "\n".join(text_parts), _optional_string(candidate.get("finishReason"))


def _extract_usage(data: Mapping[str, object]) -> ProviderUsage:
    usage = data.get("usageMetadata")
    if usage is None:
        return ProviderUsage()
    if not isinstance(usage, dict):
        raise _invalid_response("google response contained invalid usage metadata")
    return ProviderUsage(
        input_tokens=require_non_negative_int(
            usage.get("promptTokenCount", 0), provider="google", field="promptTokenCount"
        ),
        output_tokens=require_non_negative_int(
            usage.get("candidatesTokenCount", 0), provider="google", field="candidatesTokenCount"
        ),
    )


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(
        provider="google",
        code=ProviderErrorCode.INVALID_RESPONSE,
        message=message,
        retryable=False,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
