from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import load_tree_export
from treeguard.change_intent import ChangeIntentDraft, IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.scenario_validation import (
    ACTION_SCHEMA_VERSION,
    INTENT_RUN_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    REVIEW_DECISION,
    ReviewedValidationScenario,
    ScenarioReviewAction,
    ScenarioValidationError,
    apply_scenario_review,
    run_reviewed_intent_slice,
)
from treeguard.tree_understanding import (
    SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
    ScenarioCandidateDraft,
    ScenarioPreparationNotExecuted,
    build_scenario_preparation_batch,
    build_scenario_preparation_plan,
    build_scenario_preparation_projection,
    build_tree_diagnostic_profile,
)
from treeguard.workbench_validation import (
    ValidationScenarioOracle,
    ValidationScenarioRequest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def _all_projections(tree, profile, plan):
    return tuple(
        build_scenario_preparation_projection(
            tree,
            profile,
            plan,
            unit.plan_unit_ref,
        )
        for unit in plan.units
    )


class FakeIntentDraftProvider:
    def __init__(self, *, clarification: bool = False) -> None:
        self.clarification = clarification
        self.calls = 0

    def draft(self, request: IntentRequest, tree) -> ChangeIntentDraft:
        self.calls += 1
        question = (
            "Which fictional structural interpretation should be used?"
            if self.clarification
            else None
        )
        return ChangeIntentDraft.from_model_dict(
            {
                "schema_version": "change-intent-model-output.v1",
                "subject": "Fictional structural request",
                "role": "Validation fixture",
                "scenario": "Imaginary catalog",
                "lifecycle": "Fixture lifetime",
                "ownership": "UNKNOWN",
                "node_kind": request.node_kind_hint,
                "value_type": request.value_type_hint,
                "cardinality": request.cardinality_hint,
                "confirmed_facts": ["A fictional validation request was supplied."],
                "assumptions": [],
                "evidence_gaps": (
                    ["The fictional structural interpretation is unresolved."]
                    if question is not None
                    else []
                ),
                "clarification_question": question,
            },
            request,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-test-model",
            prompt_version="treeguard.change-intent.test.v1",
        )


def _context(plan_unit_ref: str = "U004"):
    result = load_tree_export(FIXTURE_PATH)
    if result.tree is None:
        raise AssertionError("fictional tree fixture failed adaptation")
    tree = result.tree
    profile = build_tree_diagnostic_profile(tree)
    plan = build_scenario_preparation_plan(tree, profile)
    projection = build_scenario_preparation_projection(
        tree,
        profile,
        plan,
        plan_unit_ref,
    )
    model_payload = {
        "schema_version": SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
        "plan_unit_ref": projection.plan_unit_ref,
        "scenario_ref": "S001",
        "planning_mode": projection.planning_mode,
        "scenario_family": projection.scenario_family,
        "target_stage": projection.target_stage,
        "requirement_text": "Prepare a fictional structural change request.",
        "proposed_parent_ref": projection.proposed_parent_ref,
        "node_kind_hint": projection.node_kind_hint,
        "value_type_hint": projection.value_type_hint,
        "cardinality_hint": projection.cardinality_hint,
        "supporting_node_refs": [projection.primary_anchor_ref],
        "source_signal_refs": list(projection.signal_refs),
        "requested_aspects": [
            {
                "aspect": "The selected fictional structure.",
                "supporting_node_refs": [projection.primary_anchor_ref],
            }
        ],
        "rationale": "The bounded structure supports this fictional request.",
        "uncertainties": (
            ["The fictional request still needs bounded context."]
            if projection.scenario_family
            in {"HOMONYM_CLARIFICATION", "UNBOUNDED_COMBINATION"}
            else []
        ),
        "evidence_gaps": (
            ["The fictional tree lacks the requested business evidence."]
            if projection.scenario_family == "INSUFFICIENT_EVIDENCE"
            else []
        ),
    }
    candidate = ScenarioCandidateDraft.from_model_dict(
        model_payload,
        projection,
        plan,
        profile,
        tree,
        model_provider="FICTIONAL_TEST_PROVIDER",
        model_capability="JSON_OBJECT",
        model_name="fictional-test-model",
        prompt_version="treeguard.scenario-preparation.test.v1",
    )
    not_executed = tuple(
        ScenarioPreparationNotExecuted(
            plan_unit_ref=unit.plan_unit_ref,
            reason_code="FIXTURE_SCOPE_NOT_ATTEMPTED",
        )
        for unit in plan.units
        if unit.plan_unit_ref != plan_unit_ref
    )
    batch = build_scenario_preparation_batch(
        plan,
        (candidate,),
        (),
        not_executed=not_executed,
        projections=_all_projections(tree, profile, plan),
        source_node_count=profile.node_count,
        preparation_source_status="FIXTURE_REPLAY",
    )
    return (
        tree,
        profile,
        plan,
        projection,
        batch,
        batch.candidates[0],
    )


def _action(
    tree,
    profile,
    plan,
    projection,
    batch,
    batch_candidate,
    *,
    draft_status: str = "READY_FOR_HUMAN_REVIEW",
) -> ScenarioReviewAction:
    return ScenarioReviewAction(
        expected_candidate_hash=batch_candidate.draft.draft_hash,
        expected_batch_hash=batch.batch_hash,
        expected_candidate_ref=batch_candidate.candidate_ref,
        expected_snapshot_hash=tree.snapshot_hash,
        expected_profile_hash=profile.profile_hash,
        expected_plan_hash=plan.plan_hash,
        expected_projection_hash=projection.projection_hash,
        decision=REVIEW_DECISION,
        reviewer_ref="fictional-reviewer",
        recorded_at="2030-01-02T03:04:05Z",
        final_request=ValidationScenarioRequest(
            requirement_text="Prepare a fictional structural change request.",
            proposed_parent_node_id=None,
            node_kind_hint="UNKNOWN",
            value_type_hint=None,
            cardinality_hint="UNKNOWN",
        ),
        observable_oracle=ValidationScenarioOracle(
            draft_status=draft_status,
            clarification_status=None,
            candidate_status=None,
            recommendation_status=None,
        ),
    )


class ScenarioValidationTests(unittest.TestCase):
    def test_review_freezes_request_oracle_and_source_bindings(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context()
        action = _action(
            tree, profile, plan, projection, batch, batch_candidate
        )

        reviewed = apply_scenario_review(
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )

        self.assertEqual(reviewed.status, "APPROVED_FOR_VALIDATION")
        self.assertEqual(batch.status, "PARTIAL")
        self.assertEqual(batch.completed_unit_count, 1)
        self.assertEqual(batch.failed_unit_count, 0)
        self.assertGreater(batch.not_executed_unit_count, 0)
        self.assertEqual(reviewed.request, action.final_request)
        self.assertEqual(reviewed.oracle, action.observable_oracle)
        self.assertEqual(
            reviewed.source_candidate_hash,
            batch_candidate.draft.draft_hash,
        )
        self.assertEqual(reviewed.source_batch_hash, batch.batch_hash)
        self.assertEqual(reviewed.candidate_ref, batch_candidate.candidate_ref)
        self.assertEqual(reviewed.source_snapshot_hash, tree.snapshot_hash)
        self.assertEqual(reviewed.source_profile_hash, profile.profile_hash)
        self.assertEqual(reviewed.source_plan_hash, plan.plan_hash)
        self.assertFalse(reviewed.semantic_approval)
        self.assertFalse(reviewed.gold_eligible)
        self.assertFalse(reviewed.patch_eligible)
        self.assertFalse(action.semantic_approval)
        self.assertFalse(action.gold_eligible)
        self.assertFalse(action.patch_eligible)

    def test_action_and_reviewed_record_round_trip_exact_contracts(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context()
        action = _action(
            tree, profile, plan, projection, batch, batch_candidate
        )
        parsed_action = ScenarioReviewAction.from_dict(action.to_dict())
        reviewed = apply_scenario_review(
            parsed_action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )

        parsed_reviewed = ReviewedValidationScenario.from_dict(
            reviewed.to_dict(),
            parsed_action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )

        self.assertEqual(parsed_action, action)
        self.assertEqual(parsed_reviewed, reviewed)
        self.assertEqual(action.to_dict()["schema_version"], ACTION_SCHEMA_VERSION)
        self.assertEqual(
            reviewed.to_dict()["schema_version"],
            RECORD_SCHEMA_VERSION,
        )

    def test_stale_action_is_rejected(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context()
        action = replace(
            _action(
                tree, profile, plan, projection, batch, batch_candidate
            ),
            expected_candidate_hash="0" * 64,
        )

        with self.assertRaises(ScenarioValidationError) as caught:
            apply_scenario_review(
                action,
                batch,
                batch_candidate,
                projection,
                plan,
                profile,
                tree,
            )

        self.assertEqual(caught.exception.code, "SCENARIO_REVIEW_ACTION_STALE")

    def test_first_slice_oracle_rejects_every_later_stage_expectation(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context()
        later_statuses = {
            "clarification_status": "READY_FOR_HUMAN_REVIEW",
            "candidate_status": "READY_FOR_HUMAN_REVIEW",
            "recommendation_status": "READY_FOR_HUMAN_REVIEW",
        }
        for field_name, field_value in later_statuses.items():
            with self.subTest(field_name=field_name):
                oracle_values = {
                    "draft_status": "NEEDS_CLARIFICATION",
                    "clarification_status": None,
                    "candidate_status": None,
                    "recommendation_status": None,
                }
                oracle_values[field_name] = field_value
                with self.assertRaises(ValueError):
                    ScenarioReviewAction(
                        expected_candidate_hash=batch_candidate.draft.draft_hash,
                        expected_batch_hash=batch.batch_hash,
                        expected_candidate_ref=batch_candidate.candidate_ref,
                        expected_snapshot_hash=tree.snapshot_hash,
                        expected_profile_hash=profile.profile_hash,
                        expected_plan_hash=plan.plan_hash,
                        expected_projection_hash=projection.projection_hash,
                        decision=REVIEW_DECISION,
                        reviewer_ref="fictional-reviewer",
                        recorded_at="2030-01-02T03:04:05Z",
                        final_request=ValidationScenarioRequest(
                            requirement_text="A fictional request.",
                            proposed_parent_node_id=None,
                            node_kind_hint="UNKNOWN",
                            value_type_hint=None,
                            cardinality_hint="UNKNOWN",
                        ),
                        observable_oracle=ValidationScenarioOracle(
                            **oracle_values,
                        ),
                    )

    def test_pending_candidate_cannot_bypass_review_gate(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context()
        action = _action(
            tree, profile, plan, projection, batch, batch_candidate
        )
        provider = FakeIntentDraftProvider()

        with self.assertRaises(ScenarioValidationError) as caught:
            run_reviewed_intent_slice(
                batch_candidate.draft,  # type: ignore[arg-type]
                action,
                batch,
                batch_candidate,
                projection,
                plan,
                profile,
                tree,
                provider,
            )

        self.assertEqual(caught.exception.code, "SCENARIO_REVIEW_REQUIRED")
        self.assertEqual(provider.calls, 0)

    def test_intent_slice_calls_draft_once_and_marks_later_stages_not_run(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context("U004")
        action = _action(
            tree, profile, plan, projection, batch, batch_candidate
        )
        reviewed = apply_scenario_review(
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )
        provider = FakeIntentDraftProvider()

        result = run_reviewed_intent_slice(
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            provider,
        )

        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.intent_validation_status, "MATCH")
        self.assertEqual(result.retrieval_validation_status, "NOT_RUN")
        self.assertEqual(result.recommendation_validation_status, "NOT_RUN")
        self.assertEqual(result.target_validation_status, "MATCH")
        self.assertEqual(
            result.to_dict()["schema_version"],
            INTENT_RUN_SCHEMA_VERSION,
        )

    def test_intent_mismatch_is_observed_without_running_later_stages(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context("U004")
        action = _action(
            tree, profile, plan, projection, batch, batch_candidate
        )
        reviewed = apply_scenario_review(
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )
        provider = FakeIntentDraftProvider(clarification=True)

        result = run_reviewed_intent_slice(
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            provider,
        )

        self.assertEqual(result.actual_draft_status, "NEEDS_CLARIFICATION")
        self.assertEqual(result.intent_validation_status, "MISMATCH")
        self.assertEqual(result.target_validation_status, "MISMATCH")
        self.assertEqual(result.retrieval_validation_status, "NOT_RUN")
        self.assertEqual(result.recommendation_validation_status, "NOT_RUN")

    def test_non_intent_target_records_intent_but_target_remains_not_run(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context("U001")
        self.assertEqual(batch_candidate.draft.target_stage, "RETRIEVAL")
        action = _action(
            tree, profile, plan, projection, batch, batch_candidate
        )
        reviewed = apply_scenario_review(
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )
        provider = FakeIntentDraftProvider()

        result = run_reviewed_intent_slice(
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            provider,
        )

        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.intent_validation_status, "MATCH")
        self.assertEqual(result.target_validation_status, "NOT_RUN")
        self.assertEqual(result.retrieval_validation_status, "NOT_RUN")

    def test_rehashed_tampering_is_rejected_before_provider_call(self) -> None:
        tree, profile, plan, projection, batch, batch_candidate = _context()
        action = _action(
            tree, profile, plan, projection, batch, batch_candidate
        )
        reviewed = apply_scenario_review(
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )
        payload = reviewed.to_dict()
        payload["source_snapshot_hash"] = "0" * 64
        payload.pop("reviewed_hash")
        tampered = replace(
            reviewed,
            source_snapshot_hash="0" * 64,
            reviewed_hash=canonical_digest(payload),
        )
        provider = FakeIntentDraftProvider()

        with self.assertRaises(ScenarioValidationError) as caught:
            run_reviewed_intent_slice(
                tampered,
                action,
                batch,
                batch_candidate,
                projection,
                plan,
                profile,
                tree,
                provider,
            )

        self.assertEqual(
            caught.exception.code,
            "SCENARIO_REVIEWED_SOURCE_MISMATCH",
        )
        self.assertEqual(provider.calls, 0)

    def test_run_level_refs_distinguish_two_local_s001_candidates(self) -> None:
        first = _context("U001")
        second = _context("U004")
        tree, profile, plan = first[:3]
        first_projection = first[3]
        second_projection = second[3]
        first_draft = first[5].draft
        second_draft = second[5].draft
        not_executed = tuple(
            ScenarioPreparationNotExecuted(
                plan_unit_ref=unit.plan_unit_ref,
                reason_code="FIXTURE_SCOPE_NOT_ATTEMPTED",
            )
            for unit in plan.units
            if unit.plan_unit_ref not in {"U001", "U004"}
        )
        batch = build_scenario_preparation_batch(
            plan,
            (first_draft, second_draft),
            (),
            not_executed=not_executed,
            projections=_all_projections(tree, profile, plan),
            source_node_count=profile.node_count,
            preparation_source_status="FIXTURE_REPLAY",
        )
        first_candidate, second_candidate = batch.candidates
        self.assertEqual(first_candidate.draft.scenario_ref, "S001")
        self.assertEqual(second_candidate.draft.scenario_ref, "S001")
        self.assertEqual(first_candidate.candidate_ref, "C001")
        self.assertEqual(second_candidate.candidate_ref, "C002")
        self.assertEqual(batch.status, "PARTIAL")
        self.assertEqual(batch.failed_unit_count, 0)
        self.assertGreater(batch.not_executed_unit_count, 0)

        first_action = _action(
            tree,
            profile,
            plan,
            first_projection,
            batch,
            first_candidate,
        )
        second_action = _action(
            tree,
            profile,
            plan,
            second_projection,
            batch,
            second_candidate,
        )
        first_reviewed = apply_scenario_review(
            first_action,
            batch,
            first_candidate,
            first_projection,
            plan,
            profile,
            tree,
        )
        second_reviewed = apply_scenario_review(
            second_action,
            batch,
            second_candidate,
            second_projection,
            plan,
            profile,
            tree,
        )

        self.assertEqual(first_reviewed.candidate_ref, "C001")
        self.assertEqual(second_reviewed.candidate_ref, "C002")
        self.assertEqual(first_reviewed.status, "APPROVED_FOR_VALIDATION")
        self.assertEqual(second_reviewed.status, "APPROVED_FOR_VALIDATION")
        self.assertNotEqual(
            first_reviewed.scenario_family,
            second_reviewed.scenario_family,
        )
        self.assertEqual(first_reviewed.source_batch_hash, batch.batch_hash)
        self.assertEqual(second_reviewed.source_batch_hash, batch.batch_hash)

    def test_contract_schemas_are_strict_and_forbid_policy_escalation(self) -> None:
        for filename in (
            "scenario-review-action.v1.schema.json",
            "scenario-review-record.v1.schema.json",
            "scenario-review-intent-run.v1.schema.json",
        ):
            payload = json.loads((PROJECT_ROOT / "contracts" / filename).read_text())
            self.assertFalse(payload["additionalProperties"])
        action_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "scenario-review-action.v1.schema.json"
            ).read_text()
        )
        self.assertEqual(action_schema["properties"]["semantic_approval"]["const"], False)
        self.assertEqual(action_schema["properties"]["gold_eligible"]["const"], False)
        self.assertEqual(action_schema["properties"]["patch_eligible"]["const"], False)
        self.assertEqual(
            action_schema["properties"]["expected_candidate_ref"]["pattern"],
            r"^C(?:00[1-9]|0[12][0-9]|03[0-2])$",
        )
        oracle_schema = action_schema["$defs"]["oracle"]["properties"]
        for field_name in (
            "clarification_status",
            "candidate_status",
            "recommendation_status",
        ):
            self.assertIsNone(oracle_schema[field_name]["const"])


if __name__ == "__main__":
    unittest.main()
