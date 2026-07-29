from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import adapt_tree_document, load_tree_export
from treeguard.ai_review import (
    BailianConfig,
    BailianProviderError,
    BailianSemanticRecommendationProvider,
)
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.hashing import canonical_digest
from treeguard.retrieval import build_candidate_set
from treeguard.semantic_recommendation import (
    RecommendationRecord,
    RecommendationReviewAction,
    SemanticRecommendationDraft,
    SemanticRecommendationError,
    apply_recommendation_review,
    build_semantic_candidate_projection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
)


def _sources(
    *,
    subject: str | None = "Display height",
    role: str | None = "Catalog measurement",
    scenario: str | None = "Imaginary exhibition",
    lifecycle: str | None = "Catalog lifetime",
    confirmed_facts: list[str] | None = None,
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
    draft = ChangeIntentDraft.from_model_dict(
        {
            "schema_version": "change-intent-model-output.v1",
            "subject": subject,
            "role": role,
            "scenario": scenario,
            "lifecycle": lifecycle,
            "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
            "node_kind": "PROPERTY",
            "value_type": "float" if subject is not None else None,
            "cardinality": "SINGLE",
            "confirmed_facts": (
                ["A display measurement is requested."]
                if confirmed_facts is None
                else confirmed_facts
            ),
            "assumptions": [],
            "evidence_gaps": [],
            "clarification_question": None,
        },
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
    confirmation = apply_intent_review(request, draft, action, tree)
    return tree, confirmation, build_candidate_set(confirmation, tree)


def _model_payload(
    projection,
    *,
    action: str = "USE_EXISTING_NODE",
    selected_relation: str = "SEMANTICALLY_EQUIVALENT",
) -> dict:
    assessments = [
        {
            "candidate_ref": item.candidate_ref,
            "relation": (
                selected_relation if index == 0 else "NOT_EQUIVALENT"
            ),
            "reason": "The fictional contract was compared locally.",
        }
        for index, item in enumerate(projection.candidates)
    ]
    positive = action in {
        "USE_EXISTING_NODE",
        "ADD_NODE_FROM_CONTRACT",
        "ADD_CONTEXT_FIELD",
    }
    return {
        "schema_version": "semantic-recommendation-model-output.v1",
        "candidate_assessments": assessments,
        "recommended_action": action,
        "selected_candidate_ref": (
            projection.candidates[0].candidate_ref
            if positive and projection.candidates
            else None
        ),
        "rationale": "The fictional candidates support one bounded suggestion.",
        "uncertainties": (
            ["The fictional source remains incomplete."]
            if action == "ABSTAIN"
            else []
        ),
        "evidence_gaps": (
            ["A fictional supporting record is missing."]
            if action == "NEED_EVIDENCE"
            else []
        ),
        "clarification_question": (
            "Which fictional catalog context applies?"
            if action == "NEED_CLARIFICATION"
            else None
        ),
    }


def _draft(payload, tree, confirmation, candidate_set):
    return SemanticRecommendationDraft.from_model_dict(
        payload,
        confirmation,
        candidate_set,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.semantic-recommendation.zh.v1",
    )


def _review_action_payload(
    draft,
    *,
    decision: str,
    revised_recommendation=None,
    reviewer_reasoning: str | None = "A fictional expert recorded this reasoning.",
):
    return {
        "schema_version": "recommendation-review-action.v1",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "expected_draft_hash": draft.draft_hash,
        "decision": decision,
        "reviewer_ref": "fictional-steward",
        "recorded_at": "2030-01-02T03:04:05Z",
        "reviewer_reasoning": reviewer_reasoning,
        "revised_recommendation": revised_recommendation,
    }


class SemanticRecommendationTests(unittest.TestCase):
    def test_projection_is_top_eight_allowlist_without_stable_ids(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        model_view = projection.to_model_dict()
        encoded = json.dumps(model_view, ensure_ascii=False, sort_keys=True)

        self.assertLessEqual(len(projection.candidates), 8)
        self.assertEqual(
            tuple(item.candidate_ref for item in projection.candidates),
            tuple(
                f"C{index:03d}"
                for index in range(1, len(projection.candidates) + 1)
            ),
        )
        self.assertEqual(
            set(model_view),
            {
                "schema_version",
                "projection_version",
                "intent",
                "candidate_status",
                "candidates",
            },
        )
        self.assertNotIn("node_id", encoded)
        self.assertNotIn("node_hash", encoded)
        self.assertNotIn("candidate_set_hash", encoded)
        self.assertNotIn("VALUE", encoded)
        self.assertNotIn("metadata_extra", encoded)
        input_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "semantic-recommendation-model-input.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(set(input_schema["required"]), set(model_view))
        self.assertEqual(
            set(input_schema["$defs"]["candidate"]["required"]),
            set(projection.candidates[0].to_dict()),
        )

        oversized_first = replace(
            projection.candidates[0],
            path_labels=("x" * 1_000,) * 128,
        )
        with self.assertRaisesRegex(ValueError, "size limit"):
            replace(
                projection,
                candidates=(oversized_first, *projection.candidates[1:]),
            )

    def test_all_six_actions_obey_local_policy_and_replay(self) -> None:
        relation_by_action = {
            "USE_EXISTING_NODE": "SEMANTICALLY_EQUIVALENT",
            "ADD_NODE_FROM_CONTRACT": "REUSES_CONTRACT",
            "ADD_CONTEXT_FIELD": "CONTEXTUALLY_RELATED",
            "NEED_CLARIFICATION": "NOT_EQUIVALENT",
            "NEED_EVIDENCE": "NOT_EQUIVALENT",
            "ABSTAIN": "NOT_EQUIVALENT",
        }
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )

        for action, relation in relation_by_action.items():
            with self.subTest(action=action):
                payload = _model_payload(
                    projection,
                    action=action,
                    selected_relation=relation,
                )
                draft = _draft(
                    payload,
                    tree,
                    confirmation,
                    candidate_set,
                )
                replayed = SemanticRecommendationDraft.from_dict(
                    draft.to_dict(),
                    confirmation,
                    candidate_set,
                    tree,
                )

                self.assertEqual(replayed.to_dict(), draft.to_dict())
                self.assertFalse(draft.to_dict()["semantic_approval"])
                self.assertFalse(draft.to_dict()["patch_eligible"])

        draft_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "semantic-recommendation-draft.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        output_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "semantic-recommendation-model-output.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(set(draft_schema["required"]), set(draft.to_dict()))
        self.assertEqual(
            set(output_schema["required"]),
            set(draft.to_model_dict()),
        )

    def test_unknown_refs_extra_fields_and_wrong_relations_fail_closed(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        valid = _model_payload(projection)

        missing = copy.deepcopy(valid)
        missing["candidate_assessments"].pop()
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(missing, tree, confirmation, candidate_set)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_CANDIDATE_COVERAGE_INVALID",
        )

        unknown = copy.deepcopy(valid)
        unknown["candidate_assessments"][0]["candidate_ref"] = "C008"
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(unknown, tree, confirmation, candidate_set)
        self.assertIn(
            context.exception.code,
            {
                "SEMANTIC_CANDIDATE_COVERAGE_INVALID",
                "SEMANTIC_CANDIDATE_REF_INVALID",
            },
        )

        extra = copy.deepcopy(valid)
        extra["patch"] = {"operation": "ADD"}
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(extra, tree, confirmation, candidate_set)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_MODEL_FIELDS_INVALID",
        )

        wrong_relation = copy.deepcopy(valid)
        wrong_relation["candidate_assessments"][0]["relation"] = (
            "CONTEXTUALLY_RELATED"
        )
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(wrong_relation, tree, confirmation, candidate_set)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_ACTION_POLICY_INVALID",
        )

        internal_id = copy.deepcopy(valid)
        internal_id["rationale"] = "Use node-008 for the fictional change."
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(internal_id, tree, confirmation, candidate_set)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_INTERNAL_ID_FORBIDDEN",
        )

        positive_abstain = _model_payload(
            projection,
            action="ABSTAIN",
            selected_relation="SEMANTICALLY_EQUIVALENT",
        )
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(positive_abstain, tree, confirmation, candidate_set)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_ACTION_POLICY_INVALID",
        )

    def test_model_input_and_serialized_output_are_detached(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        payload = _model_payload(projection)
        draft = _draft(payload, tree, confirmation, candidate_set)
        original_count = len(draft.candidate_assessments)
        original_reason = draft.candidate_assessments[0].reason

        payload["candidate_assessments"].append(
            {
                "candidate_ref": "C008",
                "relation": "NEED_EVIDENCE",
                "reason": "Caller mutation.",
            }
        )
        payload["candidate_assessments"][0]["reason"] = "Caller mutation."
        serialized = draft.to_dict()
        serialized["candidate_assessments"][0]["reason"] = "Output mutation."
        serialized["uncertainties"].append("Output mutation.")

        self.assertEqual(len(draft.candidate_assessments), original_count)
        self.assertEqual(draft.candidate_assessments[0].reason, original_reason)
        self.assertEqual(draft.uncertainties, ())

        reversed_assessments = tuple(reversed(draft.candidate_assessments))
        reversed_payload = draft.to_dict()
        reversed_payload["candidate_assessments"] = [
            item.to_dict() for item in reversed_assessments
        ]
        reversed_payload.pop("draft_hash")
        with self.assertRaises(ValueError):
            replace(
                draft,
                candidate_assessments=reversed_assessments,
                draft_hash=canonical_digest(reversed_payload),
            )
        with self.assertRaises(ValueError):
            replace(
                draft.to_content(),
                candidate_assessments=reversed_assessments,
            )

    def test_missing_candidates_and_context_evidence_cannot_authorize_add(self) -> None:
        tree, confirmation, candidate_set = _sources(
            subject="QuasarFlux",
            role=None,
            scenario=None,
            lifecycle=None,
            confirmed_facts=[],
            proposed_parent_node_id=None,
        )
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        self.assertEqual(projection.candidates, ())
        abstain = _model_payload(projection, action="ABSTAIN")
        self.assertEqual(
            _draft(
                abstain,
                tree,
                confirmation,
                candidate_set,
            ).recommended_action,
            "ABSTAIN",
        )

        positive = copy.deepcopy(abstain)
        positive["recommended_action"] = "ADD_NODE_FROM_CONTRACT"
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(positive, tree, confirmation, candidate_set)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_ACTION_POLICY_INVALID",
        )

        tree, confirmation, candidate_set = _sources(
            scenario=None,
            confirmed_facts=[],
        )
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        context_add = _model_payload(
            projection,
            action="ADD_CONTEXT_FIELD",
            selected_relation="CONTEXTUALLY_RELATED",
        )
        with self.assertRaises(SemanticRecommendationError) as context:
            _draft(context_add, tree, confirmation, candidate_set)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_CONTEXT_EVIDENCE_REQUIRED",
        )

    def test_stored_draft_rejects_rehashed_source_binding_tamper(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        draft = _draft(
            _model_payload(projection),
            tree,
            confirmation,
            candidate_set,
        )
        tampered = draft.to_dict()
        tampered["source_projection_hash"] = "0" * 64
        payload = dict(tampered)
        payload.pop("draft_hash")
        tampered["draft_hash"] = canonical_digest(payload)

        with self.assertRaises(SemanticRecommendationError) as context:
            SemanticRecommendationDraft.from_dict(
                tampered,
                confirmation,
                candidate_set,
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_DRAFT_SOURCE_MISMATCH",
        )

        changed_document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        changed_document["map_topology"]["ROOT_DEMO"]["subnodes"]["CATALOG"][
            "subnodes"
        ]["TITLE"]["metadata"]["node_name"] = "Alternate fictional title"
        changed_result = adapt_tree_document(changed_document)
        self.assertIsNotNone(changed_result.tree)
        with self.assertRaises(SemanticRecommendationError) as context:
            SemanticRecommendationDraft.from_dict(
                draft.to_dict(),
                confirmation,
                candidate_set,
                changed_result.tree,
            )
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_CANDIDATE_SOURCE_MISMATCH",
        )

    def test_non_baseline_candidate_limit_is_rejected(self) -> None:
        tree, confirmation, _ = _sources()
        candidate_set = build_candidate_set(
            confirmation,
            tree,
            max_candidates=5,
        )

        with self.assertRaises(SemanticRecommendationError) as context:
            build_semantic_candidate_projection(
                confirmation,
                candidate_set,
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_CANDIDATE_POLICY_INVALID",
        )

    def test_provider_retries_with_json_mode_and_bounded_projection(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        valid = _model_payload(projection)

        class RecordingProvider(BailianSemanticRecommendationProvider):
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
                    {
                        "schema_version": (
                            "semantic-recommendation-model-output.v1"
                        )
                    }
                    if len(self.bodies) == 1
                    else valid
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
        draft = provider.recommend(confirmation, candidate_set, tree)
        encoded = json.dumps(provider.bodies, ensure_ascii=False, sort_keys=True)

        self.assertEqual(len(provider.bodies), 2)
        self.assertEqual(draft.recommended_action, "USE_EXISTING_NODE")
        self.assertEqual(
            provider.bodies[0]["response_format"],
            {"type": "json_object"},
        )
        self.assertEqual(provider.bodies[0]["temperature"], 0)
        self.assertFalse(provider.bodies[0]["stream"])
        user_payload = json.loads(
            provider.bodies[0]["messages"][1]["content"]
        )
        self.assertTrue(
            user_payload["deterministic_policy"][
                "add_context_field_requires_scenario_and_confirmed_fact"
            ]
        )
        self.assertEqual(
            user_payload["output_contract"][
                "candidate_assessment_required_fields"
            ],
            ["candidate_ref", "relation", "reason"],
        )
        self.assertNotIn("node-008", encoded)
        self.assertNotIn("tree-fictional-museum", encoded)
        self.assertNotIn(candidate_set.candidate_set_hash, encoded)
        self.assertNotIn(confirmation.confirmation_hash, encoded)

        class InvalidProvider(BailianSemanticRecommendationProvider):
            def _post_json(self, body):
                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "schema_version": (
                                            "semantic-recommendation-"
                                            "model-output.v1"
                                        )
                                    }
                                )
                            },
                        }
                    ]
                }

        with self.assertRaises(BailianProviderError) as context:
            InvalidProvider(
                BailianConfig(api_key="fixture-key", max_attempts=1)
            ).recommend(confirmation, candidate_set, tree)
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_MODEL_FIELDS_INVALID",
        )

    def test_human_confirm_revise_reject_are_operational_records_only(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        draft = _draft(
            _model_payload(projection),
            tree,
            confirmation,
            candidate_set,
        )
        revised = draft.to_content().to_dict()
        revised["recommended_action"] = "NEED_EVIDENCE"
        revised["selected_candidate_ref"] = None
        revised["evidence_gaps"] = [
            "A fictional specialist record is still required."
        ]

        cases = (
            ("CONFIRM_RECOMMENDATION", None, "CONFIRMED"),
            ("REVISE_RECOMMENDATION", revised, "REVISED"),
            ("REJECT_RECOMMENDATION", None, "REJECTED"),
        )
        for decision, revision, expected_status in cases:
            with self.subTest(decision=decision):
                action = RecommendationReviewAction.from_dict(
                    _review_action_payload(
                        draft,
                        decision=decision,
                        revised_recommendation=revision,
                    ),
                    confirmation,
                    candidate_set,
                    tree,
                )
                record = apply_recommendation_review(
                    draft,
                    action,
                    confirmation,
                    candidate_set,
                    tree,
                )
                replayed = RecommendationRecord.from_dict(
                    record.to_dict(),
                    draft,
                    action,
                    confirmation,
                    candidate_set,
                    tree,
                )

                self.assertEqual(replayed.to_dict(), record.to_dict())
                self.assertEqual(record.status, expected_status)
                self.assertFalse(record.to_dict()["semantic_approval"])
                self.assertFalse(record.to_dict()["patch_eligible"])
                self.assertFalse(record.to_dict()["gold_eligible"])
                self.assertEqual(
                    record.to_dict()["record_semantics"],
                    "OPERATIONAL_FEEDBACK_ONLY",
                )
                if expected_status == "REJECTED":
                    self.assertIsNone(record.effective_recommendation)
                else:
                    self.assertIsNotNone(record.effective_recommendation)

        action_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "recommendation-review-action.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        record_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "recommendation-record.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        content_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "semantic-recommendation-content.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(set(action_schema["required"]), set(action.to_dict()))
        self.assertEqual(set(record_schema["required"]), set(record.to_dict()))
        self.assertEqual(
            set(content_schema["required"]),
            set(draft.to_content().to_dict()),
        )

    def test_review_reasoning_can_be_recorded_without_becoming_gold(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        draft = _draft(
            _model_payload(projection),
            tree,
            confirmation,
            candidate_set,
        )
        reasoning = (
            "The fictional expert is uncertain and wants another specialist "
            "to inspect the scenario."
        )
        action = RecommendationReviewAction.from_dict(
            _review_action_payload(
                draft,
                decision="REJECT_RECOMMENDATION",
                reviewer_reasoning=reasoning,
            ),
            confirmation,
            candidate_set,
            tree,
        )
        record = apply_recommendation_review(
            draft,
            action,
            confirmation,
            candidate_set,
            tree,
        )
        report = record.aggregate_report()

        self.assertEqual(record.reviewer_reasoning, reasoning)
        self.assertNotIn(reasoning, json.dumps(report, sort_keys=True))
        self.assertEqual(
            set(report),
            {
                "report_version",
                "valid",
                "record_semantics",
                "status",
                "semantic_approval",
                "patch_eligible",
                "gold_eligible",
            },
        )
        self.assertFalse(report["gold_eligible"])

    def test_stale_or_invalid_human_revision_fails_closed(self) -> None:
        tree, confirmation, candidate_set = _sources()
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        draft = _draft(
            _model_payload(projection),
            tree,
            confirmation,
            candidate_set,
        )
        stale_payload = _review_action_payload(
            draft,
            decision="CONFIRM_RECOMMENDATION",
        )
        stale_payload["expected_draft_hash"] = "0" * 64
        stale = RecommendationReviewAction.from_dict(
            stale_payload,
            confirmation,
            candidate_set,
            tree,
        )
        with self.assertRaises(SemanticRecommendationError) as context:
            apply_recommendation_review(
                draft,
                stale,
                confirmation,
                candidate_set,
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "RECOMMENDATION_ACTION_STALE",
        )

        invalid_revision = draft.to_content().to_dict()
        invalid_revision["recommended_action"] = "ADD_NODE_FROM_CONTRACT"
        invalid_revision["candidate_assessments"][0]["relation"] = (
            "CONTEXTUALLY_RELATED"
        )
        with self.assertRaises(SemanticRecommendationError) as context:
            RecommendationReviewAction.from_dict(
                _review_action_payload(
                    draft,
                    decision="REVISE_RECOMMENDATION",
                    revised_recommendation=invalid_revision,
                ),
                confirmation,
                candidate_set,
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "SEMANTIC_ACTION_POLICY_INVALID",
        )

        action = RecommendationReviewAction.from_dict(
            _review_action_payload(
                draft,
                decision="CONFIRM_RECOMMENDATION",
            ),
            confirmation,
            candidate_set,
            tree,
        )
        record = apply_recommendation_review(
            draft,
            action,
            confirmation,
            candidate_set,
            tree,
        )
        tampered = record.to_dict()
        tampered["reviewer_reasoning"] = "Rehashed tampering."
        record_payload = dict(tampered)
        record_payload.pop("record_hash")
        tampered["record_hash"] = canonical_digest(record_payload)
        with self.assertRaises(SemanticRecommendationError) as context:
            RecommendationRecord.from_dict(
                tampered,
                draft,
                action,
                confirmation,
                candidate_set,
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "RECOMMENDATION_RECORD_SOURCE_MISMATCH",
        )


if __name__ == "__main__":
    unittest.main()
