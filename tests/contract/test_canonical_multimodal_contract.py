"""Canonical multimodal inputs must be bounded, correlated and capability-gated."""

import unittest
from uuid import UUID

from governed_llm_gateway_contracts import (
    AudioBlock,
    AudioMediaType,
    Base64Source,
    DataClassification,
    GatewayRequest,
    HttpsUrlSource,
    ImageBlock,
    ImageMediaType,
    Message,
    MessageRole,
    RiskLevel,
    TextBlock,
    ToolCall,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
    WorkloadRequirements,
)


def _request(
    messages: tuple[Message, ...],
    requirements: WorkloadRequirements,
) -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=UUID("99999999-9999-4999-8999-999999999999"),
        workload="agent.tool-use",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=requirements,
        messages=messages,
    )


class CanonicalMultimodalContractTests(unittest.TestCase):
    def test_invalid_base64_is_rejected_at_contract_construction(self) -> None:
        with self.assertRaisesRegex(ValueError, "base64 media data is invalid"):
            Base64Source("not valid base64!")

    def test_media_urls_are_https_uncredentialed_and_not_query_bearing(self) -> None:
        for url in (
            "http://example.com/image.png",
            "https://user@example.com/image.png",
            "https://example.com/image.png?secret=1",
            "file:///tmp/image.png",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                HttpsUrlSource(url)

    def test_legacy_and_block_representations_cannot_be_ambiguous(self) -> None:
        with self.assertRaisesRegex(ValueError, "legacy content/images or canonical blocks"):
            Message(
                role=MessageRole.USER,
                content="legacy",
                blocks=(TextBlock("canonical"),),
            )

    def test_image_and_audio_require_explicit_capabilities(self) -> None:
        image = Message(
            role=MessageRole.USER,
            content="",
            blocks=(
                ImageBlock(ImageMediaType.PNG, Base64Source("aGVsbG8=")),
                AudioBlock(AudioMediaType.WAV, Base64Source("aGVsbG8=")),
            ),
        )
        with self.assertRaisesRegex(ValueError, "image input requires vision"):
            _request((image,), WorkloadRequirements(audio=True))
        with self.assertRaisesRegex(ValueError, "audio input requires audio"):
            _request((image,), WorkloadRequirements(vision=True))

    def test_url_image_can_retain_unknown_media_type_but_inline_image_cannot(self) -> None:
        remote = ImageBlock(None, HttpsUrlSource("https://example.com/image"))
        self.assertIsNone(remote.media_type)
        with self.assertRaisesRegex(ValueError, "inline image blocks require a media_type"):
            ImageBlock(None, Base64Source("aGVsbG8="))

    def test_tool_results_must_follow_their_correlated_tool_use(self) -> None:
        result = Message(
            role=MessageRole.TOOL,
            content="",
            blocks=(ToolResultBlock(ToolResult(call_id="call-1", content="done")),),
        )
        use = Message(
            role=MessageRole.ASSISTANT,
            content="",
            blocks=(ToolUseBlock(ToolCall(call_id="call-1", name="lookup", arguments={})),),
        )
        with self.assertRaisesRegex(ValueError, "prior tool-use"):
            _request((result, use), WorkloadRequirements(tool_calling=True))
        request = _request((use, result), WorkloadRequirements(tool_calling=True))
        self.assertEqual(len(request.messages), 2)

    def test_parallel_tool_calls_require_the_separate_capability(self) -> None:
        assistant = Message(
            role=MessageRole.ASSISTANT,
            content="",
            blocks=(
                ToolUseBlock(ToolCall(call_id="a", name="lookup", arguments={})),
                ToolUseBlock(ToolCall(call_id="b", name="lookup", arguments={})),
            ),
        )
        with self.assertRaisesRegex(ValueError, "parallel_tool_calling"):
            _request((assistant,), WorkloadRequirements(tool_calling=True))
        accepted = _request(
            (assistant,),
            WorkloadRequirements(tool_calling=True, parallel_tool_calling=True),
        )
        self.assertTrue(accepted.requirements.parallel_tool_calling)
