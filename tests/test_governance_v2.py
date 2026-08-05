from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import load_tree_export
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.change_understanding_v2 import (
    ChangeUnderstandingV2,
    ChangeUnderstandingV2Error,
)
from treeguard.hashing import canonical_digest
from treeguard.retrieval import build_candidate_set
from treeguard.semantic_policy_v2 import (
    RecommendationPolicyDecisionV2,
    SemanticPolicyV2Error,
    SemanticRelationDraftV2,
    apply_deterministic_recommendation_policy_v2,
    build_semantic_relation_projection_v2,
)
from treeguard.semantic_recommendation import (
    build_semantic_candidate_projection,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def _understanding_payload(**overrides):
    payload = {
        "schema_version": "change-understanding-model-output.v2",
        "node_kind": "PROPERTY",
        "value_type": "float",
        "cardinality": "SINGLE",
        "clarification_question": None,
        "spans": [{"role": "TARGET", "text": "Display height"}],
    }
    payload.update(overrides)
    return payload


def _sources():
    loaded = load_tree_export(FIXTURE)
    assert loaded.tree is not None
    tree = loaded.tree
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
    understanding = ChangeUnderstandingV2.from_model_dict(
        _understanding_payload(),
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.change-understanding.zh.v2",
    )
    legacy_draft = ChangeIntentDraft.from_model_dict(
        {
            "schema_version": "change-intent-model-output.v1",
            "subject": "Display height",
            "role": None,
            "scenario": None,
            "lifecycle": None,
            "ownership": "UNKNOWN",
            "node_kind": "PROPERTY",
            "value_type": "float",
            "cardinality": "SINGLE",
            "confirmed_facts": [],
            "assumptions": [],
            "evidence_gaps": ["Legacy free text that v2 must not consume"],
            "clarification_question": None,
        },
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.change-intent.zh.v4",
    )
    action = IntentReviewAction.from_dict(
        {
            "schema_version": "intent-review-action.v1",
            "expected_draft_hash": legacy_draft.draft_hash,
            "decision": "CONFIRM_FOR_RETRIEVAL",
            "reviewer_ref": "fictional-steward",
            "recorded_at": "2030-01-02T03:04:05Z",
            "confirmed_intent": legacy_draft.intent.to_dict(),
        }
    )
    confirmation = apply_intent_review(
        request,
        legacy_draft,
        action,
        tree,
    )
    candidate_set = build_candidate_set(confirmation, tree)
    legacy_projection = build_semantic_candidate_projection(
        confirmation,
        candidate_set,
        tree,
    )
    projection = build_semantic_relation_projection_v2(
        understanding,
        legacy_projection,
        confirmation,
    )
    return (
        tree,
        request,
        understanding,
        confirmation,
        legacy_projection,
        projection,
    )


def _relation_payload(projection, relations=None):
    relation_values = relations or [
        "SEMANTICALLY_EQUIVALENT",
        *(["NOT_EQUIVALENT"] * (len(projection.candidates) - 1)),
    ]
    return {
        "schema_version": "semantic-relation-model-output.v2",
        "candidate_assessments": [
            {
                "candidate_ref": candidate.candidate_ref,
                "relation": relation,
                "reason": "The fictional candidate was compared.",
            }
            for candidate, relation in zip(
                projection.candidates,
                relation_values,
                strict=True,
            )
        ],
    }


def _relation_draft(tree, projection, relations=None):
    return SemanticRelationDraftV2.from_model_dict(
        _relation_payload(projection, relations),
        projection,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.semantic-relation.zh.v2",
    )


def _with_structural_intent(understanding, **changes):
    intent_payload = {
        key: value
        for key, value in understanding.structural_intent.to_dict().items()
        if key != "intent_hash"
    }
    intent_payload.update(changes)
    intent = replace(
        understanding.structural_intent,
        **changes,
        intent_hash=canonical_digest(intent_payload),
    )
    artifact_payload = understanding.to_dict()
    artifact_payload["structural_intent"] = intent.to_dict()
    artifact_payload.pop("understanding_hash")
    return replace(
        understanding,
        structural_intent=intent,
        understanding_hash=canonical_digest(artifact_payload),
    )


class ChangeUnderstandingV2Tests(unittest.TestCase):
    def test_combined_output_builds_four_field_intent_and_source_bound_roles(self) -> None:
        tree, request, understanding, _, _, _ = _sources()

        self.assertEqual(understanding.review_status, "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(
            set(understanding.structural_intent.to_dict()),
            {
                "schema_version",
                "source_request_hash",
                "node_kind",
                "value_type",
                "cardinality",
                "clarification_question",
                "intent_hash",
            },
        )
        self.assertEqual(understanding.role_evidence.spans[0].text, "Display height")
        self.assertEqual(
            request.requirement_text[
                understanding.role_evidence.spans[0].start :
                understanding.role_evidence.spans[0].end
            ],
            "Display height",
        )
        self.assertEqual(
            ChangeUnderstandingV2.from_dict(
                understanding.to_dict(),
                request,
                tree,
            ),
            understanding,
        )

    def test_hints_roles_internal_ids_and_rehashed_tamper_fail_closed(self) -> None:
        tree, request, understanding, _, _, _ = _sources()
        invalid_cases = (
            (
                _understanding_payload(node_kind="CONCEPT"),
                "UNDERSTANDING_V2_HINT_CONFLICT",
            ),
            (
                _understanding_payload(spans=[{"role": "TARGET", "text": "Missing"}]),
                "UNDERSTANDING_V2_ROLE_MODEL_SPAN_NOT_FOUND",
            ),
            (
                _understanding_payload(
                    clarification_question="Should node-008 be selected?"
                ),
                "UNDERSTANDING_V2_INTERNAL_ID_FORBIDDEN",
            ),
        )
        for payload, expected_code in invalid_cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(ChangeUnderstandingV2Error) as captured:
                    ChangeUnderstandingV2.from_model_dict(
                        payload,
                        request,
                        tree,
                        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                        model_capability="JSON_OBJECT",
                        model_name="fixture-model",
                        prompt_version="treeguard.change-understanding.zh.v2",
                    )
                self.assertEqual(captured.exception.code, expected_code)

        tampered = copy.deepcopy(understanding.to_dict())
        tampered["structural_intent"]["cardinality"] = "MULTIPLE"
        tampered["understanding_hash"] = canonical_digest(
            {key: value for key, value in tampered.items() if key != "understanding_hash"}
        )
        with self.assertRaises(ChangeUnderstandingV2Error):
            ChangeUnderstandingV2.from_dict(tampered, request, tree)

    def test_mutable_model_payload_and_serialized_output_are_detached(self) -> None:
        tree, request, understanding, _, _, _ = _sources()
        payload = _understanding_payload()
        rebuilt = ChangeUnderstandingV2.from_model_dict(
            payload,
            request,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_capability="JSON_OBJECT",
            model_name="fixture-model",
            prompt_version="treeguard.change-understanding.zh.v2",
        )
        serialized = rebuilt.to_dict()
        payload["spans"][0]["text"] = "Mutation"
        serialized["role_evidence"]["spans"][0]["text"] = "Mutation"
        self.assertEqual(rebuilt, understanding)


class SemanticPolicyV2Tests(unittest.TestCase):
    def test_v2_projection_drops_legacy_free_text_and_relation_output_has_no_action(self) -> None:
        tree, _, understanding, _, legacy_projection, projection = _sources()
        model_input = projection.to_model_dict()
        encoded = json.dumps(model_input, sort_keys=True)

        self.assertNotIn("Legacy free text that v2 must not consume", encoded)
        self.assertEqual(
            set(model_input["structural_intent"]),
            {"node_kind", "value_type", "cardinality"},
        )
        draft = _relation_draft(tree, projection)
        self.assertEqual(
            set(_relation_payload(projection)),
            {"schema_version", "candidate_assessments"},
        )
        self.assertEqual(
            SemanticRelationDraftV2.from_dict(
                draft.to_dict(),
                projection,
                tree,
            ),
            draft,
        )
        self.assertEqual(
            projection.source_candidate_set_hash,
            legacy_projection.source_candidate_set_hash,
        )
        self.assertEqual(
            projection.source_understanding_hash,
            understanding.understanding_hash,
        )

    def test_deterministic_policy_maps_relations_without_addition_permissions(self) -> None:
        (
            tree,
            _,
            understanding,
            confirmation,
            legacy_projection,
            projection,
        ) = _sources()
        relaxed_understanding = _with_structural_intent(
            understanding,
            value_type=None,
        )
        relaxed_projection = build_semantic_relation_projection_v2(
            relaxed_understanding,
            legacy_projection,
            confirmation,
        )
        cases = (
            (
                understanding,
                projection,
                ["SEMANTICALLY_EQUIVALENT"]
                + ["NOT_EQUIVALENT"] * (len(projection.candidates) - 1),
                "USE_EXISTING_NODE",
                "UNIQUE_COMPATIBLE_EQUIVALENT",
            ),
            (
                relaxed_understanding,
                relaxed_projection,
                ["SEMANTICALLY_EQUIVALENT", "SEMANTICALLY_EQUIVALENT"]
                + ["NOT_EQUIVALENT"]
                * (len(relaxed_projection.candidates) - 2),
                "NEED_CLARIFICATION",
                "MULTIPLE_COMPATIBLE_EQUIVALENTS",
            ),
            (
                understanding,
                projection,
                ["NEED_EVIDENCE"]
                + ["NOT_EQUIVALENT"] * (len(projection.candidates) - 1),
                "NEED_EVIDENCE",
                "CANDIDATE_EVIDENCE_REQUIRED",
            ),
            (
                understanding,
                projection,
                ["CONTEXTUALLY_RELATED"]
                + ["REUSES_CONTRACT"] * (len(projection.candidates) - 1),
                "ABSTAIN",
                "NO_COMPATIBLE_EQUIVALENT",
            ),
        )
        for case_understanding, case_projection, relations, action, reason in cases:
            with self.subTest(action=action):
                draft = _relation_draft(tree, case_projection, relations)
                first = apply_deterministic_recommendation_policy_v2(
                    draft,
                    case_projection,
                    case_understanding,
                )
                second = apply_deterministic_recommendation_policy_v2(
                    draft,
                    case_projection,
                    case_understanding,
                )
                self.assertEqual(first, second)
                self.assertEqual(first.recommended_action, action)
                self.assertEqual(first.decision_reason_code, reason)
                self.assertNotIn("ADD_", first.recommended_action)
                self.assertEqual(
                    RecommendationPolicyDecisionV2.from_dict(
                        first.to_dict(),
                        draft,
                        case_projection,
                        case_understanding,
                    ),
                    first,
                )

    def test_structural_conflict_unknown_refs_and_rehashed_decisions_fail_closed(self) -> None:
        (
            tree,
            _,
            understanding,
            confirmation,
            legacy_projection,
            projection,
        ) = _sources()
        incompatible_understanding = _with_structural_intent(
            understanding,
            node_kind="CONCEPT",
        )
        incompatible_projection = build_semantic_relation_projection_v2(
            incompatible_understanding,
            legacy_projection,
            confirmation,
        )
        draft = _relation_draft(tree, incompatible_projection)
        decision = apply_deterministic_recommendation_policy_v2(
            draft,
            incompatible_projection,
            incompatible_understanding,
        )
        self.assertEqual(decision.recommended_action, "ABSTAIN")

        invalid = _relation_payload(projection)
        invalid["candidate_assessments"][0]["candidate_ref"] = "C008"
        with self.assertRaises(SemanticPolicyV2Error) as captured:
            SemanticRelationDraftV2.from_model_dict(
                invalid,
                projection,
                tree,
                model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                model_capability="JSON_OBJECT",
                model_name="fixture-model",
                prompt_version="treeguard.semantic-relation.zh.v2",
            )
        self.assertEqual(
            captured.exception.code,
            "SEMANTIC_V2_CANDIDATE_COVERAGE_INVALID",
        )

        valid_draft = _relation_draft(tree, projection)
        valid_decision = apply_deterministic_recommendation_policy_v2(
            valid_draft,
            projection,
            understanding,
        )
        tampered = valid_decision.to_dict()
        tampered["recommended_action"] = "ABSTAIN"
        tampered["selected_candidate_ref"] = None
        tampered["decision_reason_code"] = "NO_COMPATIBLE_EQUIVALENT"
        tampered["decision_hash"] = canonical_digest(
            {key: value for key, value in tampered.items() if key != "decision_hash"}
        )
        with self.assertRaises(SemanticPolicyV2Error):
            RecommendationPolicyDecisionV2.from_dict(
                tampered,
                valid_draft,
                projection,
                understanding,
            )

    def test_clarification_short_circuits_before_semantic_projection(self) -> None:
        _, request, understanding, confirmation, legacy_projection, _ = _sources()
        tree = load_tree_export(FIXTURE).tree
        assert tree is not None
        clarifying = ChangeUnderstandingV2.from_model_dict(
            _understanding_payload(
                clarification_question="Which fictional scope applies?"
            ),
            request,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_capability="JSON_OBJECT",
            model_name="fixture-model",
            prompt_version="treeguard.change-understanding.zh.v2",
        )
        self.assertEqual(clarifying.review_status, "NEEDS_CLARIFICATION")
        with self.assertRaises(SemanticPolicyV2Error) as captured:
            build_semantic_relation_projection_v2(
                clarifying,
                legacy_projection,
                confirmation,
            )
        self.assertEqual(
            captured.exception.code,
            "SEMANTIC_V2_CLARIFICATION_REQUIRED",
        )

    def test_projection_rejects_a_confirmation_for_another_request(self) -> None:
        _, _, understanding, confirmation, legacy_projection, _ = _sources()
        confirmation_payload = confirmation.to_dict()
        confirmation_payload["source_request_hash"] = "f" * 64
        confirmation_payload.pop("confirmation_hash")
        mismatched_confirmation = replace(
            confirmation,
            source_request_hash="f" * 64,
            confirmation_hash=canonical_digest(confirmation_payload),
        )

        with self.assertRaises(SemanticPolicyV2Error) as captured:
            build_semantic_relation_projection_v2(
                understanding,
                legacy_projection,
                mismatched_confirmation,
            )
        self.assertEqual(captured.exception.code, "SEMANTIC_V2_SOURCE_MISMATCH")


class GovernanceV2SchemaTests(unittest.TestCase):
    def test_v2_schema_required_fields_match_runtime_outputs(self) -> None:
        tree, _, understanding, _, _, projection = _sources()
        draft = _relation_draft(tree, projection)
        decision = apply_deterministic_recommendation_policy_v2(
            draft,
            projection,
            understanding,
        )
        runtime_outputs = {
            "structural-intent.v2.schema.json": understanding.structural_intent.to_dict(),
            "retrieval-role-evidence.v1.schema.json": understanding.role_evidence.to_dict(),
            "change-understanding.v2.schema.json": understanding.to_dict(),
            "semantic-relation-model-input.v2.schema.json": projection.to_model_dict(),
            "semantic-relation-draft.v2.schema.json": draft.to_dict(),
            "recommendation-policy-decision.v2.schema.json": decision.to_dict(),
        }
        for filename, output in runtime_outputs.items():
            with self.subTest(contract=filename):
                schema = json.loads(
                    (ROOT / "contracts" / filename).read_text(encoding="utf-8")
                )
                self.assertEqual(set(schema["required"]), set(output))


if __name__ == "__main__":
    unittest.main()
