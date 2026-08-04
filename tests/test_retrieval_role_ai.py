from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from treeguard import load_tree_export
from treeguard.ai_review import (
    BailianConfig,
    BailianProviderError,
    BailianRetrievalRoleProvider,
    build_retrieval_role_request_body,
)
from treeguard.change_intent import IntentRequest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests/fixtures/fictional/tree_export.json"


def _request() -> IntentRequest:
    imported = load_tree_export(FIXTURE_PATH)
    assert imported.tree is not None
    return IntentRequest.from_dict(
        {
            "schema_version": "intent-request.v1",
            "requirement_text": "在 CATALOG 范围复用 Height，排除 Display title。",
            "proposed_parent_node_id": "node-003",
            "node_kind_hint": "PROPERTY",
            "value_type_hint": "float",
            "cardinality_hint": "SINGLE",
        },
        imported.tree,
    )


def _response(payload: Any) -> dict[str, Any]:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            }
        ]
    }


class RecordingRoleProvider(BailianRetrievalRoleProvider):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        super().__init__(
            BailianConfig(api_key="fictional-key", max_attempts=2)
        )
        self.responses = responses
        self.bodies: list[dict[str, Any]] = []

    def _post_json(self, body: dict[str, Any]) -> Any:
        self.bodies.append(body)
        return self.responses.pop(0)


class RetrievalRoleProviderTests(unittest.TestCase):
    def test_provider_sends_requirement_only_and_returns_model_evidence(self) -> None:
        provider = RecordingRoleProvider(
            [
                _response(
                    {
                        "schema_version": "retrieval-role-model-output.v1",
                        "spans": [
                            {"role": "SCOPE", "text": "CATALOG"},
                            {"role": "TARGET", "text": "Height"},
                            {"role": "EXCLUSION", "text": "Display title"},
                        ],
                    }
                )
            ]
        )

        evidence = provider.extract_roles(_request())

        self.assertEqual(len(provider.bodies), 1)
        body = provider.bodies[0]
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertFalse(body["enable_thinking"])
        self.assertIn("最小完整名词短语", body["messages"][0]["content"])
        self.assertNotIn("警戒组织", body["messages"][0]["content"])
        user_payload = json.loads(body["messages"][1]["content"])
        self.assertEqual(
            set(user_payload),
            {"allowed_roles", "output_contract", "requirement_text"},
        )
        self.assertNotIn("node-003", repr(body))
        self.assertEqual(evidence.provenance, "UNVERIFIED_MODEL_CALIBRATION")

    def test_contract_failure_retries_with_code_without_rejected_output(self) -> None:
        provider = RecordingRoleProvider(
            [
                _response(
                    {
                        "schema_version": "retrieval-role-model-output.v1",
                        "spans": [{"role": "SCOPE", "text": "CATALOG"}],
                    }
                ),
                _response(
                    {
                        "schema_version": "retrieval-role-model-output.v1",
                        "spans": [{"role": "TARGET", "text": "Height"}],
                    }
                ),
            ]
        )

        evidence = provider.extract_roles(_request())

        self.assertEqual(len(provider.bodies), 2)
        retry_payload = json.loads(provider.bodies[1]["messages"][1]["content"])
        self.assertEqual(
            retry_payload["previous_validation_error"],
            "ROLE_MODEL_TARGET_MISSING",
        )
        self.assertNotIn('"role": "SCOPE"', provider.bodies[1]["messages"][0]["content"])
        self.assertEqual(evidence.spans[0].text, "Height")

    def test_two_invalid_outputs_fail_with_the_last_stable_code(self) -> None:
        provider = RecordingRoleProvider(
            [
                _response({"schema_version": "retrieval-role-model-output.v1", "spans": []}),
                _response({"schema_version": "retrieval-role-model-output.v1", "spans": []}),
            ]
        )

        with self.assertRaises(BailianProviderError) as context:
            provider.extract_roles(_request())

        self.assertEqual(context.exception.code, "ROLE_MODEL_SPANS_INVALID")

    def test_request_builder_rejects_an_unregistered_retry_code(self) -> None:
        with self.assertRaises(BailianProviderError) as context:
            build_retrieval_role_request_body(
                _request(),
                "qwen3.6-35b-a3b",
                retry_code="ROLE_MODEL_UNKNOWN",
            )
        self.assertEqual(context.exception.code, "ROLE_MODEL_RETRY_CODE_INVALID")


if __name__ == "__main__":
    unittest.main()
