from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from treeguard import load_tree_export
from treeguard.ai_review import (
    BailianConfig,
    BailianIntentDraftProvider,
)
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentClarificationAnswer,
    IntentClarificationRound,
    IntentConfirmation,
    IntentRequest,
    IntentReviewAction,
    IntentValidationError,
    apply_intent_review,
    build_intent_clarification_model_input,
    reviewable_intent_draft_from_dict,
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


def _question_model_payload() -> dict:
    payload = _model_payload()
    payload["evidence_gaps"] = ["The fictional measurement unit is unknown."]
    payload["clarification_question"] = (
        "Which fictional measurement unit should be used?"
    )
    return payload


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


def _question_draft(request, tree):
    return ChangeIntentDraft.from_model_dict(
        _question_model_payload(),
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.change-intent.zh.v1",
    )


def _answer(draft):
    return IntentClarificationAnswer.from_dict(
        {
            "schema_version": "intent-clarification-answer.v1",
            "identity_status": "UNVERIFIED_FILE_ASSERTION",
            "expected_draft_hash": draft.draft_hash,
            "answer_text": "Use imaginary catalog units.",
            "answered_by_ref": "fictional-steward",
            "recorded_at": "2030-01-02T03:04:05Z",
        }
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
    def test_model_content_errors_identify_the_invalid_field_safely(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        invalid_values = {
            "subject": "",
            "ownership": "NOT_AN_OWNERSHIP",
            "node_kind": "NOT_A_KIND",
            "cardinality": "NOT_A_CARDINALITY",
            "confirmed_facts": ["duplicate", "duplicate"],
            "assumptions": [{"not": "text"}],
            "evidence_gaps": None,
            "clarification_question": [],
        }

        for field_name, invalid_value in invalid_values.items():
            with self.subTest(field_name=field_name):
                payload = _model_payload()
                payload[field_name] = invalid_value
                with self.assertRaises(IntentValidationError) as captured:
                    ChangeIntentDraft.from_model_dict(
                        payload,
                        request,
                        tree,
                        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                        model_capability="JSON_OBJECT",
                        model_name="fixture-model",
                        prompt_version="treeguard.change-intent.zh.v3",
                    )
                self.assertEqual(
                    captured.exception.code,
                    f"INTENT_MODEL_{field_name.upper()}_INVALID",
                )
                self.assertNotIn("duplicate", str(captured.exception))
                self.assertNotIn("NOT_A_", str(captured.exception))

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

    def test_minimal_request_allows_unknown_hints_and_no_parent(self) -> None:
        tree = _tree()
        payload = _request_payload()
        payload.update(
            {
                "proposed_parent_node_id": None,
                "node_kind_hint": "UNKNOWN",
                "value_type_hint": None,
                "cardinality_hint": "UNKNOWN",
            }
        )
        request = IntentRequest.from_dict(payload, tree)

        self.assertEqual(
            request.to_model_dict(tree),
            {
                "requirement_text": "Record display height.",
                "hints": {
                    "node_kind": "UNKNOWN",
                    "value_type": None,
                    "cardinality": "UNKNOWN",
                },
                "proposed_parent": None,
            },
        )

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

    def test_clarification_is_required_before_confirmation(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        draft = _question_draft(request, tree)

        with self.assertRaises(IntentValidationError) as context:
            apply_intent_review(request, draft, _action(draft), tree)
        self.assertEqual(
            context.exception.code,
            "INTENT_CLARIFICATION_REQUIRED",
        )

        rejected = apply_intent_review(
            request,
            draft,
            _action(draft, decision="REJECT_DRAFT"),
            tree,
        )
        self.assertEqual(rejected.status, "REJECTED")

    def test_single_clarification_round_replays_and_can_be_confirmed(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        initial_draft = _question_draft(request, tree)
        answer = _answer(initial_draft)
        model_input = build_intent_clarification_model_input(
            request,
            initial_draft,
            answer,
            tree,
        )
        round_artifact = IntentClarificationRound.from_model_dict(
            _model_payload(),
            request,
            initial_draft,
            answer,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_capability="JSON_OBJECT",
            model_name="fixture-model",
            prompt_version="treeguard.change-intent-clarification.zh.v1",
        )
        replayed_round = reviewable_intent_draft_from_dict(
            round_artifact.to_dict(),
            request,
            tree,
        )
        action = _action(replayed_round)
        confirmation = apply_intent_review(
            request,
            replayed_round,
            action,
            tree,
        )
        replayed_confirmation = IntentConfirmation.from_dict(
            confirmation.to_dict(),
            request,
            replayed_round,
            action,
            tree,
        )

        self.assertEqual(round_artifact.review_status, "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(replayed_round.to_dict(), round_artifact.to_dict())
        self.assertEqual(
            replayed_confirmation.to_dict(),
            confirmation.to_dict(),
        )
        encoded = json.dumps(model_input, sort_keys=True)
        self.assertNotIn("node-002", encoded)
        self.assertNotIn(initial_draft.draft_hash, encoded)
        self.assertEqual(
            model_input["clarification"]["answer"],
            "Use imaginary catalog units.",
        )
        model_input_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "intent-clarification-model-input.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(model_input_schema["required"]),
            set(model_input),
        )
        for contract_name, artifact in (
            ("intent-clarification-answer.v1.schema.json", answer),
            (
                "intent-clarification-round.v1.schema.json",
                round_artifact,
            ),
        ):
            schema = json.loads(
                (PROJECT_ROOT / "contracts" / contract_name).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(set(schema["required"]), set(artifact.to_dict()))

        tampered = round_artifact.to_dict()
        tampered["answer"]["answer_text"] = "A changed fictional answer."
        tampered["source_answer_hash"] = canonical_digest(tampered["answer"])
        tampered_payload = dict(tampered)
        tampered_payload.pop("round_hash")
        tampered["round_hash"] = canonical_digest(tampered_payload)
        changed_round = IntentClarificationRound.from_dict(
            tampered,
            request,
            tree,
        )
        with self.assertRaises(IntentValidationError) as context:
            apply_intent_review(request, changed_round, action, tree)
        self.assertEqual(context.exception.code, "INTENT_ACTION_STALE")

    def test_clarification_limit_stops_confirmation(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        initial_draft = _question_draft(request, tree)
        answer = _answer(initial_draft)
        round_artifact = IntentClarificationRound.from_model_dict(
            _question_model_payload(),
            request,
            initial_draft,
            answer,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_capability="JSON_OBJECT",
            model_name="fixture-model",
            prompt_version="treeguard.change-intent-clarification.zh.v1",
        )

        self.assertEqual(
            round_artifact.review_status,
            "CLARIFICATION_LIMIT_REACHED",
        )
        with self.assertRaises(IntentValidationError) as context:
            apply_intent_review(
                request,
                round_artifact,
                _action(round_artifact),
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_CLARIFICATION_LIMIT_REACHED",
        )

        stale_answer = _answer(initial_draft).to_dict()
        stale_answer["expected_draft_hash"] = "0" * 64
        with self.assertRaises(IntentValidationError) as context:
            build_intent_clarification_model_input(
                request,
                initial_draft,
                IntentClarificationAnswer.from_dict(stale_answer),
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_CLARIFICATION_ANSWER_STALE",
        )

    def test_clarification_inputs_and_confirmed_content_fail_closed(
        self,
    ) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        ready_draft = _draft(request, tree)
        question_draft = _question_draft(request, tree)

        with self.assertRaises(IntentValidationError) as context:
            build_intent_clarification_model_input(
                request,
                ready_draft,
                IntentClarificationAnswer.from_dict(
                    {
                        "schema_version": "intent-clarification-answer.v1",
                        "identity_status": "UNVERIFIED_FILE_ASSERTION",
                        "expected_draft_hash": ready_draft.draft_hash,
                        "answer_text": "No clarification was requested.",
                        "answered_by_ref": "fictional-steward",
                        "recorded_at": "2030-01-02T03:04:05Z",
                    }
                ),
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_CLARIFICATION_NOT_REQUIRED",
        )

        base_answer = _answer(question_draft).to_dict()
        invalid_answers = (
            (
                {**base_answer, "unexpected": True},
                "INTENT_CLARIFICATION_ANSWER_FIELDS_INVALID",
            ),
            (
                {**base_answer, "answer_text": " "},
                "INTENT_CLARIFICATION_ANSWER_VALUE_INVALID",
            ),
            (
                {**base_answer, "recorded_at": "not-a-time"},
                "INTENT_CLARIFICATION_ANSWER_VALUE_INVALID",
            ),
            (
                {**base_answer, "identity_status": "VERIFIED"},
                "INTENT_CLARIFICATION_ANSWER_POLICY_INVALID",
            ),
        )
        for payload, expected_code in invalid_answers:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(IntentValidationError) as context:
                    IntentClarificationAnswer.from_dict(payload)
                self.assertEqual(context.exception.code, expected_code)

        answer_with_id = {
            **base_answer,
            "answer_text": "Use node-002 for this fictional answer.",
        }
        with self.assertRaises(IntentValidationError) as context:
            build_intent_clarification_model_input(
                request,
                question_draft,
                IntentClarificationAnswer.from_dict(answer_with_id),
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_CLARIFICATION_INTERNAL_ID_FORBIDDEN",
        )

        with patch(
            "treeguard.change_intent.MAX_CLARIFICATION_MODEL_INPUT_CHARS",
            1,
        ):
            with self.assertRaises(IntentValidationError) as context:
                build_intent_clarification_model_input(
                    request,
                    question_draft,
                    _answer(question_draft),
                    tree,
                )
        self.assertEqual(
            context.exception.code,
            "INTENT_CLARIFICATION_PROJECTION_TOO_LARGE",
        )

        unresolved_action = _action(ready_draft).to_dict()
        unresolved_action["confirmed_intent"] = _question_model_payload()
        unresolved_action["confirmed_intent"].pop("schema_version")
        with self.assertRaises(IntentValidationError) as context:
            apply_intent_review(
                request,
                ready_draft,
                IntentReviewAction.from_dict(unresolved_action),
                tree,
            )
        self.assertEqual(
            context.exception.code,
            "INTENT_ACTION_CLARIFICATION_UNRESOLVED",
        )

    def test_provider_retries_with_exact_contract_and_safe_error_code(
        self,
    ) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        rejected_marker = "fictional-rejected-response-marker"
        traces = []

        class RecordingProvider(BailianIntentDraftProvider):
            def __init__(self):
                super().__init__(
                    BailianConfig(
                        api_key="fixture-key",
                        max_attempts=2,
                    ),
                    trace_sink=traces.append,
                )
                self.bodies = []

            def _post_json(self, body):
                self.bodies.append(body)
                payload = _model_payload()
                if len(self.bodies) == 1:
                    payload["cardinality"] = "NOT_A_CARDINALITY"
                    payload["confirmed_facts"].append(rejected_marker)
                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps(payload)},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 40,
                        "completion_tokens": 20,
                        "total_tokens": 60,
                        "provider_private_counter": 999,
                    },
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
        first_user_payload = json.loads(
            provider.bodies[0]["messages"][1]["content"]
        )
        retry_user_payload = json.loads(
            provider.bodies[1]["messages"][1]["content"]
        )
        output_contract = first_user_payload["output_contract"]
        self.assertEqual(
            set(output_contract["exact_object_template"]),
            set(_model_payload()),
        )
        self.assertFalse(output_contract["additional_fields_allowed"])
        self.assertTrue(output_contract["top_level_object_only"])
        self.assertIn(
            "输入直接支持时",
            output_contract["template_usage"],
        )
        self.assertEqual(
            output_contract["field_semantics"]["subject"],
            "本次要治理的信息项或字段名称，不是树 ID",
        )
        self.assertIn("必须写入", output_contract["hint_policy"])
        self.assertEqual(
            first_user_payload["stage_policy"]["intent_goal"],
            "COMPILE_SEARCHABLE_INTENT",
        )
        self.assertTrue(
            first_user_payload["stage_policy"][
                "candidate_conflicts_belong_to_semantic_stage"
            ]
        )
        self.assertTrue(
            first_user_payload["stage_policy"][
                "request_ambiguity_still_requires_one_question"
            ]
        )
        self.assertNotIn(
            "complete_explicit_hints_prefer_null_question",
            first_user_payload["stage_policy"],
        )
        self.assertIn(
            "不得仅因为可能存在树结构冲突而提前提问",
            provider.bodies[0]["messages"][0]["content"],
        )
        self.assertIn(
            "需求文本自身仍存在未解决的互斥解释",
            provider.bodies[0]["messages"][0]["content"],
        )
        self.assertEqual(
            retry_user_payload["previous_validation_error"],
            "INTENT_MODEL_CARDINALITY_INVALID",
        )
        self.assertIn(
            "失败类别为 INTENT_MODEL_CARDINALITY_INVALID",
            provider.bodies[1]["messages"][0]["content"],
        )
        self.assertIn(
            "不能机械照抄",
            provider.bodies[0]["messages"][0]["content"],
        )
        self.assertIn(
            "subject 表示本次要治理的信息项或字段名称",
            provider.bodies[0]["messages"][0]["content"],
        )
        self.assertEqual(
            draft.prompt_version,
            "treeguard.change-intent.zh.v4",
        )
        self.assertNotIn(rejected_marker, json.dumps(provider.bodies[1]))
        self.assertNotIn("node-002", encoded)
        self.assertNotIn("tree-fictional-museum", encoded)
        self.assertEqual(len(traces), 2)
        self.assertEqual(traces[0].stage, "INTENT_DRAFT")
        self.assertEqual(
            traces[0].validation_error_code,
            "INTENT_MODEL_CARDINALITY_INVALID",
        )
        self.assertEqual(traces[1].validation_status, "PASSED")
        self.assertEqual(traces[1].thinking_status, "DISABLED")
        self.assertEqual(
            traces[0].request_messages[0].content,
            provider.bodies[0]["messages"][0]["content"],
        )
        self.assertIn(rejected_marker, traces[0].response_content)
        self.assertEqual(
            dict(traces[1].usage),
            {
                "prompt_tokens": 40,
                "completion_tokens": 20,
                "total_tokens": 60,
            },
        )
        encoded_trace = json.dumps(
            [trace.to_dict() for trace in traces],
            ensure_ascii=False,
        )
        self.assertNotIn("fixture-key", encoded_trace)
        self.assertNotIn("dashscope.aliyuncs.com", encoded_trace)
        self.assertNotIn("provider_private_counter", encoded_trace)

    def test_provider_clarifies_with_json_mode_and_bounded_projection(self) -> None:
        tree = _tree()
        request = IntentRequest.from_dict(_request_payload(), tree)
        initial_draft = _question_draft(request, tree)
        answer = _answer(initial_draft)
        traces = []

        class RecordingProvider(BailianIntentDraftProvider):
            def __init__(self):
                super().__init__(
                    BailianConfig(
                        api_key="fixture-key",
                        max_attempts=2,
                    ),
                    trace_sink=traces.append,
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
        round_artifact = provider.clarify(
            request,
            initial_draft,
            answer,
            tree,
        )
        encoded = json.dumps(provider.bodies, sort_keys=True)

        self.assertEqual(len(provider.bodies), 2)
        self.assertEqual(
            round_artifact.review_status,
            "READY_FOR_HUMAN_REVIEW",
        )
        self.assertEqual(
            provider.bodies[0]["response_format"],
            {"type": "json_object"},
        )
        self.assertNotIn("node-002", encoded)
        self.assertNotIn(initial_draft.draft_hash, encoded)
        system_prompt = provider.bodies[0]["messages"][0]["content"]
        self.assertIn("不得同时保留", system_prompt)
        self.assertIn("一个最重要的原子问题", system_prompt)
        self.assertIn("不得拼接两个问题", system_prompt)
        self.assertIn("必须返回 JSON null", system_prompt)
        self.assertIn("必须返回空数组", system_prompt)
        self.assertEqual(len(traces), 2)
        self.assertEqual(
            {trace.stage for trace in traces},
            {"INTENT_CLARIFICATION"},
        )
        self.assertEqual(
            [trace.validation_status for trace in traces],
            ["FAILED", "PASSED"],
        )


if __name__ == "__main__":
    unittest.main()
