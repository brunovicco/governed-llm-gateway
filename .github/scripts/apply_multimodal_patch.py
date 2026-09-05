from pathlib import Path


def rep(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, got {count}: {old[:80]!r}")
    file.write_text(text.replace(old, new, 1))


rep(
    "packages/gateway-contracts/src/governed_llm_gateway_contracts/enums.py",
    '''class Modality(StrEnum):
    """Provider-neutral input modalities relevant to model eligibility."""

    TEXT = "text"
    IMAGE = "image"
''',
    '''class Modality(StrEnum):
    """Provider-neutral input modalities relevant to model eligibility."""

    TEXT = "text"
    IMAGE = "image"


class ImageMediaType(StrEnum):
    """Initial provider-neutral image media types supported by URL input."""

    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
''',
)

contracts = "packages/gateway-contracts/src/governed_llm_gateway_contracts/contracts.py"
rep(
    contracts,
    "from re import fullmatch\nfrom uuid import UUID\n",
    "from re import fullmatch\nfrom urllib.parse import urlsplit\nfrom uuid import UUID\n",
)
rep(
    contracts,
    '''    ExecutionStatus,
    MessageRole,
    RejectionReason,
''',
    '''    ExecutionStatus,
    ImageMediaType,
    MessageRole,
    RejectionReason,
''',
)
rep(
    contracts,
    '''_TOOL_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,127}"
_SCHEMA_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,63}"


@dataclass(frozen=True, slots=True)
class Message:
    """Provider-neutral message."""

    role: MessageRole
    content: str
''',
    '''_TOOL_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,127}"
_SCHEMA_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,63}"
_MAX_IMAGE_URL_LENGTH = 2048
_MAX_IMAGES_PER_MESSAGE = 8
_MAX_IMAGES_PER_REQUEST = 16


@dataclass(frozen=True, slots=True)
class ImageInput:
    """Provider-neutral HTTPS image reference forwarded without gateway fetching."""

    media_type: ImageMediaType
    url: str

    def __post_init__(self) -> None:
        """Reject ambiguous or credential-bearing image references before provider I/O."""
        if not isinstance(self.media_type, ImageMediaType):
            raise ValueError("image media_type must use the provider-neutral vocabulary")
        if not self.url or self.url.strip() != self.url:
            raise ValueError("image URL must be a normalized non-empty string")
        if len(self.url) > _MAX_IMAGE_URL_LENGTH:
            raise ValueError("image URL exceeds the maximum supported length")
        try:
            parsed = urlsplit(self.url)
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("image URL is invalid") from exc
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("image URL must be an absolute HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("image URL must not contain userinfo")
        if parsed.query or parsed.fragment:
            raise ValueError("image URL must not contain query or fragment")


@dataclass(frozen=True, slots=True)
class Message:
    """Provider-neutral message with bounded optional image-understanding input."""

    role: MessageRole
    content: str
    images: tuple[ImageInput, ...] = ()

    def __post_init__(self) -> None:
        """Keep the first multimodal contract bounded to user-supplied URL images."""
        if len(self.images) > _MAX_IMAGES_PER_MESSAGE:
            raise ValueError("message exceeds the maximum image count")
        if any(not isinstance(image, ImageInput) for image in self.images):
            raise ValueError("message images must use the provider-neutral ImageInput contract")
        if self.images and self.role is not MessageRole.USER:
            raise ValueError("image input is supported only on user messages")
''',
)
rep(
    contracts,
    '''        if self.structured_output is not None and not self.requirements.structured_output:
            raise ValueError("structured output schema requires structured_output capability")
''',
    '''        if self.structured_output is not None and not self.requirements.structured_output:
            raise ValueError("structured output schema requires structured_output capability")
        image_count = sum(len(message.images) for message in self.messages)
        if image_count > _MAX_IMAGES_PER_REQUEST:
            raise ValueError("request exceeds the maximum image count")
        if image_count and not self.requirements.vision:
            raise ValueError("image input requires vision capability")
''',
)

init_path = "packages/gateway-contracts/src/governed_llm_gateway_contracts/__init__.py"
rep(
    init_path,
    '''    GatewayResponse,
    GatewayStreamEvent,
    Message,
''',
    '''    GatewayResponse,
    GatewayStreamEvent,
    ImageInput,
    Message,
''',
)
rep(
    init_path,
    '''    ExecutionStatus,
    MessageRole,
    Modality,
''',
    '''    ExecutionStatus,
    ImageMediaType,
    MessageRole,
    Modality,
''',
)
rep(
    init_path,
    '''    "GatewayStreamEvent",
    "Message",
''',
    '''    "GatewayStreamEvent",
    "ImageInput",
    "ImageMediaType",
    "Message",
''',
)

api = "apps/gateway-api/src/governed_llm_gateway_api/stream_generate.py"
rep(
    api,
    '''    GatewayRequest,
    GatewayStreamEvent,
    Message,
''',
    '''    GatewayRequest,
    GatewayStreamEvent,
    ImageInput,
    ImageMediaType,
    Message,
''',
)
rep(
    api,
    '''class GenerateMessageModel(BaseModel):
    """One provider-neutral message accepted by the streaming API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: MessageRole
    content: str = Field(min_length=1)
''',
    '''class GenerateImageModel(BaseModel):
    """Bounded HTTPS image reference accepted by the streaming API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    media_type: ImageMediaType
    url: str = Field(min_length=1, max_length=2048)

    def to_contract(self) -> ImageInput:
        """Build the immutable provider-neutral image input contract."""
        return ImageInput(media_type=self.media_type, url=self.url)


class GenerateMessageModel(BaseModel):
    """One provider-neutral message accepted by the streaming API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: MessageRole
    content: str = Field(min_length=1)
    images: tuple[GenerateImageModel, ...] = Field(default=(), max_length=8)
''',
)
rep(
    api,
    '''        messages = tuple(Message(role=item.role, content=item.content) for item in self.messages)
''',
    '''        messages = tuple(
            Message(
                role=item.role,
                content=item.content,
                images=tuple(image.to_contract() for image in item.images),
            )
            for item in self.messages
        )
''',
)

client = "packages/gateway-client/src/governed_llm_gateway_client/client.py"
rep(
    client,
    '''        "messages": [
            {"role": message.role.value, "content": message.content} for message in request.messages
        ],
''',
    '''        "messages": [_serialize_message(message) for message in request.messages],
''',
)
rep(
    client,
    '''def _validate_identity_response(response: httpx.Response) -> None:
''',
    '''def _serialize_message(message: Message) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role.value,
        "content": message.content,
    }
    if message.images:
        payload["images"] = [
            {"media_type": image.media_type.value, "url": image.url}
            for image in message.images
        ]
    return payload


def _validate_identity_response(response: httpx.Response) -> None:
''',
)

provider = "packages/gateway-core/src/governed_llm_gateway_core/application/provider.py"
rep(
    provider,
    '''    native_structured_output: bool = False
    native_tool_calling: bool = False
    native_streaming: bool = False
''',
    '''    native_structured_output: bool = False
    native_tool_calling: bool = False
    native_image_input: bool = False
    native_streaming: bool = False
''',
)
rep(
    provider,
    '''        if self.tools:
            validate_tool_definitions(self.tools)


@dataclass(frozen=True, slots=True)
class ProviderResponse:
''',
    '''        if self.tools:
            validate_tool_definitions(self.tools)

    @property
    def has_image_input(self) -> bool:
        """Return whether the request contains provider-neutral image input."""
        return any(message.images for message in self.messages)


@dataclass(frozen=True, slots=True)
class ProviderResponse:
''',
)

common = "packages/gateway-core/src/governed_llm_gateway_core/adapters/provider_common.py"
rep(
    common,
    "from governed_llm_gateway_core.application.provider import ProviderError, ProviderErrorCode\n",
    '''from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
)
''',
)
rep(
    common,
    '''from .http_json import JsonHttpResponse, TransportFailure, TransportFailureKind


def require_success_payload''',
    '''from .http_json import JsonHttpResponse, TransportFailure, TransportFailureKind


def require_supported_request_features(
    provider: str,
    request: ProviderRequest,
    support: ProviderFeatureSupport,
) -> None:
    """Reject provider-neutral features this API family cannot translate safely."""
    if request.has_image_input and not support.native_image_input:
        raise ProviderError(
            provider=provider,
            code=ProviderErrorCode.INVALID_REQUEST,
            message=f"{provider} API family does not support provider-neutral image input",
            retryable=False,
        )


def require_success_payload''',
)

openai = "packages/gateway-core/src/governed_llm_gateway_core/adapters/openai_responses.py"
rep(
    openai,
    '''    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
''',
    '''    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
    require_supported_request_features,
''',
)
rep(
    openai,
    '''    feature_support = ProviderFeatureSupport(
        native_structured_output=True,
        native_tool_calling=True,
    )
''',
    '''    feature_support = ProviderFeatureSupport(
        native_structured_output=True,
        native_tool_calling=True,
        native_image_input=True,
    )
''',
)
rep(
    openai,
    '''    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate text, structured output, or client-side tool calls."""
        instructions = "\\n\\n".join(
''',
    '''    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate text, structured output, image analysis, or client-side tool calls."""
        require_supported_request_features("openai", request, self.feature_support)
        instructions = "\\n\\n".join(
''',
)
rep(
    openai,
    '''        input_messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
''',
    '''        input_messages = _openai_input_messages(request)
''',
)
rep(
    openai,
    '''def _extract_text(data: Mapping[str, object]) -> str:
''',
    '''def _openai_input_messages(request: ProviderRequest) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            continue
        if not message.images:
            messages.append({"role": message.role.value, "content": message.content})
            continue
        content: list[dict[str, object]] = [{"type": "input_text", "text": message.content}]
        content.extend(
            {"type": "input_image", "image_url": image.url} for image in message.images
        )
        messages.append({"role": message.role.value, "content": content})
    return messages


def _extract_text(data: Mapping[str, object]) -> str:
''',
)

openai_stream = "packages/gateway-core/src/governed_llm_gateway_core/adapters/openai_responses_streaming.py"
rep(
    openai_stream,
    '''from .openai_responses import OpenAIResponsesAdapter, _require_openai_strict_schema
from .provider_common import normalize_transport_failure
''',
    '''from .openai_responses import (
    OpenAIResponsesAdapter,
    _openai_input_messages,
    _require_openai_strict_schema,
)
from .provider_common import normalize_transport_failure, require_supported_request_features
''',
)
rep(
    openai_stream,
    '''        native_structured_output=True,
        native_tool_calling=True,
        native_streaming=True,
''',
    '''        native_structured_output=True,
        native_tool_calling=True,
        native_image_input=True,
        native_streaming=True,
''',
)
rep(
    openai_stream,
    '''    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        """Yield provider-neutral Responses events and close the upstream stream on cancellation."""
        instructions = "\\n\\n".join(
''',
    '''    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        """Yield provider-neutral Responses events and close the upstream stream on cancellation."""
        require_supported_request_features("openai", request, self.feature_support)
        instructions = "\\n\\n".join(
''',
)
rep(
    openai_stream,
    '''        input_messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
''',
    '''        input_messages = _openai_input_messages(request)
''',
)

for path, provider_name, method in (
    (
        "packages/gateway-core/src/governed_llm_gateway_core/adapters/anthropic.py",
        "anthropic",
        '''    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate text, structured output, or client-side tool calls."""
''',
    ),
    (
        "packages/gateway-core/src/governed_llm_gateway_core/adapters/gemini.py",
        "google",
        '''    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate text, structured output, or client-side function calls."""
''',
    ),
):
    rep(
        path,
        '''    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
''',
        '''    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
    require_supported_request_features,
''',
    )
    rep(
        path,
        method,
        method + f'        require_supported_request_features("{provider_name}", request, self.feature_support)\n',
    )

compatible = "packages/gateway-core/src/governed_llm_gateway_core/adapters/openai_compatible.py"
rep(
    compatible,
    '''    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
''',
    '''    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
    require_supported_request_features,
''',
)
method = '''    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate through an endpoint whose optional features were explicitly verified."""
'''
rep(
    compatible,
    method,
    method + "        require_supported_request_features(self._provider, request, self.feature_support)\n",
)

for path, provider_expr, method in (
    (
        "packages/gateway-core/src/governed_llm_gateway_core/adapters/anthropic_streaming.py",
        '"anthropic"',
        '''    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        """Yield normalized Messages events and close upstream resources on cancellation."""
''',
    ),
    (
        "packages/gateway-core/src/governed_llm_gateway_core/adapters/gemini_streaming.py",
        '"google"',
        '''    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        """Yield normalized Gemini stream events and require final usage metadata."""
''',
    ),
):
    rep(
        path,
        "from .provider_common import normalize_transport_failure, require_non_negative_int\n",
        '''from .provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_supported_request_features,
)
''',
    )
    rep(
        path,
        method,
        method + f"        require_supported_request_features({provider_expr}, request, self.feature_support)\n",
    )

compatible_stream = "packages/gateway-core/src/governed_llm_gateway_core/adapters/openai_compatible_streaming.py"
rep(
    compatible_stream,
    "from .provider_common import normalize_transport_failure, require_non_negative_int\n",
    '''from .provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_supported_request_features,
)
''',
)
method = '''    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        """Yield normalized chat-completion chunks for an explicitly verified endpoint."""
'''
rep(
    compatible_stream,
    method,
    method + "        require_supported_request_features(self._provider, request, self.feature_support)\n",
)
