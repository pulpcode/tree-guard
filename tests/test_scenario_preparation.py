from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import adapt_tree_document
from treeguard.hashing import canonical_digest
from treeguard.tree_understanding import (
    MAX_PLAN_UNITS,
    SCENARIO_PROJECTION_UNIT_FAILURE_CODES,
    SCENARIO_BATCH_SCHEMA_VERSION,
    SCENARIO_CANDIDATE_SCHEMA_VERSION,
    SCENARIO_FAMILY_ORDER,
    SCENARIO_MODEL_INPUT_SCHEMA_VERSION,
    SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
    SCENARIO_PLAN_SCHEMA_VERSION,
    NewNodePlacementSeed,
    ScenarioCandidateDraft,
    ScenarioPreparationFailure,
    ScenarioPreparationNotExecuted,
    TreeUnderstandingError,
    build_scenario_preparation_batch,
    build_scenario_preparation_plan,
    build_scenario_preparation_projection,
    build_tree_diagnostic_profile,
    verify_scenario_preparation_batch_against_sources,
    verify_scenario_preparation_plan_against_sources,
    verify_scenario_preparation_projection_against_sources,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_REQUIREMENT_TEXT__"
)
ASPECT_TEMPLATE_SENTINEL = "__TREEGUARD_MUST_REWRITE_REQUESTED_ASPECT__"
RATIONALE_TEMPLATE_SENTINEL = "__TREEGUARD_MUST_REWRITE_RATIONALE__"
EVIDENCE_GAP_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_EVIDENCE_GAP__"
)


def _node(
    node_id: str,
    parent_node_id: str | None,
    label: str,
    name: str,
    path: tuple[str, ...],
    order: int,
    *,
    value_type: str | None = None,
    multiple: bool = False,
    children: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "node_id": node_id,
        "node_type": "property" if value_type is not None else "concept",
        "node_name": name,
        "node_label": label,
        "node_label_route": "/-/".join((*path, label)),
        "node_order": order,
        "extension": {"must_not_reach_model": "canary"},
    }
    if parent_node_id is not None:
        metadata["parent_node_id"] = parent_node_id
    if value_type is not None:
        metadata.update(
            {
                "value_type": value_type,
                "is_list": multiple,
                "value_constraints": {"raw_constraints": {}},
            }
        )
    wrapper: dict[str, object] = {"metadata": metadata}
    if children:
        wrapper["subnodes"] = {
            child["metadata"]["node_label"]: child  # type: ignore[index]
            for child in children
        }
    return wrapper


def _scenario_tree():
    root_label = "ATLAS_ROOT"

    def branch(
        prefix: str,
        order: int,
        shared_multiple: bool,
        *,
        add_depth: bool,
    ) -> dict[str, object]:
        branch_label = f"{prefix.upper()}_BRANCH"
        branch_id = f"{prefix}-branch"
        shared = _node(
            f"{prefix}-shared",
            branch_id,
            f"{prefix.upper()}_SHARED",
            "Shared signal",
            (root_label, branch_label),
            1,
            value_type="string",
            multiple=shared_multiple,
        )
        children: tuple[dict[str, object], ...]
        if add_depth:
            container_label = f"{prefix.upper()}_CONTAINER"
            container_id = f"{prefix}-container"
            container = _node(
                container_id,
                branch_id,
                container_label,
                f"{prefix.title()} container",
                (root_label, branch_label),
                2,
                children=(
                    _node(
                        f"{prefix}-deep",
                        container_id,
                        f"{prefix.upper()}_DEEP",
                        f"{prefix.title()} deep marker",
                        (root_label, branch_label, container_label),
                        1,
                        value_type="integer",
                    ),
                ),
            )
            children = (shared, container)
        else:
            children = (shared,)
        return _node(
            branch_id,
            "atlas-root",
            branch_label,
            f"{prefix.title()} atlas",
            (root_label,),
            order,
            children=children,
        )

    document = {
        "metadata": {
            "id": "fictional-scenario-version",
            "map_id": "fictional-scenario-tree",
            "map_type": "resource",
            "map_name": "Entirely imaginary scenario atlas",
            "version": "V1",
            "category_id": "fictional-scenario-category",
            "concurrent_version": 1,
        },
        "map_topology": {
            root_label: _node(
                "atlas-root",
                None,
                root_label,
                "Imaginary scenario atlas",
                (),
                1,
                children=(
                    branch("alpha", 1, False, add_depth=False),
                    branch("beta", 2, True, add_depth=True),
                    branch("gamma", 3, False, add_depth=True),
                ),
            )
        },
    }
    result = adapt_tree_document(document)
    if result.tree is None:
        raise AssertionError([issue.code for issue in result.issues])
    return result.tree


def _seed() -> NewNodePlacementSeed:
    return NewNodePlacementSeed(
        parent_node_id="alpha-branch",
        proposed_name="Novel beacon",
        node_kind_hint="PROPERTY",
        value_type_hint="string",
        cardinality_hint="SINGLE",
    )


def _model_output(projection) -> dict[str, object]:
    supporting_refs = [projection.primary_anchor_ref]
    uncertainties = (
        ["当前结构存在必须由用户澄清的上下文不确定性。"]
        if projection.scenario_family
        in {"HOMONYM_CLARIFICATION", "UNBOUNDED_COMBINATION"}
        else []
    )
    evidence_gaps = (
        ["当前树结构不包含完成该业务判断所需的证据。"]
        if projection.scenario_family == "INSUFFICIENT_EVIDENCE"
        else []
    )
    return {
        "schema_version": SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
        "plan_unit_ref": projection.plan_unit_ref,
        "scenario_ref": "S001",
        "planning_mode": projection.planning_mode,
        "scenario_family": projection.scenario_family,
        "target_stage": projection.target_stage,
        "requirement_text": "请根据当前结构准备一个单一的字段建模需求。",
        "proposed_parent_ref": projection.proposed_parent_ref,
        "node_kind_hint": projection.node_kind_hint,
        "value_type_hint": projection.value_type_hint,
        "cardinality_hint": projection.cardinality_hint,
        "supporting_node_refs": supporting_refs,
        "source_signal_refs": list(projection.signal_refs),
        "requested_aspects": [
            {
                "aspect": "单一结构诉求",
                "supporting_node_refs": supporting_refs,
            }
        ],
        "rationale": "投影中的结构锚点能够支持这个候选需求。",
        "uncertainties": uncertainties,
        "evidence_gaps": evidence_gaps,
    }


def _draft(tree, profile, plan, unit_ref: str) -> ScenarioCandidateDraft:
    projection = build_scenario_preparation_projection(
        tree,
        profile,
        plan,
        unit_ref,
    )
    return ScenarioCandidateDraft.from_model_dict(
        _model_output(projection),
        projection,
        plan,
        profile,
        tree,
        model_provider="fictional-provider",
        model_capability="scenario-preparation",
        model_name="fictional-model",
        prompt_version="scenario-prompt.v1",
    )


def _all_projections(tree, profile, plan):
    return tuple(
        build_scenario_preparation_projection(
            tree,
            profile,
            plan,
            unit.plan_unit_ref,
        )
        for unit in plan.units
    )


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for item in value.values()
            for key in _keys(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


class ScenarioPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = _scenario_tree()
        self.profile = build_tree_diagnostic_profile(self.tree)

    def test_plan_is_risk_first_seeded_and_storage_order_independent(self) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            new_node_placement_seed=_seed(),
        )
        self.assertEqual(tuple(plan.family_statuses), SCENARIO_FAMILY_ORDER)
        self.assertTrue(
            all(
                plan.family_statuses[family] == "PLANNED"
                for family in SCENARIO_FAMILY_ORDER
            )
        )
        risk_units = tuple(
            unit for unit in plan.units if unit.unit_role == "RISK_CHALLENGE"
        )
        self.assertEqual(
            tuple(unit.scenario_family for unit in risk_units),
            SCENARIO_FAMILY_ORDER,
        )
        stage_by_family = {
            unit.scenario_family: unit.target_stage for unit in risk_units
        }
        self.assertEqual(stage_by_family["CLEAR_EXISTING_REUSE"], "RETRIEVAL")
        self.assertEqual(stage_by_family["HOMONYM_CLARIFICATION"], "INTENT")
        self.assertEqual(stage_by_family["KIND_CONFLICT"], "RECOMMENDATION")
        self.assertEqual(stage_by_family["CARDINALITY_CONFLICT"], "RECOMMENDATION")

        reordered_tree = replace(self.tree, nodes=tuple(reversed(self.tree.nodes)))
        reordered_profile = build_tree_diagnostic_profile(reordered_tree)
        reordered_plan = build_scenario_preparation_plan(
            reordered_tree,
            reordered_profile,
            new_node_placement_seed=_seed(),
        )
        self.assertEqual(plan, reordered_plan)
        verify_scenario_preparation_plan_against_sources(
            plan,
            self.profile,
            self.tree,
        )
        self.assertEqual(
            type(plan).from_dict(plan.to_dict(), self.profile, self.tree),
            plan,
        )
        tampered = plan.to_dict()
        tampered["units"][0]["target_stage"] = "INTENT"
        tampered_payload = dict(tampered)
        tampered_payload.pop("plan_hash")
        tampered["plan_hash"] = canonical_digest(tampered_payload)
        with self.assertRaises(TreeUnderstandingError) as caught:
            type(plan).from_dict(tampered, self.profile, self.tree)
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_PLAN_SOURCE_MISMATCH",
        )

    def test_new_node_family_requires_an_explicit_absent_name_seed(self) -> None:
        unseeded = build_scenario_preparation_plan(self.tree, self.profile)
        self.assertEqual(
            unseeded.family_statuses["NEW_NODE_PLACEMENT"],
            "NOT_APPLICABLE",
        )
        existing_name_seed = replace(_seed(), proposed_name="  shared SIGNAL ")
        with self.assertRaises(TreeUnderstandingError) as caught:
            build_scenario_preparation_plan(
                self.tree,
                self.profile,
                new_node_placement_seed=existing_name_seed,
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_NEW_NODE_SEED_INVALID",
        )

    def test_plan_limits_reject_bool_and_values_above_hard_bound(self) -> None:
        hard_limit_plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            max_plan_units=MAX_PLAN_UNITS,
        )
        self.assertEqual(hard_limit_plan.max_plan_units, MAX_PLAN_UNITS)
        self.assertLessEqual(len(hard_limit_plan.units), MAX_PLAN_UNITS)

        for value in (True, MAX_PLAN_UNITS + 1):
            with self.subTest(value=value):
                with self.assertRaises(TreeUnderstandingError) as caught:
                    build_scenario_preparation_plan(
                        self.tree,
                        self.profile,
                        max_plan_units=value,
                    )
                self.assertEqual(
                    caught.exception.code,
                    "SCENARIO_PREPARATION_PLAN_UNIT_LIMIT_INVALID",
                )

    def test_root_child_name_reuse_is_not_a_cross_branch_homonym(self) -> None:
        root_label = "ECHO_ROOT"
        document = {
            "metadata": {
                "id": "fictional-root-child-version",
                "map_id": "fictional-root-child-tree",
                "map_type": "resource",
                "map_name": "Entirely imaginary root-child homonym",
                "version": "V1",
                "category_id": "fictional-root-child-category",
                "concurrent_version": 1,
            },
            "map_topology": {
                root_label: _node(
                    "echo-root",
                    None,
                    root_label,
                    "Echo marker",
                    (),
                    1,
                    children=(
                        _node(
                            "echo-branch",
                            "echo-root",
                            "ECHO_BRANCH",
                            "Echo marker",
                            (root_label,),
                            1,
                            children=(
                                _node(
                                    "echo-property",
                                    "echo-branch",
                                    "ECHO_PROPERTY",
                                    "Echo detail",
                                    (root_label, "ECHO_BRANCH"),
                                    1,
                                    value_type="string",
                                ),
                            ),
                        ),
                    ),
                )
            },
        }
        result = adapt_tree_document(document)
        self.assertIsNotNone(result.tree)
        tree = result.tree
        if tree is None:
            raise AssertionError("fictional root-child tree failed adaptation")
        profile = build_tree_diagnostic_profile(tree)
        self.assertTrue(
            any(
                finding.code == "NAME_REUSED_ACROSS_PATHS"
                for finding in profile.findings
            )
        )

        plan = build_scenario_preparation_plan(tree, profile)

        self.assertEqual(
            plan.family_statuses["HOMONYM_CLARIFICATION"],
            "NOT_APPLICABLE",
        )
        for unit in plan.units:
            build_scenario_preparation_projection(
                tree,
                profile,
                plan,
                unit.plan_unit_ref,
            )

    def test_projection_is_bounded_replayable_and_has_no_internal_view(
        self,
    ) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            node_limit=6,
            new_node_placement_seed=_seed(),
        )
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U002",
        )
        self.assertLessEqual(projection.included_node_count, 6)
        self.assertGreater(projection.omitted_node_count, 0)
        verify_scenario_preparation_projection_against_sources(
            projection,
            plan,
            self.profile,
            self.tree,
        )
        model_view = projection.to_model_dict()
        self.assertEqual(
            model_view["schema_version"],
            SCENARIO_MODEL_INPUT_SCHEMA_VERSION,
        )
        forbidden = {
            "node_id",
            "source_snapshot_hash",
            "source_profile_hash",
            "source_plan_hash",
            "projection_hash",
            "path",
            "path_labels",
            "label",
            "route",
            "source_route",
            "VALUE",
            "value",
            "extension",
            "metadata",
            "metadata_extra",
        }
        self.assertFalse(_keys(model_view) & forbidden)
        serialized = json.dumps(model_view, ensure_ascii=False)
        self.assertNotIn("alpha-branch", serialized)
        self.assertNotIn("must_not_reach_model", serialized)

        reordered_tree = replace(
            self.tree,
            nodes=tuple(reversed(self.tree.nodes)),
        )
        reordered_profile = build_tree_diagnostic_profile(reordered_tree)
        reordered_plan = build_scenario_preparation_plan(
            reordered_tree,
            reordered_profile,
            node_limit=6,
            new_node_placement_seed=_seed(),
        )
        reordered_projection = build_scenario_preparation_projection(
            reordered_tree,
            reordered_profile,
            reordered_plan,
            "U002",
        )
        self.assertEqual(projection, reordered_projection)
        self.assertEqual(
            projection.to_model_dict(),
            reordered_projection.to_model_dict(),
        )
        self.assertEqual(
            projection.projection_hash,
            reordered_projection.projection_hash,
        )

    def test_candidate_parser_is_exact_source_bound_and_pending_only(self) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            new_node_placement_seed=_seed(),
        )
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U002",
        )
        draft = ScenarioCandidateDraft.from_model_dict(
            _model_output(projection),
            projection,
            plan,
            self.profile,
            self.tree,
            model_provider="fictional-provider",
            model_capability="scenario-preparation",
            model_name="fictional-model",
            prompt_version="scenario-prompt.v1",
        )
        self.assertEqual(draft.review_status, "PENDING_HUMAN_REVIEW")
        self.assertFalse(draft.semantic_approval)
        self.assertFalse(draft.gold_eligible)
        self.assertFalse(draft.patch_eligible)
        self.assertEqual(
            draft.proposed_parent_ref,
            projection.proposed_parent_ref,
        )
        self.assertEqual(draft.node_kind_hint, "PROPERTY")
        self.assertEqual(draft.value_type_hint, "string")
        self.assertEqual(draft.cardinality_hint, "SINGLE")
        self.assertEqual(
            ScenarioCandidateDraft.from_dict(
                draft.to_dict(),
                projection,
                plan,
                self.profile,
                self.tree,
            ),
            draft,
        )

        extra = _model_output(projection)
        extra["oracle"] = "model must not choose this"
        with self.assertRaises(TreeUnderstandingError) as caught:
            ScenarioCandidateDraft.from_model_dict(
                extra,
                projection,
                plan,
                self.profile,
                self.tree,
                model_provider="fictional-provider",
                model_capability="scenario-preparation",
                model_name="fictional-model",
                prompt_version="scenario-prompt.v1",
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_MODEL_FIELDS_INVALID",
        )

    def test_candidate_rejects_plan_echo_and_projection_ref_changes(self) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            new_node_placement_seed=_seed(),
        )
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U003",
        )
        changed_echo = _model_output(projection)
        changed_echo["scenario_family"] = "CLEAR_EXISTING_REUSE"
        with self.assertRaises(TreeUnderstandingError) as caught:
            ScenarioCandidateDraft.from_model_dict(
                changed_echo,
                projection,
                plan,
                self.profile,
                self.tree,
                model_provider="fictional-provider",
                model_capability="scenario-preparation",
                model_name="fictional-model",
                prompt_version="scenario-prompt.v1",
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_MODEL_PLAN_ECHO_INVALID",
        )

        changed_ref = _model_output(projection)
        changed_ref["supporting_node_refs"] = ["N999"]
        changed_ref["requested_aspects"] = [
            {"aspect": "越界引用", "supporting_node_refs": ["N999"]}
        ]
        with self.assertRaises(TreeUnderstandingError) as caught:
            ScenarioCandidateDraft.from_model_dict(
                changed_ref,
                projection,
                plan,
                self.profile,
                self.tree,
                model_provider="fictional-provider",
                model_capability="scenario-preparation",
                model_name="fictional-model",
                prompt_version="scenario-prompt.v1",
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_MODEL_NODE_REF_INVALID",
        )

    def test_planning_modes_reject_non_evidence_refs_and_preserve_ambiguity(
        self,
    ) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            new_node_placement_seed=_seed(),
        )
        units_by_mode = {
            mode: next(unit for unit in plan.units if unit.planning_mode == mode)
            for mode in ("BRANCH_LOCAL", "CONTRAST", "AMBIGUITY")
        }
        for mode, unit in units_by_mode.items():
            with self.subTest(mode=mode):
                projection = build_scenario_preparation_projection(
                    self.tree,
                    self.profile,
                    plan,
                    unit.plan_unit_ref,
                )
                non_evidence_refs = tuple(
                    sorted(set(projection.node_refs) - set(projection.evidence_node_refs))
                )
                self.assertTrue(non_evidence_refs)
                changed = _model_output(projection)
                changed["supporting_node_refs"] = [non_evidence_refs[0]]
                changed["requested_aspects"] = [
                    {
                        "aspect": "模式外上下文",
                        "supporting_node_refs": [non_evidence_refs[0]],
                    }
                ]
                with self.assertRaises(TreeUnderstandingError) as caught:
                    ScenarioCandidateDraft.from_model_dict(
                        changed,
                        projection,
                        plan,
                        self.profile,
                        self.tree,
                        model_provider="fictional-provider",
                        model_capability="scenario-preparation",
                        model_name="fictional-model",
                        prompt_version="scenario-prompt.v1",
                    )
                self.assertEqual(
                    caught.exception.code,
                    "SCENARIO_PREPARATION_MODEL_NODE_REF_INVALID",
                )

        ambiguity = units_by_mode["AMBIGUITY"]
        ambiguity_projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            ambiguity.plan_unit_ref,
        )
        self.assertEqual(ambiguity.parent_hint_policy, "ABSENT")
        self.assertIsNone(ambiguity_projection.proposed_parent_ref)
        ambiguity_draft = ScenarioCandidateDraft.from_model_dict(
            _model_output(ambiguity_projection),
            ambiguity_projection,
            plan,
            self.profile,
            self.tree,
            model_provider="fictional-provider",
            model_capability="scenario-preparation",
            model_name="fictional-model",
            prompt_version="scenario-prompt.v1",
        )
        self.assertIsNone(ambiguity_draft.proposed_parent_ref)

    def test_scenario_text_failures_use_scenario_error_codes(self) -> None:
        plan = build_scenario_preparation_plan(self.tree, self.profile)
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U001",
        )
        invalid_text = _model_output(projection)
        invalid_text["rationale"] = "invalid\x00text"
        with self.assertRaises(TreeUnderstandingError) as caught:
            ScenarioCandidateDraft.from_model_dict(
                invalid_text,
                projection,
                plan,
                self.profile,
                self.tree,
                model_provider="fictional-provider",
                model_capability="scenario-preparation",
                model_name="fictional-model",
                prompt_version="scenario-prompt.v1",
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
        )

    def test_candidate_rejects_every_unrewritten_template_sentinel(
        self,
    ) -> None:
        plan = build_scenario_preparation_plan(self.tree, self.profile)
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U001",
        )
        sentinels = (
            REQUIREMENT_TEMPLATE_SENTINEL,
            ASPECT_TEMPLATE_SENTINEL,
            RATIONALE_TEMPLATE_SENTINEL,
            EVIDENCE_GAP_TEMPLATE_SENTINEL,
        )
        for sentinel in sentinels:
            for target_field in (
                "requirement_text",
                "requested_aspect",
                "rationale",
                "uncertainties",
                "evidence_gaps",
            ):
                with self.subTest(
                    sentinel=sentinel,
                    target_field=target_field,
                ):
                    payload = _model_output(projection)
                    unrewritten_text = f"前缀 {sentinel} 后缀"
                    if target_field == "requested_aspect":
                        payload["requested_aspects"] = [
                            {
                                "aspect": unrewritten_text,
                                "supporting_node_refs": payload[
                                    "supporting_node_refs"
                                ],
                            }
                        ]
                    elif target_field in {"uncertainties", "evidence_gaps"}:
                        payload[target_field] = [unrewritten_text]
                    else:
                        payload[target_field] = unrewritten_text
                    with self.assertRaises(TreeUnderstandingError) as caught:
                        ScenarioCandidateDraft.from_model_dict(
                            payload,
                            projection,
                            plan,
                            self.profile,
                            self.tree,
                            model_provider="fictional-provider",
                            model_capability="scenario-preparation",
                            model_name="fictional-model",
                            prompt_version="scenario-prompt.v3",
                        )
                    self.assertEqual(
                        caught.exception.code,
                        "SCENARIO_PREPARATION_MODEL_TEXT_POLICY_INVALID",
                    )

    def test_all_natural_language_fields_reject_standalone_projection_refs(
        self,
    ) -> None:
        plan = build_scenario_preparation_plan(self.tree, self.profile)
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U001",
        )
        for projection_ref in ("N001", "D001", "S001"):
            for target_field in (
                "requirement_text",
                "requested_aspect",
                "rationale",
                "uncertainties",
                "evidence_gaps",
            ):
                with self.subTest(
                    projection_ref=projection_ref,
                    target_field=target_field,
                ):
                    payload = _model_output(projection)
                    temporary_reference_text = (
                        f"请围绕 {projection_ref} 准备结构建模需求。"
                    )
                    if target_field == "requested_aspect":
                        payload["requested_aspects"] = [
                            {
                                "aspect": temporary_reference_text,
                                "supporting_node_refs": payload[
                                    "supporting_node_refs"
                                ],
                            }
                        ]
                    elif target_field in {"uncertainties", "evidence_gaps"}:
                        payload[target_field] = [temporary_reference_text]
                    else:
                        payload[target_field] = temporary_reference_text
                    with self.assertRaises(TreeUnderstandingError) as caught:
                        ScenarioCandidateDraft.from_model_dict(
                            payload,
                            projection,
                            plan,
                            self.profile,
                            self.tree,
                            model_provider="fictional-provider",
                            model_capability="scenario-preparation",
                            model_name="fictional-model",
                            prompt_version="scenario-prompt.v3",
                        )
                    self.assertEqual(
                        caught.exception.code,
                        "SCENARIO_PREPARATION_MODEL_TEXT_POLICY_INVALID",
                    )

        allowed = _model_output(projection)
        allowed["requirement_text"] = "请为代号 N001A 准备结构建模需求。"
        allowed["requested_aspects"] = [
            {
                "aspect": "说明代号 D001A 的结构含义。",
                "supporting_node_refs": allowed["supporting_node_refs"],
            }
        ]
        allowed["rationale"] = "S001A 是业务代号，不是投影临时引用。"
        allowed["uncertainties"] = ["需要确认代号 N001A 的业务定义。"]
        allowed["evidence_gaps"] = ["尚缺少代号 D001A 的结构定义。"]
        draft = ScenarioCandidateDraft.from_model_dict(
            allowed,
            projection,
            plan,
            self.profile,
            self.tree,
            model_provider="fictional-provider",
            model_capability="scenario-preparation",
            model_name="fictional-model",
            prompt_version="scenario-prompt.v3",
        )
        self.assertIn(projection.primary_anchor_ref, draft.supporting_node_refs)

        with self.assertRaisesRegex(
            ValueError,
            "scenario candidate text policy is invalid",
        ):
            replace(draft, rationale="内部说明仍引用 N001。")

        stored_v2 = draft.to_dict()
        stored_v2["prompt_version"] = "treeguard.scenario-preparation.zh.v2"
        stored_v2["rationale"] = "历史说明仍引用 N001。"
        with self.assertRaises(TreeUnderstandingError) as caught:
            ScenarioCandidateDraft.from_dict(
                stored_v2,
                projection,
                plan,
                self.profile,
                self.tree,
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_MODEL_TEXT_POLICY_INVALID",
        )

    def test_structured_n_d_s_refs_remain_allowed_and_order_insensitive(
        self,
    ) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            new_node_placement_seed=_seed(),
        )
        contrast_unit = next(
            unit for unit in plan.units if unit.planning_mode == "CONTRAST"
        )
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            contrast_unit.plan_unit_ref,
        )
        reversed_refs = list(reversed(projection.anchor_refs))
        self.assertGreater(len(reversed_refs), 1)
        payload = _model_output(projection)
        payload["supporting_node_refs"] = reversed_refs
        payload["requested_aspects"] = [
            {
                "aspect": "对比两个有界结构上下文。",
                "supporting_node_refs": reversed_refs,
            }
        ]

        draft = ScenarioCandidateDraft.from_model_dict(
            payload,
            projection,
            plan,
            self.profile,
            self.tree,
            model_provider="fictional-provider",
            model_capability="scenario-preparation",
            model_name="fictional-model",
            prompt_version="scenario-prompt.v2",
        )

        self.assertEqual(draft.supporting_node_refs, tuple(sorted(reversed_refs)))
        self.assertEqual(
            draft.requested_aspects[0].supporting_node_refs,
            tuple(sorted(reversed_refs)),
        )
        self.assertEqual(draft.scenario_ref, "S001")
        self.assertTrue(
            all(ref.startswith("N") for ref in draft.supporting_node_refs)
        )
        self.assertTrue(draft.source_signal_refs)
        self.assertTrue(
            all(ref.startswith("D") for ref in draft.source_signal_refs)
        )

    def test_common_chinese_business_terms_are_not_text_policy_markers(
        self,
    ) -> None:
        plan = build_scenario_preparation_plan(self.tree, self.profile)
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U001",
        )
        payload = _model_output(projection)
        payload["requirement_text"] = "请为验证系统增加一项结构配置。"
        payload["requested_aspects"] = [
            {
                "aspect": "描述检索系统所需的结构字段。",
                "supporting_node_refs": payload["supporting_node_refs"],
            }
        ]
        payload["rationale"] = "主要锚点是该虚构业务中的正式结构概念。"
        payload["uncertainties"] = ["需要确认系统验证流程的结构边界。"]
        payload["evidence_gaps"] = ["尚缺检索配置的结构依据。"]

        draft = ScenarioCandidateDraft.from_model_dict(
            payload,
            projection,
            plan,
            self.profile,
            self.tree,
            model_provider="fictional-provider",
            model_capability="scenario-preparation",
            model_name="fictional-model",
            prompt_version="scenario-prompt.v3",
        )

        self.assertEqual(draft.requirement_text, payload["requirement_text"])

    def test_family_specific_disclosure_policy_is_minimal_and_exact(
        self,
    ) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            new_node_placement_seed=_seed(),
        )
        units_by_family = {
            unit.scenario_family: unit
            for unit in plan.units
            if unit.unit_role == "RISK_CHALLENGE"
        }

        for family in (
            "HOMONYM_CLARIFICATION",
            "UNBOUNDED_COMBINATION",
        ):
            with self.subTest(family=family, missing="uncertainties"):
                unit = units_by_family[family]
                projection = build_scenario_preparation_projection(
                    self.tree,
                    self.profile,
                    plan,
                    unit.plan_unit_ref,
                )
                payload = _model_output(projection)
                payload["uncertainties"] = []
                with self.assertRaises(TreeUnderstandingError) as caught:
                    ScenarioCandidateDraft.from_model_dict(
                        payload,
                        projection,
                        plan,
                        self.profile,
                        self.tree,
                        model_provider="fictional-provider",
                        model_capability="scenario-preparation",
                        model_name="fictional-model",
                        prompt_version="scenario-prompt.v2",
                    )
                self.assertEqual(
                    caught.exception.code,
                    "SCENARIO_PREPARATION_MODEL_FAMILY_POLICY_INVALID",
                )

                valid = _model_output(projection)
                draft = ScenarioCandidateDraft.from_model_dict(
                    valid,
                    projection,
                    plan,
                    self.profile,
                    self.tree,
                    model_provider="fictional-provider",
                    model_capability="scenario-preparation",
                    model_name="fictional-model",
                    prompt_version="scenario-prompt.v2",
                )
                self.assertTrue(draft.uncertainties)

        evidence_unit = units_by_family["INSUFFICIENT_EVIDENCE"]
        evidence_projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            evidence_unit.plan_unit_ref,
        )
        missing_evidence = _model_output(evidence_projection)
        missing_evidence["evidence_gaps"] = []
        with self.assertRaises(TreeUnderstandingError) as caught:
            ScenarioCandidateDraft.from_model_dict(
                missing_evidence,
                evidence_projection,
                plan,
                self.profile,
                self.tree,
                model_provider="fictional-provider",
                model_capability="scenario-preparation",
                model_name="fictional-model",
                prompt_version="scenario-prompt.v2",
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_MODEL_FAMILY_POLICY_INVALID",
        )
        valid_evidence = ScenarioCandidateDraft.from_model_dict(
            _model_output(evidence_projection),
            evidence_projection,
            plan,
            self.profile,
            self.tree,
            model_provider="fictional-provider",
            model_capability="scenario-preparation",
            model_name="fictional-model",
            prompt_version="scenario-prompt.v2",
        )
        self.assertTrue(valid_evidence.evidence_gaps)

        families_without_extra_disclosure = set(SCENARIO_FAMILY_ORDER) - {
            "HOMONYM_CLARIFICATION",
            "INSUFFICIENT_EVIDENCE",
            "UNBOUNDED_COMBINATION",
        }
        for family in sorted(families_without_extra_disclosure):
            with self.subTest(family=family, disclosure="not-required"):
                unit = units_by_family[family]
                projection = build_scenario_preparation_projection(
                    self.tree,
                    self.profile,
                    plan,
                    unit.plan_unit_ref,
                )
                payload = _model_output(projection)
                payload["uncertainties"] = []
                payload["evidence_gaps"] = []
                draft = ScenarioCandidateDraft.from_model_dict(
                    payload,
                    projection,
                    plan,
                    self.profile,
                    self.tree,
                    model_provider="fictional-provider",
                    model_capability="scenario-preparation",
                    model_name="fictional-model",
                    prompt_version="scenario-prompt.v2",
                )
                self.assertFalse(draft.uncertainties)
                self.assertFalse(draft.evidence_gaps)

    def test_batch_assigns_run_refs_and_reports_partial_and_failed(self) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            max_plan_units=3,
            new_node_placement_seed=_seed(),
        )
        first = _draft(self.tree, self.profile, plan, "U001")
        failures = (
            ScenarioPreparationFailure(
                plan_unit_ref="U002",
                error_code="FICTIONAL_MODEL_OUTPUT_INVALID",
            ),
        )
        not_executed = (
            ScenarioPreparationNotExecuted(
                plan_unit_ref="U003",
                reason_code="FICTIONAL_RUN_BUDGET_STOP",
            ),
        )
        projections = _all_projections(self.tree, self.profile, plan)
        partial = build_scenario_preparation_batch(
            plan,
            (first,),
            failures,
            not_executed,
            projections=projections,
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )
        self.assertEqual(partial.status, "PARTIAL")
        self.assertEqual(partial.candidates[0].candidate_ref, "C001")
        self.assertEqual(partial.candidates[0].draft.scenario_ref, "S001")
        self.assertEqual(partial.planned_unit_count, 3)
        self.assertEqual(partial.attempted_unit_count, 2)
        self.assertEqual(partial.completed_unit_count, 1)
        self.assertEqual(partial.failed_unit_count, 1)
        self.assertEqual(partial.not_executed_unit_count, 1)
        self.assertEqual(partial.not_executed[0].plan_unit_ref, "U003")
        self.assertGreater(partial.omitted_target_count, 0)
        self.assertEqual(partial.preparation_source_status, "FIXTURE_REPLAY")
        self.assertEqual(partial.review_status, "PENDING_HUMAN_REVIEW")
        self.assertFalse(partial.semantic_approval)
        self.assertFalse(partial.gold_eligible)
        self.assertFalse(partial.patch_eligible)
        self.assertEqual(
            partial.family_outcomes["CLEAR_EXISTING_REUSE"],
            "CANDIDATE_READY",
        )
        self.assertEqual(
            partial.family_outcomes["NEW_NODE_PLACEMENT"],
            "FAILED",
        )
        self.assertEqual(
            partial.family_outcomes["HOMONYM_CLARIFICATION"],
            "NOT_EXECUTED",
        )
        self.assertTrue(
            all(
                item.validation_status == "NOT_RUN"
                for item in partial.target_stage_coverage.values()
            )
        )
        unique_projected_node_ids = {
            node_id
            for projection in projections
            for node_id in projection.reference_to_node_id.values()
        }
        self.assertEqual(
            partial.projected_node_coverage.included_node_count,
            len(unique_projected_node_ids),
        )
        self.assertLess(
            partial.projected_node_coverage.included_node_count,
            sum(item.included_node_count for item in projections),
        )
        self.assertEqual(
            type(partial).from_dict(
                partial.to_dict(),
                plan,
                self.profile,
                self.tree,
            ),
            partial,
        )
        verify_scenario_preparation_batch_against_sources(
            partial,
            plan,
            self.profile,
            self.tree,
        )

        tampered = partial.to_dict()
        tampered_coverage = tampered["projected_node_coverage"]
        tampered_coverage["included_node_count"] -= 1
        tampered_coverage["omitted_node_count"] += 1
        tampered_payload = dict(tampered)
        tampered_payload.pop("batch_hash")
        tampered["batch_hash"] = canonical_digest(tampered_payload)
        with self.assertRaises(TreeUnderstandingError) as caught:
            type(partial).from_dict(
                tampered,
                plan,
                self.profile,
                self.tree,
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_BATCH_SOURCE_MISMATCH",
        )

        all_not_executed = tuple(
            ScenarioPreparationNotExecuted(
                plan_unit_ref=unit.plan_unit_ref,
                reason_code="FICTIONAL_RUN_NOT_ATTEMPTED",
            )
            for unit in reversed(plan.units)
        )
        skipped = build_scenario_preparation_batch(
            plan,
            (),
            (),
            all_not_executed,
            projections=reversed(projections),
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )
        reordered_skipped = build_scenario_preparation_batch(
            plan,
            (),
            (),
            reversed(all_not_executed),
            projections=projections,
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )
        self.assertEqual(skipped.status, "PARTIAL")
        self.assertEqual(skipped.attempted_unit_count, 0)
        self.assertEqual(skipped.failed_unit_count, 0)
        self.assertEqual(skipped, reordered_skipped)

        failed = build_scenario_preparation_batch(
            plan,
            (),
            tuple(
                ScenarioPreparationFailure(
                    plan_unit_ref=unit.plan_unit_ref,
                    error_code="FICTIONAL_MODEL_OUTPUT_INVALID",
                )
                for unit in plan.units
            ),
            projections=_all_projections(self.tree, self.profile, plan),
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.reviewable_candidate_count, 0)

    def test_family_and_branch_coverage_keep_distinct_semantics(self) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            new_node_placement_seed=_seed(),
        )
        projections = _all_projections(self.tree, self.profile, plan)
        clear_risk = next(
            unit
            for unit in plan.units
            if unit.unit_role == "RISK_CHALLENGE"
            and unit.scenario_family == "CLEAR_EXISTING_REUSE"
        )
        clear_branch = next(
            unit for unit in plan.units if unit.unit_role == "BRANCH_COVERAGE"
        )
        branch_candidate = _draft(
            self.tree,
            self.profile,
            plan,
            clear_branch.plan_unit_ref,
        )
        masked_family_batch = build_scenario_preparation_batch(
            plan,
            (branch_candidate,),
            (
                ScenarioPreparationFailure(
                    plan_unit_ref=clear_risk.plan_unit_ref,
                    error_code="FICTIONAL_MODEL_OUTPUT_INVALID",
                ),
            ),
            tuple(
                ScenarioPreparationNotExecuted(
                    plan_unit_ref=unit.plan_unit_ref,
                    reason_code="FICTIONAL_RUN_NOT_ATTEMPTED",
                )
                for unit in plan.units
                if unit.plan_unit_ref
                not in {clear_risk.plan_unit_ref, clear_branch.plan_unit_ref}
            ),
            projections=projections,
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )

        self.assertEqual(
            masked_family_batch.family_outcomes["CLEAR_EXISTING_REUSE"],
            "FAILED",
        )
        self.assertIn(
            clear_branch.allowed_branch_node_ids[0],
            masked_family_batch.branch_coverage.candidate_ready_branch_node_ids,
        )

        non_local_units = tuple(
            next(
                unit
                for unit in plan.units
                if unit.planning_mode == planning_mode
            )
            for planning_mode in ("CONTRAST", "AMBIGUITY")
        )
        non_local_refs = {unit.plan_unit_ref for unit in non_local_units}
        non_local_batch = build_scenario_preparation_batch(
            plan,
            tuple(
                _draft(
                    self.tree,
                    self.profile,
                    plan,
                    unit.plan_unit_ref,
                )
                for unit in non_local_units
            ),
            (),
            tuple(
                ScenarioPreparationNotExecuted(
                    plan_unit_ref=unit.plan_unit_ref,
                    reason_code="FICTIONAL_RUN_NOT_ATTEMPTED",
                )
                for unit in plan.units
                if unit.plan_unit_ref not in non_local_refs
            ),
            projections=projections,
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )

        self.assertEqual(
            non_local_batch.branch_coverage.candidate_ready_branch_node_ids,
            (),
        )

    def test_batch_replay_requires_the_exact_projection_failure_code(self) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            max_plan_units=2,
            node_limit=1,
        )
        failures: list[ScenarioPreparationFailure] = []
        projections = []
        for unit in plan.units:
            try:
                projection = build_scenario_preparation_projection(
                    self.tree,
                    self.profile,
                    plan,
                    unit.plan_unit_ref,
                )
            except TreeUnderstandingError as exc:
                self.assertIn(
                    exc.code,
                    SCENARIO_PROJECTION_UNIT_FAILURE_CODES,
                )
                failures.append(
                    ScenarioPreparationFailure(
                        plan_unit_ref=unit.plan_unit_ref,
                        error_code=exc.code,
                    )
                )
            else:
                projections.append(projection)
        self.assertTrue(failures)
        batch = build_scenario_preparation_batch(
            plan,
            (),
            failures,
            projections=projections,
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )
        self.assertEqual(
            type(batch).from_dict(
                batch.to_dict(),
                plan,
                self.profile,
                self.tree,
            ),
            batch,
        )

        tampered = batch.to_dict()
        actual_code = tampered["failures"][0]["error_code"]
        tampered["failures"][0]["error_code"] = next(
            code
            for code in SCENARIO_PROJECTION_UNIT_FAILURE_CODES
            if code != actual_code
        )
        tampered_payload = dict(tampered)
        tampered_payload.pop("batch_hash")
        tampered["batch_hash"] = canonical_digest(tampered_payload)
        with self.assertRaises(TreeUnderstandingError) as caught:
            type(batch).from_dict(
                tampered,
                plan,
                self.profile,
                self.tree,
            )
        self.assertEqual(
            caught.exception.code,
            "SCENARIO_PREPARATION_BATCH_PROJECTION_SOURCE_MISMATCH",
        )

    def test_schema_top_level_required_fields_match_serializers(self) -> None:
        plan = build_scenario_preparation_plan(
            self.tree,
            self.profile,
            max_plan_units=1,
        )
        projection = build_scenario_preparation_projection(
            self.tree,
            self.profile,
            plan,
            "U001",
        )
        draft = _draft(self.tree, self.profile, plan, "U001")
        batch = build_scenario_preparation_batch(
            plan,
            (draft,),
            (),
            projections=(projection,),
            source_node_count=self.profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )
        artifacts = (
            (
                "scenario-preparation-plan.v1.schema.json",
                SCENARIO_PLAN_SCHEMA_VERSION,
                plan.to_dict(),
            ),
            (
                "scenario-preparation-model-input.v1.schema.json",
                SCENARIO_MODEL_INPUT_SCHEMA_VERSION,
                projection.to_model_dict(),
            ),
            (
                "scenario-preparation-model-output.v1.schema.json",
                SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
                draft.to_model_dict(),
            ),
            (
                "scenario-preparation-candidate.v1.schema.json",
                SCENARIO_CANDIDATE_SCHEMA_VERSION,
                draft.to_dict(),
            ),
            (
                "scenario-preparation-batch.v1.schema.json",
                SCENARIO_BATCH_SCHEMA_VERSION,
                batch.to_dict(),
            ),
        )
        for filename, version, payload in artifacts:
            with self.subTest(filename=filename):
                schema = json.loads((PROJECT_ROOT / "contracts" / filename).read_text())
                self.assertEqual(
                    schema["properties"]["schema_version"]["const"],
                    version,
                )
                self.assertEqual(set(schema["required"]), set(payload))
                self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
