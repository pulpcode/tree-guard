from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from treeguard.adapter import load_tree_export
from treeguard.change_intent import (
    CONFIRMATION_SCHEMA_VERSION,
    IntentConfirmation,
    IntentContent,
    IntentRequest,
)
from treeguard.hashing import canonical_digest
from treeguard.retrieval_hybrid import (
    EMBEDDING_DIMENSIONS,
    HybridRetrievalError,
    build_hybrid_candidate_set,
    build_hybrid_embedding_index,
    build_hybrid_node_documents,
    build_hybrid_query_document,
    build_hybrid_query_embedding,
    vector_leg_enabled,
)
from treeguard.retrieval_role_tolerant import (
    build_boundary_tolerant_role_candidate_set,
)
from treeguard.retrieval_roles import build_retrieval_role_evidence


H1_FIXTURE = ROOT / "tests/fixtures/fictional/fire_h1_hybrid_calibration"
TREE_FIXTURE = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow/tree.json"


class HybridRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        imported = load_tree_export(TREE_FIXTURE)
        assert imported.tree is not None
        cls.tree = imported.tree
        payload = json.loads((H1_FIXTURE / "scenarios.json").read_text(encoding="utf-8"))
        cls.scenarios = {item["scenario_ref"]: item for item in payload["scenarios"]}
        cls.documents = build_hybrid_node_documents(cls.tree)

    def _case(self, scenario_ref: str):
        scenario = self.scenarios[scenario_ref]
        request = IntentRequest.from_dict(
            {"schema_version": "intent-request.v1", **scenario["request"]},
            self.tree,
        )
        intent = IntentContent(
            subject=None,
            role=None,
            scenario=None,
            lifecycle=None,
            ownership="UNKNOWN",
            node_kind=scenario["request"]["node_kind_hint"],
            value_type=scenario["request"]["value_type_hint"],
            cardinality=scenario["request"]["cardinality_hint"],
            confirmed_facts=(),
            assumptions=(),
            evidence_gaps=(),
            clarification_question=None,
        )
        draft_hash = canonical_digest(["treeguard.h1-test.v1", scenario_ref, "draft"])
        action_hash = canonical_digest(["treeguard.h1-test.v1", scenario_ref, "action"])
        payload = {
            "schema_version": CONFIRMATION_SCHEMA_VERSION,
            "status": "CONFIRMED_FOR_RETRIEVAL",
            "identity_status": "UNVERIFIED_FILE_ASSERTION",
            "semantic_approval": False,
            "patch_eligible": False,
            "source_request_hash": request.request_hash,
            "source_snapshot_hash": self.tree.snapshot_hash,
            "source_draft_hash": draft_hash,
            "source_action_hash": action_hash,
            "proposed_parent_node_id": request.proposed_parent_node_id,
            "reviewer_ref": "h1-test",
            "recorded_at": "2026-08-05T00:00:00Z",
            "intent": intent.to_dict(),
        }
        confirmation = IntentConfirmation(
            status="CONFIRMED_FOR_RETRIEVAL",
            source_request_hash=request.request_hash,
            source_snapshot_hash=self.tree.snapshot_hash,
            source_draft_hash=draft_hash,
            source_action_hash=action_hash,
            proposed_parent_node_id=request.proposed_parent_node_id,
            reviewer_ref="h1-test",
            recorded_at="2026-08-05T00:00:00Z",
            intent=intent,
            confirmation_hash=canonical_digest(payload),
        )
        annotations = tuple((item["role"], item["text"]) for item in scenario["silver_roles"])
        evidence = build_retrieval_role_evidence(request, annotations)
        return evidence, request, confirmation

    @staticmethod
    def _unit(axis: int, sign: float = 1.0) -> tuple[float, ...]:
        values = [0.0] * EMBEDDING_DIMENSIONS
        values[axis] = sign
        return tuple(values)

    def test_documents_are_canonical_bounded_and_model_safe(self) -> None:
        second = build_hybrid_node_documents(self.tree)

        self.assertEqual(self.documents, second)
        self.assertEqual(
            tuple(item.node_id for item in self.documents),
            tuple(sorted(item.node_id for item in self.documents)),
        )
        self.assertEqual(len(self.documents), 1357)
        for document in self.documents:
            with self.subTest(node_id=document.node_id):
                self.assertNotIn(document.node_id, document.to_model_text())
                self.assertNotIn("VALUE", document.to_model_text())
                self.assertLessEqual(len(document.to_model_text()), 2_000)

    def test_query_uses_source_bound_roles_and_removes_exclusion_text(self) -> None:
        evidence, request, confirmation = self._case("H1S015")

        document = build_hybrid_query_document(evidence, request, confirmation, self.tree)

        self.assertIn("交通资源下复用启停规则", document.text)
        self.assertIn("外部衔接域", document.text)
        self.assertNotIn("先遣侦察启停规则", document.text)
        self.assertTrue(vector_leg_enabled(document, self.documents))

    def test_explicit_empty_without_tree_anchor_preserves_lexical_result(self) -> None:
        evidence, request, confirmation = self._case("H1S021")
        query = build_hybrid_query_document(evidence, request, confirmation, self.tree)
        lexical = build_boundary_tolerant_role_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            include_model_expansion=False,
            max_candidates=40,
        )

        result = build_hybrid_candidate_set(evidence, request, confirmation, self.tree)

        self.assertFalse(vector_leg_enabled(query, self.documents))
        self.assertEqual(result.status, lexical.status)
        self.assertEqual(result.candidates, lexical.candidates)
        self.assertFalse(result.to_dict()["embedding_used"])
        self.assertFalse(result.to_dict()["allows_addition"])

    def test_vector_leg_recovers_a_lexical_miss_deterministically(self) -> None:
        evidence, request, confirmation = self._case("H1S001")
        lexical = build_boundary_tolerant_role_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            include_model_expansion=False,
            max_candidates=40,
        )
        lexical_ids = {item.node_id for item in lexical.candidates}
        self.assertNotIn("M5N0016", lexical_ids)
        vectors = {
            document.node_id: (
                self._unit(0)
                if document.node_id == "M5N0016"
                else self._unit(0, -1.0)
                if document.node_id in lexical_ids
                else self._unit(1)
            )
            for document in self.documents
        }
        index = build_hybrid_embedding_index(self.tree, self.documents, vectors)
        query_document = build_hybrid_query_document(evidence, request, confirmation, self.tree)
        query_embedding = build_hybrid_query_embedding(query_document, self._unit(0))

        first = build_hybrid_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            index=index,
            query_embedding=query_embedding,
        )
        second = build_hybrid_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            index=index,
            query_embedding=query_embedding,
        )

        ranks = {item.node_id: item.rank for item in first.candidates}
        self.assertLessEqual(ranks["M5N0016"], 20)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertTrue(first.to_dict()["embedding_used"])
        self.assertFalse(first.to_dict()["allows_addition"])

    def test_exact_exclusion_removes_the_highest_similarity_node(self) -> None:
        evidence, request, confirmation = self._case("H1S015")
        vectors = {
            document.node_id: self._unit(0) if document.node_id == "M5N0026" else self._unit(1)
            for document in self.documents
        }
        index = build_hybrid_embedding_index(self.tree, self.documents, vectors)
        query_document = build_hybrid_query_document(evidence, request, confirmation, self.tree)
        query_embedding = build_hybrid_query_embedding(query_document, self._unit(0))

        result = build_hybrid_candidate_set(
            evidence,
            request,
            confirmation,
            self.tree,
            index=index,
            query_embedding=query_embedding,
        )

        self.assertNotIn("M5N0026", {item.node_id for item in result.candidates})

    def test_embedding_contract_rejects_bad_or_stale_inputs(self) -> None:
        evidence, request, confirmation = self._case("H1S001")
        query_document = build_hybrid_query_document(evidence, request, confirmation, self.tree)
        bad_vectors = (
            (1.0,),
            (True,) + (0.0,) * (EMBEDDING_DIMENSIONS - 1),
            (float("nan"),) + (0.0,) * (EMBEDDING_DIMENSIONS - 1),
            (0.0,) * EMBEDDING_DIMENSIONS,
        )
        for values in bad_vectors:
            with self.subTest(vector_case=str(values[:1])):
                with self.assertRaises(HybridRetrievalError) as caught:
                    build_hybrid_query_embedding(query_document, values)
                self.assertEqual(caught.exception.code, "HYBRID_EMBEDDING_RESPONSE_INVALID")
        with self.assertRaises(HybridRetrievalError) as caught:
            build_hybrid_embedding_index(self.tree, self.documents[:-1], {})
        self.assertEqual(caught.exception.code, "HYBRID_DOCUMENT_SET_INVALID")
        with self.assertRaises(HybridRetrievalError) as caught:
            build_hybrid_candidate_set(
                evidence,
                request,
                confirmation,
                self.tree,
                index=None,
                query_embedding=build_hybrid_query_embedding(query_document, self._unit(0)),
            )
        self.assertEqual(caught.exception.code, "HYBRID_EMBEDDING_REQUIRED")

        stale_tree = replace(self.tree, snapshot_hash="0" * 64)
        stale_documents = build_hybrid_node_documents(stale_tree)
        vectors = {document.node_id: self._unit(0) for document in stale_documents}
        stale_index = build_hybrid_embedding_index(stale_tree, stale_documents, vectors)
        with self.assertRaises(HybridRetrievalError) as caught:
            build_hybrid_candidate_set(
                evidence,
                request,
                confirmation,
                self.tree,
                index=stale_index,
                query_embedding=build_hybrid_query_embedding(query_document, self._unit(0)),
            )
        self.assertEqual(caught.exception.code, "HYBRID_INDEX_STALE")


if __name__ == "__main__":
    unittest.main()
