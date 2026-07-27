from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from treeguard import TreeFormatError, adapt_tree_document, load_tree_export


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


class AdapterTests(unittest.TestCase):
    def test_direct_export_flattens_recursive_compound_properties(self) -> None:
        result = load_tree_export(FIXTURE_PATH)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.observed_node_count, 8)
        self.assertEqual(result.observed_value_count, 1)
        assert result.tree is not None
        by_id = {node.node_id: node for node in result.tree.nodes}
        self.assertEqual(by_id["node-005"].value_contract.value_type, "class")
        self.assertEqual(by_id["node-005"].child_node_ids, ("node-006",))
        self.assertEqual(by_id["node-006"].value_contract.value_type, "class")
        self.assertEqual(by_id["node-006"].child_node_ids, ("node-007", "node-008"))
        self.assertEqual(
            by_id["node-007"].path_labels,
            ("ROOT_DEMO", "CATALOG", "ITEM_PROFILE", "DIMENSIONS", "WIDTH"),
        )

    def test_api_envelope_and_direct_export_have_same_schema_hash(self) -> None:
        document = load_fixture()
        direct = adapt_tree_document(document)
        envelope = adapt_tree_document({"status": 200, "message": "ok", "data": document})

        self.assertTrue(direct.is_valid)
        self.assertTrue(envelope.is_valid)
        assert direct.tree is not None
        assert envelope.tree is not None
        self.assertEqual(direct.tree.snapshot_hash, envelope.tree.snapshot_hash)
        self.assertEqual(envelope.source_format, "tree-api-response.v1")

    def test_value_envelope_payload_is_not_retained_in_canonical_snapshot(self) -> None:
        result = load_tree_export(FIXTURE_PATH)
        assert result.tree is not None
        encoded = json.dumps(result.tree.to_dict(), ensure_ascii=False, sort_keys=True)

        self.assertNotIn("simple_value", encoded)
        self.assertNotIn("Fictional exhibit", encoded)
        by_id = {node.node_id: node for node in result.tree.nodes}
        self.assertTrue(by_id["node-003"].has_value_envelope)

    def test_map_type_is_explicit_and_does_not_change_schema_hash(self) -> None:
        resource = load_fixture()
        instance = copy.deepcopy(resource)
        instance["metadata"]["map_type"] = "instance"

        resource_result = adapt_tree_document(resource)
        instance_result = adapt_tree_document(instance)

        self.assertTrue(resource_result.is_valid)
        self.assertTrue(instance_result.is_valid)
        assert resource_result.tree is not None
        assert instance_result.tree is not None
        self.assertTrue(resource_result.tree.is_resource_map)
        self.assertFalse(instance_result.tree.is_resource_map)
        self.assertEqual(
            resource_result.tree.snapshot_hash,
            instance_result.tree.snapshot_hash,
        )
        self.assertIn(
            "INSTANCE_TREE_SCHEMA_PROJECTION",
            {issue.code for issue in instance_result.issues},
        )

    def test_missing_concurrent_version_is_a_hard_error(self) -> None:
        document = load_fixture()
        del document["metadata"]["concurrent_version"]

        result = adapt_tree_document(document)

        self.assertFalse(result.is_valid)
        self.assertIn("INVALID_SOURCE_REVISION", {issue.code for issue in result.issues})

    def test_only_class_properties_may_have_property_children(self) -> None:
        non_class_parent = load_fixture()
        find_source_node(non_class_parent, "node-005")["metadata"]["value_type"] = "string"
        invalid_parent_result = adapt_tree_document(non_class_parent)

        non_property_child = load_fixture()
        find_source_node(non_property_child, "node-006")["metadata"]["node_type"] = "concept"
        invalid_child_result = adapt_tree_document(non_property_child)

        self.assertFalse(invalid_parent_result.is_valid)
        self.assertIn(
            "NON_CLASS_PROPERTY_HAS_CHILDREN",
            {issue.code for issue in invalid_parent_result.issues},
        )
        self.assertFalse(invalid_child_result.is_valid)
        self.assertIn(
            "PROPERTY_HAS_NON_PROPERTY_CHILD",
            {issue.code for issue in invalid_child_result.issues},
        )

    def test_node_label_must_be_unique_among_siblings(self) -> None:
        document = load_fixture()
        find_source_node(document, "node-004")["metadata"]["node_label"] = "TITLE"

        result = adapt_tree_document(document)

        self.assertFalse(result.is_valid)
        self.assertIn("DUPLICATE_SIBLING_LABEL", {issue.code for issue in result.issues})

    def test_audit_and_value_changes_do_not_change_schema_hash(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        after["metadata"]["last_modify_time"] = "2040-02-02 11:00:00"
        title = find_source_node(after, "node-003")
        title["metadata"]["last_modify_time"] = "2040-02-02 11:00:00"
        title["value"]["simple_value"] = "Different fictional value"

        before_result = adapt_tree_document(before)
        after_result = adapt_tree_document(after)
        assert before_result.tree is not None
        assert after_result.tree is not None
        self.assertEqual(before_result.tree.snapshot_hash, after_result.tree.snapshot_hash)

    def test_semantic_or_structural_change_changes_schema_hash(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        find_source_node(after, "node-008")["metadata"]["node_name"] = "Revised height"

        before_result = adapt_tree_document(before)
        after_result = adapt_tree_document(after)
        assert before_result.tree is not None
        assert after_result.tree is not None
        self.assertNotEqual(before_result.tree.snapshot_hash, after_result.tree.snapshot_hash)

    def test_source_object_order_does_not_change_schema_hash(self) -> None:
        before = load_fixture()
        after = copy.deepcopy(before)
        catalog = find_source_node(after, "node-002")
        catalog["subnodes"] = dict(reversed(list(catalog["subnodes"].items())))

        before_result = adapt_tree_document(before)
        after_result = adapt_tree_document(after)
        assert before_result.tree is not None
        assert after_result.tree is not None
        self.assertEqual(before_result.tree.snapshot_hash, after_result.tree.snapshot_hash)
        self.assertEqual(before_result.tree.to_dict(), after_result.tree.to_dict())

    def test_canonical_snapshot_is_detached_and_deeply_immutable(self) -> None:
        document = load_fixture()
        result = adapt_tree_document(document)
        assert result.tree is not None
        original = result.tree.to_dict()

        title = find_source_node(document, "node-003")
        title["metadata"]["value_constraints"]["raw_constraints"]["new"] = True
        title["metadata"]["extension"]["new"] = True
        self.assertEqual(result.tree.to_dict(), original)

        by_id = {node.node_id: node for node in result.tree.nodes}
        with self.assertRaises(TypeError):
            by_id["node-003"].extension["new"] = True

        exported = result.tree.to_dict()
        exported["nodes"][0]["metadata_extra"]["new"] = True
        self.assertEqual(result.tree.to_dict(), original)

    def test_parent_mismatch_is_a_hard_error(self) -> None:
        document = load_fixture()
        find_source_node(document, "node-008")["metadata"]["parent_node_id"] = "wrong-parent"

        result = adapt_tree_document(document)

        self.assertFalse(result.is_valid)
        self.assertIsNone(result.tree)
        self.assertIn("PARENT_ID_MISMATCH", {issue.code for issue in result.issues})

    def test_unknown_value_type_is_preserved_as_warning(self) -> None:
        document = load_fixture()
        find_source_node(document, "node-003")["metadata"]["value_type"] = "future_type"
        find_source_node(document, "node-003")["value"]["metadata"][
            "value_type"
        ] = "future_type"

        result = adapt_tree_document(document)

        self.assertTrue(result.is_valid)
        self.assertIn("UNOBSERVED_VALUE_TYPE", {issue.code for issue in result.issues})
        assert result.tree is not None
        by_id = {node.node_id: node for node in result.tree.nodes}
        self.assertEqual(by_id["node-003"].value_contract.value_type, "future_type")

    def test_unknown_node_wrapper_field_fails_closed_without_leaking_value(self) -> None:
        document = load_fixture()
        secret = "value-that-must-not-enter-canonical-output"
        find_source_node(document, "node-003")["future_value_payload"] = secret

        result = adapt_tree_document(document)
        report = json.dumps(result.conformance_report(), sort_keys=True)

        self.assertFalse(result.is_valid)
        self.assertIsNone(result.tree)
        self.assertIn(
            "UNCLASSIFIED_NODE_ENVELOPE_FIELD",
            {issue.code for issue in result.issues},
        )
        self.assertNotIn(secret, report)

    def test_node_limit_counts_invalid_candidates_and_reports_once(self) -> None:
        document = load_fixture()
        with patch("treeguard.adapter.MAX_NODES", 2):
            result = adapt_tree_document(document)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.observed_node_count, 2)
        self.assertEqual(
            [issue.code for issue in result.issues].count("MAX_NODE_COUNT_EXCEEDED"),
            1,
        )

    def test_curl_transcript_requires_explicit_opt_in(self) -> None:
        document = {"status": 200, "message": "ok", "data": load_fixture()}
        text = "curl --location 'http://example.invalid/tree'\n" + json.dumps(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(TreeFormatError):
                load_tree_export(path)
            result = load_tree_export(path, allow_curl_transcript=True)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.source_format, "tree-api-response.v1+curl-transcript")

    def test_conformance_report_contains_no_identifiers_or_paths(self) -> None:
        result = load_tree_export(FIXTURE_PATH)
        encoded = json.dumps(result.conformance_report(), sort_keys=True)

        self.assertNotIn("tree-fictional-museum", encoded)
        self.assertNotIn("node-001", encoded)
        self.assertNotIn("ROOT_DEMO", encoded)


if __name__ == "__main__":
    unittest.main()
