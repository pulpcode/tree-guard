from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard.adapter import adapt_tree_document, load_tree_export
from treeguard.ai_review import (
    INTENT_CLARIFICATION_PROMPT_VERSION,
    INTENT_PROMPT_VERSION,
    SEMANTIC_PROMPT_VERSION,
)
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentClarificationAnswer,
    IntentClarificationRound,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.fictional_fire_data import (
    DATASET_ID,
    TIER_SPECS,
    build_fictional_fire_manifest,
    build_fictional_fire_scenarios,
    build_fictional_fire_tree,
    write_fictional_fire_dataset,
)
from treeguard.retrieval import build_candidate_set
from treeguard.semantic_recommendation import (
    RecommendationReviewAction,
    SemanticRecommendationDraft,
    SemanticRecommendationError,
    apply_recommendation_review,
    build_semantic_candidate_projection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = (
    PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "fire_validation"
)


def _draft(payload, request, tree):
    return ChangeIntentDraft.from_model_dict(
        payload,
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fictional-fixture-model",
        prompt_version=INTENT_PROMPT_VERSION,
    )


def _run_scenario(item, tree):
    request = IntentRequest.from_dict(item["request"], tree)
    draft = _draft(item["initial_model_output"], request, tree)
    current = draft
    if item["clarification"] is not None:
        answer = IntentClarificationAnswer.from_dict(
            {
                "schema_version": "intent-clarification-answer.v1",
                "identity_status": "UNVERIFIED_FILE_ASSERTION",
                "expected_draft_hash": draft.draft_hash,
                "answer_text": item["clarification"]["answer_text"],
                "answered_by_ref": "fictional-starbay-reviewer",
                "recorded_at": "2035-01-02T03:04:05Z",
            }
        )
        current = IntentClarificationRound.from_model_dict(
            item["clarification"]["model_output"],
            request,
            draft,
            answer,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_capability="JSON_OBJECT",
            model_name="fictional-fixture-model",
            prompt_version=INTENT_CLARIFICATION_PROMPT_VERSION,
        )
    if item["review_decision"] is None:
        return draft, current, None, None
    action = IntentReviewAction.from_dict(
        {
            "schema_version": "intent-review-action.v1",
            "expected_draft_hash": current.draft_hash,
            "decision": item["review_decision"],
            "reviewer_ref": "fictional-starbay-reviewer",
            "recorded_at": "2035-01-02T03:04:05Z",
            "confirmed_intent": (
                current.intent.to_dict()
                if item["review_decision"] == "CONFIRM_FOR_RETRIEVAL"
                else None
            ),
        }
    )
    confirmation = apply_intent_review(
        request,
        current,
        action,
        tree,
    )
    candidate_set = (
        build_candidate_set(confirmation, tree)
        if confirmation.status == "CONFIRMED_FOR_RETRIEVAL"
        else None
    )
    return draft, current, confirmation, candidate_set


class FictionalFireDatasetTests(unittest.TestCase):
    def test_tiers_are_deterministic_adaptable_and_exactly_sized(self) -> None:
        for tier, spec in TIER_SPECS.items():
            with self.subTest(tier=tier):
                first = build_fictional_fire_tree(tier)
                second = build_fictional_fire_tree(tier)
                self.assertEqual(first, second)

                result = adapt_tree_document(first)
                self.assertTrue(result.is_valid)
                self.assertEqual(result.issues, ())
                self.assertEqual(
                    result.observed_node_count,
                    spec["node_count"],
                )
                self.assertIsNotNone(result.tree)
                self.assertEqual(
                    len({node.node_id for node in result.tree.nodes}),
                    spec["node_count"],
                )

    def test_materialized_files_are_byte_stable_generator_outputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generated = write_fictional_fire_dataset(directory)
            self.assertEqual(len(generated), 7)
            for path in generated:
                materialized = FIXTURE_ROOT / path.name
                self.assertTrue(materialized.is_file(), path.name)
                self.assertEqual(
                    path.read_bytes(),
                    materialized.read_bytes(),
                    path.name,
                )

    def test_manifest_separates_semantic_and_scale_roles(self) -> None:
        manifest = build_fictional_fire_manifest()

        self.assertEqual(manifest["dataset_id"], DATASET_ID)
        self.assertTrue(manifest["fictional"])
        self.assertFalse(manifest["semantic_approval"])
        self.assertFalse(manifest["gold_eligible"])
        self.assertFalse(manifest["patch_eligible"])
        self.assertEqual(
            [item["benchmark_role"] for item in manifest["tiers"]],
            [
                "precision_contract",
                "semantic_interference",
                "scale_stability",
            ],
        )
        self.assertEqual(
            [item["node_count"] for item in manifest["tiers"]],
            [31, 401, 2_001],
        )
        self.assertEqual(
            [item["scenario_count"] for item in manifest["tiers"]],
            [8, 16, 24],
        )

    def test_all_scenarios_execute_against_their_oracles(self) -> None:
        for tier, spec in TIER_SPECS.items():
            tree_result = load_tree_export(
                FIXTURE_ROOT / f"tree-{tier}.json"
            )
            self.assertIsNotNone(tree_result.tree)
            scenarios = json.loads(
                (
                    FIXTURE_ROOT / f"scenarios-{tier}.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                scenarios["scenario_count"],
                spec["scenario_count"],
            )
            self.assertEqual(
                len(scenarios["items"]),
                spec["scenario_count"],
            )

            for item in scenarios["items"]:
                with self.subTest(tier=tier, scenario=item["scenario_ref"]):
                    draft, current, confirmation, candidate_set = (
                        _run_scenario(item, tree_result.tree)
                    )
                    oracle = item["oracle"]
                    self.assertEqual(
                        draft.review_status,
                        oracle["draft_status"],
                    )
                    if item["clarification"] is not None:
                        self.assertEqual(
                            current.review_status,
                            oracle["clarification_status"],
                        )
                    if confirmation is not None:
                        self.assertEqual(
                            confirmation.status,
                            oracle["confirmation_status"],
                        )
                        self.assertFalse(
                            confirmation.to_dict()["semantic_approval"]
                        )
                        self.assertFalse(
                            confirmation.to_dict()["patch_eligible"]
                        )
                    if candidate_set is not None:
                        self.assertEqual(
                            candidate_set.status,
                            oracle["candidate_status"],
                        )
                        self.assertLessEqual(
                            len(candidate_set.candidates),
                            oracle["candidate_limit"],
                        )
                        required = oracle[
                            "required_first_candidate_id"
                        ]
                        if required is not None:
                            self.assertEqual(
                                candidate_set.candidates[0].node_id,
                                required,
                            )
                        if candidate_set.status == "CANDIDATES_READY":
                            projection = (
                                build_semantic_candidate_projection(
                                    confirmation,
                                    candidate_set,
                                    tree_result.tree,
                                )
                            )
                            self.assertLessEqual(
                                len(projection.candidates),
                                oracle["semantic_projection_limit"],
                            )
                            self._assert_semantic_oracle(
                                item,
                                confirmation,
                                candidate_set,
                                tree_result.tree,
                            )

    def _assert_semantic_oracle(
        self,
        item,
        confirmation,
        candidate_set,
        tree,
    ) -> None:
        semantic = item["semantic"]
        oracle = item["oracle"]
        if semantic is None:
            self.assertIsNone(oracle["recommendation_status"])
            self.assertIsNone(oracle["semantic_error_code"])
            return
        if oracle["semantic_error_code"] is not None:
            with self.assertRaises(
                SemanticRecommendationError
            ) as context:
                SemanticRecommendationDraft.from_model_dict(
                    semantic["model_output"],
                    confirmation,
                    candidate_set,
                    tree,
                    model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                    model_capability="JSON_OBJECT",
                    model_name="fictional-fixture-model",
                    prompt_version=SEMANTIC_PROMPT_VERSION,
                )
            self.assertEqual(
                context.exception.code,
                oracle["semantic_error_code"],
            )
            return

        draft = SemanticRecommendationDraft.from_model_dict(
            semantic["model_output"],
            confirmation,
            candidate_set,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_capability="JSON_OBJECT",
            model_name="fictional-fixture-model",
            prompt_version=SEMANTIC_PROMPT_VERSION,
        )
        action = RecommendationReviewAction.from_dict(
            {
                "schema_version": "recommendation-review-action.v1",
                "identity_status": "UNVERIFIED_FILE_ASSERTION",
                "expected_draft_hash": draft.draft_hash,
                "decision": semantic["review_decision"],
                "reviewer_ref": "fictional-starbay-reviewer",
                "recorded_at": "2035-01-02T03:04:05Z",
                "reviewer_reasoning": "完全虚构的星湾复核说明。",
                "revised_recommendation": None,
            },
            confirmation,
            candidate_set,
            tree,
        )
        record = apply_recommendation_review(
            draft,
            action,
            confirmation,
            candidate_set,
            tree,
        )
        self.assertEqual(
            record.status,
            oracle["recommendation_status"],
        )
        self.assertFalse(record.to_dict()["semantic_approval"])
        self.assertFalse(record.to_dict()["gold_eligible"])
        self.assertFalse(record.to_dict()["patch_eligible"])

    def test_large_tier_retrieval_survives_node_reordering(self) -> None:
        result = adapt_tree_document(build_fictional_fire_tree("large"))
        self.assertIsNotNone(result.tree)
        item = build_fictional_fire_scenarios("large")["items"][-1]
        _, _, confirmation, candidate_set = _run_scenario(
            item,
            result.tree,
        )
        self.assertIsNotNone(confirmation)
        self.assertIsNotNone(candidate_set)

        reordered = replace(
            result.tree,
            nodes=tuple(reversed(result.tree.nodes)),
        )
        replayed = build_candidate_set(confirmation, reordered)
        self.assertEqual(
            candidate_set.to_dict(),
            replayed.to_dict(),
        )

    def test_fault_matrix_declares_required_fail_closed_oracles(self) -> None:
        manifest = json.loads(
            (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
        )
        faults = {
            item["fault"]: item
            for item in manifest["model_fault_oracles"]
        }
        self.assertEqual(
            set(faults),
            {
                "invalid-json",
                "extra-field",
                "missing-field",
                "http-429",
                "http-500",
                "timeout",
                "response-too-large",
                "retry-then-valid",
                "trace-canary",
            },
        )
        self.assertEqual(
            faults["retry-then-valid"]["final_status"],
            "SUCCEEDED",
        )
        self.assertEqual(
            faults["trace-canary"]["final_status"],
            "REDACTED",
        )
        expected_codes = {
            "invalid-json": "INTENT_MODEL_RESPONSE_INVALID",
            "extra-field": "INTENT_MODEL_FIELDS_INVALID",
            "missing-field": "INTENT_MODEL_FIELDS_INVALID",
            "http-429": "SIMULATOR_MODEL_HTTP_429",
            "http-500": "SIMULATOR_MODEL_HTTP_500",
            "timeout": "SIMULATOR_MODEL_CONNECTION_FAILED",
            "response-too-large": "SIMULATOR_MODEL_RESPONSE_TOO_LARGE",
            "retry-then-valid": None,
            "trace-canary": None,
        }
        self.assertEqual(
            {
                fault: item["expected_error_code"]
                for fault, item in faults.items()
            },
            expected_codes,
        )
        for item in faults.values():
            self.assertGreaterEqual(item["expected_attempts"], 1)
            self.assertIn("api_key", item["public_view_must_exclude"])
            self.assertIn(
                "stable_node_id",
                item["public_view_must_exclude"],
            )

    def test_files_contain_no_values_real_examples_or_foreign_assets(self) -> None:
        encoded = json.dumps(
            {
                "manifest": build_fictional_fire_manifest(),
                "trees": {
                    tier: build_fictional_fire_tree(tier)
                    for tier in TIER_SPECS
                },
                "scenarios": {
                    tier: build_fictional_fire_scenarios(tier)
                    for tier in TIER_SPECS
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for forbidden in (
            '"value"',
            '"VALUE"',
            "schema-flow",
            "消火栓",
            "灭火器",
            "防火门",
            "疏散通道",
            "微型消防站",
            "/Users/",
            "Authorization:",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

        for tier in TIER_SPECS:
            result = load_tree_export(
                FIXTURE_ROOT / f"tree-{tier}.json"
            )
            self.assertTrue(result.is_valid)


if __name__ == "__main__":
    unittest.main()
