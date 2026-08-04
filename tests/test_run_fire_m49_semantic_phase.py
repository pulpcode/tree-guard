from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_fire_m49_semantic_phase import (
    M49SemanticRunError,
    PlannedSemanticProvider,
    read_approved_semantic_plan,
    run_live,
    validate_result,
)
from treeguard.ai_review import (
    DEFAULT_MODEL,
    BailianAIReviewProvider,
    BailianConfig,
)


class FireM49SemanticRunTests(unittest.TestCase):
    def test_execution_flag_is_required_before_plan_or_environment_read(self) -> None:
        with patch(
            "scripts.run_fire_m49_semantic_phase.read_approved_semantic_plan",
            side_effect=AssertionError("plan must not be read"),
        ):
            with self.assertRaisesRegex(
                M49SemanticRunError, "M49_SEMANTIC_EXECUTION_NOT_APPROVED"
            ):
                run_live(
                    semantic_plan_file=Path("not-read"),
                    approved_semantic_plan_sha256="0" * 64,
                    intent_plan_file=Path("not-read"),
                    intent_plan_sha256="1" * 64,
                    intent_results_file=Path("not-read"),
                    intent_results_sha256="2" * 64,
                    private_output=Path("not-written"),
                    execution_approved=False,
                )

    def test_wrong_plan_hash_fails_before_replay(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-semantic-plan-") as temp:
            path = Path(temp) / "plan.json"
            path.write_text("{}\n", encoding="utf-8")
            path.chmod(0o600)
            with patch(
                "scripts.run_fire_m49_semantic_phase.build_plan",
                side_effect=AssertionError("replay must not start"),
            ):
                with self.assertRaisesRegex(
                    M49SemanticRunError, "M49_SEMANTIC_PLAN_INVALID"
                ):
                    read_approved_semantic_plan(
                        path,
                        "0" * 64,
                        intent_plan_file=Path("not-read"),
                        intent_plan_sha256="1" * 64,
                        intent_results_file=Path("not-read"),
                        intent_results_sha256="2" * 64,
                    )

    def test_provider_rejects_unplanned_body_before_transport(self) -> None:
        provider = PlannedSemanticProvider(
            BailianConfig(api_key="NOT_USED", model=DEFAULT_MODEL), set(), []
        )
        with patch.object(
            BailianAIReviewProvider,
            "_post_json",
            side_effect=AssertionError("transport must not run"),
        ):
            with self.assertRaisesRegex(
                M49SemanticRunError, "M49_SEMANTIC_BODY_NOT_PLANNED"
            ):
                provider._post_json({"model": DEFAULT_MODEL, "messages": []})

    def test_same_frozen_body_can_be_accounted_as_transport_recovery(self) -> None:
        body = {"model": DEFAULT_MODEL, "messages": []}
        from scripts.prepare_fire_m49_runtime_plan import wire_bytes
        from hashlib import sha256

        digest = sha256(wire_bytes(body)).hexdigest()
        audit: list[dict[str, object]] = []
        provider = PlannedSemanticProvider(
            BailianConfig(api_key="NOT_USED", model=DEFAULT_MODEL),
            {digest},
            audit,
        )
        with patch.object(BailianAIReviewProvider, "_post_json", return_value={}):
            provider._post_json(body)
            provider._post_json(body)
            provider._post_json(body)
            with self.assertRaisesRegex(
                M49SemanticRunError, "M49_SEMANTIC_UNIT_CALL_LIMIT_EXCEEDED"
            ):
                provider._post_json(body)
        self.assertEqual([1, 2, 3], [item["attempt"] for item in audit])
        self.assertEqual({digest}, {item["wire_sha256"] for item in audit})

    def test_rehashed_unplanned_result_call_is_rejected(self) -> None:
        planned_hash = "a" * 64
        plan = {
            "dataset_ref": "fictional-fire-m49-sealed-v1",
            "source_intent_plan_sha256": "1" * 64,
            "source_intent_results_sha256": "2" * 64,
            "intent_observation_count": 72,
            "intent_full_match_count": 1,
            "semantic_observation_count": 1,
            "maximum_actual_request_count": 3,
            "units": [
                {
                    "observation_ref": "R01:S001",
                    "round_index": 1,
                    "scenario_ref": "S001",
                    "source_intent_draft_hash": "3" * 64,
                    "source_confirmation_hash": "4" * 64,
                    "source_candidate_set_hash": "5" * 64,
                    "possible_requests": [{"wire_sha256": planned_hash}],
                }
            ],
        }
        item = {
            "observation_ref": "R01:S001",
            "round_index": 1,
            "scenario_ref": "S001",
            "source_intent_draft_hash": "3" * 64,
            "source_confirmation_hash": "4" * 64,
            "source_candidate_set_hash": "5" * 64,
            "status": "RUN_FAILED",
            "failure_code": "BAILIAN_CONNECTION_FAILED",
            "calls": [{"attempt": 1, "wire_sha256": planned_hash}],
            "validation_error_codes": ["BAILIAN_CONNECTION_FAILED"],
            "retrieval_status": "MATCH",
            "recommendation_status": "RUN_FAILED",
            "end_to_end_status": "MISMATCH",
            "draft": None,
        }
        payload = {
            "schema_version": "fire-m49-sealed-semantic-results.v1",
            "purpose": "M49_SEALED_SILVER_SEMANTIC_ONLY",
            "dataset_ref": plan["dataset_ref"],
            "source_class": "CLEANROOM_SYNTHETIC",
            "fictional": True,
            "derived_from_real": False,
            "quality_tier": "CODEX_ASSISTED_SILVER",
            "evaluation_role": "CALIBRATION_ONLY",
            "gold_eligible": False,
            "gate_eligible": False,
            "patch_eligible": False,
            "contains_oracle": False,
            "contains_credentials": False,
            "semantic_plan_file_sha256": "0" * 64,
            "source_intent_plan_sha256": "1" * 64,
            "source_intent_results_sha256": "2" * 64,
            "model": DEFAULT_MODEL,
            "prompt_version": "treeguard.semantic-recommendation.zh.v4",
            "intent_observation_count": 72,
            "intent_full_match_count": 1,
            "semantic_observation_count": 1,
            "actual_request_count": 1,
            "single_wire_call_count": 1,
            "multi_wire_call_observation_count": 0,
            "contract_retry_observation_count": 0,
            "transport_retry_call_count": 0,
            "draft_ready_count": 0,
            "run_failed_count": 1,
            "failure_code_counts": {"BAILIAN_CONNECTION_FAILED": 1},
            "validation_error_code_counts": {"BAILIAN_CONNECTION_FAILED": 1},
            "retrieval_match_count": 1,
            "retrieval_mismatch_count": 0,
            "recommendation_match_count": 0,
            "recommendation_mismatch_count": 0,
            "clarification_end_to_end_match_count": 0,
            "end_to_end_match_count": 0,
            "end_to_end_mismatch_count": 72,
            "stable_scenario_count": 0,
            "unstable_scenario_count": 24,
            "results": [item],
            "next_gate": "LOCAL_SILVER_DIAGNOSTIC_REVIEW",
        }
        self.assertEqual(
            "PASS", validate_result(payload, plan, "0" * 64)["status"]
        )
        wrong_plan_binding = copy.deepcopy(payload)
        wrong_plan_binding["semantic_plan_file_sha256"] = "e" * 64
        with self.assertRaisesRegex(
            M49SemanticRunError, "M49_SEMANTIC_RESULT_POLICY_INVALID"
        ):
            validate_result(wrong_plan_binding, plan, "0" * 64)
        tampered = copy.deepcopy(payload)
        tampered["results"][0]["calls"][0]["wire_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            M49SemanticRunError, "M49_SEMANTIC_RESULT_ITEM_INVALID"
        ):
            validate_result(tampered, plan)


if __name__ == "__main__":
    unittest.main()
