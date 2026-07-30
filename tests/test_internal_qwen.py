import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from treeguard.ai_review import (
    BailianProviderError,
    INTERNAL_QWEN_PROVIDER_NAME,
    InternalQwenConfig,
    InternalQwenIntentDraftProvider,
    InternalQwenSemanticRecommendationProvider,
)
from treeguard.workbench_governance import DefaultProviderFactory
from treeguard.expert_synthesis import InternalQwenExpertSynthesisProvider


class _MemoryResponse:
    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class _CapturingOpener:
    def __init__(self) -> None:
        self.request = None
        self.timeout = None

    def open(self, request, timeout: float):
        self.request = request
        self.timeout = timeout
        return _MemoryResponse(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "{}"},
                    }
                ]
            }
        )


class _FailingOpener:
    def open(self, request, timeout: float):
        raise urllib.error.URLError("fictional connection failure")


class InternalQwenProviderTests(unittest.TestCase):
    def test_request_uses_nested_thinking_switch_without_authorization(
        self,
    ) -> None:
        provider = InternalQwenIntentDraftProvider(
            InternalQwenConfig(
                base_url="http://10.20.30.40:8000/v1",
                model="qwen3.6",
            )
        )
        opener = _CapturingOpener()
        provider._opener = opener
        body = provider._intent_request_body(
            {
                "requirement_text": "完全虚构的测试需求",
                "hints": {
                    "node_kind": "UNKNOWN",
                    "value_type": None,
                    "cardinality": "UNKNOWN",
                },
                "proposed_parent": None,
            },
            retry_code=None,
        )

        provider._post_json(body)

        self.assertNotIn("enable_thinking", body)
        self.assertEqual(
            body["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertFalse(body["stream"])
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(
            opener.request.full_url,
            "http://10.20.30.40:8000/v1/chat/completions",
        )
        headers = dict(opener.request.header_items())
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["Content-type"], "application/json")
        sent = json.loads(opener.request.data)
        self.assertEqual(sent["model"], "qwen3.6")
        self.assertEqual(
            sent["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertEqual(provider.provider_name, INTERNAL_QWEN_PROVIDER_NAME)

    def test_semantic_provider_uses_same_qwen_transport_contract(self) -> None:
        provider = InternalQwenSemanticRecommendationProvider(
            InternalQwenConfig(
                base_url="https://model.internal/v1",
                max_attempts=1,
            )
        )

        self.assertEqual(
            provider._completion_options(),
            {
                "response_format": {"type": "json_object"},
                "chat_template_kwargs": {"enable_thinking": False},
                "temperature": 0,
                "stream": False,
            },
        )
        self.assertEqual(
            provider._request_headers(),
            {"Content-Type": "application/json"},
        )

    def test_transport_failure_uses_qwen_error_family(self) -> None:
        provider = InternalQwenIntentDraftProvider(
            InternalQwenConfig(
                base_url="http://10.20.30.40:8000/v1",
                max_attempts=1,
            )
        )
        provider._opener = _FailingOpener()

        with self.assertRaises(BailianProviderError) as caught:
            provider._post_json(
                {
                    "model": "qwen3.6",
                    "messages": [],
                    **provider._completion_options(),
                }
            )

        self.assertEqual(caught.exception.code, "QWEN_CONNECTION_FAILED")

    def test_expert_synthesis_stays_inside_qwen_trust_boundary(self) -> None:
        provider = InternalQwenExpertSynthesisProvider(
            InternalQwenConfig(
                base_url="http://10.20.30.40:8000/v1",
                max_attempts=1,
            )
        )
        body = provider._request_body(
            {"fictional_expert_thought": "完全虚构"},
            retry=False,
        )

        provider._validate_transport_approval("unused", None)
        self.assertNotIn("enable_thinking", body)
        self.assertEqual(
            body["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertEqual(
            provider._request_headers(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(provider.provider_name, INTERNAL_QWEN_PROVIDER_NAME)

    def test_config_loads_private_dotenv_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            env_path = directory / ".env"
            env_path.write_text(
                "\n".join(
                    (
                        "TREEGUARD_QWEN_BASE_URL=http://10.20.30.40:8000/v1",
                        "TREEGUARD_QWEN_MODEL=qwen3.6",
                    )
                ),
                encoding="utf-8",
            )
            env_path.chmod(0o600)
            previous_directory = Path.cwd()
            os.chdir(directory)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    config = InternalQwenConfig.from_env()
            finally:
                os.chdir(previous_directory)

        self.assertEqual(
            config.base_url,
            "http://10.20.30.40:8000/v1",
        )
        self.assertEqual(config.model, "qwen3.6")
        self.assertFalse(hasattr(config, "api_key"))

    def test_process_environment_wins_over_dotenv(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TREEGUARD_QWEN_BASE_URL": (
                    "http://10.20.30.41:9000/v1"
                ),
                "TREEGUARD_QWEN_MODEL": "qwen3.6-fp8",
            },
            clear=True,
        ):
            config = InternalQwenConfig.from_env()

        self.assertEqual(
            config.base_url,
            "http://10.20.30.41:9000/v1",
        )
        self.assertEqual(config.model, "qwen3.6-fp8")

    def test_config_rejects_public_or_key_bearing_endpoint(self) -> None:
        for base_url in (
            "https://example.com/v1",
            "http://10.20.30.40/v1",
            "http://user:secret@10.20.30.40:8000/v1",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaises(BailianProviderError) as caught:
                    InternalQwenConfig(base_url=base_url)
                self.assertEqual(
                    caught.exception.code,
                    "QWEN_BASE_URL_INVALID",
                )

    def test_missing_configuration_does_not_fall_back_to_bailian(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            previous_directory = Path.cwd()
            os.chdir(directory_name)
            try:
                with (
                    patch.dict(os.environ, {}, clear=True),
                    self.assertRaises(BailianProviderError) as caught,
                ):
                    InternalQwenConfig.from_env()
            finally:
                os.chdir(previous_directory)

        self.assertEqual(caught.exception.code, "QWEN_BASE_URL_MISSING")

    def test_default_factory_selects_qwen_explicitly(self) -> None:
        config = InternalQwenConfig(
            base_url="http://10.20.30.40:8000/v1"
        )
        factory = DefaultProviderFactory(
            simulator_base_url="http://127.0.0.1:8765/v1"
        )

        with patch.object(
            InternalQwenConfig,
            "from_env",
            return_value=config,
        ):
            intent = factory.intent_provider("QWEN_LIVE")
            semantic = factory.semantic_provider("QWEN_LIVE")

        self.assertIsInstance(intent, InternalQwenIntentDraftProvider)
        self.assertIsInstance(
            semantic,
            InternalQwenSemanticRecommendationProvider,
        )


if __name__ == "__main__":
    unittest.main()
