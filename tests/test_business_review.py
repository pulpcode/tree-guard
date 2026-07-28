from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import adapt_tree_document
from treeguard.business_review import (
    BusinessVersionReviewError,
    VersionOrder,
    mine_business_version_pair,
    verify_business_version_review_against_snapshots,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
CONTRACT_PATH = (
    PROJECT_ROOT / "contracts" / "business-version-review.v1.schema.json"
)


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


def canonical_version(
    document: dict,
    *,
    version: str,
    record_id: str,
    revision: int,
):
    source = copy.deepcopy(document)
    source["metadata"].update(
        {
            "version": version,
            "id": record_id,
            "concurrent_version": revision,
        }
    )
    result = adapt_tree_document(source)
    if result.tree is None:
        raise AssertionError(
            f"fixture failed canonicalization: {[issue.code for issue in result.issues]}"
        )
    return result.tree


class BusinessVersionReviewTests(unittest.TestCase):
    def test_business_version_review_ignores_revision_reset(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-008")["metadata"]["node_name"] = (
            "Revised height"
        )

        run = mine_business_version_pair(
            canonical_version(
                before_document,
                version="V1",
                record_id="record-v1",
                revision=99,
            ),
            canonical_version(
                after_document,
                version="V2",
                record_id="record-v2",
                revision=1,
            ),
            base_position=0,
            target_position=1,
        )

        self.assertEqual(run.scope, "BUSINESS_VERSION")
        self.assertEqual(run.comparison_semantics, "ENDPOINT_NET_CHANGE")
        self.assertFalse(run.reconstructs_historical_operations)
        self.assertEqual(len(run.review_cases), 1)
        self.assertEqual(run.review_cases[0].change_types, ("NODE_NAME_CHANGED",))
        self.assertNotIn(
            "INTERMEDIATE_REVISIONS_UNOBSERVED",
            run.review_cases[0].reason_codes,
        )

    def test_same_business_version_and_instance_are_rejected(self) -> None:
        document = load_fixture()
        before = canonical_version(
            document,
            version="V1",
            record_id="record-v1",
            revision=1,
        )
        after = canonical_version(
            document,
            version="V1",
            record_id="record-v1",
            revision=2,
        )
        with self.assertRaises(BusinessVersionReviewError) as scope_error:
            mine_business_version_pair(
                before,
                after,
                base_position=0,
                target_position=1,
            )
        self.assertEqual(
            scope_error.exception.code,
            "BUSINESS_REVIEW_SCOPE_NOT_VERSION",
        )

        instance_document = copy.deepcopy(document)
        instance_document["metadata"]["map_type"] = "instance"
        with self.assertRaises(BusinessVersionReviewError) as source_error:
            mine_business_version_pair(
                canonical_version(
                    instance_document,
                    version="V1",
                    record_id="record-v1",
                    revision=1,
                ),
                canonical_version(
                    instance_document,
                    version="V2",
                    record_id="record-v2",
                    revision=1,
                ),
                base_position=0,
                target_position=1,
            )
        self.assertEqual(
            source_error.exception.code,
            "BUSINESS_REVIEW_SOURCE_NOT_RESOURCE",
        )

    def test_version_order_requires_explicit_adjacent_positions(self) -> None:
        with self.assertRaises(ValueError):
            VersionOrder("UNVERIFIED_EXPLICIT_SEQUENCE", 0, 2)
        with self.assertRaises(ValueError):
            VersionOrder("UNVERIFIED_EXPLICIT_SEQUENCE", True, 1)
        with self.assertRaises(ValueError):
            VersionOrder("PARSED_VERSION_STRING", 0, 1)

    def test_empty_business_version_diff_is_a_valid_run(self) -> None:
        document = load_fixture()
        run = mine_business_version_pair(
            canonical_version(
                document,
                version="V1",
                record_id="record-v1",
                revision=90,
            ),
            canonical_version(
                document,
                version="V2",
                record_id="record-v2",
                revision=1,
            ),
            base_position=3,
            target_position=4,
        )

        self.assertEqual(run.review_cases, ())
        self.assertEqual(run.informational_observations, ())
        self.assertEqual(run.summary.source_node_delta_count, 0)

    def test_contract_and_aggregate_are_allowlisted(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-008")["metadata"]["node_name"] = (
            "Sensitive fictional name"
        )
        run = mine_business_version_pair(
            canonical_version(
                before_document,
                version="V1",
                record_id="record-v1",
                revision=1,
            ),
            canonical_version(
                after_document,
                version="V2",
                record_id="record-v2",
                revision=1,
            ),
            base_position=0,
            target_position=1,
        )
        schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        serialized = run.to_dict()
        aggregate = json.dumps(run.aggregate_report(), sort_keys=True)

        self.assertEqual(set(schema["required"]), set(serialized))
        self.assertEqual(
            set(schema["$defs"]["versionOrder"]["required"]),
            set(serialized["version_order"]),
        )
        self.assertNotIn("Sensitive fictional name", aggregate)
        self.assertNotIn("node-008", aggregate)
        self.assertNotIn(run.run_hash, aggregate)

    def test_trusted_replay_rejects_tampered_run(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        find_source_node(after_document, "node-008")["metadata"]["node_name"] = (
            "Revised height"
        )
        before = canonical_version(
            before_document,
            version="V1",
            record_id="record-v1",
            revision=1,
        )
        after = canonical_version(
            after_document,
            version="V2",
            record_id="record-v2",
            revision=1,
        )
        run = mine_business_version_pair(
            before,
            after,
            base_position=0,
            target_position=1,
        )
        verify_business_version_review_against_snapshots(run, before, after)

        with self.assertRaises(ValueError):
            replace(run, comparison_semantics="HISTORICAL_OPERATIONS")


if __name__ == "__main__":
    unittest.main()
