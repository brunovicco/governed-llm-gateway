"""Real Claude Code request shapes must normalize without gaining policy authority."""

import unittest

from governed_llm_gateway_api.anthropic_messages_ingress import AnthropicMessagesRequestModel
from governed_llm_gateway_api.claude_code_compat import (
    ClaudeCodeCompatibilityError,
    normalize_claude_code_payload,
)
from pydantic import ValidationError


class ClaudeCodeConformanceTests(unittest.TestCase):
    def test_simple_session_request_remains_strict_anthropic_shape(self) -> None:
        payload = {
            "model": "governed-agent",
            "max_tokens": 64,
            "metadata": {"user_id": "claude-code-session"},
            "messages": [{"role": "user", "content": "hello"}],
        }

        normalized = normalize_claude_code_payload(payload)
        parsed = AnthropicMessagesRequestModel.model_validate(normalized)

        self.assertEqual(parsed.model, "governed-agent")
        self.assertIsNotNone(parsed.metadata)
        assert parsed.metadata is not None
        self.assertEqual(parsed.metadata.user_id, "claude-code-session")

    def test_structured_title_request_accepts_effort_without_routing_authority(self) -> None:
        payload = {
            "model": "governed-agent",
            "max_tokens": 64,
            "stream": True,
            "metadata": {"user_id": "claude-code-session"},
            "system": [{"type": "text", "text": "Return a title"}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
            "tools": [],
            "output_config": {
                "effort": "high",
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                        "required": ["title"],
                        "additionalProperties": False,
                    },
                },
            },
        }

        normalized = normalize_claude_code_payload(payload)
        normalized_output_config = normalized["output_config"]
        self.assertIsInstance(normalized_output_config, dict)
        assert isinstance(normalized_output_config, dict)
        self.assertNotIn("effort", normalized_output_config)
        parsed = AnthropicMessagesRequestModel.model_validate(normalized)
        generated = parsed.to_generation_payload(workload="agent.tool-use")

        self.assertEqual(generated.workload, "agent.tool-use")
        self.assertIsNotNone(generated.request.structured_output)
        self.assertFalse(hasattr(generated.request, "effort"))

    def test_main_agentic_request_accepts_observed_non_authoritative_controls(self) -> None:
        tools = [
            {
                "name": f"tool_{index}",
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"prompt": {"type": "string"}},
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            }
            for index in range(31)
        ]
        payload = {
            "model": "governed-agent",
            "max_tokens": 1024,
            "stream": True,
            "metadata": {"user_id": "claude-code-session"},
            "system": [{"type": "text", "text": "You are Claude Code"}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "inspect"}]}],
            "tools": tools,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
            "context_management": {"edits": []},
        }

        normalized = normalize_claude_code_payload(payload)

        self.assertNotIn("thinking", normalized)
        self.assertNotIn("context_management", normalized)
        self.assertNotIn("output_config", normalized)
        normalized_tools = normalized["tools"]
        self.assertIsInstance(normalized_tools, list)
        assert isinstance(normalized_tools, list)
        self.assertTrue(
            all(isinstance(tool, dict) and tool["description"] == "" for tool in normalized_tools)
        )

        parsed = AnthropicMessagesRequestModel.model_validate(normalized)
        generated = parsed.to_generation_payload(workload="agent.tool-use")
        request = generated.to_gateway_request()

        self.assertEqual(len(request.tools), 31)
        self.assertTrue(request.requirements.tool_calling)
        self.assertEqual(request.workload, "agent.tool-use")
        self.assertFalse(hasattr(request, "thinking"))
        self.assertFalse(hasattr(request, "context_management"))

    def test_disabled_thinking_is_bounded_and_discarded(self) -> None:
        normalized = normalize_claude_code_payload(
            {
                "model": "governed-agent",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hello"}],
                "thinking": {"type": "disabled"},
                "output_config": {"effort": "medium"},
            }
        )

        self.assertNotIn("thinking", normalized)
        self.assertNotIn("output_config", normalized)
        AnthropicMessagesRequestModel.model_validate(normalized)

    def test_unknown_thinking_fields_fail_closed(self) -> None:
        with self.assertRaises(ClaudeCodeCompatibilityError):
            normalize_claude_code_payload(
                {
                    "model": "governed-agent",
                    "max_tokens": 64,
                    "messages": [{"role": "user", "content": "hello"}],
                    "thinking": {"type": "adaptive", "unexpected": True},
                }
            )

    def test_unknown_top_level_fields_remain_for_strict_boundary_rejection(self) -> None:
        normalized = normalize_claude_code_payload(
            {
                "model": "governed-agent",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hello"}],
                "unreviewed_control": "must-fail",
            }
        )

        self.assertIn("unreviewed_control", normalized)
        with self.assertRaises(ValidationError):
            AnthropicMessagesRequestModel.model_validate(normalized)

    def test_unknown_output_config_fields_remain_fail_closed(self) -> None:
        normalized = normalize_claude_code_payload(
            {
                "model": "governed-agent",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hello"}],
                "output_config": {"effort": "high", "unreviewed": True},
            }
        )

        with self.assertRaises(ValidationError):
            AnthropicMessagesRequestModel.model_validate(normalized)


if __name__ == "__main__":
    unittest.main()
