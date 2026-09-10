"""The unmodified OpenAI SDK must work against the gateway's compatible ingress.

The shim exists so a consumer can repoint `base_url` and keep its client. Asserting the
wire shape by hand proves the fields are present; only driving the real SDK proves the
client accepts them. This runs against a local loopback server and needs no credential
and no network.
"""

import threading
import unittest

import uvicorn
from fastapi import FastAPI
from governed_llm_gateway_api.openai_compatible_ingress import attach_openai_compatible_route
from openai import OpenAI, UnprocessableEntityError
from test_openai_compatible_ingress import CREDENTIAL, RecordingCoordinator


class _LoopbackGateway:
    """Serve the ingress on an ephemeral loopback port for the duration of a test class."""

    def __init__(self) -> None:
        app = FastAPI()
        attach_openai_compatible_route(app, RecordingCoordinator())  # type: ignore[arg-type]
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def __enter__(self) -> str:
        self._thread.start()
        deadline = threading.Event()
        while not self._server.started:
            if deadline.wait(0.05):  # pragma: no cover - defensive
                break
            if not self._thread.is_alive():  # pragma: no cover - defensive
                raise RuntimeError("loopback gateway failed to start")
        port = self._server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/v1"

    def __exit__(self, *exc_info: object) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


class OpenAISdkCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._gateway = _LoopbackGateway()
        base_url = self._gateway.__enter__()
        self.addCleanup(self._gateway.__exit__)
        self.client = OpenAI(base_url=base_url, api_key=CREDENTIAL, max_retries=0)

    def test_the_sdk_parses_a_non_streaming_completion(self) -> None:
        completion = self.client.chat.completions.create(
            model="rag.answer",
            messages=[{"role": "user", "content": "explain deterministic routing"}],
        )

        self.assertEqual(completion.object, "chat.completion")
        self.assertEqual(completion.model, "rag.answer")
        self.assertEqual(completion.choices[0].message.content, "deterministic routing")
        self.assertEqual(completion.choices[0].message.role, "assistant")
        self.assertEqual(completion.choices[0].finish_reason, "stop")
        self.assertIsNotNone(completion.usage)
        assert completion.usage is not None
        self.assertEqual(completion.usage.total_tokens, 14)

    def test_the_sdk_assembles_a_streamed_completion(self) -> None:
        assembled: list[str] = []
        finish_reason: str | None = None

        for chunk in self.client.chat.completions.create(
            model="rag.answer",
            messages=[{"role": "user", "content": "explain deterministic routing"}],
            stream=True,
        ):
            if chunk.choices and chunk.choices[0].delta.content:
                assembled.append(chunk.choices[0].delta.content)
            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        self.assertEqual("".join(assembled), "deterministic routing")
        self.assertEqual(finish_reason, "stop")

    def test_the_sdk_surfaces_a_rejected_sampling_control(self) -> None:
        """A caller must learn that the gateway owns sampling, not silently lose the setting."""
        with self.assertRaises(UnprocessableEntityError):
            self.client.chat.completions.create(
                model="rag.answer",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.7,
            )


if __name__ == "__main__":
    unittest.main()
