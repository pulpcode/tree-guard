from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from fire_m5_retrieval_roles import (
    aggregate_annotation_report,
    build_silver_role_evidence,
)
from run_fire_m5_retrieval_ab import (
    build_view_sources,
    load_experiment_sources,
)


FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow"


class FireM5RetrievalRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.formal, cls.oracle, cls.tree, cls.branches = load_experiment_sources(
            FIXTURE_DIR
        )

    def test_annotations_cover_the_frozen_denominator_without_oracle_targets(self) -> None:
        report = aggregate_annotation_report(self.formal)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["scenario_count"], 18)
        self.assertEqual(
            report["role_counts"],
            {"TARGET": 21, "SCOPE": 5, "EXCLUSION": 3},
        )
        encoded = repr(report)
        for forbidden in (
            "scenario_ref",
            "node_id",
            "requirement_text",
            "acceptable_node_ids",
            "evidence_hash",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_every_annotation_is_an_exact_source_bound_span(self) -> None:
        for scenario in self.formal:
            with self.subTest(scenario=scenario["scenario_ref"]):
                request, _, _ = build_view_sources(
                    scenario,
                    self.oracle[scenario["scenario_ref"]],
                    self.tree,
                    self.branches,
                    "V_REQUIREMENT_ONLY",
                )
                evidence = build_silver_role_evidence(scenario, request)
                self.assertTrue(any(span.role == "TARGET" for span in evidence.spans))
                for span in evidence.spans:
                    self.assertEqual(
                        request.requirement_text[span.start : span.end],
                        span.text,
                    )

    def test_annotation_generation_is_deterministic_across_request_views(self) -> None:
        scenario = self.formal[8]
        evidence_by_view = {}
        for view in (
            "V_CANONICAL",
            "V_PARENT_ABSENT",
            "V_PARENT_WRONG_BRANCH",
            "V_REQUIREMENT_ONLY",
        ):
            request, _, _ = build_view_sources(
                scenario,
                self.oracle[scenario["scenario_ref"]],
                self.tree,
                self.branches,
                view,
            )
            evidence_by_view[view] = build_silver_role_evidence(scenario, request)

        spans = [item.spans for item in evidence_by_view.values()]
        self.assertTrue(all(item == spans[0] for item in spans))
        self.assertNotEqual(
            evidence_by_view["V_PARENT_ABSENT"].source_request_hash,
            evidence_by_view["V_PARENT_WRONG_BRANCH"].source_request_hash,
        )


if __name__ == "__main__":
    unittest.main()
