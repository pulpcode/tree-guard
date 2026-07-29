from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import load_tree_export
from treeguard.ai_review import (
    BailianConfig,
    BailianIntentDraftProvider,
)
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentConfirmation,
    IntentRequest,
    IntentReviewAction,
    IntentValidationError,
    apply_intent_review,
)
from treeguard.hashing import canonical_digest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def _tree():
    result = load_tree_export(FIXTURE_PATH)
    assert result.tree is not None
    return result.tree


def _request_payload(*, requirement_text: str = "Record display height.") -> dict:
    return {
        "schema_version": "intent-request.v1",
        "requirement_text": requirement_text,
        "proposed_parent_node_id": "node-002",
        "node_kind_hint": "PROPERTY",
        "value_type_hint": "float",
        "cardinality_hint": "SINGLE",
    }


def _model_payload(*, subject: str = "Display height") -> dict:
    return {
        "schema_version": "change-intent-model-output.v1",
        "subject": subject,
        "role": "Catalog measurement",
        "scenario": "Imaginary exhibition",
        "lifecycle": "Catalog lifetime",
        "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
        "node_kind": "PROPERTY",
        "value_type": "float",
        "cardinality": "SINGLE",
        "confirmed_facts": ["A display height is requested."],
        "assumptions": ["The value describes one catalog item."],
        "evidence_gaps": [],
        "clarification_question": None,
    }


def _draft(request, tree):
    return ChangeIntentDraft.from_model_dict(
        _model_payload(),
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.change-intent.zh.v1",
    )


def _action(draft, *, decision: str = "CONFIRM_FOR_RETRIEVAL"):
    return IntentReviewAction.from_dict(
        {
            "schema_version": "intent-review-action.v1",
            "expected_draft_hash": draft.draft_hash,
            "decision": decision,
            "reviewer_ref": "fictional-steward",
            "recorded_at": "2030-01-02T03:04:05Z",
            "confirmed_intent": (
                draft.intent.to_dict()
                if decision == "CONFIRM_FOR_RETRIEVAL"
                else None
            ),
        }
    )


class ChangeIntentTests(unittest.TestCase):
    def test_request_projection_is_allowlisted_and_omits_internal_ids(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        model_view = request.to_model_dict(tree)
        encoded = json.dumps(model_view, sort_keys=True)

        self.assertEqual(
            set(model_view),
            {"requirement_text", "hints", "proposed_parent"},
        )
        self.assertNotIn("node-002", encoded)
        self.assertNotIn("tree-fictional-museum", encoded)
        self.assertNotIn("simple_value", encoded)
        self.assertNotIn("Fictional exhibit", encoded)

    def test_model_output_is_detached_and_internal_ids_are_rejected(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        payload = _model_payload()
        draft = ChangeIntentDraft.from_model_dict(
            payload,
            request,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_capability="JSON_OBJECT",
            model_name="fixture-model",
            prompt_version="treeguard.change-intent.zh.v1",
        )
        payload["confirmed_facts"].append("caller mutation")
        serialized = draft.to_dict()
        serialized["intent"]["confirmed_facts"].append("output mutation")

        self.assertEqual(
            draft.intent.confirmed_facts,
            ("A display height is requested.",),
        )
        self.assertEqual(
            set(draft.to_dict()),
            {
                "schema_version",
                "model_provider",
                "model_capability",
                "model_name",
                "prompt_version",
                "model_provenance_status",
                "source_request_hash",
                "source_snapshot_hash",
                "review_status",
                "intent",
                "draft_hash",
            },
        )

        with self.assertRaises(IntentValidationError) as context:
            ChangeIntentDraft.from_model_dict(
                _model_payload(subject="node-008"),
                request,
                tree,
                model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                model_capability="JSON_OBJECT",
                model_name="fixture-model",
                prompt_version="treeguard.change-intent.zh.v1",
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_MODEL_INTERNAL_ID_FORBIDDEN",
        )

        with self.assertRaises(IntentValidationError) as context:
            ChangeIntentDraft.from_model_dict(
                _model_payload(subject="node-999"),
                request,
                tree,
                model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                model_capability="JSON_OBJECT",
                model_name="fixture-model",
                prompt_version="treeguard.change-intent.zh.v1",
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_MODEL_INTERNAL_ID_FORBIDDEN",
        )

    def test_confirmation_is_retrieval_only_and_replays_trusted_sources(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        draft = _draft(request, tree)
        action = _action(draft)
        confirmation = apply_intent_review(request, draft, action, tree)
        replayed = IntentConfirmation.from_dict(
            confirmation.to_dict(),
            request,
            draft,
            action,
            tree,
        )

        self.assertEqual(replayed.to_dict(), confirmation.to_dict())
        draft_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "change-intent-draft.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        confirmation_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "intent-confirmation.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(set(draft_schema["required"]), set(draft.to_dict()))
        self.assertEqual(
            set(confirmation_schema["required"]),
            set(confirmation.to_dict()),
        )
        self.assertEqual(confirmation.status, "CONFIRMED_FOR_RETRIEVAL")
        self.assertFalse(confirmation.to_dict()["semantic_approval"])
        self.assertFalse(confirmation.to_dict()["patch_eligible"])

        tampered = confirmation.to_dict()
        tampered["reviewer_ref"] = "different-fictional-reviewer"
        tampered_payload = dict(tampered)
        tampered_payload.pop("confirmation_hash")
        tampered["confirmation_hash"] = canonical_digest(tampered_payload)
        with self.assertRaises(IntentValidationError) as context:
            IntentConfirmation.from_dict(
                tampered,
                request,
                draft,
                action,
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_CONFIRMATION_SOURCE_MISMATCH",
        )

    def test_stale_action_and_wrong_request_are_rejected(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        draft = _draft(request, tree)
        stale_payload = _action(draft).to_dict()
        stale_payload["expected_draft_hash"] = "0" * 64
        stale_action = IntentReviewAction.from_dict(stale_payload)

        with self.assertRaises(IntentValidationError) as context:
            apply_intent_review(request, draft, stale_action, tree)
        self.assertEqual(context.exception.code, "INTENT_ACTION_STALE")

        other_request = IntentRequest.from_dict(
            _request_payload(requirement_text="Record a fictional width."),
            tree,
        )
        with self.assertRaises(IntentValidationError) as context:
            ChangeIntentDraft.from_dict(draft.to_dict(), other_request, tree)
        self.assertEqual(
            context.exception.code,
            "INTENT_DRAFT_SOURCE_MISMATCH",
        )

        with self.assertRaises(IntentValidationError) as context:
            IntentRequest.from_dict(
                _request_payload(),
                replace(tree, source_map_type="instance"),
            )
        self.assertEqual(context.exception.code, "INTENT_SOURCE_NOT_RESOURCE")

        inconsistent = draft.to_dict()
        inconsistent["review_status"] = "NEEDS_CLARIFICATION"
        inconsistent_payload = dict(inconsistent)
        inconsistent_payload.pop("draft_hash")
        inconsistent["draft_hash"] = canonical_digest(inconsistent_payload)
        with self.assertRaises(IntentValidationError) as context:
            ChangeIntentDraft.from_dict(inconsistent, request, tree)
        self.assertEqual(context.exception.code, "INTENT_DRAFT_INVALID")

    def test_provider_retries_with_json_mode_and_no_internal_ids(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)

        class RecordingProvider(BailianIntentDraftProvider):
            def __init__(self):
                super().__init__(
                    BailianConfig(
                        api_key="fixture-key",
                        max_attempts=2,
                    )
                )
                self.bodies = []

            def _post_json(self, body):
                self.bodies.append(body)
                payload = (
                    {"schema_version": "change-intent-model-output.v1"}
                    if len(self.bodies) == 1
                    else _model_payload()
                )
                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps(payload)},
                        }
                    ]
                }

        provider = RecordingProvider()
        draft = provider.draft(request, tree)
        encoded = json.dumps(provider.bodies, sort_keys=True)

        self.assertEqual(len(provider.bodies), 2)
        self.assertEqual(draft.intent.subject, "Display height")
        self.assertEqual(
            provider.bodies[0]["response_format"],
            {"type": "json_object"},
        )
        self.assertNotIn("node-002", encoded)
        self.assertNotIn("tree-fictional-museum", encoded)


if __name__ == "__main__":
    unittest.main()
