from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import adapt_tree_document
from treeguard.hashing import canonical_digest
from treeguard.tree_understanding import (
    ALGORITHM_VERSION,
    DRAFT_SCHEMA_VERSION,
    MODEL_INPUT_SCHEMA_VERSION,
    MODEL_OUTPUT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    TreeDiagnosticFinding,
    TreeDiagnosticProfile,
    TreeUnderstandingDraft,
    TreeUnderstandingError,
    build_tree_understanding_projection,
    build_tree_diagnostic_profile,
    verify_tree_understanding_projection_against_sources,
    verify_tree_diagnostic_profile_against_tree,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source_node(
    *,
    node_id: str,
    parent_node_id: str | None,
    label: str,
    name: str,
    path: tuple[str, ...],
    order: int,
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
        "extension": {},
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


def _fictional_tree():
    root_label = "LATTICE_ROOT"

    def branch(prefix: str, order: int, signal_type: str, signal_multiple: bool):
        profile_id = f"{prefix}-profile"
        profile_label = f"{prefix.upper()}_PROFILE"
        profile = _source_node(
            node_id=profile_id,
            parent_node_id=f"{prefix}-branch",
            label=profile_label,
            name=f"{prefix.title()} blueprint",
            path=(root_label, f"{prefix.upper()}_BRANCH"),
            order=2,
            value_type="class",
            children=(
                _source_node(
                    node_id=f"{prefix}-phase",
                    parent_node_id=profile_id,
                    label=f"{prefix.upper()}_PHASE",
                    name="Phase",
                    path=(
                        root_label,
                        f"{prefix.upper()}_BRANCH",
                        profile_label,
                    ),
                    order=1,
                    value_type="string",
                ),
                _source_node(
                    node_id=f"{prefix}-mode",
                    parent_node_id=profile_id,
                    label=f"{prefix.upper()}_MODE",
                    name="Mode",
                    path=(
                        root_label,
                        f"{prefix.upper()}_BRANCH",
                        profile_label,
                    ),
                    order=2,
                    value_type="string",
                    multiple=True,
                ),
            ),
        )
        return _source_node(
            node_id=f"{prefix}-branch",
            parent_node_id="lattice-root",
            label=f"{prefix.upper()}_BRANCH",
            name=f"{prefix.title()} lattice",
            path=(root_label,),
            order=order,
            children=(
                _source_node(
                    node_id=f"{prefix}-signal",
                    parent_node_id=f"{prefix}-branch",
                    label=f"{prefix.upper()}_SIGNAL",
                    name="Signal",
                    path=(root_label, f"{prefix.upper()}_BRANCH"),
                    order=1,
                    value_type=signal_type,
                    multiple=signal_multiple,
                ),
                profile,
            ),
        )

    document = {
        "metadata": {
            "id": "fictional-version-record",
            "map_id": "sensitive-tree-ref-canary",
            "map_type": "resource",
            "map_name": "Entirely imaginary lattice",
            "version": "V1",
            "category_id": "fictional-category",
            "concurrent_version": 1,
        },
        "map_topology": {
            root_label: _source_node(
                node_id="lattice-root",
                parent_node_id=None,
                label=root_label,
                name="Imaginary lattice",
                path=(),
                order=1,
                children=(
                    branch("alpha", 1, "string", False),
                    branch("beta", 2, "integer", True),
                ),
            )
        },
    }
    result = adapt_tree_document(document)
    if result.tree is None:
        raise AssertionError(
            f"fictional tree failed adaptation: {[issue.code for issue in result.issues]}"
        )
    return result.tree


def _wide_fictional_tree(node_count: int):
    root_label = "SCALE_ROOT"
    children = tuple(
        _source_node(
            node_id=f"scale-leaf-{index:04d}",
            parent_node_id="scale-root",
            label=f"SCALE_LEAF_{index:04d}",
            name=f"Scale leaf {index:04d}",
            path=(root_label,),
            order=index,
            value_type="string",
        )
        for index in range(1, node_count)
    )
    document = {
        "metadata": {
            "id": "scale-version-record",
            "map_id": "scale-tree",
            "map_type": "resource",
            "map_name": "Entirely imaginary scale lattice",
            "version": "V1",
            "category_id": "scale-category",
            "concurrent_version": 1,
        },
        "map_topology": {
            root_label: _source_node(
                node_id="scale-root",
                parent_node_id=None,
                label=root_label,
                name="Scale lattice",
                path=(),
                order=1,
                children=children,
            )
        },
    }
    result = adapt_tree_document(document)
    if result.tree is None:
        raise AssertionError(
            f"scale tree failed adaptation: {[issue.code for issue in result.issues]}"
        )
    return result.tree


def _rehash_profile(
    profile: TreeDiagnosticProfile,
    findings: tuple[TreeDiagnosticFinding, ...],
) -> TreeDiagnosticProfile:
    payload = profile.to_dict()
    payload["findings"] = [finding.to_dict() for finding in findings]
    payload.pop("profile_hash")
    return replace(
        profile,
        findings=findings,
        profile_hash=canonical_digest(payload),
    )


def _valid_model_output(projection) -> dict[str, object]:
    node_refs = tuple(item.node_ref for item in projection.nodes)
    finding_refs = tuple(item.finding_ref for item in projection.findings)
    return {
        "schema_version": MODEL_OUTPUT_SCHEMA_VERSION,
        "summary": "The imaginary lattice contains parallel profiles.",
        "finding_assessments": [
            {
                "finding_ref": finding_ref,
                "disposition": "EXPECTED_PATTERN",
                "reason": "The repeated shape may be intentional in this fictional tree.",
            }
            for finding_ref in finding_refs
        ],
        "generation_status": "SCENARIOS_PROPOSED",
        "virtual_scenarios": [
            {
                "scenario_ref": "S001",
                "title": "Distinguish two imaginary signals",
                "natural_language_request": (
                    "Locate the signal that accepts several numeric observations."
                ),
                "validation_goal": "TYPE_CARDINALITY",
                "supporting_node_refs": list(node_refs[:2]),
                "source_finding_refs": list(finding_refs[:1]),
                "rationale": "This checks whether similar branches remain distinguishable.",
            }
        ],
        "uncertainties": ["The fictional names may omit business context."],
        "evidence_gaps": [],
    }


class TreeUnderstandingTests(unittest.TestCase):
    def test_profile_contract_statistics_and_findings(self) -> None:
        profile = build_tree_diagnostic_profile(_fictional_tree())
        serialized = profile.to_dict()
        schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "tree-diagnostic-profile.v1.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(profile.schema_version, SCHEMA_VERSION)
        self.assertEqual(profile.algorithm_version, ALGORITHM_VERSION)
        self.assertEqual(set(schema["required"]), set(serialized))
        self.assertEqual(
            set(schema["$defs"]["topLevelBranch"]["required"]),
            set(serialized["top_level_branches"][0]),
        )
        self.assertEqual(
            set(schema["$defs"]["finding"]["required"]),
            set(serialized["findings"][0]),
        )
        self.assertEqual(profile.node_count, 11)
        self.assertEqual(profile.root_count, 1)
        self.assertEqual(profile.max_depth, 3)
        self.assertEqual(dict(profile.kind_counts), {"CONCEPT": 3, "PROPERTY": 8})
        self.assertEqual(
            dict(profile.value_type_counts),
            {"NONE": 3, "class": 2, "integer": 1, "string": 5},
        )
        self.assertEqual(
            dict(profile.cardinality_counts),
            {"MULTIPLE": 3, "NONE": 3, "SINGLE": 5},
        )
        self.assertEqual(
            dict(profile.depth_counts),
            {"0": 1, "1": 2, "2": 4, "3": 4},
        )
        self.assertEqual(
            [
                (
                    item.branch_node_id,
                    item.node_count,
                    item.max_relative_depth,
                    item.max_direct_child_count,
                )
                for item in profile.top_level_branches
            ],
            [
                ("alpha-branch", 5, 2, 2),
                ("beta-branch", 5, 2, 2),
            ],
        )
        self.assertEqual(
            [(finding.code, finding.node_ids) for finding in profile.findings],
            [
                (
                    "NAME_REUSED_ACROSS_PATHS",
                    ("alpha-mode", "beta-mode"),
                ),
                (
                    "NAME_REUSED_ACROSS_PATHS",
                    ("alpha-phase", "beta-phase"),
                ),
                (
                    "NAME_REUSED_ACROSS_PATHS",
                    ("alpha-signal", "beta-signal"),
                ),
                (
                    "NAME_CONTRACT_CONFLICT",
                    ("alpha-signal", "beta-signal"),
                ),
                (
                    "CHILD_CONTRACT_VECTOR_REUSED",
                    ("alpha-profile", "beta-profile"),
                ),
            ],
        )

    def test_node_storage_order_does_not_change_profile(self) -> None:
        tree = _fictional_tree()
        reordered = replace(
            tree,
            nodes=tuple(reversed(tree.nodes)),
            root_node_ids=tuple(reversed(tree.root_node_ids)),
        )

        first = build_tree_diagnostic_profile(tree)
        second = build_tree_diagnostic_profile(reordered)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.profile_hash, second.profile_hash)

    def test_full_scan_covers_2001_independently_generated_nodes(self) -> None:
        profile = build_tree_diagnostic_profile(_wide_fictional_tree(2_001))

        self.assertEqual(profile.node_count, 2_001)
        self.assertEqual(profile.max_depth, 1)
        self.assertEqual(
            dict(profile.kind_counts),
            {"CONCEPT": 1, "PROPERTY": 2_000},
        )
        self.assertEqual(len(profile.top_level_branches), 2_000)
        self.assertEqual(profile.findings, ())

    def test_bounded_projection_is_allowlisted_and_reports_coverage(self) -> None:
        tree = _wide_fictional_tree(2_001)
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        model_view = projection.to_model_dict()
        encoded = json.dumps(model_view, ensure_ascii=False, sort_keys=True)
        schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "tree-understanding-model-input.v1.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(model_view["schema_version"], MODEL_INPUT_SCHEMA_VERSION)
        self.assertEqual(set(schema["required"]), set(model_view))
        self.assertEqual(
            set(schema["$defs"]["node"]["required"]),
            set(model_view["nodes"][0]),
        )
        self.assertEqual(len(projection.nodes), 64)
        self.assertEqual(
            model_view["coverage"],
            {
                "total_node_count": 2_001,
                "included_node_count": 64,
                "omitted_node_count": 1_937,
                "total_finding_count": 0,
                "included_finding_count": 0,
                "omitted_finding_count": 0,
                "coverage_complete": False,
            },
        )
        self.assertEqual(
            tuple(item.node_ref for item in projection.nodes),
            tuple(f"N{index:03d}" for index in range(1, 65)),
        )
        self.assertNotIn("scale-root", encoded)
        self.assertNotIn("scale-leaf-0001", encoded)
        self.assertNotIn(tree.snapshot_hash, encoded)
        self.assertNotIn(profile.profile_hash, encoded)
        self.assertNotIn("SCALE_ROOT", encoded)

    def test_projection_and_refs_are_deterministic_under_node_reordering(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        reordered = replace(
            tree,
            nodes=tuple(reversed(tree.nodes)),
            root_node_ids=tuple(reversed(tree.root_node_ids)),
        )
        reordered_profile = build_tree_diagnostic_profile(reordered)

        first = build_tree_understanding_projection(tree, profile)
        second = build_tree_understanding_projection(
            reordered,
            reordered_profile,
        )

        self.assertEqual(first.to_model_dict(), second.to_model_dict())
        self.assertEqual(first.reference_to_node_id, second.reference_to_node_id)
        self.assertEqual(first.projection_hash, second.projection_hash)

    def test_projection_replay_rejects_rehashed_reference_tampering(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        tampered_mapping = dict(projection.reference_to_node_id)
        tampered_mapping["N001"] = "unknown-node"
        tampered = replace(
            projection,
            reference_to_node_id=tampered_mapping,
        )

        with self.assertRaises(TreeUnderstandingError) as captured:
            verify_tree_understanding_projection_against_sources(
                tampered,
                profile,
                tree,
            )

        self.assertEqual(
            captured.exception.code,
            "TREE_UNDERSTANDING_PROJECTION_SOURCE_MISMATCH",
        )

    def test_model_draft_contract_and_trusted_reconstruction(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        draft = TreeUnderstandingDraft.from_model_dict(
            _valid_model_output(projection),
            projection,
            profile,
            tree,
            model_provider="INTERNAL_QWEN_OPENAI_COMPATIBLE",
            model_capability="TREE_VALIDATION_PREPARATION",
            model_name="fictional-qwen",
            prompt_version="treeguard.tree-understanding.zh.v1",
        )
        serialized = draft.to_dict()
        draft_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "tree-understanding-draft.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        output_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "tree-understanding-model-output.v1.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(serialized["schema_version"], DRAFT_SCHEMA_VERSION)
        self.assertEqual(set(draft_schema["required"]), set(serialized))
        self.assertEqual(
            set(output_schema["required"]),
            set(draft.to_model_dict()),
        )
        self.assertEqual(
            set(draft_schema["$defs"]["findingAssessment"]["required"]),
            set(serialized["finding_assessments"][0]),
        )
        self.assertEqual(
            set(draft_schema["$defs"]["scenario"]["required"]),
            set(serialized["virtual_scenarios"][0]),
        )
        self.assertEqual(
            set(output_schema["$defs"]["findingAssessment"]["required"]),
            set(draft.to_model_dict()["finding_assessments"][0]),
        )
        self.assertEqual(
            set(output_schema["$defs"]["scenario"]["required"]),
            set(draft.to_model_dict()["virtual_scenarios"][0]),
        )
        self.assertEqual(serialized["review_status"], "PENDING_HUMAN_REVIEW")
        self.assertFalse(serialized["semantic_approval"])
        self.assertFalse(serialized["gold_eligible"])
        self.assertFalse(serialized["patch_eligible"])
        self.assertEqual(
            TreeUnderstandingDraft.from_dict(
                serialized,
                projection,
                profile,
                tree,
            ),
            draft,
        )

    def test_projection_and_draft_outputs_are_detached(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        draft = TreeUnderstandingDraft.from_model_dict(
            _valid_model_output(projection),
            projection,
            profile,
            tree,
            model_provider="INTERNAL_QWEN_OPENAI_COMPATIBLE",
            model_capability="TREE_VALIDATION_PREPARATION",
            model_name="fictional-qwen",
            prompt_version="treeguard.tree-understanding.zh.v1",
        )

        with self.assertRaises(TypeError):
            projection.reference_to_node_id["N001"] = "changed"  # type: ignore[index]
        model_view = projection.to_model_dict()
        model_view["nodes"][0]["name"] = "changed"
        serialized = draft.to_dict()
        serialized["virtual_scenarios"][0]["title"] = "changed"

        self.assertNotEqual(projection.nodes[0].name, "changed")
        self.assertNotEqual(draft.virtual_scenarios[0].title, "changed")

    def test_need_evidence_can_abstain_from_scenario_generation(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        payload = _valid_model_output(projection)
        payload["generation_status"] = "NEED_EVIDENCE"
        payload["virtual_scenarios"] = []
        payload["evidence_gaps"] = [
            "The fictional projection omits the user population."
        ]

        draft = TreeUnderstandingDraft.from_model_dict(
            payload,
            projection,
            profile,
            tree,
            model_provider="INTERNAL_QWEN_OPENAI_COMPATIBLE",
            model_capability="TREE_VALIDATION_PREPARATION",
            model_name="fictional-qwen",
            prompt_version="treeguard.tree-understanding.zh.v1",
        )

        self.assertEqual(draft.generation_status, "NEED_EVIDENCE")
        self.assertEqual(draft.virtual_scenarios, ())

    def test_scenario_reference_order_is_canonicalized_locally(
        self,
    ) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        canonical_payload = _valid_model_output(projection)
        reordered_payload = _valid_model_output(projection)
        scenario = reordered_payload["virtual_scenarios"][0]  # type: ignore[index]
        scenario["supporting_node_refs"] = list(  # type: ignore[index]
            reversed(scenario["supporting_node_refs"])  # type: ignore[index]
        )
        scenario["source_finding_refs"] = list(  # type: ignore[index]
            reversed(projection.finding_refs)
        )
        canonical_payload["virtual_scenarios"][0][  # type: ignore[index]
            "source_finding_refs"
        ] = list(projection.finding_refs)

        drafts = [
            TreeUnderstandingDraft.from_model_dict(
                payload,
                projection,
                profile,
                tree,
                model_provider="INTERNAL_QWEN_OPENAI_COMPATIBLE",
                model_capability="TREE_VALIDATION_PREPARATION",
                model_name="fictional-qwen",
                prompt_version="treeguard.tree-understanding.zh.v5",
            )
            for payload in (canonical_payload, reordered_payload)
        ]

        self.assertEqual(drafts[0].to_dict(), drafts[1].to_dict())
        self.assertEqual(drafts[0].draft_hash, drafts[1].draft_hash)
        self.assertEqual(
            drafts[1].virtual_scenarios[0].supporting_node_refs,
            tuple(sorted(projection.node_refs[:2])),
        )
        self.assertEqual(
            drafts[1].virtual_scenarios[0].source_finding_refs,
            tuple(sorted(projection.finding_refs)),
        )

    def test_model_output_rejects_unknown_refs_and_policy_conflicts(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)

        cases = []
        unknown_ref = _valid_model_output(projection)
        unknown_ref["virtual_scenarios"][0]["supporting_node_refs"] = [  # type: ignore[index]
            "N999"
        ]
        cases.append(
            (
                unknown_ref,
                "TREE_UNDERSTANDING_MODEL_NODE_REF_INVALID",
            )
        )
        status_conflict = _valid_model_output(projection)
        status_conflict["generation_status"] = "NEED_EVIDENCE"
        cases.append(
            (
                status_conflict,
                "TREE_UNDERSTANDING_MODEL_GENERATION_POLICY_INVALID",
            )
        )
        internal_id = _valid_model_output(projection)
        internal_id["summary"] = "Inspect alpha-signal directly."
        cases.append(
            (
                internal_id,
                "TREE_UNDERSTANDING_MODEL_INTERNAL_ID_FORBIDDEN",
            )
        )
        extra_field = _valid_model_output(projection)
        extra_field["unexpected"] = True
        cases.append(
            (
                extra_field,
                "TREE_UNDERSTANDING_MODEL_FIELDS_INVALID",
            )
        )
        duplicate_ref = _valid_model_output(projection)
        first_ref = duplicate_ref["virtual_scenarios"][0][  # type: ignore[index]
            "supporting_node_refs"
        ][0]
        duplicate_ref["virtual_scenarios"][0][  # type: ignore[index]
            "supporting_node_refs"
        ] = [first_ref, first_ref]
        cases.append(
            (
                duplicate_ref,
                "TREE_UNDERSTANDING_MODEL_NODE_REF_INVALID",
            )
        )
        empty_support = _valid_model_output(projection)
        empty_support["virtual_scenarios"][0][  # type: ignore[index]
            "supporting_node_refs"
        ] = []
        cases.append(
            (
                empty_support,
                "TREE_UNDERSTANDING_MODEL_NODE_REF_INVALID",
            )
        )
        malformed_ref = _valid_model_output(projection)
        malformed_ref["virtual_scenarios"][0][  # type: ignore[index]
            "supporting_node_refs"
        ] = ["node-alpha"]
        cases.append(
            (
                malformed_ref,
                "TREE_UNDERSTANDING_MODEL_NODE_REF_INVALID",
            )
        )
        unknown_finding_ref = _valid_model_output(projection)
        unknown_finding_ref["virtual_scenarios"][0][  # type: ignore[index]
            "source_finding_refs"
        ] = ["D999"]
        cases.append(
            (
                unknown_finding_ref,
                "TREE_UNDERSTANDING_MODEL_FINDING_REF_INVALID",
            )
        )
        finding_order = _valid_model_output(projection)
        finding_order["finding_assessments"] = list(  # type: ignore[arg-type]
            reversed(finding_order["finding_assessments"])  # type: ignore[arg-type]
        )
        cases.append(
            (
                finding_order,
                "TREE_UNDERSTANDING_MODEL_FINDING_COVERAGE_INVALID",
            )
        )

        for payload, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(TreeUnderstandingError) as captured:
                    TreeUnderstandingDraft.from_model_dict(
                        payload,
                        projection,
                        profile,
                        tree,
                        model_provider="INTERNAL_QWEN_OPENAI_COMPATIBLE",
                        model_capability="TREE_VALIDATION_PREPARATION",
                        model_name="fictional-qwen",
                        prompt_version="treeguard.tree-understanding.zh.v1",
                    )
                self.assertEqual(captured.exception.code, expected_code)

    def test_rehashed_draft_with_wrong_source_is_rejected(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)
        draft = TreeUnderstandingDraft.from_model_dict(
            _valid_model_output(projection),
            projection,
            profile,
            tree,
            model_provider="INTERNAL_QWEN_OPENAI_COMPATIBLE",
            model_capability="TREE_VALIDATION_PREPARATION",
            model_name="fictional-qwen",
            prompt_version="treeguard.tree-understanding.zh.v1",
        )
        tampered = draft.to_dict()
        tampered["source_profile_hash"] = "0" * 64
        tampered.pop("draft_hash")
        tampered["draft_hash"] = canonical_digest(tampered)

        with self.assertRaises(TreeUnderstandingError) as captured:
            TreeUnderstandingDraft.from_dict(
                tampered,
                projection,
                profile,
                tree,
            )

        self.assertEqual(
            captured.exception.code,
            "TREE_UNDERSTANDING_DRAFT_SOURCE_MISMATCH",
        )

    def test_profile_containers_are_immutable_and_outputs_are_detached(self) -> None:
        profile = build_tree_diagnostic_profile(_fictional_tree())

        with self.assertRaises(TypeError):
            profile.kind_counts["PROPERTY"] = 999  # type: ignore[index]
        serialized = profile.to_dict()
        serialized["kind_counts"]["PROPERTY"] = 999

        self.assertEqual(profile.kind_counts["PROPERTY"], 8)

    def test_aggregate_report_is_allowlisted(self) -> None:
        profile = build_tree_diagnostic_profile(_fictional_tree())
        report = profile.aggregate_report()

        encoded = json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
        )

        self.assertEqual(
            set(report),
            {
                "report_version",
                "profile_schema_version",
                "algorithm_version",
                "node_count",
                "root_count",
                "max_depth",
                "top_level_branch_count",
                "finding_count",
                "finding_code_counts",
            },
        )
        self.assertNotIn("sensitive-tree-ref-canary", encoded)
        self.assertNotIn("lattice-root", encoded)
        self.assertNotIn("Signal", encoded)
        self.assertNotIn(profile.source_snapshot_hash, encoded)
        self.assertNotIn(profile.profile_hash, encoded)
        self.assertEqual(
            report["finding_code_counts"],
            {
                "CHILD_CONTRACT_VECTOR_REUSED": 1,
                "NAME_CONTRACT_CONFLICT": 1,
                "NAME_REUSED_ACROSS_PATHS": 3,
            },
        )

    def test_invalid_branch_container_fails_as_contract_error(self) -> None:
        profile = build_tree_diagnostic_profile(_fictional_tree())

        with self.assertRaisesRegex(
            ValueError,
            "top-level branches must be a non-empty tuple",
        ):
            replace(
                profile,
                top_level_branches=("not-a-branch",),  # type: ignore[arg-type]
            )

    def test_invalid_tree_relation_fails_with_stable_code(self) -> None:
        tree = _fictional_tree()
        nodes = list(tree.nodes)
        root_index = next(
            index for index, node in enumerate(nodes) if node.node_id == "lattice-root"
        )
        nodes[root_index] = replace(
            nodes[root_index],
            child_node_ids=("missing-node",),
        )

        with self.assertRaises(TreeUnderstandingError) as captured:
            build_tree_diagnostic_profile(replace(tree, nodes=tuple(nodes)))

        self.assertEqual(
            captured.exception.code,
            "TREE_UNDERSTANDING_TREE_RELATION_INVALID",
        )

    def test_rehashed_unknown_finding_is_rejected_against_source_tree(self) -> None:
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        first = profile.findings[0]
        forged = TreeDiagnosticFinding(
            code=first.code,
            node_ids=("alpha-mode", "unknown-node"),
            occurrence_count=2,
        )
        tampered = _rehash_profile(
            profile,
            (forged, *profile.findings[1:]),
        )

        with self.assertRaises(TreeUnderstandingError) as captured:
            verify_tree_diagnostic_profile_against_tree(tampered, tree)

        self.assertEqual(
            captured.exception.code,
            "TREE_UNDERSTANDING_PROFILE_SOURCE_MISMATCH",
        )


if __name__ == "__main__":
    unittest.main()
