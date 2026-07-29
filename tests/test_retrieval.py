from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import adapt_tree_document, load_tree_export
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentConfirmation,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.hashing import canonical_digest
from treeguard.retrieval import (
    CandidateRetrievalError,
    CandidateSet,
    build_candidate_set,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def _sources(
    *,
    subject: str | None = "Display height",
    proposed_parent_node_id: str | None = "node-004",
):
    result = load_tree_export(FIXTURE_PATH)
    assert result.tree is not None
    tree = result.tree
    request = IntentRequest.from_dict(
        {
            "schema_version": "intent-request.v1",
            "requirement_text": "Record one imaginary display measurement.",
            "proposed_parent_node_id": proposed_parent_node_id,
            "node_kind_hint": "PROPERTY",
            "value_type_hint": "float",
            "cardinality_hint": "SINGLE",
        },
        tree,
    )
    model_payload = {
        "schema_version": "change-intent-model-output.v1",
        "subject": subject,
        "role": None,
        "scenario": None,
        "lifecycle": None,
        "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
        "node_kind": "PROPERTY",
        "value_type": "float" if subject is not None else None,
        "cardinality": "SINGLE",
        "confirmed_facts": [],
        "assumptions": [],
        "evidence_gaps": [],
        "clarification_question": None,
    }
    draft = ChangeIntentDraft.from_model_dict(
        model_payload,
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.change-intent.zh.v1",
    )
    action = IntentReviewAction.from_dict(
        {
            "schema_version": "intent-review-action.v1",
            "expected_draft_hash": draft.draft_hash,
            "decision": "CONFIRM_FOR_RETRIEVAL",
            "reviewer_ref": "fictional-steward",
            "recorded_at": "2030-01-02T03:04:05Z",
            "confirmed_intent": draft.intent.to_dict(),
        }
    )
    return tree, apply_intent_review(request, draft, action, tree)


class CandidateRetrievalTests(unittest.TestCase):
    def test_global_lexical_match_outranks_local_parent_boost(self) -> None:
        tree, confirmation = _sources()
        candidate_set = build_candidate_set(confirmation, tree)

        self.assertEqual(candidate_set.status, "CANDIDATES_READY")
        self.assertEqual(candidate_set.candidates[0].node_id, "node-008")
        self.assertEqual(
            candidate_set.candidates[0].score.parent_relation,
            "NONE",
        )
        self.assertTrue(
            any(
                item.score.parent_relation == "PROPOSED_PARENT"
                for item in candidate_set.candidates
            )
        )
        self.assertFalse(candidate_set.to_dict()["embedding_used"])
        self.assertFalse(candidate_set.to_dict()["allows_addition"])
        schema = json.loads(
            (
                PROJECT_ROOT / "contracts" / "candidate-set.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(set(schema["required"]), set(candidate_set.to_dict()))
        self.assertEqual(
            set(schema["$defs"]["candidate"]["required"]),
            set(candidate_set.candidates[0].to_dict()),
        )

    def test_retrieval_is_deterministic_under_node_reordering_and_replay(self) -> None:
        tree, confirmation = _sources()
        reordered_tree = replace(tree, nodes=tuple(reversed(tree.nodes)))
        first = build_candidate_set(confirmation, tree, max_candidates=5)
        second = build_candidate_set(
            confirmation,
            reordered_tree,
            max_candidates=5,
        )
        replayed = CandidateSet.from_dict(
            first.to_dict(),
            confirmation,
            tree,
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.to_dict(), replayed.to_dict())

        tampered = first.to_dict()
        tampered["candidates"][0]["score"]["total"] += 1
        with self.assertRaises(CandidateRetrievalError):
            CandidateSet.from_dict(tampered, confirmation, tree)

    def test_insufficient_signal_does_not_become_add_permission(self) -> None:
        tree, confirmation = _sources(subject=None)
        candidate_set = build_candidate_set(confirmation, tree)

        self.assertEqual(candidate_set.status, "INSUFFICIENT_SIGNAL")
        self.assertEqual(candidate_set.candidates, ())
        self.assertFalse(candidate_set.to_dict()["allows_addition"])

        _, unmatched_confirmation = _sources(
            subject="QuasarFlux",
            proposed_parent_node_id=None,
        )
        unmatched = build_candidate_set(unmatched_confirmation, tree)
        self.assertEqual(unmatched.status, "NO_CANDIDATES")
        self.assertFalse(unmatched.to_dict()["allows_addition"])

    def test_unsupported_and_unclassified_fields_do_not_enter_candidates(self) -> None:
        tree, confirmation = _sources()
        nodes = tuple(
            replace(node, kind="UNSUPPORTED")
            if node.node_id == "node-008"
            else node
            for node in tree.nodes
        )
        candidate_set = build_candidate_set(
            confirmation,
            replace(tree, nodes=nodes),
        )
        encoded = json.dumps(candidate_set.to_dict(), sort_keys=True)

        self.assertNotIn("node-008", {item.node_id for item in candidate_set.candidates})
        self.assertNotIn("extension", encoded)
        self.assertNotIn("metadata_extra", encoded)
        self.assertNotIn("has_value_envelope", encoded)

    def test_rejected_and_stale_confirmations_fail_closed(self) -> None:
        tree, confirmation = _sources()
        rejected_payload = confirmation.to_dict()
        rejected_payload["status"] = "REJECTED"
        rejected_payload["intent"] = None
        rejected_payload.pop("confirmation_hash")
        rejected = IntentConfirmation(
            status="REJECTED",
            source_request_hash=confirmation.source_request_hash,
            source_snapshot_hash=confirmation.source_snapshot_hash,
            source_draft_hash=confirmation.source_draft_hash,
            source_action_hash=confirmation.source_action_hash,
            proposed_parent_node_id=confirmation.proposed_parent_node_id,
            reviewer_ref=confirmation.reviewer_ref,
            recorded_at=confirmation.recorded_at,
            intent=None,
            confirmation_hash=canonical_digest(rejected_payload),
        )
        with self.assertRaises(CandidateRetrievalError) as context:
            build_candidate_set(rejected, tree)
        self.assertEqual(
            context.exception.code,
            "CANDIDATE_INTENT_NOT_CONFIRMED",
        )

        changed = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        changed = copy.deepcopy(changed)
        changed["metadata"]["concurrent_version"] += 1
        changed["map_topology"]["ROOT_DEMO"]["metadata"]["node_name"] = (
            "Revised fictional museum"
        )
        changed_result = adapt_tree_document(changed)
        assert changed_result.tree is not None
        with self.assertRaises(CandidateRetrievalError) as context:
            build_candidate_set(confirmation, changed_result.tree)
        self.assertEqual(context.exception.code, "CANDIDATE_SOURCE_STALE")


if __name__ == "__main__":
    unittest.main()
