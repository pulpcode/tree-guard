from __future__ import annotations

import json
import unittest

from treeguard.ai_review import (
    BailianConfig,
    BailianProviderError,
    BailianTreeUnderstandingProvider,
    InternalQwenConfig,
    InternalQwenTreeUnderstandingProvider,
    TREE_UNDERSTANDING_PROMPT_VERSION,
)
from treeguard.tree_understanding import (
    build_tree_diagnostic_profile,
    build_tree_understanding_projection,
)
from tests.test_tree_understanding import (
    _fictional_tree,
    _valid_model_output,
)


class TreeUnderstandingProviderTests(unittest.TestCase):
    def _provider(self, *, max_attempts: int = 2):
        return InternalQwenTreeUnderstandingProvider(
            InternalQwenConfig(
                base_url="http://10.20.30.40:8000/v1",
                model="fictional-qwen",
                max_attempts=max_attempts,
            )
        )

    def test_internal_qwen_returns_locally_validated_pending_draft(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        provider = self._provider()
        sent: list[dict[str, object]] = []

        def fake_post(body):
            sent.append(body)
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                _valid_model_output(projection),
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            }

        provider._post_json = fake_post  # type: ignore[method-assign]
        draft = provider.analyze(tree, profile)

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["response_format"], {"type": "json_object"})
        self.assertEqual(
            sent[0]["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertEqual(sent[0]["temperature"], 0)
        self.assertEqual(provider._request_headers(), {"Content-Type": "application/json"})
        encoded_request = json.dumps(sent[0], ensure_ascii=False, sort_keys=True)
        self.assertNotIn("lattice-root", encoded_request)
        self.assertNotIn("alpha-signal", encoded_request)
        self.assertNotIn(tree.snapshot_hash, encoded_request)
        self.assertNotIn(profile.profile_hash, encoded_request)
        self.assertEqual(draft.review_status, "PENDING_HUMAN_REVIEW")
        self.assertFalse(draft.semantic_approval)
        self.assertFalse(draft.gold_eligible)
        self.assertFalse(draft.patch_eligible)

    def test_invalid_output_retries_once_then_fails_closed(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        provider = self._provider(max_attempts=2)
        attempts = 0

        def fake_post(body):
            nonlocal attempts
            attempts += 1
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "schema_version": "wrong",
                                }
                            )
                        },
                    }
                ]
            }

        provider._post_json = fake_post  # type: ignore[method-assign]

        with self.assertRaises(BailianProviderError) as captured:
            provider.analyze(tree, profile)

        self.assertEqual(attempts, 2)
        self.assertEqual(
            captured.exception.code,
            "TREE_UNDERSTANDING_MODEL_FIELDS_INVALID",
        )

    def test_second_complete_output_replaces_invalid_first_attempt(
        self,
    ) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        provider = self._provider(max_attempts=2)
        attempts = 0

        def fake_post(body):
            nonlocal attempts
            attempts += 1
            output = _valid_model_output(projection)
            if attempts == 1:
                output.pop("generation_status")
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                output,
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            }

        provider._post_json = fake_post  # type: ignore[method-assign]
        draft = provider.analyze(tree, profile)

        self.assertEqual(attempts, 2)
        self.assertEqual(draft.generation_status, "SCENARIOS_PROPOSED")
        self.assertEqual(len(draft.virtual_scenarios), 1)

    def test_bailian_requires_approval_before_network(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        provider = BailianTreeUnderstandingProvider(
            BailianConfig(
                api_key="fictional-token",
                model="fictional-qwen",
            )
        )
        network_called = False

        def fake_post(body):
            nonlocal network_called
            network_called = True
            raise AssertionError("network must not be called without approval")

        provider._post_json = fake_post  # type: ignore[method-assign]

        with self.assertRaises(BailianProviderError) as captured:
            provider.analyze(tree, profile)

        self.assertEqual(
            captured.exception.code,
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertFalse(network_called)

    def test_bailian_approved_fictional_projection_uses_local_contract(
        self,
    ) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        provider = BailianTreeUnderstandingProvider(
            BailianConfig(
                api_key="fictional-token",
                model="fictional-qwen",
            )
        )
        sent: list[dict[str, object]] = []

        def fake_post(body):
            sent.append(body)
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                _valid_model_output(projection),
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            }

        provider._post_json = fake_post  # type: ignore[method-assign]
        draft = provider.analyze(
            tree,
            profile,
            external_data_approved=True,
        )

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["response_format"], {"type": "json_object"})
        self.assertFalse(sent[0]["enable_thinking"])
        self.assertNotIn("chat_template_kwargs", sent[0])
        self.assertEqual(sent[0]["temperature"], 0)
        self.assertEqual(
            TREE_UNDERSTANDING_PROMPT_VERSION,
            "treeguard.tree-understanding.zh.v5",
        )
        system_prompt = sent[0]["messages"][0]["content"]
        self.assertIn("引用数组不得重复", system_prompt)
        self.assertIn("数组顺序不表示优先级", system_prompt)
        self.assertIn("generation_status 不得省略", system_prompt)
        user_payload = json.loads(sent[0]["messages"][1]["content"])
        self.assertEqual(
            user_payload["output_contract"][
                "finding_assessment_required_fields"
            ],
            ["finding_ref", "disposition", "reason"],
        )
        self.assertEqual(
            [
                item["finding_ref"]
                for item in user_payload["exact_object_template"][
                    "finding_assessments"
                ]
            ],
            list(projection.finding_refs),
        )
        self.assertEqual(
            set(
                user_payload["exact_object_template"][
                    "finding_assessments"
                ][0]
            ),
            {"finding_ref", "disposition", "reason"},
        )
        self.assertEqual(
            user_payload["allowed_references"]["supporting_node_refs"],
            list(projection.node_refs),
        )
        self.assertEqual(
            user_payload["allowed_references"]["source_finding_refs"],
            list(projection.finding_refs),
        )
        self.assertTrue(
            user_payload["output_contract"][
                "reference_arrays_must_be_unique_and_allowlisted"
            ]
        )
        self.assertFalse(
            user_payload["output_contract"][
                "reference_array_order_is_semantic"
            ]
        )
        self.assertTrue(
            user_payload["output_contract"][
                "reference_arrays_are_canonicalized_locally"
            ]
        )
        self.assertTrue(
            user_payload["output_contract"][
                "generation_status_must_be_present"
            ]
        )
        self.assertEqual(
            provider._request_headers(),
            {
                "Authorization": "Bearer fictional-token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(draft.model_provider, "BAILIAN_OPENAI_COMPATIBLE")
        self.assertEqual(draft.review_status, "PENDING_HUMAN_REVIEW")
        self.assertFalse(draft.semantic_approval)
        self.assertFalse(draft.gold_eligible)
        self.assertFalse(draft.patch_eligible)

    def test_internal_qwen_rejects_bailian_configuration(self) -> None:
        with self.assertRaises(BailianProviderError) as captured:
            InternalQwenTreeUnderstandingProvider(  # type: ignore[arg-type]
                BailianConfig(api_key="fictional-token")
            )

        self.assertEqual(captured.exception.code, "QWEN_CONFIG_INVALID")

        with self.assertRaises(BailianProviderError) as captured:
            BailianTreeUnderstandingProvider(  # type: ignore[arg-type]
                InternalQwenConfig(
                    base_url="http://10.20.30.40:8000/v1",
                    model="fictional-qwen",
                )
            )

        self.assertEqual(captured.exception.code, "BAILIAN_CONFIG_INVALID")


if __name__ == "__main__":
    unittest.main()
