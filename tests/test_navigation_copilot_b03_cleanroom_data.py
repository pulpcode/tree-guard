from __future__ import annotations

import unittest
from copy import deepcopy

from tests import navigation_copilot_b03_cleanroom_builder as b03


class NavigationCopilotB03CleanroomDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = b03.build_artifacts()
        cls.report = cls.artifacts["preflight"]

    def test_exact_denominators_and_machine_gates(self) -> None:
        self.assertEqual(self.report["node_count"], 864)
        self.assertEqual(
            self.report["role_counts"],
            {
                "blueprint_background": 560,
                "curated_core": 160,
                "stress_only_filler": 144,
            },
        )
        self.assertEqual(self.report["candidate_count"], 56)
        self.assertEqual(self.report["final_count"], 48)
        self.assertEqual(self.report["target_present_plan_count"], 42)
        self.assertEqual(self.report["wrong_context_count"], 8)
        self.assertEqual(len(self.report["repeat_scenario_refs"]), 16)
        self.assertTrue(
            all(count == 0 for count in self.report["finding_code_counts"].values())
        )

    def test_natural_language_gate_covers_every_candidate(self) -> None:
        self.assertEqual(
            self.report["natural_language_gate"],
            {
                "reviewed_count": 56,
                "passed_count": 56,
                "failed_count": 0,
                "proper_noun_placeholder_check_passed_count": 56,
            },
        )
        invalid = deepcopy(b03.SCENARIO_SPECS[0])
        invalid["scenario_ref"] = "b03:natural-language:canary"
        invalid["requirement_text"] = "请按棱湾暗号找到目标，然后增加说明属性。"
        invalid["proper_noun_dependency"] = True
        self.assertEqual(
            b03._natural_language_findings((invalid,)),
            ["b03:natural-language:canary"],
        )

    def test_semantic_skeleton_and_combination_gates(self) -> None:
        semantic = self.report["semantic_signatures"]
        self.assertEqual(semantic["full_signature_count"], 56)
        self.assertEqual(semantic["full_max_repetition"], 1)
        self.assertLessEqual(semantic["simplified_max_repetition"], 2)
        self.assertEqual(semantic["curated_blueprint_signature_count"], 160)
        skeleton = self.report["skeleton_signatures"]
        self.assertLessEqual(skeleton["curated_direct_max_repetition"], 2)
        self.assertEqual(skeleton["curated_depth2_max_repetition"], 1)
        self.assertLessEqual(skeleton["nonfiller_direct_max_repetition"], 6)
        self.assertLess(skeleton["max_depth2_share_bps"], 500)
        self.assertLess(skeleton["max_branch_jaccard_bps"], 7000)
        self.assertTrue(
            all(
                density <= 3500
                for density in self.report["combination_density_bps"].values()
            )
        )

    def test_repeated_build_is_byte_identical(self) -> None:
        rebuilt = b03.build_artifacts()
        for key in (
            "blueprint_bytes",
            "tree_bytes",
            "candidate_bytes",
            "final_bytes",
            "selection_plan_bytes",
            "classification_bytes",
            "preflight_bytes",
            "review_bytes",
        ):
            self.assertEqual(self.artifacts[key], rebuilt[key], key)
        self.assertTrue(self.report["deterministic_rebuild_match"])

    def test_phase2b_canaries_are_absent(self) -> None:
        self.assertEqual(
            self.report["phase2a_canary"],
            {
                "oracle_absent": True,
                "silver_absent": True,
                "freeze_report_absent": True,
            },
        )
        self.assertTrue(all(not path.exists() for path in b03.FORBIDDEN_PHASE2A_PATHS))


if __name__ == "__main__":
    unittest.main()
