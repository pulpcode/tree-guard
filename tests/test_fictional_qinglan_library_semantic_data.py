from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from treeguard.adapter import adapt_tree_document
from treeguard.fictional_qinglan_library_semantic_data import (
    ALLOWED_FACETS_BY_SUBJECT,
    DATASET_REF,
    PRIMARY_ROLE,
    RUN_REF,
    SOURCE_CLASS,
    TARGET_CLASS_OWNER_COUNT,
    TARGET_FAMILY_COUNTS,
    TARGET_LINEAGE_REFERENCE_COUNT,
    TARGET_NODE_COUNT,
    TARGET_SCENARIO_COUNT,
    build_human_review_checklist,
    build_qinglan_library_semantic_manifest,
    build_qinglan_library_semantic_scenarios,
    build_qinglan_library_semantic_tree,
    build_semantic_blueprint_view,
    candidate_files,
    run_qinglan_library_semantic_preflight,
    run_read_only_critic,
    write_qinglan_library_semantic_candidate,
)


def _wrappers(document: dict) -> list[dict]:
    pending = list(document["map_topology"].values())
    items = []
    while pending:
        wrapper = pending.pop()
        items.append(wrapper)
        pending.extend(wrapper.get("subnodes", {}).values())
    return items


class FictionalQinglanLibrarySemanticDataTests(unittest.TestCase):
    def test_tree_adapts_with_exact_medium_shape(self) -> None:
        document = build_qinglan_library_semantic_tree()
        result = adapt_tree_document(document)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.observed_node_count, TARGET_NODE_COUNT)
        self.assertEqual(result.observed_value_count, 0)
        self.assertEqual(result.issues, ())
        self.assertIsNotNone(result.tree)
        assert result.tree is not None
        self.assertEqual(
            Counter(node.kind for node in result.tree.nodes),
            {"CONCEPT": 20, "PROPERTY": 292},
        )
        self.assertEqual(
            Counter(
                node.value_contract.value_type
                for node in result.tree.nodes
                if node.kind == "PROPERTY"
            ),
            {
                "boolean": 34,
                "class": 52,
                "integer": 52,
                "string": 135,
                "time_code": 19,
            },
        )
        self.assertEqual(
            Counter(
                node.value_contract.cardinality
                for node in result.tree.nodes
                if node.kind == "PROPERTY"
            ),
            {"MULTIPLE": 117, "SINGLE": 175},
        )
        metadata = document["metadata"]
        self.assertEqual(metadata["source_class"], SOURCE_CLASS)
        self.assertTrue(metadata["fictional"])
        self.assertFalse(metadata["derived_from_real"])
        self.assertFalse(metadata["gold_eligible"])
        self.assertFalse(metadata["patch_eligible"])

    def test_family_and_lineage_counts_match_blueprint(self) -> None:
        result = adapt_tree_document(
            build_qinglan_library_semantic_tree()
        )
        assert result.tree is not None
        nodes = result.tree.nodes
        family_counts = Counter(
            node.extension["dataset_family"] for node in nodes
        )
        lineage_ids = {
            node.node_id
            for node in nodes
            if node.extension["lineage_role"] == "lineage_reference"
        }

        self.assertEqual(dict(family_counts), TARGET_FAMILY_COUNTS)
        self.assertEqual(
            len(lineage_ids),
            TARGET_LINEAGE_REFERENCE_COUNT,
        )
        self.assertTrue(
            {
                "ql-001",
                "ql-018",
                "ql-024",
                "ql-029",
                "ql-032",
                "ql-038",
                "ql-039",
            }.issubset(lineage_ids)
        )
        self.assertFalse(
            any(
                node.extension["lineage_role"] == "replay_anchor"
                for node in nodes
            )
        )

    def test_all_properties_belong_to_explicit_allowed_table(self) -> None:
        result = adapt_tree_document(
            build_qinglan_library_semantic_tree()
        )
        assert result.tree is not None
        scalar_property_ids = {
            node.node_id
            for node in result.tree.nodes
            if (
                node.kind == "PROPERTY"
                and node.value_contract is not None
                and node.value_contract.value_type != "class"
            )
        }
        class_owner_ids = {
            node.node_id
            for node in result.tree.nodes
            if (
                node.kind == "PROPERTY"
                and node.value_contract is not None
                and node.value_contract.value_type == "class"
            )
        }
        allowed_ids = {
            facet.node_id
            for facets in ALLOWED_FACETS_BY_SUBJECT.values()
            for facet in facets
        }

        self.assertEqual(scalar_property_ids, allowed_ids)
        self.assertEqual(len(scalar_property_ids), 240)
        self.assertEqual(len(class_owner_ids), TARGET_CLASS_OWNER_COUNT)
        self.assertLess(
            run_qinglan_library_semantic_preflight()[
                "combination_density"
            ],
            0.10,
        )

    def test_scenarios_are_unique_bounded_and_non_gold(self) -> None:
        scenarios = build_qinglan_library_semantic_scenarios()

        self.assertEqual(len(scenarios), TARGET_SCENARIO_COUNT)
        self.assertEqual(
            len({item["scenario_ref"] for item in scenarios}),
            TARGET_SCENARIO_COUNT,
        )
        self.assertEqual(
            len({item["primary_risk"] for item in scenarios}),
            TARGET_SCENARIO_COUNT,
        )
        self.assertEqual(
            sum(
                "replay_anchor" in item["challenge_tags"]
                for item in scenarios
            ),
            0,
        )
        for item in scenarios:
            self.assertEqual(item["source_class"], SOURCE_CLASS)
            self.assertEqual(item["candidate_source"], "AI_SYNTHETIC")
            self.assertTrue(item["fictional"])
            self.assertFalse(item["gold_eligible"])
            self.assertFalse(item["patch_eligible"])
            self.assertNotIn("oracle", item)
            self.assertEqual(
                item["proposed_observable_state"]["authority"],
                "PROVISIONAL_HUMAN_REVIEW_REQUIRED",
            )

    def test_instance_boundary_scenarios_bind_declared_owners(self) -> None:
        scenarios = {
            item["scenario_ref"]: item
            for item in build_qinglan_library_semantic_scenarios()
        }

        self.assertEqual(
            scenarios["QS-C14"]["request"]["proposed_parent_node_id"],
            "qs-s008",
        )
        self.assertEqual(
            scenarios["QS-C15"]["request"]["proposed_parent_node_id"],
            "ql-008",
        )
        self.assertEqual(
            scenarios["QS-C16"]["request"]["proposed_parent_node_id"],
            "ql-006",
        )
        self.assertEqual(
            scenarios["QS-C17"]["request"]["proposed_parent_node_id"],
            "ql-018",
        )
        self.assertEqual(
            {
                scenarios[ref]["proposed_observable_state"]["category"]
                for ref in ("QS-C14", "QS-C17")
            },
            {"STABLE_CANDIDATE"},
        )

    def test_kind_conflict_scenario_does_not_mix_scalar_or_cardinality_risks(
        self,
    ) -> None:
        scenarios = {
            item["scenario_ref"]: item
            for item in build_qinglan_library_semantic_scenarios()
        }
        request = scenarios["QS-C04"]["request"]

        self.assertIsNone(request["proposed_parent_node_id"])
        self.assertEqual(request["node_kind_hint"], "CONCEPT")
        self.assertIsNone(request["value_type_hint"])
        self.assertEqual(request["cardinality_hint"], "UNKNOWN")
        self.assertEqual(
            scenarios["QS-C12"]["request"]["proposed_parent_node_id"],
            "ql-001",
        )

    def test_value_owners_distinguish_singletons_and_record_lists(
        self,
    ) -> None:
        document = build_qinglan_library_semantic_tree()
        wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(document)
        }

        audio = wrappers["qs-s008"]["metadata"]
        duration = next(
            item["metadata"]
            for item in wrappers["qs-s008"]["subnodes"].values()
            if item["metadata"]["node_name"] == "音频时长"
        )
        basic_information = wrappers["ql-009"]["metadata"]
        library_name = wrappers["ql-029"]["metadata"]
        quiet_area = wrappers["qs-s013"]["metadata"]
        group_study_room = wrappers["ql-010"]["metadata"]
        multipurpose_hall = wrappers["ql-011"]["metadata"]

        self.assertEqual(audio["node_type"], "property")
        self.assertEqual(audio["value_type"], "class")
        self.assertTrue(audio["is_list"])
        self.assertEqual(
            audio["extension"]["value_owner_scope"],
            "REPEATED_RECORD",
        )
        self.assertEqual(duration["parent_node_id"], "qs-s008")
        self.assertEqual(
            duration["extension"]["value_owner_scope"],
            "PARENT_CLASS_RECORD",
        )

        self.assertEqual(basic_information["node_type"], "concept")
        self.assertEqual(
            basic_information["extension"]["semantic_role"],
            "SINGLETON_SECTION",
        )
        self.assertEqual(
            library_name["extension"]["value_owner_scope"],
            "PARENT_SINGLETON_SECTION",
        )
        self.assertEqual(library_name["node_name"], "馆舍名称")
        self.assertEqual(library_name["value_type"], "string")
        self.assertFalse(library_name["is_list"])

        self.assertEqual(quiet_area["node_type"], "property")
        self.assertEqual(quiet_area["value_type"], "class")
        self.assertTrue(quiet_area["is_list"])
        self.assertEqual(
            quiet_area["extension"]["value_owner_scope"],
            "REPEATED_RECORD",
        )
        for space_owner in (group_study_room, multipurpose_hall):
            self.assertEqual(space_owner["node_type"], "property")
            self.assertEqual(space_owner["value_type"], "class")
            self.assertTrue(space_owner["is_list"])
            self.assertEqual(
                space_owner["extension"]["value_owner_scope"],
                "REPEATED_RECORD",
            )

    def test_preflight_rejects_ambiguous_value_owner_boundaries(
        self,
    ) -> None:
        document = build_qinglan_library_semantic_tree()
        wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(document)
        }

        audio = wrappers["qs-s008"]["metadata"]
        audio["node_type"] = "concept"
        audio.pop("value_type")
        audio.pop("is_list")
        audio.pop("value_constraints")
        audio.pop("value_placeholder")
        audio["extension"]["semantic_role"] = "ORGANIZATIONAL_CONCEPT"
        audio["extension"]["value_owner_scope"] = "NOT_APPLICABLE"

        basic_information = wrappers["ql-009"]["metadata"]
        basic_information["extension"]["semantic_role"] = (
            "ORGANIZATIONAL_CONCEPT"
        )
        basic_information["extension"]["value_owner_scope"] = (
            "NOT_APPLICABLE"
        )

        report = run_qinglan_library_semantic_preflight(tree=document)

        self.assertEqual(report["status"], "FAIL")
        self.assertGreaterEqual(
            report["finding_code_counts"]["DATASET_VALUE_OWNER_INVALID"],
            2,
        )

    def test_preflight_passes_with_aggregate_only_report(self) -> None:
        report = run_qinglan_library_semantic_preflight()

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["finding_code_counts"], {})
        self.assertEqual(report["counts"]["nodes"], 312)
        self.assertEqual(report["counts"]["scenarios"], 20)
        self.assertEqual(report["counts"]["concepts"], 20)
        self.assertEqual(report["counts"]["class_properties"], 52)
        self.assertEqual(report["counts"]["scalar_properties"], 240)
        self.assertEqual(
            report["counts"]["singleton_section_concepts"],
            1,
        )
        self.assertEqual(report["counts"]["repeated_class_records"], 51)
        self.assertEqual(report["counts"]["singleton_class_records"], 1)
        self.assertEqual(report["counts"]["lineage_reference_nodes"], 24)
        self.assertEqual(report["counts"]["replay_anchor_nodes"], 0)
        self.assertEqual(report["counts"]["replay_scenarios"], 0)
        self.assertEqual(report["counts"]["families"], TARGET_FAMILY_COUNTS)
        self.assertEqual(max(map(int, report["counts"]["depths"])), 7)
        self.assertNotIn("tree", report)
        self.assertNotIn("scenario_text", report)

    def test_preflight_rejects_source_value_and_numbered_name(self) -> None:
        document = build_qinglan_library_semantic_tree()
        document["metadata"]["source_class"] = "PROTECTED_DERIVED"
        wrappers = _wrappers(document)
        wrappers[0]["value"] = {"metadata": {}}
        wrappers[-1]["metadata"]["node_name"] = "字段 1"

        report = run_qinglan_library_semantic_preflight(tree=document)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["finding_code_counts"]["DATASET_SOURCE_CLASS_INVALID"],
            1,
        )
        self.assertEqual(
            report["finding_code_counts"]["DATASET_COUNT_MISMATCH"],
            1,
        )
        self.assertEqual(
            report["finding_code_counts"][
                "DATASET_NUMBERED_SIBLING_NAME"
            ],
            1,
        )

    def test_preflight_rejects_unknown_parent_oracle_and_filler_target(
        self,
    ) -> None:
        scenarios = build_qinglan_library_semantic_scenarios()
        scenarios[0]["request"][
            "proposed_parent_node_id"
        ] = "unknown-fictional-parent"
        scenarios[1]["oracle"] = {"semantic_approval": True}
        blueprint = build_semantic_blueprint_view()
        filler_id = blueprint["node_families"]["stress_only_filler"][0]
        scenarios[2]["request"]["proposed_parent_node_id"] = filler_id

        report = run_qinglan_library_semantic_preflight(
            scenarios=scenarios
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["finding_code_counts"]["DATASET_REFERENCE_INVALID"],
            1,
        )
        self.assertEqual(
            report["finding_code_counts"]["DATASET_ORACLE_OVERCLAIM"],
            1,
        )
        self.assertEqual(
            report["finding_code_counts"]["DATASET_FILLER_TARGETED"],
            1,
        )

    def test_builders_return_detached_objects(self) -> None:
        first_tree = build_qinglan_library_semantic_tree()
        second_tree = build_qinglan_library_semantic_tree()
        first_tree["metadata"]["version"] = "changed"
        self.assertNotEqual(first_tree, second_tree)

        first_scenarios = build_qinglan_library_semantic_scenarios()
        first_scenarios[0]["challenge_tags"].append("mutated")
        second_scenarios = build_qinglan_library_semantic_scenarios()
        self.assertNotIn("mutated", second_scenarios[0]["challenge_tags"])

    def test_candidate_is_byte_deterministic_and_non_overwriting(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first_dir = Path(temp_dir) / "first"
            second_dir = Path(temp_dir) / "second"
            first_paths = write_qinglan_library_semantic_candidate(
                first_dir
            )
            second_paths = write_qinglan_library_semantic_candidate(
                second_dir
            )

            self.assertEqual(
                [path.name for path in first_paths],
                [path.name for path in second_paths],
            )
            for first_path, second_path in zip(
                first_paths,
                second_paths,
            ):
                self.assertEqual(
                    first_path.read_bytes(),
                    second_path.read_bytes(),
                )
            with self.assertRaises(FileExistsError):
                write_qinglan_library_semantic_candidate(first_dir)

    def test_candidate_stops_before_human_promotion(self) -> None:
        files = candidate_files()
        manifest = files["manifest.json"]
        checklist = files["promotion-checklist.json"]
        critic = run_read_only_critic(
            preflight=files["l1-report.json"]
        )

        self.assertEqual(manifest["dataset_ref"], DATASET_REF)
        self.assertEqual(manifest["run_ref"], RUN_REF)
        self.assertEqual(manifest["primary_role"], PRIMARY_ROLE)
        self.assertEqual(manifest["state"], "MACHINE_VALIDATED")
        self.assertEqual(
            manifest["synthetic_lineage"]["lineage_reference_nodes"],
            24,
        )
        self.assertEqual(
            manifest["synthetic_lineage"]["exact_replay_anchor_nodes"],
            0,
        )
        self.assertFalse(checklist["codex_pre_reviewed"])
        self.assertFalse(checklist["human_screened"])
        self.assertFalse(checklist["human_tree_scope_reviewed"])
        self.assertFalse(checklist["frozen"])
        self.assertFalse(checklist["formal_fixture_promoted"])
        self.assertFalse(checklist["runtime_registered"])
        self.assertEqual(critic["critic_authority"], "NON_AUTHORITATIVE")
        self.assertEqual(critic["blocking_count"], 0)

    def test_promoted_fixture_matches_frozen_generator_bytes(self) -> None:
        fixture_dir = (
            Path(__file__).parent
            / "fixtures"
            / "fictional"
            / "qinglan_library_semantic"
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
            write_qinglan_library_semantic_candidate(generated_dir)
            for filename in promoted_data_files:
                self.assertEqual(
                    (fixture_dir / filename).read_bytes(),
                    (generated_dir / filename).read_bytes(),
                )

        tree = json.loads(
            (fixture_dir / "tree.json").read_text(encoding="utf-8")
        )
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
            / "qinglan_library_semantic"
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
        self.assertEqual(promotion["source_class"], SOURCE_CLASS)
        self.assertTrue(promotion["fictional"])
        self.assertFalse(promotion["derived_from_real"])
        self.assertFalse(promotion["gold_eligible"])
        self.assertFalse(promotion["patch_eligible"])
        self.assertTrue(promotion["formal_fixture_promoted"])
        self.assertFalse(promotion["runtime_registered"])
        self.assertEqual(
            promotion["human_review"]["tree_scope_decision"],
            "CONFIRM_SCOPE",
        )
        self.assertEqual(
            promotion["legacy_similarity_audit"]["decision"],
            "ACCEPT",
        )
        self.assertEqual(
            promotion["legacy_similarity_audit"]["finding_codes"],
            [],
        )

    def test_review_sampling_is_fixed_and_single_reviewer(self) -> None:
        first = build_human_review_checklist()
        second = build_human_review_checklist()

        self.assertEqual(first, second)
        self.assertEqual(len(first["screen_all"]), 20)
        self.assertEqual(len(first["codex_pre_review_all"]), 20)
        self.assertEqual(len(first["random_self_recheck"]), 5)
        self.assertEqual(len(first["high_risk_self_recheck"]), 5)
        self.assertEqual(first["dual_review"], [])
        self.assertEqual(first["time_limit_minutes"], 150)
        self.assertTrue(first["tree_scope_review_required"])
        self.assertEqual(
            first["tree_scope_review_contract"][
                "singleton_section_node_ids"
            ],
            ["ql-009"],
        )
        self.assertEqual(
            set(
                first["tree_scope_review_contract"][
                    "repeated_space_record_node_ids"
                ]
            ),
            {"qs-s013", "ql-010", "ql-011"},
        )


if __name__ == "__main__":
    unittest.main()
