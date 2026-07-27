from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import adapt_tree_document
from treeguard.diff import (
    CHANGE_TYPE_ORDER,
    SnapshotDiffError,
    diff_snapshots,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


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
    revision: int | None = None,
    version: str | None = None,
    record_id: str | None = None,
):
    source = copy.deepcopy(document)
    if revision is not None:
        source["metadata"]["concurrent_version"] = revision
    if version is not None:
        source["metadata"]["version"] = version
    if record_id is not None:
        source["metadata"]["id"] = record_id
    result = adapt_tree_document(source)
    if result.tree is None:
        raise AssertionError(
            f"fixture failed canonicalization: {[issue.code for issue in result.issues]}"
        )
    return result.tree


def change_types(diff) -> list[str]:
    return [
        change_type
        for delta in diff.node_deltas
        for change_type in delta.change_types
    ]


class SnapshotDiffTests(unittest.TestCase):
    def test_diff_contract_matches_serialized_field_sets(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-008")["metadata"]["node_name"] = "Changed"
        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )
        schema = json.loads(
            (PROJECT_ROOT / "contracts" / "tree-diff.v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        serialized = result.to_dict()
        node_delta = serialized["node_deltas"][0]
        field_delta = node_delta["field_deltas"][0]

        self.assertEqual(set(schema["required"]), set(serialized))
        self.assertEqual(
            set(schema["$defs"]["snapshotRef"]["required"]),
            set(serialized["base"]),
        )
        self.assertEqual(
            set(schema["$defs"]["nodeDelta"]["required"]),
            set(node_delta),
        )
        self.assertEqual(
            set(schema["$defs"]["fieldDelta"]["required"]),
            set(field_delta),
        )

    def test_identical_snapshot_has_no_schema_changes(self) -> None:
        tree = canonical_tree(load_fixture())

        result = diff_snapshots(tree, tree)

        self.assertEqual(result.scope, "SAVE_REVISION")
        self.assertEqual(result.node_deltas, ())
        self.assertEqual(result.summary.node_delta_count, 0)

    def test_revision_only_and_value_only_save_have_no_schema_changes(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-003")["value"][
            "simple_value"
        ] = "Another fictional value"
        after_document["metadata"]["last_modify_time"] = "2042-02-02 10:00:00"

        before = canonical_tree(before_document, revision=7)
        after = canonical_tree(after_document, revision=8)
        result = diff_snapshots(before, after)

        self.assertEqual(result.scope, "SAVE_REVISION")
        self.assertEqual(result.node_deltas, ())
        self.assertEqual(before.snapshot_hash, after.snapshot_hash)
        self.assertEqual(result.warnings, ())

    def test_value_presence_and_node_audit_changes_do_not_leak_into_diff(self) -> None:
        before_document = load_fixture()
        before_node = find_source_node(before_document, "node-003")
        value_envelope = before_node.pop("value")
        after_document = copy.deepcopy(before_document)
        after_node = find_source_node(after_document, "node-003")
        sensitive_marker = "sensitive-value-must-not-appear"
        value_envelope["simple_value"] = sensitive_marker
        after_node["value"] = value_envelope
        after_node["metadata"].update(
            {
                "creator": sensitive_marker,
                "last_modifier": sensitive_marker,
                "create_time": sensitive_marker,
                "last_modify_time": sensitive_marker,
            }
        )

        before = canonical_tree(before_document, revision=7)
        after = canonical_tree(after_document, revision=8)
        before_by_id = {node.node_id: node for node in before.nodes}
        after_by_id = {node.node_id: node for node in after.nodes}
        result = diff_snapshots(before, after)
        encoded = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)

        self.assertFalse(before_by_id["node-003"].has_value_envelope)
        self.assertTrue(after_by_id["node-003"].has_value_envelope)
        self.assertEqual(result.node_deltas, ())
        self.assertNotIn(sensitive_marker, encoded)
        self.assertNotIn("has_value_envelope", encoded)

    def test_revision_order_warning_and_diff_hash_bind_snapshot_refs(self) -> None:
        document = load_fixture()
        revision_seven = canonical_tree(document, revision=7)
        revision_eight = canonical_tree(document, revision=8)
        revision_nine = canonical_tree(document, revision=9)

        first = diff_snapshots(revision_seven, revision_eight)
        second = diff_snapshots(revision_eight, revision_nine)
        reversed_diff = diff_snapshots(revision_eight, revision_seven)

        self.assertNotEqual(first.diff_hash, second.diff_hash)
        self.assertEqual(
            [warning.code for warning in reversed_diff.warnings],
            ["SOURCE_REVISION_DECREASED"],
        )

    def test_name_change_is_one_field_delta(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-008")["metadata"][
            "node_name"
        ] = "Revised fictional dimension"

        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )

        self.assertEqual(len(result.node_deltas), 1)
        delta = result.node_deltas[0]
        self.assertEqual(delta.node_id, "node-008")
        self.assertEqual(delta.change_types, ("NODE_NAME_CHANGED",))
        self.assertEqual(delta.field_deltas[0].field_path, "name")

    def test_ancestor_label_change_does_not_modify_descendants(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        catalog = find_source_node(after_document, "node-002")
        item = catalog["subnodes"].pop("ITEM_PROFILE")
        item["metadata"]["node_label"] = "PROFILE_REVISED"
        catalog["subnodes"]["PROFILE_REVISED"] = item

        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )

        self.assertEqual(
            [(delta.node_id, delta.change_types) for delta in result.node_deltas],
            [("node-005", ("NODE_LABEL_CHANGED",))],
        )

    def test_moving_subtree_reports_only_moved_root(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        root = next(iter(after_document["map_topology"].values()))
        catalog = find_source_node(after_document, "node-002")
        moved = catalog["subnodes"].pop("ITEM_PROFILE")
        moved["metadata"]["parent_node_id"] = "node-001"
        root["subnodes"]["ITEM_PROFILE"] = moved

        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )

        self.assertEqual(
            [(delta.node_id, delta.change_types) for delta in result.node_deltas],
            [("node-005", ("NODE_MOVED",))],
        )

    def test_added_and_removed_nodes_use_node_id_without_parent_noise(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        catalog = find_source_node(after_document, "node-002")
        catalog["subnodes"]["NEW_FIELD"] = {
            "metadata": {
                "node_id": "node-009",
                "parent_node_id": "node-002",
                "node_type": "property",
                "node_name": "New fictional field",
                "node_label": "NEW_FIELD",
                "node_label_route": "ROOT_DEMO/-/CATALOG/-/NEW_FIELD",
                "node_order": 4,
                "value_type": "string",
                "is_list": False,
                "value_constraints": {},
            }
        }

        added = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )
        removed = diff_snapshots(
            canonical_tree(after_document, revision=8),
            canonical_tree(before_document, revision=9),
        )

        self.assertEqual(
            [(delta.node_id, delta.change_types) for delta in added.node_deltas],
            [("node-009", ("NODE_ADDED",))],
        )
        self.assertEqual(
            [(delta.node_id, delta.change_types) for delta in removed.node_deltas],
            [("node-009", ("NODE_REMOVED",))],
        )

    def test_value_type_cardinality_constraints_and_order_are_field_level(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        node = find_source_node(after_document, "node-004")
        node["metadata"]["value_type"] = "integer"
        node["metadata"]["is_list"] = False
        node["metadata"]["value_constraints"] = {"minimum": 1}
        node["metadata"]["node_order"] = 20

        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )
        delta = result.node_deltas[0]

        self.assertEqual(
            delta.change_types,
            (
                "VALUE_TYPE_CHANGED",
                "CARDINALITY_CHANGED",
                "CONSTRAINTS_CHANGED",
                "ORDER_OBSERVED_CHANGED",
            ),
        )
        self.assertEqual(
            [field.category for field in delta.field_deltas],
            ["SEMANTIC", "SEMANTIC", "SEMANTIC", "INFORMATIONAL"],
        )

    def test_multiple_changes_remain_one_delta_in_fixed_order(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        root = next(iter(after_document["map_topology"].values()))
        catalog = find_source_node(after_document, "node-002")
        moved = catalog["subnodes"].pop("TITLE")
        moved["metadata"].update(
            {
                "parent_node_id": "node-001",
                "node_name": "Revised fictional title",
                "node_label": "TITLE_REVISED",
                "node_type": "concept",
            }
        )
        moved["metadata"].pop("value_type")
        moved["metadata"].pop("is_list")
        moved["metadata"].pop("value_constraints")
        moved["metadata"].pop("value_placeholder")
        moved.pop("value")
        root["subnodes"]["TITLE_REVISED"] = moved

        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )

        self.assertEqual(len(result.node_deltas), 1)
        delta = result.node_deltas[0]
        self.assertEqual(
            delta.change_types,
            (
                "NODE_MOVED",
                "NODE_LABEL_CHANGED",
                "NODE_NAME_CHANGED",
                "NODE_KIND_CHANGED",
                "VALUE_CONTRACT_REMOVED",
            ),
        )
        ranks = [CHANGE_TYPE_ORDER.index(item) for item in delta.change_types]
        self.assertEqual(ranks, sorted(ranks))

    def test_constraint_and_extension_key_order_do_not_create_changes(self) -> None:
        before_document = load_fixture()
        node = find_source_node(before_document, "node-003")
        node["metadata"]["value_constraints"] = {"alpha": 1, "beta": 2}
        node["metadata"]["extension"] = {"left": 1, "right": 2}
        after_document = copy.deepcopy(before_document)
        after_node = find_source_node(after_document, "node-003")
        after_node["metadata"]["value_constraints"] = {"beta": 2, "alpha": 1}
        after_node["metadata"]["extension"] = {"right": 2, "left": 1}

        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )

        self.assertEqual(result.node_deltas, ())

    def test_business_version_scope_does_not_compare_revisions(self) -> None:
        document = load_fixture()

        result = diff_snapshots(
            canonical_tree(document, revision=99, version="V1", record_id="record-v1"),
            canonical_tree(document, revision=1, version="V2", record_id="record-v2"),
        )

        self.assertEqual(result.scope, "BUSINESS_VERSION")
        self.assertEqual(result.node_deltas, ())

    def test_identity_conflicts_are_rejected(self) -> None:
        document = load_fixture()
        base = canonical_tree(document, revision=7)

        other_tree_document = copy.deepcopy(document)
        other_tree_document["metadata"]["map_id"] = "another-fictional-tree"
        with self.assertRaises(SnapshotDiffError) as tree_error:
            diff_snapshots(base, canonical_tree(other_tree_document, revision=8))
        self.assertEqual(tree_error.exception.code, "TREE_ID_MISMATCH")

        with self.assertRaises(SnapshotDiffError) as record_error:
            diff_snapshots(
                base,
                canonical_tree(document, revision=8, record_id="conflicting-record"),
            )
        self.assertEqual(
            record_error.exception.code,
            "VERSION_RECORD_ID_CONFLICT",
        )

        changed_document = copy.deepcopy(document)
        find_source_node(changed_document, "node-008")["metadata"]["node_name"] = "Changed"
        with self.assertRaises(SnapshotDiffError) as content_error:
            diff_snapshots(base, canonical_tree(changed_document, revision=7))
        self.assertEqual(
            content_error.exception.code,
            "SNAPSHOT_CONTENT_CONFLICT",
        )

        instance_document = copy.deepcopy(document)
        instance_document["metadata"]["map_type"] = "instance"
        with self.assertRaises(SnapshotDiffError) as map_type_error:
            diff_snapshots(base, canonical_tree(instance_document, revision=8))
        self.assertEqual(
            map_type_error.exception.code,
            "SOURCE_MAP_TYPE_MISMATCH",
        )

        with self.assertRaises(SnapshotDiffError) as schema_version_error:
            diff_snapshots(
                base,
                replace(base, schema_version="tree-snapshot.v2"),
            )
        self.assertEqual(
            schema_version_error.exception.code,
            "SNAPSHOT_SCHEMA_VERSION_MISMATCH",
        )

        unsupported_base = replace(base, schema_version="tree-snapshot.v2")
        with self.assertRaises(SnapshotDiffError) as unsupported_schema_error:
            diff_snapshots(unsupported_base, unsupported_base)
        self.assertEqual(
            unsupported_schema_error.exception.code,
            "UNSUPPORTED_SNAPSHOT_SCHEMA_VERSION",
        )

        with self.assertRaises(SnapshotDiffError) as reused_record_error:
            diff_snapshots(
                base,
                canonical_tree(document, revision=1, version="V2"),
            )
        self.assertEqual(
            reused_record_error.exception.code,
            "VERSION_RECORD_ID_REUSED",
        )

    def test_duplicate_node_id_is_rejected_even_for_constructed_snapshot(self) -> None:
        tree = canonical_tree(load_fixture())
        duplicate = replace(tree, nodes=tree.nodes + (tree.nodes[0],))

        with self.assertRaises(SnapshotDiffError) as error:
            diff_snapshots(tree, duplicate)

        self.assertEqual(error.exception.code, "DUPLICATE_NODE_ID")

    def test_diff_hash_and_serialization_are_deterministic(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-008")["metadata"]["node_name"] = "Changed"
        before = canonical_tree(before_document, revision=7)
        after = canonical_tree(after_document, revision=8)

        first = diff_snapshots(before, after)
        second = diff_snapshots(
            replace(before, nodes=tuple(reversed(before.nodes))),
            replace(after, nodes=tuple(reversed(after.nodes))),
        )

        self.assertEqual(first.diff_hash, second.diff_hash)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_runtime_contract_rejects_inconsistent_delta_summary_and_hash(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-008")["metadata"]["node_name"] = "Changed"
        result = diff_snapshots(
            canonical_tree(before_document, revision=7),
            canonical_tree(after_document, revision=8),
        )

        with self.assertRaises(ValueError):
            replace(result.node_deltas[0], status="ADDED")
        with self.assertRaises(ValueError):
            replace(result.summary, modified_count=2)
        with self.assertRaises(ValueError):
            replace(result, diff_hash="0" * 64)


if __name__ == "__main__":
    unittest.main()
