from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import adapt_tree_document
from treeguard.diff import CHANGE_TYPE_ORDER, diff_snapshots
from treeguard.hashing import canonical_digest
from treeguard.history import (
    POLICY_VERSION,
    REASON_CODE_ORDER,
    HistoryMiningError,
    mine_history_pair,
    verify_history_run_against_snapshots,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "history-review.v1.schema.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def find_source_node(document: dict, node_id: str) -> dict:
    def walk(wrapper: dict) -> dict | None:
        if wrapper["metadata"]["node_id"] == node_id:
            return wrapper
        for child in wrapper.get("subnodes", {}).values():
            found = walk(child)
            if found is not None:
                return found
        return None

    for root in document["map_topology"].values():
        found = walk(root)
        if found is not None:
            return found
    raise AssertionError(f"fixture node not found: {node_id}")


def canonical_tree(
    document: dict,
    *,
    revision: int,
    version: str | None = None,
    record_id: str | None = None,
    map_type: str | None = None,
):
    source = copy.deepcopy(document)
    source["metadata"]["concurrent_version"] = revision
    if version is not None:
        source["metadata"]["version"] = version
    if record_id is not None:
        source["metadata"]["id"] = record_id
    if map_type is not None:
        source["metadata"]["map_type"] = map_type
    result = adapt_tree_document(source)
    if result.tree is None:
        raise AssertionError(
            f"fixture failed canonicalization: {[issue.code for issue in result.issues]}"
        )
    return result.tree


def adjacent_run(before_document: dict, after_document: dict):
    return mine_history_pair(
        canonical_tree(before_document, revision=7),
        canonical_tree(after_document, revision=8),
    )


def name_change(document: dict, node_id: str, name: str) -> None:
    find_source_node(document, node_id)["metadata"]["node_name"] = name


def remove_value(document: dict, node_id: str) -> None:
    find_source_node(document, node_id).pop("value", None)


def add_compound_value(document: dict, node_id: str) -> None:
    node = find_source_node(document, node_id)
    node["value"] = {
        "metadata": {
            "node_id": node_id,
            "value_type": "class",
            "is_list": False,
        },
        "complex_value": {"fictional_nested_payload": {}},
    }


def sibling_order_documents() -> tuple[dict, dict]:
    before = load_fixture()
    after = copy.deepcopy(before)
    find_source_node(after, "node-003")["metadata"]["node_order"] = 2
    find_source_node(after, "node-004")["metadata"]["node_order"] = 1
    return before, after


def collect_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested
            for item in value.values()
            for nested in collect_keys(item)
        }
    if isinstance(value, list):
        return {nested for item in value for nested in collect_keys(item)}
    return set()


def rehashed_case(case, source_diff_hash: str, **changes):
    candidate = replace(case, **changes)
    serialized = candidate.to_dict()
    serialized.pop("case_id")
    payload = {
        "policy_version": POLICY_VERSION,
        "source_diff_hash": source_diff_hash,
        **serialized,
    }
    return replace(
        candidate,
        case_id=canonical_digest(payload),
    )


class HistoryMiningTests(unittest.TestCase):
    def test_adjacent_resource_pair_succeeds(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        name_change(after, "node-008", "Revised fictional height")

        run = adjacent_run(before, after)

        self.assertEqual(run.scope, "SAVE_REVISION")
        self.assertEqual(run.revision_gap, 1)
        self.assertEqual(run.interval_completeness, "ADJACENT")
        self.assertFalse(run.reconstructs_historical_operations)
        self.assertEqual(len(run.review_cases), 1)
        case = run.review_cases[0]
        self.assertEqual(case.node_ids, ("node-008",))
        self.assertEqual(case.change_types, ("NODE_NAME_CHANGED",))
        self.assertEqual(case.risk_level, "REVIEW_REQUIRED")
        self.assertEqual(case.gate_status, "REVIEWABLE")
        self.assertEqual(case.reason_codes, ())

    def test_reverse_equal_instance_and_cross_business_pairs_are_rejected(self) -> None:
        document = load_fixture()

        scenarios = (
            (
                "reverse",
                canonical_tree(document, revision=8),
                canonical_tree(document, revision=7),
                "HISTORY_REVISION_NOT_FORWARD",
            ),
            (
                "equal",
                canonical_tree(document, revision=7),
                canonical_tree(document, revision=7),
                "HISTORY_REVISION_NOT_FORWARD",
            ),
            (
                "instance",
                canonical_tree(document, revision=7, map_type="instance"),
                canonical_tree(document, revision=8, map_type="instance"),
                "HISTORY_SOURCE_NOT_RESOURCE",
            ),
            (
                "cross-business",
                canonical_tree(
                    document,
                    revision=7,
                    version="V1",
                    record_id="record-v1",
                ),
                canonical_tree(
                    document,
                    revision=1,
                    version="V2",
                    record_id="record-v2",
                ),
                "HISTORY_SCOPE_NOT_SAVE_REVISION",
            ),
        )
        for label, before, after, expected_code in scenarios:
            with self.subTest(label=label):
                with self.assertRaises(HistoryMiningError) as error:
                    mine_history_pair(before, after)
                self.assertEqual(error.exception.code, expected_code)

    def test_revision_gap_marks_case_unknown(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        name_change(after_document, "node-008", "Gapped fictional change")

        run = mine_history_pair(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=10),
        )

        self.assertEqual(run.revision_gap, 3)
        self.assertEqual(run.interval_completeness, "GAPPED")
        self.assertEqual(run.review_cases[0].gate_status, "UNKNOWN")
        self.assertIn(
            "INTERMEDIATE_REVISIONS_UNOBSERVED",
            run.review_cases[0].reason_codes,
        )

    def test_revision_gap_does_not_downgrade_value_blocker(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        target = find_source_node(after, "node-003")
        target["metadata"]["value_type"] = "integer"
        target.pop("value")

        run = mine_history_pair(
            canonical_tree(before, revision=7),
            canonical_tree(after, revision=10),
        )
        case = run.review_cases[0]

        self.assertEqual(case.gate_status, "BLOCKED")
        self.assertIn("INTERMEDIATE_REVISIONS_UNOBSERVED", case.reason_codes)
        self.assertIn("VALUE_MIGRATION_UNSUPPORTED", case.reason_codes)

    def test_pure_sibling_order_changes_form_one_informational_observation(self) -> None:
        before, after = sibling_order_documents()

        run = adjacent_run(before, after)

        self.assertEqual(run.review_cases, ())
        self.assertEqual(len(run.informational_observations), 1)
        observation = run.informational_observations[0]
        self.assertEqual(observation.basis, "SIBLING_ORDER_CONTEXT")
        self.assertEqual(observation.node_ids, ("node-003", "node-004"))
        self.assertEqual(observation.context_node_ids, ("node-002",))
        self.assertEqual(observation.change_types, ("ORDER_OBSERVED_CHANGED",))
        self.assertEqual(run.summary.informational_only_node_count, 2)

    def test_semantic_change_suppresses_order_change(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        node = find_source_node(after, "node-008")
        node["metadata"]["node_name"] = "Revised fictional height"
        node["metadata"]["node_order"] = 3

        run = adjacent_run(before, after)

        self.assertEqual(len(run.review_cases), 1)
        self.assertEqual(
            run.review_cases[0].change_types,
            ("NODE_NAME_CHANGED",),
        )
        self.assertEqual(run.informational_observations, ())
        self.assertEqual(run.summary.suppressed_informational_change_count, 1)

    def test_direct_parent_child_additions_form_one_cluster(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        catalog = find_source_node(after, "node-002")
        catalog.setdefault("subnodes", {})["NEW_PROFILE"] = {
            "metadata": {
                "node_id": "node-009",
                "parent_node_id": "node-002",
                "node_type": "property",
                "node_name": "New fictional profile",
                "node_label": "NEW_PROFILE",
                "node_label_route": "ROOT_DEMO/-/CATALOG/-/NEW_PROFILE",
                "node_order": 4,
                "value_type": "class",
                "is_list": False,
                "value_placeholder": "",
                "value_constraints": {},
                "extension": {},
                "remark": "",
            },
            "subnodes": {
                "NEW_DETAIL": {
                    "metadata": {
                        "node_id": "node-010",
                        "parent_node_id": "node-009",
                        "node_type": "property",
                        "node_name": "New fictional detail",
                        "node_label": "NEW_DETAIL",
                        "node_label_route": (
                            "ROOT_DEMO/-/CATALOG/-/NEW_PROFILE/-/NEW_DETAIL"
                        ),
                        "node_order": 1,
                        "value_type": "string",
                        "is_list": False,
                        "value_placeholder": "",
                        "value_constraints": {},
                        "extension": {},
                        "remark": "",
                    }
                }
            },
        }

        run = adjacent_run(before, after)

        self.assertEqual(len(run.review_cases), 1)
        self.assertEqual(run.review_cases[0].node_ids, ("node-009", "node-010"))
        self.assertEqual(run.review_cases[0].change_types, ("NODE_ADDED",))

    def test_same_parent_general_changes_remain_separate(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        name_change(after, "node-003", "Revised title")
        name_change(after, "node-004", "Revised tags")

        run = adjacent_run(before, after)

        self.assertEqual(
            {case.node_ids for case in run.review_cases},
            {("node-003",), ("node-004",)},
        )

    def test_move_does_not_bridge_old_and_new_parent_domains(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        old_parent = find_source_node(after, "node-006")
        moved = old_parent["subnodes"].pop("HEIGHT")
        moved["metadata"].update(
            {
                "parent_node_id": "node-002",
                "node_label_route": "ROOT_DEMO/-/CATALOG/-/HEIGHT",
                "node_order": 4,
            }
        )
        new_parent = find_source_node(after, "node-002")
        new_parent["subnodes"]["HEIGHT"] = moved
        old_parent["metadata"]["node_name"] = "Revised old parent"
        new_parent["metadata"]["node_name"] = "Revised new parent"

        run = adjacent_run(before, after)

        self.assertEqual(
            {case.node_ids for case in run.review_cases},
            {("node-002",), ("node-006",), ("node-008",)},
        )
        moved_case = next(
            case for case in run.review_cases if case.node_ids == ("node-008",)
        )
        self.assertEqual(moved_case.change_types, ("NODE_MOVED",))

    def test_root_is_a_hard_clustering_boundary(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        name_change(after, "node-001", "Revised root")
        name_change(after, "node-002", "Revised catalog")
        name_change(after, "node-003", "Revised title")

        run = adjacent_run(before, after)

        self.assertEqual(
            {case.node_ids for case in run.review_cases},
            {("node-001",), ("node-002", "node-003")},
        )

    def test_value_type_and_cardinality_with_base_value_are_blocked(self) -> None:
        for field, value, expected_change in (
            ("value_type", "integer", "VALUE_TYPE_CHANGED"),
            ("is_list", True, "CARDINALITY_CHANGED"),
        ):
            with self.subTest(field=field):
                before = load_fixture()
                after = copy.deepcopy(before)
                target = find_source_node(after, "node-003")
                target["metadata"][field] = value
                target.pop("value")

                case = adjacent_run(before, after).review_cases[0]

                self.assertIn(expected_change, case.change_types)
                self.assertEqual(case.gate_status, "BLOCKED")
                self.assertIn("VALUE_MIGRATION_UNSUPPORTED", case.reason_codes)
                self.assertTrue(
                    case.node_evidence[0].base_direct_value_envelope_observed
                )

    def test_property_removal_with_base_value_is_blocked(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        find_source_node(after, "node-002")["subnodes"].pop("TITLE")

        case = adjacent_run(before, after).review_cases[0]

        self.assertEqual(case.change_types, ("NODE_REMOVED",))
        self.assertEqual(case.gate_status, "BLOCKED")
        self.assertIn("VALUE_MIGRATION_UNSUPPORTED", case.reason_codes)

    def test_shape_change_without_base_value_is_unknown(self) -> None:
        before = load_fixture()
        remove_value(before, "node-003")
        after = copy.deepcopy(before)
        find_source_node(after, "node-003")["metadata"]["is_list"] = True

        case = adjacent_run(before, after).review_cases[0]

        self.assertEqual(case.gate_status, "UNKNOWN")
        self.assertIn("VALUE_ABSENCE_UNPROVEN", case.reason_codes)
        self.assertNotIn("VALUE_MIGRATION_UNSUPPORTED", case.reason_codes)
        self.assertFalse(
            case.node_evidence[0].base_direct_value_envelope_observed
        )
        self.assertFalse(
            case.node_evidence[0].base_ancestor_value_envelope_observed
        )

    def test_target_only_value_does_not_trigger_migration_block(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        target = find_source_node(after, "node-004")
        target["metadata"]["is_list"] = False
        target["value"] = {
            "metadata": {
                "node_id": "node-004",
                "value_type": "string",
                "is_list": False,
            },
            "simple_value": "target-only fictional value",
        }

        case = adjacent_run(before, after).review_cases[0]

        self.assertEqual(case.gate_status, "UNKNOWN")
        self.assertIn("VALUE_ABSENCE_UNPROVEN", case.reason_codes)
        self.assertNotIn("VALUE_MIGRATION_UNSUPPORTED", case.reason_codes)
        self.assertFalse(
            case.node_evidence[0].base_direct_value_envelope_observed
        )
        self.assertTrue(
            case.node_evidence[0].target_direct_value_envelope_observed
        )

    def test_compound_ancestor_value_evidence_covers_child_changes(self) -> None:
        for scenario in ("type", "cardinality", "remove", "constraints"):
            with self.subTest(scenario=scenario):
                before = load_fixture()
                add_compound_value(before, "node-006")
                after = copy.deepcopy(before)
                if scenario == "type":
                    find_source_node(after, "node-007")["metadata"][
                        "value_type"
                    ] = "integer"
                elif scenario == "cardinality":
                    find_source_node(after, "node-007")["metadata"]["is_list"] = True
                elif scenario == "remove":
                    find_source_node(after, "node-006")["subnodes"].pop("WIDTH")
                else:
                    find_source_node(after, "node-007")["metadata"][
                        "value_constraints"
                    ] = {"fictional_minimum": 1}

                case = adjacent_run(before, after).review_cases[0]
                evidence = case.node_evidence[0]

                self.assertFalse(evidence.base_direct_value_envelope_observed)
                self.assertTrue(evidence.base_ancestor_value_envelope_observed)
                if scenario == "constraints":
                    self.assertEqual(case.gate_status, "UNKNOWN")
                    self.assertIn(
                        "VALUE_REVALIDATION_REQUIRED",
                        case.reason_codes,
                    )
                else:
                    self.assertEqual(case.gate_status, "BLOCKED")
                    self.assertIn(
                        "VALUE_MIGRATION_UNSUPPORTED",
                        case.reason_codes,
                    )

    def test_constraints_are_unknown_and_base_value_requires_revalidation(self) -> None:
        for base_has_value in (False, True):
            with self.subTest(base_has_value=base_has_value):
                before = load_fixture()
                if not base_has_value:
                    remove_value(before, "node-003")
                after = copy.deepcopy(before)
                find_source_node(after, "node-003")["metadata"][
                    "value_constraints"
                ] = {"fictional_minimum": 1}

                case = adjacent_run(before, after).review_cases[0]

                self.assertEqual(case.gate_status, "UNKNOWN")
                self.assertIn(
                    "CONSTRAINT_SEMANTICS_UNCLASSIFIED",
                    case.reason_codes,
                )
                self.assertEqual(
                    "VALUE_REVALIDATION_REQUIRED" in case.reason_codes,
                    base_has_value,
                )

    def test_unclassified_and_unsupported_changes_are_unknown(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        find_source_node(after, "node-008")["metadata"]["extension"] = {
            "future_behavior": True
        }
        unclassified_case = adjacent_run(before, after).review_cases[0]
        self.assertEqual(unclassified_case.gate_status, "UNKNOWN")
        self.assertIn("UNCLASSIFIED_CHANGE_PRESENT", unclassified_case.reason_codes)

        unsupported_before = load_fixture()
        unsupported_after = copy.deepcopy(unsupported_before)
        find_source_node(unsupported_before, "node-004")["metadata"][
            "node_type"
        ] = "future-property-a"
        find_source_node(unsupported_after, "node-004")["metadata"][
            "node_type"
        ] = "future-property-b"
        unsupported_case = adjacent_run(
            unsupported_before,
            unsupported_after,
        ).review_cases[0]
        self.assertEqual(unsupported_case.gate_status, "UNKNOWN")
        self.assertIn(
            "UNSUPPORTED_NODE_KIND_PRESENT",
            unsupported_case.reason_codes,
        )

    def test_sensitive_value_never_enters_run_or_aggregate(self) -> None:
        marker = "sensitive-instance-marker-must-not-appear"
        before = load_fixture()
        find_source_node(before, "node-003")["value"]["simple_value"] = marker
        after = copy.deepcopy(before)
        target = find_source_node(after, "node-003")
        target["metadata"]["value_type"] = "integer"
        target.pop("value")

        run = adjacent_run(before, after)
        serialized_run = json.dumps(run.to_dict(), ensure_ascii=False, sort_keys=True)
        aggregate = run.aggregate_report()
        serialized_aggregate = json.dumps(aggregate, ensure_ascii=False, sort_keys=True)

        self.assertNotIn(marker, serialized_run)
        self.assertNotIn(marker, serialized_aggregate)
        aggregate_keys = collect_keys(aggregate)
        self.assertFalse(
            any(
                key.endswith("_id")
                or key.endswith("_ids")
                or key.endswith("_hash")
                for key in aggregate_keys
            )
        )

    def test_same_diff_hash_but_value_evidence_changes_case_and_run_hashes(self) -> None:
        before_with_value = load_fixture()
        before_without_value = copy.deepcopy(before_with_value)
        remove_value(before_without_value, "node-003")
        after = copy.deepcopy(before_without_value)
        find_source_node(after, "node-003")["metadata"]["value_type"] = "integer"

        before_with_tree = canonical_tree(before_with_value, revision=7)
        before_without_tree = canonical_tree(before_without_value, revision=7)
        after_tree = canonical_tree(after, revision=8)
        with_value_diff = diff_snapshots(before_with_tree, after_tree)
        without_value_diff = diff_snapshots(before_without_tree, after_tree)
        with_value_run = mine_history_pair(before_with_tree, after_tree)
        without_value_run = mine_history_pair(before_without_tree, after_tree)

        self.assertEqual(with_value_diff.diff_hash, without_value_diff.diff_hash)
        self.assertEqual(
            with_value_run.source_diff_hash,
            without_value_run.source_diff_hash,
        )
        self.assertEqual(with_value_run.review_cases[0].gate_status, "BLOCKED")
        self.assertEqual(without_value_run.review_cases[0].gate_status, "UNKNOWN")
        self.assertNotEqual(
            with_value_run.review_cases[0].case_id,
            without_value_run.review_cases[0].case_id,
        )
        self.assertNotEqual(with_value_run.run_hash, without_value_run.run_hash)

    def test_reversed_node_storage_order_is_deterministic(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        name_change(after_document, "node-008", "Deterministic fictional change")
        before = canonical_tree(before_document, revision=7)
        after = canonical_tree(after_document, revision=8)

        first = mine_history_pair(before, after)
        second = mine_history_pair(
            replace(before, nodes=tuple(reversed(before.nodes))),
            replace(after, nodes=tuple(reversed(after.nodes))),
        )

        self.assertEqual(first.to_dict(), second.to_dict())

    def test_contract_required_fields_match_serialized_objects(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        name_change(after, "node-008", "Contract fictional change")
        semantic_run = adjacent_run(before, after)
        order_before, order_after = sibling_order_documents()
        informational_run = adjacent_run(order_before, order_after)
        schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        serialized = semantic_run.to_dict()
        case = serialized["review_cases"][0]
        node_evidence = case["node_evidence"][0]
        observation = informational_run.to_dict()["informational_observations"][0]

        self.assertEqual(set(schema["required"]), set(serialized))
        self.assertEqual(
            set(schema["$defs"]["snapshotRef"]["required"]),
            set(serialized["base"]),
        )
        self.assertEqual(
            set(schema["$defs"]["reviewCase"]["required"]),
            set(case),
        )
        self.assertEqual(
            set(schema["$defs"]["nodeEvidence"]["required"]),
            set(node_evidence),
        )
        self.assertEqual(
            set(schema["$defs"]["informationalObservation"]["required"]),
            set(observation),
        )
        self.assertEqual(
            set(schema["$defs"]["summary"]["required"]),
            set(serialized["summary"]),
        )
        self.assertEqual(
            schema["$defs"]["reasonCode"]["enum"],
            list(REASON_CODE_ORDER),
        )
        self.assertEqual(
            schema["$defs"]["changeType"]["enum"],
            list(CHANGE_TYPE_ORDER),
        )
        self.assertTrue(schema["properties"]["review_cases"]["uniqueItems"])
        self.assertTrue(
            schema["properties"]["informational_observations"]["uniqueItems"]
        )
        self.assertEqual(
            schema["$defs"]["reviewCase"]["properties"]["node_evidence"][
                "minItems"
            ],
            1,
        )
        self.assertIn("shapeBreakingEvidence", schema["$defs"])
        self.assertTrue(schema["allOf"])

    def test_run_hash_tampering_is_rejected(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        name_change(after, "node-008", "Hash fictional change")
        run = adjacent_run(before, after)

        with self.assertRaises(ValueError):
            replace(run, run_hash="0" * 64)

    def test_case_id_and_aggregate_allowlists_reject_tampering(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        find_source_node(after, "node-003")["metadata"]["value_type"] = "integer"
        find_source_node(after, "node-003").pop("value")
        run = adjacent_run(before, after)
        case = run.review_cases[0]

        with self.assertRaises(ValueError):
            replace(case, gate_status="REVIEWABLE")
        with self.assertRaises(ValueError):
            rehashed_case(
                case,
                run.source_diff_hash,
                gate_status="REVIEWABLE",
                reason_codes=(),
            )

        tampered_case = replace(case, case_id="0" * 64)
        tampered_payload = run.to_dict()
        tampered_payload["review_cases"] = [tampered_case.to_dict()]
        tampered_payload.pop("run_hash")
        with self.assertRaises(ValueError):
            replace(
                run,
                review_cases=(tampered_case,),
                run_hash=canonical_digest(tampered_payload),
            )

        with self.assertRaises(ValueError):
            replace(
                run.summary,
                candidate_change_type_counts={"sensitive_marker": 1},
            )

        tampered_payload = run.to_dict()
        tampered_payload["knowledge_status"] = "sensitive_status"
        tampered_payload.pop("run_hash")
        with self.assertRaises(ValueError):
            replace(
                run,
                knowledge_status="sensitive_status",
                run_hash=canonical_digest(tampered_payload),
            )

    def test_gapped_case_cannot_be_downgraded_with_rehashed_artifacts(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        name_change(after, "node-008", "Gapped downgrade attempt")
        run = mine_history_pair(
            canonical_tree(before, revision=7),
            canonical_tree(after, revision=10),
        )
        case = rehashed_case(
            run.review_cases[0],
            run.source_diff_hash,
            gate_status="REVIEWABLE",
            reason_codes=(),
        )
        summary = replace(
            run.summary,
            gate_status_counts={"REVIEWABLE": 1},
            reason_code_counts={},
        )
        tampered_payload = run.to_dict()
        tampered_payload["review_cases"] = [case.to_dict()]
        tampered_payload["summary"] = summary.to_dict()
        tampered_payload.pop("run_hash")

        with self.assertRaises(ValueError):
            replace(
                run,
                review_cases=(case,),
                summary=summary,
                run_hash=canonical_digest(tampered_payload),
            )

    def test_mutable_artifact_containers_are_rejected(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        name_change(after, "node-008", "Immutable artifact check")
        run = adjacent_run(before, after)
        case = run.review_cases[0]

        with self.assertRaises(ValueError):
            replace(case, node_evidence=list(case.node_evidence))
        with self.assertRaises(ValueError):
            replace(run, review_cases=list(run.review_cases))
        with self.assertRaises(ValueError):
            replace(
                run,
                informational_observations=list(run.informational_observations),
            )

    def test_trusted_snapshot_replay_rejects_forged_node_mapping(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        name_change(after_document, "node-002", "Changed parent")
        target = find_source_node(after_document, "node-003")
        target["metadata"]["value_type"] = "integer"
        target.pop("value")
        before = canonical_tree(before_document, revision=7)
        after = canonical_tree(after_document, revision=8)
        run = mine_history_pair(before, after)
        case = run.review_cases[0]
        first, second = case.node_evidence
        swapped_evidence = (
            replace(first, change_types=second.change_types),
            replace(second, change_types=first.change_types),
        )
        forged_case = rehashed_case(
            case,
            run.source_diff_hash,
            node_evidence=swapped_evidence,
            gate_status="UNKNOWN",
            reason_codes=("VALUE_ABSENCE_UNPROVEN",),
        )
        forged_summary = replace(
            run.summary,
            gate_status_counts={"UNKNOWN": 1},
            reason_code_counts={"VALUE_ABSENCE_UNPROVEN": 1},
        )
        forged_payload = run.to_dict()
        forged_payload["review_cases"] = [forged_case.to_dict()]
        forged_payload["summary"] = forged_summary.to_dict()
        forged_payload.pop("run_hash")
        forged_run = replace(
            run,
            review_cases=(forged_case,),
            summary=forged_summary,
            run_hash=canonical_digest(forged_payload),
        )

        with self.assertRaises(HistoryMiningError) as error:
            verify_history_run_against_snapshots(forged_run, before, after)
        self.assertEqual(error.exception.code, "HISTORY_RUN_SOURCE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
