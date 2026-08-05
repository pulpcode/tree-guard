from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard.adapter import load_tree_export
from treeguard.change_intent import (
    CONFIRMATION_SCHEMA_VERSION,
    IntentConfirmation,
    IntentContent,
    IntentRequest,
)
from treeguard.hashing import canonical_digest
from treeguard.h2_index_io import (
    read_private_h2_embedding_index,
    write_private_h2_embedding_index,
)
from treeguard.retrieval_hybrid import (
    EMBEDDING_DIMENSIONS,
    HybridRetrievalError,
    build_hybrid_node_documents,
)
from treeguard.retrieval_hybrid_h2 import (
    H2EmbeddingIndex,
    H2EmbeddingProfile,
    build_h2_candidate_set,
    build_h2_embedding_index,
    build_h2_query_embedding,
)
from treeguard.retrieval_hybrid import build_hybrid_query_document
from treeguard.retrieval_roles import build_retrieval_role_evidence


ROOT = Path(__file__).resolve().parents[1]
TREE_FIXTURE = ROOT / "tests/fixtures/fictional/tree_export.json"
INDEX_SCHEMA = ROOT / "contracts/hybrid-embedding-index.h2.v1.schema.json"
PROFILE_SCHEMA = ROOT / "contracts/embedding-profile.h2.v1.schema.json"
QUERY_SCHEMA = ROOT / "contracts/hybrid-query-embedding.h2.v1.schema.json"
CANDIDATE_SCHEMA = ROOT / "contracts/hybrid-candidate-set.h2.v1.schema.json"


def _unit() -> tuple[float, ...]:
    return (1.0,) + (0.0,) * (EMBEDDING_DIMENSIONS - 1)


class H2HybridContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        imported = load_tree_export(TREE_FIXTURE)
        assert imported.tree is not None
        cls.tree = imported.tree
        cls.documents = build_hybrid_node_documents(cls.tree)
        cls.profile = H2EmbeddingProfile.build(
            artifact_manifest_hash="e" * 64,
            batch_size=16,
        )
        cls.index = build_h2_embedding_index(
            cls.tree,
            cls.documents,
            {document.node_id: _unit() for document in cls.documents},
            cls.profile,
        )

    def test_schemas_match_runtime_field_sets(self) -> None:
        index_schema = json.loads(INDEX_SCHEMA.read_text(encoding="utf-8"))
        profile_schema = json.loads(PROFILE_SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(set(index_schema["required"]), set(self.index.to_dict()))
        self.assertEqual(
            set(index_schema["$defs"]["entry"]["required"]),
            set(self.index.entries[0].to_dict()),
        )
        self.assertEqual(
            set(profile_schema["required"]),
            set(self.profile.to_dict()),
        )

        evidence, request, confirmation = _case(self.tree)
        query_document = build_hybrid_query_document(
            evidence, request, confirmation, self.tree
        )
        query_embedding = build_h2_query_embedding(
            query_document, _unit(), self.profile
        )
        candidate_set = build_h2_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            profile=self.profile,
            index=self.index,
            query_embedding=query_embedding,
        )
        query_schema = json.loads(QUERY_SCHEMA.read_text(encoding="utf-8"))
        candidate_schema = json.loads(CANDIDATE_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            set(query_schema["required"]), set(query_embedding.to_dict())
        )
        self.assertEqual(
            set(candidate_schema["required"]), set(candidate_set.to_dict())
        )
        self.assertEqual(
            set(candidate_schema["$defs"]["candidate"]["required"]),
            set(candidate_set.candidates[0].to_dict()),
        )
        self.assertEqual(
            set(candidate_schema["$defs"]["score"]["required"]),
            set(candidate_set.candidates[0].score.to_dict()),
        )

    def test_h2_candidate_set_is_profile_bound_and_deterministic(self) -> None:
        evidence, request, confirmation = _case(self.tree)
        query_document = build_hybrid_query_document(
            evidence, request, confirmation, self.tree
        )
        query_embedding = build_h2_query_embedding(
            query_document, _unit(), self.profile
        )

        first = build_h2_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            profile=self.profile,
            index=self.index,
            query_embedding=query_embedding,
        )
        second = build_h2_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            profile=self.profile,
            index=self.index,
            query_embedding=query_embedding,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            first.to_dict()["schema_version"],
            "treeguard.hybrid-candidate-set.h2.v1",
        )
        self.assertEqual(first.source_profile_hash, self.profile.profile_hash)
        self.assertTrue(first.vector_enabled)
        self.assertFalse(first.to_dict()["allows_addition"])

    def test_private_round_trip_is_0600_and_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "h2-index.json"
            self.assertTrue(write_private_h2_embedding_index(path, self.index))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(
                read_private_h2_embedding_index(path, self.tree, self.profile),
                self.index,
            )
            self.assertFalse(write_private_h2_embedding_index(path, self.index))

    def test_wrong_profile_tree_and_rehashed_tamper_are_rejected(self) -> None:
        wrong_profile = H2EmbeddingProfile.build(
            artifact_manifest_hash="f" * 64,
            batch_size=16,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "h2-index.json"
            self.assertTrue(write_private_h2_embedding_index(path, self.index))
            with self.assertRaises(HybridRetrievalError) as captured:
                read_private_h2_embedding_index(path, self.tree, wrong_profile)
            self.assertEqual(captured.exception.code, "H2_INDEX_STALE")

        stale_tree = replace(self.tree, snapshot_hash="0" * 64)
        with self.assertRaises(HybridRetrievalError) as captured:
            from treeguard.retrieval_hybrid_h2 import verify_h2_embedding_index

            verify_h2_embedding_index(self.index, stale_tree, self.profile)
        self.assertEqual(captured.exception.code, "H2_INDEX_STALE")

        payload = self.index.to_dict()
        payload["source_profile_hash"] = "0" * 64
        payload_without_hash = {
            key: value for key, value in payload.items() if key != "index_hash"
        }
        payload["index_hash"] = canonical_digest(payload_without_hash)
        rebuilt = H2EmbeddingIndex.from_dict(payload)
        with self.assertRaises(HybridRetrievalError) as captured:
            from treeguard.retrieval_hybrid_h2 import verify_h2_embedding_index

            verify_h2_embedding_index(rebuilt, self.tree, self.profile)
        self.assertEqual(captured.exception.code, "H2_INDEX_STALE")


def _case(tree):
    request = IntentRequest.from_dict(
        {
            "schema_version": "intent-request.v1",
            "requirement_text": "Reuse the existing Display height property.",
            "proposed_parent_node_id": "node-004",
            "node_kind_hint": "PROPERTY",
            "value_type_hint": "float",
            "cardinality_hint": "SINGLE",
        },
        tree,
    )
    intent = IntentContent(
        subject=None,
        role=None,
        scenario=None,
        lifecycle=None,
        ownership="UNKNOWN",
        node_kind="PROPERTY",
        value_type="float",
        cardinality="SINGLE",
        confirmed_facts=(),
        assumptions=(),
        evidence_gaps=(),
        clarification_question=None,
    )
    draft_hash = canonical_digest(["treeguard.h2-test.v1", "draft"])
    action_hash = canonical_digest(["treeguard.h2-test.v1", "action"])
    payload = {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "status": "CONFIRMED_FOR_RETRIEVAL",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "semantic_approval": False,
        "patch_eligible": False,
        "source_request_hash": request.request_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": draft_hash,
        "source_action_hash": action_hash,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "reviewer_ref": "h2-test",
        "recorded_at": "2026-08-05T00:00:00Z",
        "intent": intent.to_dict(),
    }
    confirmation = IntentConfirmation(
        status="CONFIRMED_FOR_RETRIEVAL",
        source_request_hash=request.request_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=draft_hash,
        source_action_hash=action_hash,
        proposed_parent_node_id=request.proposed_parent_node_id,
        reviewer_ref="h2-test",
        recorded_at="2026-08-05T00:00:00Z",
        intent=intent,
        confirmation_hash=canonical_digest(payload),
    )
    evidence = build_retrieval_role_evidence(
        request, (("TARGET", "Display height"),)
    )
    return evidence, request, confirmation


if __name__ == "__main__":
    unittest.main()
