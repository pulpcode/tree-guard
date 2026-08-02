from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard.adapter import load_tree_export
from treeguard.ai_review import (
    InternalQwenConfig,
    InternalQwenScenarioPreparationProvider,
)
from treeguard.tree_understanding import (
    SCENARIO_FAMILY_ORDER,
    SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
    NewNodePlacementSeed,
    build_scenario_preparation_plan,
    build_scenario_preparation_projection,
    build_tree_diagnostic_profile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "fictional"
TREE_CASES = (
    (
        "control",
        FIXTURE_ROOT / "qinglan_library_control" / "tree.json",
        48,
    ),
    (
        "semantic",
        FIXTURE_ROOT / "qinglan_library_semantic" / "tree.json",
        312,
    ),
    (
        "production_shape",
        FIXTURE_ROOT / "qinglan_library_production_shape" / "tree.json",
        2_001,
    ),
)
OVERLAY_PATH = (
    FIXTURE_ROOT
    / "qinglan_tree_understanding_m3"
    / "new-node-placement-overlay.json"
)


def _tree(path: Path):
    result = load_tree_export(path)
    if result.tree is None:
        raise AssertionError([issue.code for issue in result.issues])
    return result.tree


def _overlay_seed(tree) -> NewNodePlacementSeed:
    overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version",
        "overlay_ref",
        "source_fixture_ref",
        "source_snapshot_hash",
        "scenario_family",
        "planning_mode",
        "target_stage",
        "fictional",
        "derived_from_real",
        "gold_eligible",
        "patch_eligible",
        "new_node_placement_seed",
    }
    if set(overlay) != expected_keys:
        raise AssertionError("M3 overlay fields changed without a contract update")
    if overlay["source_snapshot_hash"] != tree.snapshot_hash:
        raise AssertionError("M3 overlay no longer matches the semantic tree")
    seed = overlay["new_node_placement_seed"]
    return NewNodePlacementSeed(
        parent_node_id=seed["parent_node_id"],
        proposed_name=seed["proposed_name"],
        node_kind_hint=seed["node_kind_hint"],
        value_type_hint=seed["value_type_hint"],
        cardinality_hint=seed["cardinality_hint"],
    )


def _model_output_from_request(body: dict[str, object]) -> dict[str, object]:
    messages = body["messages"]
    user_payload = json.loads(messages[1]["content"])  # type: ignore[index]
    projection = user_payload["scenario_projection"]
    assignment = projection["assignment"]
    primary_ref = assignment["primary_anchor_ref"]
    node = next(
        item for item in projection["nodes"] if item["node_ref"] == primary_ref
    )
    subject = assignment["proposed_new_node_name"] or node["name"]
    scenario_family = assignment["scenario_family"]
    signal_refs = [item["signal_ref"] for item in projection["signals"]]
    return {
        "schema_version": SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
        "plan_unit_ref": assignment["plan_unit_ref"],
        "scenario_ref": "S001",
        "planning_mode": assignment["planning_mode"],
        "scenario_family": scenario_family,
        "target_stage": assignment["target_stage"],
        "requirement_text": f"请围绕“{subject}”准备一条结构建模需求。",
        "proposed_parent_ref": assignment["proposed_parent_ref"],
        "node_kind_hint": assignment["node_kind_hint"],
        "value_type_hint": assignment["value_type_hint"],
        "cardinality_hint": assignment["cardinality_hint"],
        "supporting_node_refs": [primary_ref],
        "source_signal_refs": signal_refs,
        "requested_aspects": [
            {
                "aspect": "单一结构诉求",
                "supporting_node_refs": [primary_ref],
            }
        ],
        "rationale": "该候选只引用当前有界投影中的主要结构锚点。",
        "uncertainties": (
            ["当前需求仍需补充有界上下文或范围。"]
            if scenario_family
            in {"HOMONYM_CLARIFICATION", "UNBOUNDED_COMBINATION"}
            else []
        ),
        "evidence_gaps": (
            ["当前结构没有提供完成业务判断所需的证据。"]
            if scenario_family == "INSUFFICIENT_EVIDENCE"
            else []
        ),
    }


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for item in value.values() for key in _nested_keys(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in _nested_keys(item)}
    return set()


class QinglanScenarioPreparationTests(unittest.TestCase):
    def test_three_existing_trees_are_primary_plan_inputs(self) -> None:
        for name, path, expected_nodes in TREE_CASES:
            with self.subTest(name=name):
                tree = _tree(path)
                profile = build_tree_diagnostic_profile(tree)
                seed = _overlay_seed(tree) if name == "semantic" else None
                plan = build_scenario_preparation_plan(
                    tree,
                    profile,
                    new_node_placement_seed=seed,
                )

                self.assertEqual(profile.node_count, expected_nodes)
                self.assertLessEqual(len(plan.units), 16)
                self.assertEqual(
                    plan.family_statuses["NEW_NODE_PLACEMENT"],
                    "PLANNED" if name == "semantic" else "NOT_APPLICABLE",
                )
                self.assertTrue(
                    all(
                        plan.family_statuses[family]
                        in {"PLANNED", "NOT_APPLICABLE"}
                        for family in SCENARIO_FAMILY_ORDER
                    )
                )
                projections = tuple(
                    build_scenario_preparation_projection(
                        tree,
                        profile,
                        plan,
                        unit.plan_unit_ref,
                    )
                    for unit in plan.units
                )
                for projection in projections:
                    self.assertLessEqual(projection.included_node_count, 48)
                    if expected_nodes > 48:
                        self.assertGreater(projection.omitted_node_count, 0)

                reordered = replace(tree, nodes=tuple(reversed(tree.nodes)))
                reordered_profile = build_tree_diagnostic_profile(reordered)
                reordered_plan = build_scenario_preparation_plan(
                    reordered,
                    reordered_profile,
                    new_node_placement_seed=seed,
                )
                self.assertEqual(plan, reordered_plan)
                reordered_projections = tuple(
                    build_scenario_preparation_projection(
                        reordered,
                        reordered_profile,
                        reordered_plan,
                        unit.plan_unit_ref,
                    )
                    for unit in reordered_plan.units
                )
                self.assertEqual(projections, reordered_projections)
                self.assertEqual(
                    tuple(item.to_model_dict() for item in projections),
                    tuple(
                        item.to_model_dict()
                        for item in reordered_projections
                    ),
                )

    def test_structure_extremes_and_diversity_select_stable_branches(self) -> None:
        tree = _tree(TREE_CASES[1][1])
        profile = build_tree_diagnostic_profile(tree)
        plan = build_scenario_preparation_plan(
            tree,
            profile,
            max_plan_units=10,
        )
        branch_units = tuple(
            unit.allowed_branch_node_ids[0]
            for unit in plan.units
            if unit.unit_role == "BRANCH_COVERAGE"
        )

        # ql-003 is the largest remaining branch, qs-ops is the deepest,
        # and ql-009 is the deterministic normalized-vector diversity pick.
        self.assertEqual(branch_units, ("ql-003", "qs-ops", "ql-009"))
        self.assertEqual(plan.omitted_branch_node_ids, ("ql-004", "ql-005"))

        reordered = replace(tree, nodes=tuple(reversed(tree.nodes)))
        reordered_profile = build_tree_diagnostic_profile(reordered)
        reordered_plan = build_scenario_preparation_plan(
            reordered,
            reordered_profile,
            max_plan_units=10,
        )
        self.assertEqual(plan, reordered_plan)
        self.assertEqual(
            plan.omitted_branch_node_ids,
            reordered_plan.omitted_branch_node_ids,
        )

    def test_overlay_is_independent_non_gold_and_absent_from_base_tree(self) -> None:
        tree = _tree(TREE_CASES[1][1])
        overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "scenario-preparation-overlay.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        seed = _overlay_seed(tree)

        self.assertEqual(overlay["schema_version"], "scenario-preparation-overlay.v1")
        self.assertEqual(set(schema["required"]), set(overlay))
        self.assertEqual(
            set(schema["$defs"]["newNodePlacementSeed"]["required"]),
            set(overlay["new_node_placement_seed"]),
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(
            schema["$defs"]["newNodePlacementSeed"]["additionalProperties"]
        )
        self.assertEqual(overlay["scenario_family"], "NEW_NODE_PLACEMENT")
        self.assertEqual(overlay["planning_mode"], "BRANCH_LOCAL")
        self.assertEqual(overlay["target_stage"], "RECOMMENDATION")
        self.assertTrue(overlay["fictional"])
        self.assertFalse(overlay["derived_from_real"])
        self.assertFalse(overlay["gold_eligible"])
        self.assertFalse(overlay["patch_eligible"])
        self.assertIn(seed.parent_node_id, {node.node_id for node in tree.nodes})
        self.assertNotIn(
            seed.proposed_name.casefold(),
            {" ".join(node.name.casefold().split()) for node in tree.nodes},
        )
        self.assertNotIn("requirement_text", overlay)
        self.assertNotIn("oracle", overlay)

    def test_fixture_replay_uses_hidden_references_only_after_generation(self) -> None:
        tree = _tree(TREE_CASES[1][1])
        profile = build_tree_diagnostic_profile(tree)
        plan = build_scenario_preparation_plan(
            tree,
            profile,
            new_node_placement_seed=_overlay_seed(tree),
        )
        provider = InternalQwenScenarioPreparationProvider(
            InternalQwenConfig(
                base_url="http://10.20.30.40:8000/v1",
                model="fictional-qwen",
            ),
            preparation_source_status="FIXTURE_REPLAY",
        )
        sent: list[dict[str, object]] = []

        def fake_post(body: dict[str, object]) -> dict[str, object]:
            sent.append(body)
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                _model_output_from_request(body),
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            }

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(batch.status, "SUCCESS")
        self.assertEqual(batch.preparation_source_status, "FIXTURE_REPLAY")
        self.assertEqual(batch.review_status, "PENDING_HUMAN_REVIEW")
        self.assertFalse(batch.semantic_approval)
        self.assertFalse(batch.gold_eligible)
        self.assertFalse(batch.patch_eligible)
        self.assertEqual(batch.completed_unit_count, len(plan.units))
        self.assertEqual(len(sent), len(plan.units))

        # Hidden references are deliberately opened only after the batch exists.
        scenario_path = (
            FIXTURE_ROOT / "qinglan_library_semantic" / "scenarios.json"
        )
        hidden_scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
        hidden_by_ref = {item["scenario_ref"]: item for item in hidden_scenarios}
        hidden_mapping = {
            "CLEAR_EXISTING_REUSE": ("QS-C01", "CLEAR_INTENT"),
            "HOMONYM_CLARIFICATION": ("QS-C02", "HOMONYM"),
            "WRONG_PARENT_OR_CROSS_BRANCH": ("QS-C06", "WRONG_PARENT_HINT"),
            "KIND_CONFLICT": ("QS-C04", "KIND_CONFLICT"),
            "CARDINALITY_CONFLICT": ("QS-C05", "CARDINALITY_CONFLICT"),
            "INSUFFICIENT_EVIDENCE": ("QS-C08", "INSUFFICIENT_EVIDENCE"),
            "UNBOUNDED_COMBINATION": ("QS-C10", "REFUSAL"),
        }
        for family, (scenario_ref, old_risk) in hidden_mapping.items():
            self.assertEqual(plan.family_statuses[family], "PLANNED")
            self.assertEqual(hidden_by_ref[scenario_ref]["primary_risk"], old_risk)
            self.assertFalse(hidden_by_ref[scenario_ref]["gold_eligible"])

        encoded_requests = json.dumps(sent, ensure_ascii=False, sort_keys=True)
        for scenario in hidden_scenarios:
            self.assertNotIn(scenario["scenario_ref"], encoded_requests)
            self.assertNotIn(
                scenario["request"]["requirement_text"],
                encoded_requests,
            )
        request_payloads = [
            json.loads(body["messages"][1]["content"])  # type: ignore[index]
            for body in sent
        ]
        request_keys = {
            key for payload in request_payloads for key in _nested_keys(payload)
        }
        for forbidden_key in (
            "expected_observable_category",
            "promotion_record_version",
            "human_review",
            "replay_of",
        ):
            self.assertNotIn(forbidden_key, request_keys)
        for forbidden_value in (
            "CLEAR_INTENT",
            "WRONG_PARENT_HINT",
        ):
            self.assertNotIn(forbidden_value, encoded_requests)


if __name__ == "__main__":
    unittest.main()
