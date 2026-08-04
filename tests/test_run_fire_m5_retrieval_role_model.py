from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from fire_m5_retrieval_roles import build_silver_role_evidence
from run_fire_m5_retrieval_ab import build_view_sources, load_experiment_sources
from run_fire_m5_retrieval_role_model import run_experiment
from treeguard.ai_review import BailianConfig


FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow"


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


class FireM5RetrievalRoleModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        formal, oracle, tree, branches = load_experiment_sources(FIXTURE_DIR)
        cls.outputs_by_requirement = {}
        for scenario in formal:
            request, _, _ = build_view_sources(
                scenario,
                oracle[scenario["scenario_ref"]],
                tree,
                branches,
                "V_REQUIREMENT_ONLY",
            )
            cls.outputs_by_requirement[request.requirement_text] = (
                build_silver_role_evidence(scenario, request).to_model_dict()
            )
        cls.first_requirement = formal[0]["request"]["requirement_text"]

        def transport(body: dict[str, Any]) -> Any:
            user_payload = json.loads(body["messages"][1]["content"])
            requirement = user_payload["requirement_text"]
            if (
                requirement == cls.first_requirement
                and "previous_validation_error" not in user_payload
            ):
                return _response(
                    {
                        "schema_version": "retrieval-role-model-output.v1",
                        "spans": [],
                    }
                )
            return _response(cls.outputs_by_requirement[requirement])

        cls.report = run_experiment(
            FIXTURE_DIR,
            BailianConfig(api_key="fictional-key", max_attempts=2),
            transport=transport,
        )

    def test_one_contract_retry_then_full_extraction_passes(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["failure_codes"], [])
        self.assertEqual(self.report["actual_call_count"], 19)
        self.assertEqual(self.report["first_pass_count"], 17)
        self.assertEqual(self.report["retry_success_count"], 1)
        self.assertEqual(self.report["contract_success_count"], 18)
        self.assertEqual(self.report["run_failed_count"], 0)
        self.assertEqual(self.report["transport_failure_count"], 0)
        self.assertEqual(
            self.report["validation_error_code_counts"],
            {"ROLE_MODEL_SPANS_INVALID": 1},
        )

    def test_silver_agreement_and_frozen_r1_downstream_are_exact(self) -> None:
        self.assertEqual(
            self.report["silver_agreement"],
            {
                "exact_case_count": 18,
                "model_span_count": 29,
                "silver_span_count": 29,
                "matching_span_count": 29,
                "precision_scaled_1e6": 1_000_000,
                "recall_scaled_1e6": 1_000_000,
                "missing_target_case_count": 0,
                "missing_role_counts": {},
                "extra_role_counts": {},
                "case_difference_counts": {"EXACT": 18},
                "difference_kind_counts": {},
            },
        )
        self.assertEqual(self.report["downstream_status"], "COMPLETED")
        for view, result in self.report["views"].items():
            with self.subTest(view=view):
                self.assertEqual(result["recall_at_8"], 16)
                self.assertEqual(result["mrr_scaled_1e6"], 1_000_000)
                self.assertEqual(result["empty_status_match_count"], 2)
                self.assertEqual(result["replay_match_count"], 18)

    def test_report_is_non_qualifying_and_aggregate_only(self) -> None:
        self.assertTrue(self.report["calibration_only"])
        self.assertFalse(self.report["production_qualification"])
        self.assertFalse(self.report["gold_eligible"])
        self.assertEqual(self.report["possible_request_body_count"], 180)
        encoded = repr(self.report)
        for forbidden in (
            "scenario_ref",
            "node_id",
            "requirement_text",
            "acceptable_node_ids",
            "source_request_hash",
            "evidence_hash",
            self.first_requirement,
        ):
            self.assertNotIn(forbidden, encoded)


class FireM5BoundaryTolerantRoleModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        formal, oracle, tree, branches = load_experiment_sources(FIXTURE_DIR)
        outputs_by_requirement = {}
        for scenario in formal:
            request, _, _ = build_view_sources(
                scenario,
                oracle[scenario["scenario_ref"]],
                tree,
                branches,
                "V_REQUIREMENT_ONLY",
            )
            payload = build_silver_role_evidence(scenario, request).to_model_dict()
            if scenario["scenario_ref"] == "M5S012":
                payload["spans"][1]["text"] = "现有责任边界合同"
            elif scenario["scenario_ref"] == "M5S013":
                payload["spans"][1]["text"] = "现有启停规则合同"
            outputs_by_requirement[request.requirement_text] = payload

        def transport(body: dict[str, Any]) -> Any:
            user_payload = json.loads(body["messages"][1]["content"])
            return _response(outputs_by_requirement[user_payload["requirement_text"]])

        cls.report = run_experiment(
            FIXTURE_DIR,
            BailianConfig(api_key="fictional-key", max_attempts=2),
            transport=transport,
            downstream_algorithm="R2",
        )

    def test_r2_tolerates_two_source_bound_target_superspans(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["downstream_algorithm"], "R2")
        self.assertEqual(
            self.report["silver_agreement"]["difference_kind_counts"],
            {"MODEL_SUPERSPAN": 2},
        )
        for result in self.report["views"].values():
            self.assertEqual(result["recall_at_8"], 16)
            self.assertGreaterEqual(result["mrr_scaled_1e6"], 900_000)
            self.assertEqual(result["empty_status_match_count"], 2)


if __name__ == "__main__":
    unittest.main()
