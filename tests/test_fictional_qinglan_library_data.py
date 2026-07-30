from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from treeguard.adapter import adapt_tree_document
from treeguard.fictional_qinglan_library_data import (
    ALLOWED_FACETS_BY_SUBJECT,
    DATASET_REF,
    RUN_REF,
    SOURCE_CLASS,
    TARGET_NODE_COUNT,
    TARGET_SCENARIO_COUNT,
    build_human_review_checklist,
    build_qinglan_library_scenarios,
    build_qinglan_library_tree,
    candidate_files,
    run_qinglan_library_preflight,
    run_read_only_critic,
    write_qinglan_library_candidate,
)


class FictionalQinglanLibraryDataTests(unittest.TestCase):
    def test_tree_adapts_with_exact_cleanroom_shape(self) -> None:
        document = build_qinglan_library_tree()
        result = adapt_tree_document(document)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.observed_node_count, TARGET_NODE_COUNT)
        self.assertEqual(result.observed_value_count, 0)
        self.assertEqual(result.issues, ())
        self.assertIsNotNone(result.tree)
        assert result.tree is not None
        self.assertEqual(len(result.tree.nodes), 48)
        self.assertEqual(
            Counter(node.kind for node in result.tree.nodes),
            {"CONCEPT": 21, "PROPERTY": 27},
        )
        metadata = document["metadata"]
        self.assertEqual(metadata["source_class"], SOURCE_CLASS)
        self.assertTrue(metadata["fictional"])
        self.assertFalse(metadata["derived_from_real"])
        self.assertFalse(metadata["gold_eligible"])
        self.assertFalse(metadata["patch_eligible"])

    def test_property_contract_distribution_matches_blueprint(self) -> None:
        result = adapt_tree_document(build_qinglan_library_tree())
        assert result.tree is not None
        properties = [node for node in result.tree.nodes if node.kind == "PROPERTY"]

        self.assertEqual(
            Counter(node.value_contract.value_type for node in properties),
            {"boolean": 4, "integer": 11, "string": 7, "time_code": 5},
        )
        self.assertEqual(
            Counter(node.value_contract.cardinality for node in properties),
            {"MULTIPLE": 8, "SINGLE": 19},
        )
        self.assertEqual(
            {
                node.node_id for node in properties
            },
            {
                facet_id
                for facet_ids in ALLOWED_FACETS_BY_SUBJECT.values()
                for facet_id in facet_ids
            },
        )

    def test_scenarios_are_bounded_unique_and_non_gold(self) -> None:
        scenarios = build_qinglan_library_scenarios()

        self.assertEqual(len(scenarios), TARGET_SCENARIO_COUNT)
        self.assertEqual(
            len({item["scenario_ref"] for item in scenarios}),
            TARGET_SCENARIO_COUNT,
        )
        self.assertEqual(
            len({item["primary_risk"] for item in scenarios}),
            TARGET_SCENARIO_COUNT,
        )
        for item in scenarios:
            self.assertEqual(item["source_class"], SOURCE_CLASS)
            self.assertEqual(item["candidate_source"], "AI_SYNTHETIC")
            self.assertTrue(item["fictional"])
            self.assertFalse(item["gold_eligible"])
            self.assertFalse(item["patch_eligible"])
            self.assertEqual(
                item["proposed_observable_state"]["authority"],
                "PROVISIONAL_HUMAN_REVIEW_REQUIRED",
            )
            self.assertNotIn("oracle", item)

    def test_human_review_revisions_are_encoded_without_overclaim(self) -> None:
        scenarios = {
            item["scenario_ref"]: item
            for item in build_qinglan_library_scenarios()
        }
        result = adapt_tree_document(build_qinglan_library_tree())
        assert result.tree is not None
        nodes = {node.node_id: node for node in result.tree.nodes}

        self.assertEqual(RUN_REF, "qinglan-library-control-v1-run-004")
        self.assertEqual(nodes["ql-024"].name, "默认外借许可")
        self.assertIn("该类文献默认", scenarios["QL-C01"]["request"]["requirement_text"])
        self.assertIn(
            "category_scope",
            scenarios["QL-C01"]["challenge_tags"],
        )

        self.assertIn(
            "当前没有提供社区需求资料",
            scenarios["QL-C08"]["request"]["requirement_text"],
        )
        self.assertEqual(
            scenarios["QL-C08"]["proposed_observable_state"]["category"],
            "NEED_EVIDENCE",
        )

        self.assertEqual(
            scenarios["QL-C12"]["primary_risk"],
            "REPLAY_BASELINE_ANCHOR",
        )
        self.assertEqual(
            scenarios["QL-C12"]["challenge_tags"],
            ["small_tree_replay_baseline"],
        )
        self.assertEqual(
            scenarios["QL-C12"]["proposed_observable_state"]["category"],
            "STABLE_CANDIDATE",
        )

    def test_l1_preflight_passes_and_reports_only_aggregates(self) -> None:
        report = run_qinglan_library_preflight()

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["finding_code_counts"], {})
        self.assertEqual(report["counts"]["nodes"], 48)
        self.assertEqual(report["counts"]["scenarios"], 12)
        self.assertLess(report["combination_density"], 0.5)
        self.assertNotIn("tree", report)
        self.assertNotIn("scenario_text", report)

    def test_l1_rejects_unknown_parent_and_oracle_overclaim(self) -> None:
        scenarios = build_qinglan_library_scenarios()
        scenarios[0]["request"]["proposed_parent_node_id"] = "unknown-fictional-parent"
        scenarios[1]["oracle"] = {"semantic_approval": True}

        report = run_qinglan_library_preflight(scenarios=scenarios)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["finding_code_counts"]["DATASET_REFERENCE_INVALID"],
            1,
        )
        self.assertEqual(
            report["finding_code_counts"]["DATASET_ORACLE_OVERCLAIM"],
            1,
        )

    def test_l1_rejects_source_class_change_and_value_envelope(self) -> None:
        document = build_qinglan_library_tree()
        document["metadata"]["source_class"] = "PROTECTED_DERIVED"
        root = next(iter(document["map_topology"].values()))
        root["value"] = {"metadata": {}}

        report = run_qinglan_library_preflight(tree=document)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["finding_code_counts"]["DATASET_SOURCE_CLASS_INVALID"],
            1,
        )
        self.assertEqual(
            report["finding_code_counts"]["DATASET_BOUNDARY_CANARY_FOUND"],
            1,
        )

    def test_builder_returns_detached_objects(self) -> None:
        first = build_qinglan_library_tree()
        second = build_qinglan_library_tree()
        first["metadata"]["version"] = "changed"

        self.assertNotEqual(first, second)
        self.assertEqual(second["metadata"]["version"], "QL-1.1")

    def test_candidate_staging_is_byte_deterministic_and_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first_dir = Path(temp_dir) / "first"
            second_dir = Path(temp_dir) / "second"
            first_paths = write_qinglan_library_candidate(first_dir)
            second_paths = write_qinglan_library_candidate(second_dir)

            self.assertEqual(
                [path.name for path in first_paths],
                [path.name for path in second_paths],
            )
            for first_path, second_path in zip(first_paths, second_paths):
                self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            with self.assertRaises(FileExistsError):
                write_qinglan_library_candidate(first_dir)

    def test_candidate_status_stops_before_human_promotion(self) -> None:
        files = candidate_files()
        charter = files["dataset-charter.json"]
        coverage = files["coverage-matrix.json"]
        manifest = files["manifest.json"]
        checklist = files["promotion-checklist.json"]
        critic = run_read_only_critic(
            preflight=files["l1-report.json"],
        )

        self.assertEqual(manifest["dataset_ref"], DATASET_REF)
        self.assertEqual(charter["source_class"], SOURCE_CLASS)
        self.assertEqual(len(coverage["cells"]), 12)
        self.assertEqual(manifest["state"], "MACHINE_VALIDATED")
        self.assertFalse(checklist["human_screened"])
        self.assertFalse(checklist["frozen"])
        self.assertFalse(checklist["formal_fixture_promoted"])
        self.assertEqual(critic["critic_authority"], "NON_AUTHORITATIVE")
        self.assertEqual(critic["blocking_count"], 0)

    def test_review_sampling_is_fixed_and_within_budget(self) -> None:
        first = build_human_review_checklist()
        second = build_human_review_checklist()

        self.assertEqual(first, second)
        self.assertEqual(len(first["screen_all"]), 12)
        self.assertEqual(len(first["random_sample"]), 4)
        self.assertEqual(len(first["self_recheck"]), 4)
        self.assertEqual(
            first["self_recheck"],
            ["QL-C01", "QL-C08", "QL-C10", "QL-C12"],
        )
        self.assertEqual(first["dual_review"], [])
        self.assertEqual(first["time_limit_minutes"], 120)

    def test_scenario_mutation_does_not_change_next_build(self) -> None:
        first = build_qinglan_library_scenarios()
        first[0]["challenge_tags"].append("mutated")

        second = build_qinglan_library_scenarios()
        self.assertNotIn("mutated", second[0]["challenge_tags"])

    def test_promoted_fixture_matches_frozen_generator_bytes(self) -> None:
        fixture_dir = (
            Path(__file__).parent
            / "fixtures"
            / "fictional"
            / "qinglan_library_control"
        )
        promoted_data_files = {
            "coverage-matrix.json",
            "dataset-charter.json",
            "manifest.json",
            "scenarios.json",
            "semantic-blueprint.json",
            "tree.json",
        }
        self.assertEqual(
            {path.name for path in fixture_dir.iterdir()},
            promoted_data_files | {"promotion.json", "README.md"},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            generated_dir = Path(temp_dir) / "candidate"
            write_qinglan_library_candidate(generated_dir)
            for filename in promoted_data_files:
                self.assertEqual(
                    (fixture_dir / filename).read_bytes(),
                    (generated_dir / filename).read_bytes(),
                )

        tree = json.loads((fixture_dir / "tree.json").read_text(encoding="utf-8"))
        scenarios = json.loads(
            (fixture_dir / "scenarios.json").read_text(encoding="utf-8")
        )
        result = adapt_tree_document(tree)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.observed_node_count, TARGET_NODE_COUNT)
        self.assertEqual(result.observed_value_count, 0)
        assert result.tree is not None
        node_ids = {node.node_id for node in result.tree.nodes}
        for scenario in scenarios:
            parent_id = scenario["request"]["proposed_parent_node_id"]
            self.assertTrue(parent_id is None or parent_id in node_ids)

    def test_promoted_fixture_records_non_gold_boundary(self) -> None:
        fixture_dir = (
            Path(__file__).parent
            / "fixtures"
            / "fictional"
            / "qinglan_library_control"
        )
        manifest = json.loads(
            (fixture_dir / "manifest.json").read_text(encoding="utf-8")
        )
        promotion = json.loads(
            (fixture_dir / "promotion.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["run_ref"], RUN_REF)
        self.assertEqual(manifest["state"], "MACHINE_VALIDATED")
        self.assertEqual(promotion["fixture_state"], "PROMOTED")
        self.assertEqual(promotion["candidate_state"], "FROZEN")
        self.assertEqual(
            promotion["source_class"],
            SOURCE_CLASS,
        )
        self.assertTrue(promotion["fictional"])
        self.assertFalse(promotion["derived_from_real"])
        self.assertFalse(promotion["gold_eligible"])
        self.assertFalse(promotion["patch_eligible"])
        self.assertTrue(promotion["formal_fixture_promoted"])
        self.assertFalse(promotion["runtime_registered"])
        self.assertEqual(
            promotion["legacy_similarity_audit"]["decision"],
            "ACCEPT",
        )
        self.assertEqual(
            promotion["legacy_similarity_audit"]["finding_codes"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
