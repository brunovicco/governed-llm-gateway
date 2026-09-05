import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from governed_llm_gateway_api import GenerateRequestModel
from governed_llm_gateway_client.client import _build_generate_payload
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    ImageInput,
    ImageMediaType,
    Message,
    MessageRole,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.adapters import (
    AnthropicMessagesAdapter,
    GeminiAdapter,
    OpenAICompatibleAdapter,
    OpenAIResponsesAdapter,
)
from governed_llm_gateway_core.adapters.anthropic_streaming import (
    AnthropicMessagesStreamingAdapter,
)
from governed_llm_gateway_core.adapters.gemini_streaming import GeminiStreamingAdapter
from governed_llm_gateway_core.adapters.http_json import JsonHttpResponse
from governed_llm_gateway_core.adapters.http_sse import SseEvent, SseStream
from governed_llm_gateway_core.adapters.openai_compatible_streaming import (
    OpenAICompatibleStreamingAdapter,
)
from governed_llm_gateway_core.adapters.openai_responses_streaming import (
    OpenAIResponsesStreamingAdapter,
)
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderPort,
    ProviderRequest,
    ProviderStreamEvent,
    ProviderStreamingPort,
)

REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
IMAGE_URL = "https://images.example.test/public/sample.png"


class FakeJsonTransport:
    def __init__(self, response: JsonHttpResponse | None = None) -> None:
        self.response = response or JsonHttpResponse(
            status_code=200,
            headers={},
            payload={
                "id": "resp-image",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "a diagram"}],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        )
        self.calls: list[Mapping[str, object]] = []

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


@dataclass
class FakeSseStream:
    events: list[SseEvent]
    status_code: int = 200
    headers: Mapping[str, str] = field(
        default_factory=lambda: {"content-type": "text/event-stream"}
    )
    closed: bool = False

    def __post_init__(self) -> None:
        self._index = 0

    def __aiter__(self) -> AsyncIterator[SseEvent]:
        return self

    async def __anext__(self) -> SseEvent:
        if self._index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self._index]
        self._index += 1
        return event

    async def aclose(self) -> None:
        self.closed = True


class FakeSseTransport:
    def __init__(self, stream: FakeSseStream) -> None:
        self.stream = stream
        self.calls: list[Mapping[str, object]] = []

    async def open_sse(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> SseStream:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.stream


class RejectingSseTransport:
    async def open_sse(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> SseStream:
        del url, headers, payload, timeout_seconds
        raise AssertionError("unsupported image input must fail before provider I/O")


def _image(media_type: ImageMediaType = ImageMediaType.PNG) -> ImageInput:
    return ImageInput(media_type=media_type, url=IMAGE_URL)


def _message(*, images: tuple[ImageInput, ...] = ()) -> Message:
    return Message(role=MessageRole.USER, content="Describe the image.", images=images)


def _provider_request(*, model: str = "vision-model") -> ProviderRequest:
    return ProviderRequest(model=model, messages=(_message(images=(_image(),)),))


async def _collect(stream: AsyncIterator[ProviderStreamEvent]) -> list[ProviderStreamEvent]:
    return [event async for event in stream]


@pytest.mark.parametrize(
    "media_type",
    [ImageMediaType.JPEG, ImageMediaType.PNG, ImageMediaType.WEBP],
)
def test_image_input_accepts_reviewed_media_types(media_type: ImageMediaType) -> None:
    image = _image(media_type)

    assert image.media_type is media_type
    assert image.url == IMAGE_URL


@pytest.mark.parametrize(
    "url",
    [
        "http://images.example.test/sample.png",
        "https://user:pass@images.example.test/sample.png",
        "https://images.example.test/sample.png?token=secret",
        "https://images.example.test/sample.png#fragment",
        " https://images.example.test/sample.png",
        "https://images.example.test/" + "a" * 2048,
    ],
)
def test_image_input_rejects_unsafe_or_unbounded_urls(url: str) -> None:
    with pytest.raises(ValueError):
        ImageInput(media_type=ImageMediaType.PNG, url=url)


def test_image_input_is_bounded_to_user_messages_and_counts() -> None:
    with pytest.raises(ValueError, match="only on user messages"):
        Message(role=MessageRole.SYSTEM, content="system", images=(_image(),))

    with pytest.raises(ValueError, match="maximum image count"):
        _message(images=tuple(_image() for _ in range(9)))


def test_gateway_request_requires_vision_for_images() -> None:
    with pytest.raises(ValueError, match="requires vision capability"):
        GatewayRequest(
            schema_version="1.0",
            request_id=REQUEST_ID,
            workload="multimodal.analysis",
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            messages=(_message(images=(_image(),)),),
        )


def test_gateway_request_enforces_total_image_limit() -> None:
    messages = tuple(_message(images=tuple(_image() for _ in range(8))) for _ in range(3))

    with pytest.raises(ValueError, match="maximum image count"):
        GatewayRequest(
            schema_version="1.0",
            request_id=REQUEST_ID,
            workload="multimodal.analysis",
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            requirements=WorkloadRequirements(vision=True),
            messages=messages,
        )


def test_streaming_api_projects_image_contract_without_provider_fields() -> None:
    payload = GenerateRequestModel.model_validate(
        {
            "schema_version": "1.0",
            "request_id": str(REQUEST_ID),
            "workload": "multimodal.analysis",
            "risk_level": "low",
            "data_classification": "public",
            "requirements": {"vision": True},
            "messages": [
                {
                    "role": "user",
                    "content": "Describe the image.",
                    "images": [{"media_type": "image/png", "url": IMAGE_URL}],
                }
            ],
            "context_tokens_estimated": 64,
            "max_output_tokens": 128,
        }
    )

    request = payload.to_gateway_request()

    assert request.requirements.vision is True
    assert request.messages[0].images == (_image(),)


def test_streaming_api_rejects_unknown_image_fields() -> None:
    with pytest.raises(ValueError):
        GenerateRequestModel.model_validate(
            {
                "schema_version": "1.0",
                "request_id": str(REQUEST_ID),
                "workload": "multimodal.analysis",
                "risk_level": "low",
                "data_classification": "public",
                "requirements": {"vision": True},
                "messages": [
                    {
                        "role": "user",
                        "content": "Describe the image.",
                        "images": [
                            {
                                "media_type": "image/png",
                                "url": IMAGE_URL,
                                "provider_file_id": "file-1",
                            }
                        ],
                    }
                ],
                "context_tokens_estimated": 64,
                "max_output_tokens": 128,
            }
        )


def test_thin_sdk_serializes_images_provider_neutrally() -> None:
    payload = _build_generate_payload(
        workload="multimodal.analysis",
        messages=(_message(images=(_image(),)),),
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(vision=True),
        limits=None,
        agent_identity=None,
        tools=(),
        structured_output=None,
        context_tokens_estimated=64,
        max_output_tokens=128,
        provider_timeout_seconds=30.0,
        request_id=REQUEST_ID,
    )

    assert payload["requirements"] == {
        "tool_calling": False,
        "structured_output": False,
        "vision": True,
        "min_context_tokens": 0,
    }
    assert payload["messages"] == [
        {
            "role": "user",
            "content": "Describe the image.",
            "images": [{"media_type": "image/png", "url": IMAGE_URL}],
        }
    ]
    assert "provider" not in payload
    assert "model" not in payload


def test_text_only_sdk_wire_shape_is_unchanged() -> None:
    payload = _build_generate_payload(
        workload="text.analysis",
        messages=(_message(),),
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=None,
        limits=None,
        agent_identity=None,
        tools=(),
        structured_output=None,
        context_tokens_estimated=16,
        max_output_tokens=32,
        provider_timeout_seconds=30.0,
        request_id=REQUEST_ID,
    )

    assert payload["messages"] == [{"role": "user", "content": "Describe the image."}]


def test_provider_feature_support_defaults_image_input_to_false() -> None:
    assert ProviderFeatureSupport().native_image_input is False


def test_openai_responses_translates_url_image_to_native_content_parts() -> None:
    transport = FakeJsonTransport()
    adapter = OpenAIResponsesAdapter(api_key="secret", transport=transport)

    response = asyncio.run(adapter.generate(_provider_request()))

    assert response.text == "a diagram"
    assert adapter.feature_support.native_image_input is True
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe the image."},
                {"type": "input_image", "image_url": IMAGE_URL},
            ],
        }
    ]


def test_openai_responses_streaming_uses_same_native_image_translation() -> None:
    upstream = FakeSseStream(
        [
            SseEvent(
                event=None,
                data=json.dumps({"type": "response.created", "response": {"id": "resp-image"}}),
            ),
            SseEvent(
                event=None,
                data=json.dumps({"type": "response.output_text.delta", "delta": "diagram"}),
            ),
            SseEvent(
                event=None,
                data=json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp-image",
                            "status": "completed",
                            "usage": {"input_tokens": 10, "output_tokens": 2},
                        },
                    }
                ),
            ),
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = OpenAIResponsesStreamingAdapter(api_key="secret", sse_transport=transport)

    events = asyncio.run(_collect(adapter.stream(_provider_request())))

    assert events
    assert adapter.feature_support.native_image_input is True
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe the image."},
                {"type": "input_image", "image_url": IMAGE_URL},
            ],
        }
    ]
    assert upstream.closed is True


def test_anthropic_translates_url_image_to_native_content_blocks() -> None:
    transport = FakeJsonTransport(
        JsonHttpResponse(
            status_code=200,
            headers={},
            payload={
                "id": "msg-image",
                "content": [{"type": "text", "text": "a diagram"}],
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "stop_reason": "end_turn",
            },
        )
    )
    adapter = AnthropicMessagesAdapter(api_key="secret", transport=transport)

    response = asyncio.run(adapter.generate(_provider_request()))

    assert response.text == "a diagram"
    assert adapter.feature_support.native_image_input is True
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "url", "url": IMAGE_URL},
                },
                {"type": "text", "text": "Describe the image."},
            ],
        }
    ]


def test_anthropic_streaming_uses_same_native_image_translation() -> None:
    upstream = FakeSseStream(
        [
            SseEvent(
                event=None,
                data=json.dumps(
                    {
                        "type": "message_start",
                        "message": {"id": "msg-image", "usage": {"input_tokens": 10}},
                    }
                ),
            ),
            SseEvent(
                event=None,
                data=json.dumps(
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    }
                ),
            ),
            SseEvent(
                event=None,
                data=json.dumps(
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "diagram"},
                    }
                ),
            ),
            SseEvent(
                event=None,
                data=json.dumps(
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": "end_turn"},
                        "usage": {"output_tokens": 2},
                    }
                ),
            ),
            SseEvent(event=None, data=json.dumps({"type": "message_stop"})),
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = AnthropicMessagesStreamingAdapter(api_key="secret", sse_transport=transport)

    events = asyncio.run(_collect(adapter.stream(_provider_request())))

    assert events
    assert adapter.feature_support.native_image_input is True
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "url", "url": IMAGE_URL},
                },
                {"type": "text", "text": "Describe the image."},
            ],
        }
    ]
    assert payload["stream"] is True
    assert upstream.closed is True


def test_gemini_translates_url_image_to_native_file_data() -> None:
    transport = FakeJsonTransport(
        JsonHttpResponse(
            status_code=200,
            headers={},
            payload={
                "responseId": "gemini-image",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "a diagram"}]},
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2},
            },
        )
    )
    adapter = GeminiAdapter(api_key="secret", transport=transport)

    response = asyncio.run(adapter.generate(_provider_request(model="gemini-2.5-flash")))

    assert response.text == "a diagram"
    assert adapter.feature_support.native_image_input is True
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["contents"] == [
        {
            "role": "user",
            "parts": [
                {
                    "fileData": {
                        "mimeType": "image/png",
                        "fileUri": IMAGE_URL,
                    }
                },
                {"text": "Describe the image."},
            ],
        }
    ]


def test_gemini_streaming_uses_same_native_image_translation() -> None:
    upstream = FakeSseStream(
        [
            SseEvent(
                event=None,
                data=json.dumps(
                    {
                        "responseId": "gemini-image",
                        "candidates": [
                            {
                                "finishReason": "STOP",
                                "content": {"parts": [{"text": "diagram"}]},
                            }
                        ],
                        "usageMetadata": {
                            "promptTokenCount": 10,
                            "candidatesTokenCount": 2,
                        },
                    }
                ),
            )
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = GeminiStreamingAdapter(api_key="secret", sse_transport=transport)

    events = asyncio.run(_collect(adapter.stream(_provider_request(model="gemini-2.5-flash"))))

    assert events
    assert adapter.feature_support.native_image_input is True
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["contents"] == [
        {
            "role": "user",
            "parts": [
                {
                    "fileData": {
                        "mimeType": "image/png",
                        "fileUri": IMAGE_URL,
                    }
                },
                {"text": "Describe the image."},
            ],
        }
    ]
    assert upstream.closed is True


def test_gemini_2_0_rejects_external_url_image_before_provider_io() -> None:
    transport = FakeJsonTransport()
    adapter = GeminiAdapter(api_key="secret", transport=transport)

    with pytest.raises(ProviderError) as caught:
        asyncio.run(adapter.generate(_provider_request(model="gemini-2.0-flash")))

    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert caught.value.retryable is False
    assert transport.calls == []


def test_gemini_2_0_streaming_rejects_external_url_image_before_provider_io() -> None:
    transport = RejectingSseTransport()
    adapter = GeminiStreamingAdapter(api_key="secret", sse_transport=transport)

    with pytest.raises(ProviderError) as caught:
        asyncio.run(_collect(adapter.stream(_provider_request(model="models/gemini-2.0-flash"))))

    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert caught.value.retryable is False


def test_openai_compatible_fails_closed_before_image_provider_io() -> None:
    transport = FakeJsonTransport()
    adapter: ProviderPort = OpenAICompatibleAdapter(
        provider="compatible",
        api_key="secret",
        endpoint="https://api.example.test/v1/chat/completions",
        transport=transport,
    )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(adapter.generate(_provider_request()))

    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert caught.value.retryable is False
    assert transport.calls == []


def test_openai_compatible_streaming_fails_closed_before_image_provider_io() -> None:
    transport = RejectingSseTransport()
    adapter: ProviderStreamingPort = OpenAICompatibleStreamingAdapter(
        provider="compatible",
        api_key="secret",
        endpoint="https://api.example.test/v1/chat/completions",
        supports_streaming=True,
        supports_stream_usage=True,
        sse_transport=transport,
    )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(_collect(adapter.stream(_provider_request())))

    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert caught.value.retryable is False
