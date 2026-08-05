from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DATASET = ROOT / "tests/fixtures/fictional/fire_h2_local_embedding_calibration"
sys.path.insert(0, str(SCRIPTS))

import run_fire_h2_local_embedding_lexical_a as runner


class FireH2LexicalATest(unittest.TestCase):
    def test_runner_is_bound_and_uses_no_embedding_import(self) -> None:
        self.assertEqual(
            runner.DATA_COMMIT,
            "3af7671ce4bd5e32179b94605e0f3b16f3275880",
        )
        self.assertEqual(
            runner.MANIFEST_HASH,
            "61533ab2dcd7c5d982da9c994076484e689c1de56b726ddf2ff508f94dd3712f",
        )
        self.assertEqual((runner.LEXICAL_TOP_K, runner.RESULT_TOP_K), (40, 20))
        source = (SCRIPTS / "run_fire_h2_local_embedding_lexical_a.py").read_text(
            encoding="utf-8"
        )
        imported = {
            alias.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertFalse(any("embedding" in name.lower() for name in imported))

    def test_thresholds_are_strictly_greater(self) -> None:
        base = dict(
            recall8_hits=0,
            reciprocal_rank_sum=0.0,
            hard_negative_passes=4,
            explicit_empty_passes=4,
        )
        at_limit = runner.build_aggregate_report(
            recall20_hits=18, non_literal_recall20_hits=8, **base
        )
        self.assertEqual(at_limit["status"], "H2_DATASET_DISCRIMINATIVE")
        over_total = runner.build_aggregate_report(
            recall20_hits=19, non_literal_recall20_hits=8, **base
        )
        over_non_literal = runner.build_aggregate_report(
            recall20_hits=18, non_literal_recall20_hits=9, **base
        )
        self.assertEqual(over_total["status"], "H2_DATASET_NOT_DISCRIMINATIVE")
        self.assertEqual(over_non_literal["status"], "H2_DATASET_NOT_DISCRIMINATIVE")

    def test_frozen_run_is_deterministic_and_aggregate_only(self) -> None:
        first = runner.run(DATASET)
        second = runner.run(DATASET)
        self.assertEqual(first, second)
        self.assertEqual(set(first), runner._RESULT_KEYS)
        serialized = json.dumps(first, ensure_ascii=False, sort_keys=True)
        oracle = json.loads((DATASET / "oracle-sidecar.v1.json").read_text(encoding="utf-8"))
        forbidden_values = []
        for entry in oracle["entries"]:
            forbidden_values.extend(
                [entry["target_node_id"]]
                if "target_node_id" in entry
                else entry.get("excluded_node_ids", [])
            )
        self.assertTrue(all(value not in serialized for value in forbidden_values))
        for forbidden_key in (
            "scenario_id",
            "target_node_id",
            "excluded_node_ids",
            "expected_empty_status",
            "requirement_text",
            "node_id",
            "path",
            "oracle",
        ):
            self.assertNotIn(f'"{forbidden_key}"', serialized)
        self.assertFalse(first["embedding_used"])
        self.assertFalse(first["provider_called"])
        self.assertFalse(first["index_used"])


if __name__ == "__main__":
    unittest.main()
