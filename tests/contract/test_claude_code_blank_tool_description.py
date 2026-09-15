"""Observed Claude Code built-in tool descriptions remain compatible and bounded."""

import unittest

from governed_llm_gateway_api.anthropic_messages_ingress import AnthropicMessagesRequestModel
from governed_llm_gateway_api.claude_code_compat import normalize_claude_code_payload
from pydantic import ValidationError


class ClaudeCodeBlankToolDescriptionTests(unittest.TestCase):
    def test_tool_descriptions_are_normalized_without_gaining_authority(self) -> None:
        payload = {
            "model": "governed-agent",
            "max_tokens": 32000,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                },
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "system reminder"}],
                },
            ],
            "tools": [
                {
                    "name": "empty_description",
                    "description": "",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "whitespace_description",
                    "description": "   ",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "padded_description",
                    "description": "  Useful built-in tool description.\n",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            ],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
            "context_management": {"edits": []},
        }

        normalized = normalize_claude_code_payload(payload)
        tools = normalized["tools"]
        assert isinstance(tools, list)
        first_tool = tools[0]
        second_tool = tools[1]
        third_tool = tools[2]
        assert isinstance(first_tool, dict)
        assert isinstance(second_tool, dict)
        assert isinstance(third_tool, dict)
        self.assertEqual(first_tool["description"], "Claude Code tool")
        self.assertEqual(second_tool["description"], "Claude Code tool")
        self.assertEqual(third_tool["description"], "Useful built-in tool description.")

        parsed = AnthropicMessagesRequestModel.model_validate(normalized)
        generated = parsed.to_generation_payload(workload="agent.tool-use")
        request = generated.to_gateway_request()

        self.assertEqual(len(request.tools), 3)
        self.assertTrue(request.requirements.tool_calling)

    def test_non_string_description_remains_fail_closed(self) -> None:
        payload = {
            "model": "governed-agent",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "name": "bad_description",
                    "description": None,
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                    },
                }
            ],
        }

        normalized = normalize_claude_code_payload(payload)
        with self.assertRaises(ValidationError):
            AnthropicMessagesRequestModel.model_validate(normalized)


if __name__ == "__main__":
    unittest.main()
