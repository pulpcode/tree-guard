from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from treeguard.adapter import adapt_tree_document
from treeguard.fictional_qinglan_library_production_shape_data import (
    ALLOWED_FACETS_DIGEST,
    ALLOWED_FACETS_BY_SUBJECT,
    ALLOWED_REPEATED_VECTOR_PARENT_SETS,
    ANCHOR_NODE_IDS,
    DATASET_REF,
    REPLAY_SCENARIO_MAP,
    RECORD_BLUEPRINT_BY_ID,
    RECORD_BLUEPRINT_DIGEST,
    RUN_REF,
    SOURCE_CLASS,
    TARGET_ANCHOR_COUNT,
    TARGET_DEPTH_COUNTS,
    TARGET_FAMILY_COUNTS,
    TARGET_NODE_COUNT,
    TARGET_REPLAY_SCENARIO_COUNT,
    TARGET_SCENARIO_COUNT,
    build_human_review_checklist,
    build_qinglan_library_production_shape_manifest,
    build_qinglan_library_production_shape_scenarios,
    build_qinglan_library_production_shape_tree,
    build_semantic_blueprint_view,
    candidate_files,
    run_qinglan_library_production_shape_preflight,
    run_read_only_critic,
    write_qinglan_library_production_shape_candidate,
)
from treeguard.fictional_qinglan_library_semantic_data import (
    build_qinglan_library_semantic_scenarios,
    build_qinglan_library_semantic_tree,
)


def _wrappers(document: dict) -> list[dict]:
    pending = list(document["map_topology"].values())
    items = []
    while pending:
        wrapper = pending.pop()
        items.append(wrapper)
        pending.extend(wrapper.get("subnodes", {}).values())
    return items


def _depths(nodes: tuple) -> dict[str, int]:
    by_id = {node.node_id: node for node in nodes}
    values: dict[str, int] = {}

    def visit(node_id: str) -> int:
        if node_id in values:
            return values[node_id]
        parent_id = by_id[node_id].parent_node_id
        value = 0 if parent_id is None else visit(parent_id) + 1
        values[node_id] = value
        return value

    for node_id in by_id:
        visit(node_id)
    return values


def _anchor_projection(node) -> dict:
    contract = node.value_contract
    return {
        "node_id": node.node_id,
        "parent_node_id": node.parent_node_id,
        "path_labels": node.path_labels,
        "kind": node.kind,
        "name": node.name,
        "value_type": None if contract is None else contract.value_type,
        "cardinality": None if contract is None else contract.cardinality,
        "constraints": (
            None if contract is None else dict(contract.constraints)
        ),
    }


def _reverse_subnodes(wrapper: dict) -> None:
    children = wrapper.get("subnodes", {})
    for child in children.values():
        _reverse_subnodes(child)
    wrapper["subnodes"] = dict(reversed(tuple(children.items())))


class FictionalQinglanLibraryProductionShapeDataTests(
    unittest.TestCase
):
    def test_tree_adapts_with_exact_large_shape(self) -> None:
        document = build_qinglan_library_production_shape_tree()
        result = adapt_tree_document(document)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.issues, ())
        self.assertEqual(result.observed_node_count, TARGET_NODE_COUNT)
        self.assertEqual(result.observed_value_count, 0)
        assert result.tree is not None
        self.assertEqual(
            Counter(node.kind for node in result.tree.nodes),
            {"CONCEPT": 50, "PROPERTY": 1951},
        )
        self.assertEqual(
            sum(
                node.value_contract is not None
                and node.value_contract.value_type == "class"
                for node in result.tree.nodes
            ),
            501,
        )
        metadata = document["metadata"]
        self.assertEqual(metadata["source_class"], SOURCE_CLASS)
        self.assertTrue(metadata["fictional"])
        self.assertFalse(metadata["derived_from_real"])
        self.assertFalse(metadata["gold_eligible"])
        self.assertFalse(metadata["patch_eligible"])

    def test_family_depth_and_anchor_counts_match_blueprint(self) -> None:
        result = adapt_tree_document(
            build_qinglan_library_production_shape_tree()
        )
        assert result.tree is not None
        nodes = result.tree.nodes

        self.assertEqual(
            dict(
                Counter(
                    node.extension["dataset_family"] for node in nodes
                )
            ),
            TARGET_FAMILY_COUNTS,
        )
        self.assertEqual(
            dict(Counter(_depths(nodes).values())),
            TARGET_DEPTH_COUNTS,
        )
        self.assertEqual(
            {
                node.node_id
                for node in nodes
                if node.extension["lineage_role"] == "replay_anchor"
            },
            set(ANCHOR_NODE_IDS),
        )
        self.assertEqual(len(ANCHOR_NODE_IDS), TARGET_ANCHOR_COUNT)

    def test_anchor_projection_matches_medium_and_copy_is_allowlisted(
        self,
    ) -> None:
        large_result = adapt_tree_document(
            build_qinglan_library_production_shape_tree()
        )
        medium_result = adapt_tree_document(
            build_qinglan_library_semantic_tree()
        )
        assert large_result.tree is not None
        assert medium_result.tree is not None
        large = {node.node_id: node for node in large_result.tree.nodes}
        medium = {node.node_id: node for node in medium_result.tree.nodes}

        self.assertEqual(set(large) & set(medium), set(ANCHOR_NODE_IDS))
        for node_id in ANCHOR_NODE_IDS:
            self.assertEqual(
                _anchor_projection(large[node_id]),
                _anchor_projection(medium[node_id]),
            )
        self.assertNotEqual(
            large["ql-001"].child_node_ids,
            medium["ql-001"].child_node_ids,
        )

    def test_replay_requests_match_medium_but_large_scenarios_are_new(
        self,
    ) -> None:
        scenarios = {
            item["scenario_ref"]: item
            for item in build_qinglan_library_production_shape_scenarios()
        }
        medium = {
            item["scenario_ref"]: item
            for item in build_qinglan_library_semantic_scenarios()
        }

        self.assertEqual(len(scenarios), TARGET_SCENARIO_COUNT)
        self.assertEqual(
            sum(
                "replay_anchor" in item["challenge_tags"]
                for item in scenarios.values()
            ),
            TARGET_REPLAY_SCENARIO_COUNT,
        )
        for replay_ref, source_ref in REPLAY_SCENARIO_MAP.items():
            self.assertEqual(
                scenarios[replay_ref]["request"],
                medium[source_ref]["request"],
            )
            self.assertEqual(
                scenarios[replay_ref]["proposed_observable_state"],
                medium[source_ref]["proposed_observable_state"],
            )
        self.assertEqual(
            set(scenarios) - set(REPLAY_SCENARIO_MAP),
            {"QP-C05", "QP-C06", "QP-C07", "QP-C08"},
        )
        self.assertEqual(
            len({item["primary_risk"] for item in scenarios.values()}),
            TARGET_SCENARIO_COUNT,
        )

    def test_value_owners_are_singleton_or_class_records(self) -> None:
        document = build_qinglan_library_production_shape_tree()
        wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(document)
        }

        self.assertEqual(
            wrappers["ql-009"]["metadata"]["extension"][
                "semantic_role"
            ],
            "SINGLETON_SECTION",
        )
        for item in wrappers.values():
            metadata = item["metadata"]
            extension = metadata["extension"]
            if metadata["node_type"] == "concept":
                if extension["semantic_role"] == "SINGLETON_SECTION":
                    self.assertEqual(
                        extension["attribute_scope"],
                        "ROOT_ENTITY",
                    )
                else:
                    self.assertEqual(
                        extension["value_owner_scope"],
                        "NOT_APPLICABLE",
                    )
                    for child in item["subnodes"].values():
                        child_metadata = child["metadata"]
                        if child_metadata["node_type"] == "property":
                            self.assertEqual(
                                child_metadata["value_type"],
                                "class",
                            )
            elif metadata["value_type"] != "class":
                parent = wrappers[metadata["parent_node_id"]]["metadata"]
                self.assertTrue(
                    (
                        parent["node_type"] == "property"
                        and parent["value_type"] == "class"
                    )
                    or parent["extension"]["semantic_role"]
                    == "SINGLETON_SECTION"
                )

    def test_every_class_record_declares_referent_relation_and_scope(
        self,
    ) -> None:
        document = build_qinglan_library_production_shape_tree()
        wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(document)
        }
        class_records = [
            item["metadata"]
            for item in wrappers.values()
            if item["metadata"]["node_type"] == "property"
            and item["metadata"]["value_type"] == "class"
        ]

        self.assertEqual(len(class_records), 501)
        self.assertEqual(len(RECORD_BLUEPRINT_BY_ID), 501)
        for metadata in class_records:
            extension = metadata["extension"]
            self.assertTrue(extension["represents"].strip())
            self.assertTrue(extension["parent_relation"].strip())
            self.assertEqual(
                extension["declared_cardinality"],
                "MULTIPLE" if metadata["is_list"] else "SINGLE",
            )
            self.assertEqual(
                extension["declared_entity_scope"],
                extension["entity_scope"],
            )

        nested = wrappers["qlp-bg-c4-001"]["metadata"]["extension"]
        self.assertEqual(nested["declared_cardinality"], "SINGLE")
        self.assertEqual(nested["entity_scope"], "COLLECTION_ITEM")
        self.assertIn("馆藏载体版本条目", nested["represents"])

    def test_carrier_version_group_uses_concrete_record_referents(
        self,
    ) -> None:
        document = build_qinglan_library_production_shape_tree()
        wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(document)
        }
        group = wrappers["qlp-g001"]
        child_names = {
            child["metadata"]["node_name"]
            for child in group["subnodes"].values()
        }

        self.assertNotIn("来源说明", child_names)
        self.assertIn("馆藏载体版本条目", child_names)
        record = wrappers["qlp-bg-s001"]["metadata"]["extension"]
        self.assertEqual(
            record["represents"],
            "一条具体的“馆藏载体版本条目”业务记录",
        )
        self.assertEqual(
            record["parent_relation"],
            "作为“载体与版本”分组中的可重复成员",
        )

    def test_allowed_table_covers_every_scalar_property(self) -> None:
        result = adapt_tree_document(
            build_qinglan_library_production_shape_tree()
        )
        assert result.tree is not None
        scalar_ids = {
            node.node_id
            for node in result.tree.nodes
            if (
                node.kind == "PROPERTY"
                and node.value_contract is not None
                and node.value_contract.value_type != "class"
            )
        }
        allowed_ids = {
            facet.node_id
            for facets in ALLOWED_FACETS_BY_SUBJECT.values()
            for facet in facets
        }

        self.assertEqual(scalar_ids, allowed_ids)
        self.assertLess(
            run_qinglan_library_production_shape_preflight()[
                "combination_density"
            ],
            0.10,
        )
        blueprint = build_semantic_blueprint_view()
        self.assertEqual(
            blueprint["frozen_semantic_inputs"],
            {
                "record_blueprint_digest": RECORD_BLUEPRINT_DIGEST,
                "allowed_facets_digest": ALLOWED_FACETS_DIGEST,
                "allowlist_source": "PRE_GENERATION_BLUEPRINT",
            },
        )
        self.assertFalse(
            blueprint["construction_policy"][
                "allowlist_derived_from_output"
            ]
        )

    def test_only_declared_homonym_vector_is_repeated(self) -> None:
        report = run_qinglan_library_production_shape_preflight()

        self.assertEqual(
            ALLOWED_REPEATED_VECTOR_PARENT_SETS,
            (frozenset({"qs-s029", "qs-s032"}),),
        )
        self.assertEqual(
            report["counts"]["declared_repeated_vector_groups"],
            1,
        )
        self.assertEqual(
            report["counts"]["unapproved_repeated_child_vectors"],
            0,
        )

    def test_node_reordering_keeps_snapshot_hash(self) -> None:
        original = build_qinglan_library_production_shape_tree()
        reordered = copy.deepcopy(original)
        for root in reordered["map_topology"].values():
            _reverse_subnodes(root)

        first = adapt_tree_document(original)
        second = adapt_tree_document(reordered)

        self.assertTrue(first.is_valid)
        self.assertTrue(second.is_valid)
        assert first.tree is not None
        assert second.tree is not None
        self.assertEqual(first.tree.snapshot_hash, second.tree.snapshot_hash)

    def test_stress_nodes_are_not_scenario_parents(self) -> None:
        result = adapt_tree_document(
            build_qinglan_library_production_shape_tree()
        )
        assert result.tree is not None
        filler_ids = {
            node.node_id
            for node in result.tree.nodes
            if node.extension["dataset_family"] == "stress_only_filler"
        }
        parent_ids = {
            item["request"]["proposed_parent_node_id"]
            for item in build_qinglan_library_production_shape_scenarios()
            if item["request"]["proposed_parent_node_id"] is not None
        }

        self.assertEqual(len(filler_ids), 400)
        self.assertTrue(filler_ids.isdisjoint(parent_ids))
        self.assertFalse(
            any(
                node.extension["semantic_target_eligible"]
                for node in result.tree.nodes
                if node.node_id in filler_ids
            )
        )

    def test_preflight_and_critic_pass_without_gold_claim(self) -> None:
        report = run_qinglan_library_production_shape_preflight()
        critic = run_read_only_critic(preflight=report)
        manifest = build_qinglan_library_production_shape_manifest()

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["blocking_count"], 0)
        self.assertEqual(report["finding_code_counts"], {})
        self.assertEqual(critic["critic_authority"], "NON_AUTHORITATIVE")
        self.assertEqual(critic["findings"], [])
        self.assertEqual(manifest["dataset_ref"], DATASET_REF)
        self.assertEqual(manifest["run_ref"], RUN_REF)
        self.assertFalse(manifest["gold_eligible"])
        self.assertFalse(manifest["patch_eligible"])

    def test_critic_rejects_scenario_that_names_stress_filler(self) -> None:
        scenarios = build_qinglan_library_production_shape_scenarios()
        scenarios[-1]["request"]["requirement_text"] = (
            "请直接选择闭馆后交接清单。"
        )

        critic = run_read_only_critic(scenarios=scenarios)

        self.assertEqual(critic["blocking_count"], 1)
        self.assertEqual(
            critic["findings"][0]["code"],
            "SEMANTIC_FILLER_DIRECT_REFERENCE",
        )

    def test_preflight_rejects_owner_boundary_and_undeclared_copy(
        self,
    ) -> None:
        owner_tamper = build_qinglan_library_production_shape_tree()
        owner_wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(owner_tamper)
        }
        owner = owner_wrappers["qp-s003"]["metadata"]
        owner["node_type"] = "concept"
        for key in (
            "value_type",
            "is_list",
            "value_constraints",
            "value_placeholder",
        ):
            owner.pop(key)

        copy_tamper = build_qinglan_library_production_shape_tree()
        copy_wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(copy_tamper)
        }
        copy_wrappers["qp-f005"]["metadata"]["node_id"] = "ql-006"

        owner_report = run_qinglan_library_production_shape_preflight(
            tree=owner_tamper
        )
        copy_report = run_qinglan_library_production_shape_preflight(
            tree=copy_tamper
        )

        self.assertIn(
            "DATASET_VALUE_OWNER_INVALID",
            owner_report["finding_code_counts"],
        )
        self.assertIn(
            "DATASET_UNDECLARED_ANCHOR_COPY",
            copy_report["finding_code_counts"],
        )

    def test_preflight_rejects_referent_relation_and_scope_tampering(
        self,
    ) -> None:
        referent_tamper = build_qinglan_library_production_shape_tree()
        referent_wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(referent_tamper)
        }
        extension = referent_wrappers["qlp-bg-s001"]["metadata"][
            "extension"
        ]
        extension["represents"] = ""
        extension["parent_relation"] = ""

        scope_tamper = build_qinglan_library_production_shape_tree()
        scope_wrappers = {
            item["metadata"]["node_id"]: item
            for item in _wrappers(scope_tamper)
        }
        nested_extension = scope_wrappers["qlp-bg-c4-001"]["metadata"][
            "extension"
        ]
        nested_extension["declared_entity_scope"] = "ROOT_ENTITY"
        nested_extension["entity_scope"] = "ROOT_ENTITY"
        nested_extension["attribute_scope"] = "ROOT_ENTITY"

        referent_report = run_qinglan_library_production_shape_preflight(
            tree=referent_tamper
        )
        scope_report = run_qinglan_library_production_shape_preflight(
            tree=scope_tamper
        )

        self.assertIn(
            "DATASET_RECORD_REFERENT_MISSING",
            referent_report["finding_code_counts"],
        )
        self.assertIn(
            "DATASET_PARENT_RELATION_UNDECLARED",
            referent_report["finding_code_counts"],
        )
        self.assertIn(
            "DATASET_SCOPE_ANCESTRY_CONFLICT",
            scope_report["finding_code_counts"],
        )

    def test_preflight_rejects_frozen_input_digest_tampering(self) -> None:
        document = build_qinglan_library_production_shape_tree()
        document["metadata"]["allowed_facets_digest"] = "tampered"

        report = run_qinglan_library_production_shape_preflight(
            tree=document
        )

        self.assertIn(
            "DATASET_ALLOWLIST_DERIVED_FROM_OUTPUT",
            report["finding_code_counts"],
        )

    def test_preflight_rejects_boundary_canary(self) -> None:
        document = build_qinglan_library_production_shape_tree()
        document["metadata"]["fictional_note"] = "api_key"

        report = run_qinglan_library_production_shape_preflight(
            tree=document
        )

        self.assertIn(
            "DATASET_BOUNDARY_CANARY_FOUND",
            report["finding_code_counts"],
        )

    def test_candidate_files_are_deterministic_and_non_overwriting(
        self,
    ) -> None:
        first = candidate_files()
        second = candidate_files()

        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "coverage-matrix.json",
                "dataset-charter.json",
                "human-review-checklist.json",
                "l1-report.json",
                "l2-critic-findings.json",
                "manifest.json",
                "promotion-checklist.json",
                "scenarios.json",
                "semantic-blueprint.json",
                "tree.json",
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "candidate"
            written = write_qinglan_library_production_shape_candidate(
                output
            )
            self.assertEqual(len(written), len(first))
            for filename, payload in first.items():
                self.assertEqual(
                    json.loads((output / filename).read_text("utf-8")),
                    payload,
                )
            with self.assertRaises(FileExistsError):
                write_qinglan_library_production_shape_candidate(output)

    def test_review_budget_is_single_reviewer_and_bounded(self) -> None:
        checklist = build_human_review_checklist()
        blueprint = build_semantic_blueprint_view()

        self.assertEqual(checklist["status"], "PENDING")
        self.assertEqual(checklist["dual_review"], [])
        self.assertEqual(len(checklist["screen_all_scenarios"]), 8)
        self.assertEqual(
            len(checklist["human_review_curated_nodes"]),
            40,
        )
        self.assertEqual(len(checklist["random_node_sample"]), 24)
        self.assertEqual(
            blueprint["construction_policy"][
                "declared_repeated_vector_parent_sets"
            ],
            [["qs-s029", "qs-s032"]],
        )

    def test_promoted_fixture_matches_frozen_generator_bytes(self) -> None:
        fixture_dir = (
            Path(__file__).parent
            / "fixtures"
            / "fictional"
            / "qinglan_library_production_shape"
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
            write_qinglan_library_production_shape_candidate(
                generated_dir
            )
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
            / "qinglan_library_production_shape"
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
            promotion["human_review"]["anchor_contract_decision"],
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


if __name__ == "__main__":
    unittest.main()
