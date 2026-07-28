from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from treeguard import adapt_tree_document
from treeguard.business_review import mine_business_version_pair
from treeguard.evidence import (
    EvidenceProjectionError,
    build_business_review_evidence_pack,
)
from treeguard.hashing import canonical_digest
from treeguard.models import freeze_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "llm-evidence-pack.v1.schema.json"


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


def canonical_version(document: dict, version: str, record_id: str):
    source = copy.deepcopy(document)
    source["metadata"]["version"] = version
    source["metadata"]["id"] = record_id
    result = adapt_tree_document(source)
    if result.tree is None:
        raise AssertionError(
            f"fixture failed canonicalization: {[issue.code for issue in result.issues]}"
        )
    return result.tree


def review_fixture():
    before_document = load_fixture()
    after_document = copy.deepcopy(before_document)
    find_source_node(after_document, "node-008")["metadata"]["node_name"] = (
        "Revised display height"
    )
    before = canonical_version(before_document, "V1", "record-v1")
    after = canonical_version(after_document, "V2", "record-v2")
    run = mine_business_version_pair(
        before,
        after,
        base_position=0,
        target_position=1,
    )
    return run, before, after


class EvidenceProjectionTests(unittest.TestCase):
    def test_projection_is_allowlisted_and_uses_opaque_refs(self) -> None:
        run, before, after = review_fixture()

        pack = build_business_review_evidence_pack(run, before, after)
        model_input = pack.to_model_dict()
        encoded = json.dumps(model_input, ensure_ascii=False, sort_keys=True)

        self.assertEqual(model_input["focus_nodes"][0]["ref"], "F001")
        self.assertEqual(pack.reference_to_node_id["F001"], "node-008")
        self.assertNotIn("node-008", encoded)
        self.assertNotIn(pack.case_id, encoded)
        self.assertNotIn(pack.source_run_hash, encoded)
        self.assertNotIn(pack.pack_hash, encoded)
        self.assertNotIn("reference_to_node_id", model_input)
        self.assertNotIn("metadata_extra", encoded)
        self.assertNotIn("extension", encoded)
        self.assertNotIn("remark", encoded)
        self.assertNotIn("source_route", encoded)
        self.assertNotIn("simple_value", encoded)

    def test_unclassified_values_and_raw_value_never_enter_model_input(self) -> None:
        before_document = load_fixture()
        after_document = copy.deepcopy(before_document)
        secret = "secret-that-must-not-enter-the-model"
        target = find_source_node(after_document, "node-008")
        target["metadata"]["future_field"] = secret
        target["metadata"]["extension"] = {"future_payload": secret}
        value_target = find_source_node(after_document, "node-003")
        value_target["value"]["simple_value"] = secret
        before = canonical_version(before_document, "V1", "record-v1")
        after = canonical_version(after_document, "V2", "record-v2")
        run = mine_business_version_pair(
            before,
            after,
            base_position=0,
            target_position=1,
        )

        pack = build_business_review_evidence_pack(run, before, after)
        encoded = json.dumps(pack.to_model_dict(), ensure_ascii=False, sort_keys=True)

        self.assertNotIn(secret, encoded)
        self.assertIn("METADATA_CHANGED_UNCLASSIFIED", encoded)
        self.assertIn("EXTENSION_CHANGED_UNCLASSIFIED", encoded)

    def test_projection_contract_and_context_budget(self) -> None:
        run, before, after = review_fixture()
        pack = build_business_review_evidence_pack(run, before, after)
        schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(set(schema["required"]), set(pack.to_dict()))
        with self.assertRaises(EvidenceProjectionError) as error:
            build_business_review_evidence_pack(
                run,
                before,
                after,
                max_payload_chars=10,
            )
        self.assertEqual(
            error.exception.code,
            "EVIDENCE_CONTEXT_BUDGET_EXCEEDED",
        )

    def test_manually_constructed_extra_fields_are_rejected(self) -> None:
        run, before, after = review_fixture()
        pack = build_business_review_evidence_pack(run, before, after)
        payload = pack.to_dict()
        payload.pop("pack_hash")
        payload["focus_nodes"][0]["raw_value"] = "must-not-be-sent"
        tampered_focus = tuple(
            freeze_json(item) for item in payload["focus_nodes"]
        )

        with self.assertRaises(ValueError):
            replace(
                pack,
                focus_nodes=tampered_focus,
                pack_hash=canonical_digest(payload),
            )

    def test_pack_detaches_caller_owned_proxy_backing(self) -> None:
        run, before, after = review_fixture()
        pack = build_business_review_evidence_pack(run, before, after)
        reference_backing = dict(pack.reference_to_node_id)
        focus_backing = dict(pack.focus_nodes[0])

        detached = replace(
            pack,
            focus_nodes=(MappingProxyType(focus_backing),),
            reference_to_node_id=MappingProxyType(reference_backing),
        )
        reference_backing["F001"] = "mutated-node"
        focus_backing["ref"] = "F999"

        self.assertEqual(detached.reference_to_node_id["F001"], "node-008")
        self.assertEqual(detached.focus_nodes[0]["ref"], "F001")

    def test_projection_rejects_invalid_case_and_candidate_limits(self) -> None:
        run, before, after = review_fixture()
        with self.assertRaises(EvidenceProjectionError):
            build_business_review_evidence_pack(
                run,
                before,
                after,
                case_index=1,
            )
        with self.assertRaises(EvidenceProjectionError):
            build_business_review_evidence_pack(
                run,
                before,
                after,
                max_candidates=-1,
            )


if __name__ == "__main__":
    unittest.main()
