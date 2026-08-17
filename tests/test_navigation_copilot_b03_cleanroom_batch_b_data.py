from __future__ import annotations

import unittest

from tests import navigation_copilot_b03_cleanroom_batch_b_builder as builder


class NavigationCopilotB03BatchBCleanroomDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = builder.build_artifacts()
        cls.report = cls.artifacts["preflight_payload"]

    def test_exact_denominators_and_roles(self) -> None:
        self.assertEqual(self.report["node_count"], 927)
        self.assertEqual(
            self.report["role_counts"],
            {
                "blueprint_background": 603,
                "curated_core": 176,
                "stress_only_filler": 148,
            },
        )
        self.assertEqual(self.report["candidate_category_quotas"], builder.CANDIDATE_QUOTAS)
        self.assertEqual(self.report["final_category_quotas"], builder.FINAL_QUOTAS)
        self.assertEqual(self.report["target_present_plan_count"], 42)
        self.assertEqual(self.report["target_absent_plan_count"], 6)
        self.assertEqual(self.report["wrong_context_count"], 8)
        self.assertEqual(len(self.report["repeat_scenario_refs"]), 16)

    def test_hierarchy_precedes_skeleton_and_all_reasons_pass(self) -> None:
        self.assertEqual(
            self.report["skeleton_signatures"]["validation_order"],
            [
                "semantic_hierarchy_and_child_rationales",
                "skeleton_and_signature_metrics",
            ],
        )
        gate = self.report["hierarchy_gate"]
        self.assertEqual(gate["rationale_plan_count"], gate["rationale_reviewed_count"])
        self.assertEqual(gate["rationale_plan_count"], gate["rationale_passed_count"])
        self.assertEqual(gate["rationale_rejected_count"], 0)
        self.assertGreater(gate["curated_parent_child_relationship_count"], 0)

    def test_natural_language_absent_and_nonliteral_gates(self) -> None:
        independent = self.report["independent_scenario_checks"]
        self.assertEqual(independent["checked_count"], 56)
        self.assertEqual(independent["passed_count"], 56)
        self.assertEqual(independent["rejected_count"], 0)
        self.assertEqual(independent["target_absent_answer_leak_hits"], 0)
        self.assertGreaterEqual(min(independent["target_absent_near_neighbor_counts"]), 2)
        self.assertEqual(independent["abbreviation_minor_typo_degenerate_hits"], 0)
        self.assertEqual(
            self.report["nonliteral_final_phenomena"],
            {
                "abbreviation": 2,
                "colloquial": 2,
                "cross_layer_expression": 2,
                "minor_typo": 2,
                "synonym": 2,
            },
        )
        manual = self.report["manual_scenario_review"]
        self.assertEqual(manual["reviewed_count"], 56)
        self.assertEqual(manual["accepted_count"], 56)
        self.assertEqual(manual["rejected_count"], 0)
        self.assertFalse(manual["source_scenario_boolean_used"])

    def test_bounded_skeleton_and_combination_gates(self) -> None:
        skeleton = self.report["skeleton_signatures"]
        self.assertLessEqual(skeleton["curated_direct_max_group"], 4)
        self.assertLessEqual(skeleton["curated_depth2_max_group"], 3)
        self.assertLessEqual(skeleton["nonfiller_direct_max_group"], 8)
        self.assertLessEqual(skeleton["repeated_skeleton_bps"], 4000)
        self.assertLessEqual(skeleton["max_cross_branch_count"], 3)
        self.assertLess(skeleton["max_branch_jaccard_bps"], 7000)
        self.assertTrue(
            all(item["density_bps"] <= 3500 for item in self.report["combination_density"].values())
        )

    def test_findings_canaries_and_rebuild(self) -> None:
        self.assertTrue(all(count == 0 for count in self.report["finding_code_counts"].values()))
        self.assertTrue(all(self.report["phase2a_canary"].values()))
        self.assertTrue(self.report["deterministic_rebuild_match"])
        repeated = builder.build_artifacts()
        for key in (
            "blueprint", "tree", "candidates", "final", "classification",
            "selection", "manual_review", "hierarchy_review", "preflight",
        ):
            self.assertEqual(self.artifacts[key], repeated[key])
        self.assertEqual(
            self.report["batch_a_protection"]["access_mode"],
            "NOT_OPENED_BY_BATCH_B_BUILDER",
        )


if __name__ == "__main__":
    unittest.main()
