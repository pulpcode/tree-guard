from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from fire_m5_retrieval_roles import build_silver_role_evidence
from run_fire_m5_retrieval_ab import build_view_sources, load_experiment_sources
from treeguard.retrieval_role_tolerant import (
    build_boundary_tolerant_role_candidate_set,
)
from treeguard.retrieval_roles import build_model_retrieval_role_evidence


FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow"


class BoundaryTolerantRoleRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        formal, oracle, tree, branches = load_experiment_sources(FIXTURE_DIR)
        cls.scenarios = {item["scenario_ref"]: item for item in formal}
        cls.oracle = oracle
        cls.tree = tree
        cls.branches = branches

    def _sources(self, scenario_ref: str):
        scenario = self.scenarios[scenario_ref]
        request, confirmation, _ = build_view_sources(
            scenario,
            self.oracle[scenario_ref],
            self.tree,
            self.branches,
            "V_REQUIREMENT_ONLY",
        )
        return scenario, request, confirmation

    def test_model_superspan_keeps_an_acceptable_target_in_top_8(self) -> None:
        scenario, request, confirmation = self._sources("M5S012")
        evidence = build_model_retrieval_role_evidence(
            {
                "schema_version": "retrieval-role-model-output.v1",
                "spans": [
                    {"role": "SCOPE", "text": "全域只读字典"},
                    {"role": "TARGET", "text": "现有责任边界合同"},
                ],
            },
            request,
        )

        result = build_boundary_tolerant_role_candidate_set(
            evidence, request, confirmation, self.tree
        )

        acceptable = set(
            self.oracle[scenario["scenario_ref"]]["capability_oracle"]["retrieval"][
                "acceptable_node_ids"
            ]
        )
        self.assertEqual(result.status, "CANDIDATES_READY")
        acceptable_candidates = [
            item for item in result.candidates[:8] if item.node_id in acceptable
        ]
        self.assertTrue(acceptable_candidates)
        self.assertGreater(
            acceptable_candidates[0].score.target_name_similarity,
            0,
        )

    def test_explicit_empty_target_remains_no_candidates(self) -> None:
        scenario, request, confirmation = self._sources("M5S017")
        evidence = build_silver_role_evidence(scenario, request)

        result = build_boundary_tolerant_role_candidate_set(
            evidence, request, confirmation, self.tree
        )

        self.assertEqual(result.status, "NO_CANDIDATES")
        self.assertEqual(result.candidates, ())

    def test_repeated_build_is_byte_deterministic(self) -> None:
        scenario, request, confirmation = self._sources("M5S009")
        evidence = build_silver_role_evidence(scenario, request)

        first = build_boundary_tolerant_role_candidate_set(
            evidence, request, confirmation, self.tree
        )
        second = build_boundary_tolerant_role_candidate_set(
            evidence, request, confirmation, self.tree
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertFalse(first.to_dict()["embedding_used"])
        self.assertFalse(first.to_dict()["allows_addition"])


if __name__ == "__main__":
    unittest.main()
