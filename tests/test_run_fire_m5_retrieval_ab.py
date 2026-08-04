from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_fire_m5_retrieval_ab import (
    run_ab,
    run_b2,
    run_b3,
    run_role_boundary_upper_bound,
    run_role_upper_bound,
)


FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow"


class FireM5RetrievalABTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_ab(FIXTURE_DIR)

    def test_b1_result_is_frozen_as_failed_calibration(self) -> None:
        self.assertEqual(self.report["status"], "FAIL")
        self.assertTrue(self.report["calibration_only"])
        self.assertFalse(self.report["production_qualification"])
        self.assertFalse(self.report["llm_called"])
        self.assertEqual(
            self.report["failure_codes"],
            [
                "RETRIEVAL_AB_CANONICAL_REGRESSION",
                "RETRIEVAL_AB_EMPTY_STATUS_REGRESSION",
                "RETRIEVAL_AB_PRIMARY_MRR_BELOW_MINIMUM",
                "RETRIEVAL_AB_PRIMARY_RECALL_BELOW_MINIMUM",
            ],
        )

    def test_decoupled_query_recovers_top_20_but_not_the_frozen_gate(self) -> None:
        dropped = self.report["views"]["V_FREE_TEXT_DROPPED"]
        self.assertEqual(dropped["A"]["recall_at_20"], 6)
        self.assertEqual(dropped["B"]["recall_at_20"], 16)
        self.assertEqual(dropped["B"]["recall_at_8"], 15)
        self.assertEqual(dropped["B"]["empty_status_match_count"], 0)

    def test_all_b_views_are_deterministic(self) -> None:
        for view, results in self.report["views"].items():
            with self.subTest(view=view):
                self.assertEqual(results["B"]["replay_match_count"], 18)

    def test_aggregate_report_excludes_hidden_and_text_fields(self) -> None:
        encoded = repr(self.report)
        for forbidden in (
            "scenario_ref",
            "node_id",
            "requirement_text",
            "acceptable_node_ids",
            "oracle_digest",
            "snapshot_hash",
        ):
            self.assertNotIn(forbidden, encoded)


class FireM5RetrievalB2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_b2(FIXTURE_DIR)

    def test_b2_result_is_frozen_as_failed_calibration(self) -> None:
        self.assertEqual(self.report["status"], "FAIL")
        self.assertTrue(self.report["calibration_only"])
        self.assertFalse(self.report["production_qualification"])
        self.assertFalse(self.report["llm_called"])
        self.assertEqual(
            self.report["failure_codes"],
            [
                "RETRIEVAL_B2_CANONICAL_REGRESSION",
                "RETRIEVAL_B2_PRIMARY_MRR_BELOW_MINIMUM",
                "RETRIEVAL_B2_PRIMARY_RECALL_BELOW_MINIMUM",
            ],
        )

    def test_b2_improves_empty_handling_but_misses_one_top_8_target(self) -> None:
        for view, results in self.report["views"].items():
            with self.subTest(view=view):
                b2 = results["B2"]
                self.assertEqual(b2["recall_at_8"], 15)
                self.assertEqual(b2["recall_at_20"], 16)
                self.assertEqual(b2["mrr_scaled_1e6"], 880_208)
                self.assertEqual(b2["empty_status_match_count"], 2)
                self.assertEqual(b2["replay_match_count"], 18)

    def test_b2_aggregate_report_excludes_hidden_and_text_fields(self) -> None:
        encoded = repr(self.report)
        for forbidden in (
            "scenario_ref",
            "node_id",
            "requirement_text",
            "acceptable_node_ids",
            "oracle_digest",
            "snapshot_hash",
        ):
            self.assertNotIn(forbidden, encoded)


class FireM5RetrievalB3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_b3(FIXTURE_DIR)

    def test_b3_result_is_frozen_as_failed_calibration(self) -> None:
        self.assertEqual(self.report["status"], "FAIL")
        self.assertEqual(
            self.report["failure_codes"],
            ["RETRIEVAL_B3_PRIMARY_MRR_BELOW_MINIMUM"],
        )
        self.assertTrue(self.report["calibration_only"])
        self.assertFalse(self.report["production_qualification"])
        self.assertFalse(self.report["llm_called"])

    def test_b3_recovers_all_top_8_targets_and_empty_statuses(self) -> None:
        for view, results in self.report["views"].items():
            with self.subTest(view=view):
                b3 = results["B3"]
                self.assertEqual(b3["recall_at_8"], 16)
                self.assertEqual(b3["recall_at_20"], 16)
                self.assertEqual(b3["mrr_scaled_1e6"], 843_750)
                self.assertEqual(b3["empty_status_match_count"], 2)
                self.assertEqual(b3["replay_match_count"], 18)

    def test_b3_aggregate_report_excludes_hidden_and_text_fields(self) -> None:
        encoded = repr(self.report)
        for forbidden in (
            "scenario_ref",
            "node_id",
            "requirement_text",
            "acceptable_node_ids",
            "oracle_digest",
            "snapshot_hash",
        ):
            self.assertNotIn(forbidden, encoded)


class FireM5RetrievalRoleUpperBoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_role_upper_bound(FIXTURE_DIR)

    def test_r1_result_is_frozen_as_passed_calibration_upper_bound(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["failure_codes"], [])
        self.assertTrue(self.report["calibration_only"])
        self.assertFalse(self.report["production_qualification"])
        self.assertFalse(self.report["llm_called"])

    def test_r1_meets_every_frozen_view_gate(self) -> None:
        for view, results in self.report["views"].items():
            with self.subTest(view=view):
                r1 = results["R1"]
                self.assertEqual(r1["recall_at_8"], 16)
                self.assertEqual(r1["recall_at_20"], 16)
                self.assertEqual(r1["mrr_scaled_1e6"], 1_000_000)
                self.assertEqual(r1["empty_status_match_count"], 2)
                self.assertEqual(r1["replay_match_count"], 18)

    def test_r1_report_preserves_role_and_oracle_boundaries(self) -> None:
        self.assertEqual(
            self.report["role_annotations"]["role_counts"],
            {"TARGET": 21, "SCOPE": 5, "EXCLUSION": 3},
        )
        encoded = repr(self.report)
        for forbidden in (
            "scenario_ref",
            "node_id",
            "requirement_text",
            "acceptable_node_ids",
            "oracle_digest",
            "snapshot_hash",
            "evidence_hash",
        ):
            self.assertNotIn(forbidden, encoded)


class FireM5RetrievalRoleR2UpperBoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_role_boundary_upper_bound(FIXTURE_DIR)

    def test_r2_silver_regression_meets_the_frozen_gate(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["failure_codes"], [])
        self.assertTrue(self.report["calibration_only"])
        self.assertFalse(self.report["production_qualification"])
        self.assertFalse(self.report["llm_called"])

    def test_r2_preserves_all_views_and_empty_results(self) -> None:
        for view, results in self.report["views"].items():
            with self.subTest(view=view):
                r2 = results["R2"]
                self.assertEqual(r2["recall_at_8"], 16)
                self.assertGreaterEqual(r2["mrr_scaled_1e6"], 900_000)
                self.assertEqual(r2["empty_status_match_count"], 2)
                self.assertEqual(r2["replay_match_count"], 18)

    def test_r2_report_remains_aggregate_only(self) -> None:
        encoded = repr(self.report)
        for forbidden in (
            "scenario_ref",
            "node_id",
            "requirement_text",
            "acceptable_node_ids",
            "evidence_hash",
            "snapshot_hash",
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
