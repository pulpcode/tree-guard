from __future__ import annotations

import copy
import unittest

from scripts.prepare_fire_m49_semantic_plan import (
    M49SemanticPlanError,
    PLAN_SCHEMA_VERSION,
    validate_plan,
)
from treeguard.hashing import canonical_digest
from treeguard.scenario_capability_validation import intent_matches_oracle


class FireM49SemanticPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "purpose": "M49_SEALED_SILVER_SEMANTIC_ONLY",
            "dataset_ref": "fictional-fire-m49-sealed-v1",
            "source_class": "CLEANROOM_SYNTHETIC",
            "fictional": True,
            "derived_from_real": False,
            "quality_tier": "CODEX_ASSISTED_SILVER",
            "evaluation_role": "CALIBRATION_ONLY",
            "gold_eligible": False,
            "gate_eligible": False,
            "patch_eligible": False,
            "execution_authorized": False,
            "contains_oracle": False,
            "contains_credentials": False,
            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "model": "qwen3.6-35b-a3b",
            "prompt_version": "treeguard.semantic-recommendation.zh.v4",
            "timeout_seconds": 90.0,
            "max_contract_attempts": 2,
            "max_transport_retries": 1,
            "source_intent_plan_sha256": "0" * 64,
            "source_intent_results_sha256": "1" * 64,
            "intent_observation_count": 72,
            "intent_route_match_count": 0,
            "intent_full_match_count": 0,
            "semantic_observation_count": 0,
            "initial_request_count": 0,
            "maximum_actual_request_count": 0,
            "possible_request_body_count": 0,
            "retry_policy": "TWO_CONTRACT_ATTEMPTS_AND_ONE_CONNECTION_RECOVERY",
            "units": [],
            "next_gate": "EXPLICIT_SEMANTIC_EXECUTION_APPROVAL",
        }
        self.plan["plan_digest"] = canonical_digest(self.plan)

    def test_empty_semantic_plan_is_valid_non_executable_accounting(self) -> None:
        report = validate_plan(self.plan)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(0, report["semantic_observation_count"])
        self.assertFalse(report["execution_authorized"])

    def test_rehashed_accounting_tamper_is_rejected(self) -> None:
        tampered = copy.deepcopy(self.plan)
        tampered["maximum_actual_request_count"] = 3
        tampered["plan_digest"] = canonical_digest(
            {key: value for key, value in tampered.items() if key != "plan_digest"}
        )
        with self.assertRaisesRegex(
            M49SemanticPlanError, "M49_SEMANTIC_PLAN_POLICY_INVALID"
        ):
            validate_plan(tampered)

    def test_oracle_marker_is_rejected_even_after_rehash(self) -> None:
        tampered = copy.deepcopy(self.plan)
        tampered["target_node_id"] = "fictional-target"
        tampered["plan_digest"] = canonical_digest(
            {key: value for key, value in tampered.items() if key != "plan_digest"}
        )
        with self.assertRaisesRegex(
            M49SemanticPlanError, "M49_SEMANTIC_ORACLE_LEAK"
        ):
            validate_plan(tampered)

    def test_intent_evaluator_rejects_untrusted_types(self) -> None:
        with self.assertRaises(TypeError):
            intent_matches_oracle(None, None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
