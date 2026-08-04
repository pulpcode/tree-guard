from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from fire_m5_retrieval_calibration import (
    RetrievalCalibrationError,
    build_retrieval_calibration_oracle_v2,
)
from treeguard.adapter import load_tree_export
from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads


FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow"


def _load_sources():
    scenarios = strict_json_loads(
        (FIXTURE_DIR / "scenario-candidates.json").read_text(encoding="utf-8")
    )
    oracle = strict_json_loads(
        (FIXTURE_DIR / "oracle-sidecar.json").read_text(encoding="utf-8")
    )
    imported = load_tree_export(FIXTURE_DIR / "tree.json")
    assert imported.tree is not None
    formal = tuple(
        item
        for item in scenarios["candidates"]
        if item["selection_status"] == "EXECUTION"
        and item["expected_route"] == "PROCEED"
    )
    oracle_by_ref = {item["scenario_ref"]: item for item in oracle["items"]}
    return formal, oracle_by_ref, imported.tree


class FireM5RetrievalCalibrationTests(unittest.TestCase):
    def test_v2_expands_only_request_observable_broad_classes(self) -> None:
        formal, oracle_by_ref, tree = _load_sources()

        result = build_retrieval_calibration_oracle_v2(
            formal, oracle_by_ref, tree
        )

        self.assertEqual(
            result.aggregate_report(),
            {
                "report_version": "fire-m5-retrieval-calibration-oracle.v2",
                "status": "PASS",
                "policy_version": (
                    "treeguard.fire-m5-request-observable-retrieval-oracle.v2"
                ),
                "calibration_only": True,
                "production_qualification": False,
                "gold_eligible": False,
                "gate_eligible": False,
                "item_count": 18,
                "policy_counts": {
                    "EXPLICIT_EMPTY": 2,
                    "REQUEST_OBSERVABLE_CLASS": 2,
                    "SOURCE_ORACLE_RETAINED": 14,
                },
                "target_counts": {
                    "EXPLICIT_EMPTY": 0,
                    "REQUEST_OBSERVABLE_CLASS": 74,
                    "SOURCE_ORACLE_RETAINED": 17,
                },
            },
        )

    def test_generation_is_deterministic_and_does_not_mutate_sources(self) -> None:
        formal, oracle_by_ref, tree = _load_sources()
        before = canonical_digest(oracle_by_ref)

        first = build_retrieval_calibration_oracle_v2(
            formal, oracle_by_ref, tree
        )
        second = build_retrieval_calibration_oracle_v2(
            tuple(reversed(formal)),
            oracle_by_ref,
            replace(tree, nodes=tuple(reversed(tree.nodes))),
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(canonical_digest(oracle_by_ref), before)

    def test_digest_and_item_order_tampering_are_rejected(self) -> None:
        formal, oracle_by_ref, tree = _load_sources()
        result = build_retrieval_calibration_oracle_v2(
            formal, oracle_by_ref, tree
        )

        with self.assertRaises(ValueError):
            replace(result, oracle_digest="0" * 64)
        with self.assertRaises(ValueError):
            replace(result, items=tuple(reversed(result.items)))

    def test_unobservable_broad_class_fails_closed(self) -> None:
        formal, oracle_by_ref, tree = _load_sources()
        changed = []
        changed_ref = None
        for scenario in formal:
            if scenario["coverage_cell"] == "P04" and changed_ref is None:
                changed_ref = scenario["scenario_ref"]
                changed.append(
                    {
                        **scenario,
                        "request": {
                            **scenario["request"],
                            "requirement_text": "请求一个完全不可观察的新类别。",
                        },
                    }
                )
            else:
                changed.append(scenario)

        with self.assertRaises(RetrievalCalibrationError) as context:
            build_retrieval_calibration_oracle_v2(
                tuple(changed), oracle_by_ref, tree
            )
        self.assertEqual(
            context.exception.code,
            "RETRIEVAL_CALIBRATION_CLASS_SIGNAL_MISSING",
        )

    def test_aggregate_report_excludes_hidden_targets_and_digests(self) -> None:
        formal, oracle_by_ref, tree = _load_sources()
        report = build_retrieval_calibration_oracle_v2(
            formal, oracle_by_ref, tree
        ).aggregate_report()

        encoded = repr(report)
        for forbidden in (
            "scenario_ref",
            "acceptable_node_ids",
            "node_id",
            "oracle_digest",
            "source_tree_digest",
            "requirement_text",
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
