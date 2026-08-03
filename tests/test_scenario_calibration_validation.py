from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from test_scenario_capability_validation import (
    FakeIntentDraftProvider,
    FakeSemanticProvider,
    _frozen_context,
    _preview_candidate_set,
)

from treeguard.change_intent import IntentRequest, IntentReviewAction, apply_intent_review
from treeguard.hashing import canonical_digest
from treeguard.scenario_calibration_validation import (
    CALIBRATION_OBSERVATION_SCHEMA_VERSION,
    CALIBRATION_POLICY_SCHEMA_VERSION,
    CALIBRATION_REPORT_SCHEMA_VERSION,
    CalibrationComparisonReport,
    CalibrationObservationResult,
    ScenarioCalibrationPolicy,
    build_calibration_comparison_report,
    score_calibration_observation,
)
from treeguard.scenario_capability_validation import (
    RetrievalOracle,
    freeze_capability_overlay,
    run_reviewed_capability_scenario,
)
from treeguard.semantic_recommendation import (
    SemanticRecommendationDraft,
    build_semantic_candidate_projection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CapturingSemanticProvider(FakeSemanticProvider):
    def __init__(self, *, action: str = "USE_EXISTING_NODE") -> None:
        super().__init__()
        self.action = action
        self.draft = None

    def recommend(self, confirmation, candidate_set, tree):
        if self.action == "USE_EXISTING_NODE":
            self.draft = super().recommend(confirmation, candidate_set, tree)
            return self.draft
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        positive = self.action == "ADD_NODE_FROM_CONTRACT"
        assessments = [
            {
                "candidate_ref": item.candidate_ref,
                "relation": (
                    "REUSES_CONTRACT"
                    if positive and index == 0
                    else "NOT_EQUIVALENT"
                ),
                "reason": "A bounded fictional calibration comparison.",
            }
            for index, item in enumerate(projection.candidates)
        ]
        self.draft = SemanticRecommendationDraft.from_model_dict(
            {
                "schema_version": "semantic-recommendation-model-output.v1",
                "candidate_assessments": assessments,
                "recommended_action": self.action,
                "selected_candidate_ref": (
                    projection.candidates[0].candidate_ref if positive else None
                ),
                "rationale": "A bounded fictional calibration suggestion.",
                "uncertainties": (
                    ["The fictional source remains incomplete."]
                    if self.action == "ABSTAIN"
                    else []
                ),
                "evidence_gaps": [],
                "clarification_question": None,
            },
            confirmation,
            candidate_set,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-calibration-model",
            prompt_version="treeguard.semantic.test.v1",
        )
        return self.draft


def _run_with_provider(overlay, provider):
    (
        tree,
        profile,
        plan,
        projection,
        batch,
        batch_candidate,
        action,
        reviewed,
        _,
    ) = _frozen_context()
    run = run_reviewed_capability_scenario(
        overlay,
        reviewed,
        action,
        batch,
        batch_candidate,
        projection,
        plan,
        profile,
        tree,
        FakeIntentDraftProvider(),
        provider,
    )
    return run, tree, reviewed, _preview_candidate_set(reviewed, tree)


class ScenarioCalibrationValidationTests(unittest.TestCase):
    def test_contract_schema_required_fields_match_serializers(self):
        _, _, _, _, _, _, _, _, overlay = _frozen_context()
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=overlay.overlay_hash,
            oracle=overlay.oracle,
            retrieval_mode="TARGET_HIT",
        )
        run, _, _, _ = _run_with_provider(
            overlay,
            CapturingSemanticProvider(),
        )
        observation = CalibrationObservationResult.create(
            observation_ref="R001-C001",
            source_run_hash=run.run_hash,
            source_policy_hash=policy.policy_hash,
            strict_full_path_status=run.full_path_status,
            strict_retrieval_status=run.retrieval.status,
            calibrated_retrieval_status="MATCH",
            calibrated_retrieval_reason="CALIBRATION_TARGET_HIT",
            semantic_status="NOT_OBSERVED",
            semantic_observation_source="NONE",
            source_recommendation_draft_hash=None,
            newly_semantic_eligible=False,
        )
        report = build_calibration_comparison_report((observation,))
        cases = (
            (
                "scenario-calibration-policy.v1.schema.json",
                CALIBRATION_POLICY_SCHEMA_VERSION,
                policy.to_dict(),
            ),
            (
                "scenario-calibration-observation.v1.schema.json",
                CALIBRATION_OBSERVATION_SCHEMA_VERSION,
                observation.to_dict(),
            ),
            (
                "scenario-calibration-comparison-report.v1.schema.json",
                CALIBRATION_REPORT_SCHEMA_VERSION,
                report.to_dict(),
            ),
        )
        for filename, version, payload in cases:
            with self.subTest(filename=filename):
                schema = json.loads(
                    (PROJECT_ROOT / "contracts" / filename).read_text(encoding="utf-8")
                )
                self.assertEqual(set(schema["required"]), set(payload))
                self.assertEqual(payload["schema_version"], version)

    def test_target_hit_preserves_strict_preferred_match(self):
        _, _, _, _, _, _, _, _, overlay = _frozen_context()
        provider = CapturingSemanticProvider()
        run, _, _, candidate_set = _run_with_provider(overlay, provider)
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=overlay.overlay_hash,
            oracle=overlay.oracle,
            retrieval_mode="TARGET_HIT",
        )

        result = score_calibration_observation(
            run,
            overlay.oracle,
            policy,
            observation_ref="R001-C001",
            candidate_set=candidate_set,
            recommendation_draft=provider.draft,
        )

        self.assertEqual(result.calibrated_retrieval_status, "MATCH")
        self.assertEqual(result.semantic_status, "PREFERRED_MATCH")
        self.assertFalse(result.newly_semantic_eligible)
        self.assertEqual(
            CalibrationObservationResult.from_dict(result.to_dict()),
            result,
        )

    def test_bounded_evidence_exposes_semantic_coverage_gap(self):
        (
            tree,
            _,
            plan,
            _,
            _,
            _,
            _,
            reviewed,
            overlay,
        ) = _frozen_context()
        candidates = _preview_candidate_set(reviewed, tree).candidates
        strict_miss_oracle = replace(
            overlay.oracle,
            retrieval=RetrievalOracle(
                applicable=True,
                allowed_statuses=("CANDIDATES_READY",),
                acceptable_node_ids=(candidates[1].node_id,),
                top_k=1,
            ),
        )
        strict_miss_overlay = freeze_capability_overlay(
            reviewed,
            plan,
            tree,
            review_status="ACCEPTED",
            reviewer_ref="fictional-capability-reviewer",
            recorded_at="2030-01-02T03:05:00Z",
            review_round=1,
            oracle=strict_miss_oracle,
        )
        provider = CapturingSemanticProvider()
        run, _, _, candidate_set = _run_with_provider(strict_miss_overlay, provider)
        self.assertEqual(run.retrieval.status, "MISMATCH")
        self.assertIsNone(provider.draft)
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=strict_miss_overlay.overlay_hash,
            oracle=strict_miss_overlay.oracle,
            retrieval_mode="BOUNDED_EVIDENCE",
        )

        result = score_calibration_observation(
            run,
            strict_miss_overlay.oracle,
            policy,
            observation_ref="R001-C001",
            candidate_set=candidate_set,
            recommendation_draft=None,
        )

        self.assertEqual(result.calibrated_retrieval_status, "MATCH")
        self.assertEqual(
            result.calibrated_retrieval_reason,
            "CALIBRATION_BOUNDED_EVIDENCE_READY",
        )
        self.assertEqual(result.semantic_status, "NOT_OBSERVED")
        self.assertTrue(result.newly_semantic_eligible)

    def test_non_targeting_abstain_is_safe_but_not_preferred(self):
        _, _, _, _, _, _, _, _, overlay = _frozen_context()
        provider = CapturingSemanticProvider(action="ABSTAIN")
        run, _, _, candidate_set = _run_with_provider(overlay, provider)
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=overlay.overlay_hash,
            oracle=overlay.oracle,
            retrieval_mode="TARGET_HIT",
        )

        result = score_calibration_observation(
            run,
            overlay.oracle,
            policy,
            observation_ref="R001-C001",
            candidate_set=candidate_set,
            recommendation_draft=provider.draft,
        )

        self.assertEqual(run.recommendation.status, "MISMATCH")
        self.assertEqual(result.semantic_status, "SAFE_ALTERNATIVE")

    def test_supplemental_semantic_is_separately_bound_after_strict_short_circuit(self):
        (
            tree,
            _,
            plan,
            _,
            _,
            _,
            _,
            reviewed,
            overlay,
        ) = _frozen_context()
        candidates = _preview_candidate_set(reviewed, tree).candidates
        strict_miss_overlay = freeze_capability_overlay(
            reviewed,
            plan,
            tree,
            review_status="ACCEPTED",
            reviewer_ref="fictional-capability-reviewer",
            recorded_at="2030-01-02T03:05:00Z",
            review_round=1,
            oracle=replace(
                overlay.oracle,
                retrieval=RetrievalOracle(
                    applicable=True,
                    allowed_statuses=("CANDIDATES_READY",),
                    acceptable_node_ids=(candidates[1].node_id,),
                    top_k=1,
                ),
            ),
        )
        run, _, _, candidate_set = _run_with_provider(
            strict_miss_overlay,
            CapturingSemanticProvider(),
        )
        request = IntentRequest(
            requirement_text=reviewed.request.requirement_text,
            proposed_parent_node_id=reviewed.request.proposed_parent_node_id,
            node_kind_hint=reviewed.request.node_kind_hint,
            value_type_hint=reviewed.request.value_type_hint,
            cardinality_hint=reviewed.request.cardinality_hint,
        )
        intent_draft = FakeIntentDraftProvider().draft(request, tree)
        confirmation = apply_intent_review(
            request,
            intent_draft,
            IntentReviewAction(
                expected_draft_hash=intent_draft.draft_hash,
                decision="CONFIRM_FOR_RETRIEVAL",
                reviewer_ref="m4-validation-harness",
                recorded_at=reviewed.recorded_at,
                confirmed_intent=intent_draft.intent,
            ),
            tree,
        )
        supplemental_provider = CapturingSemanticProvider(action="ABSTAIN")
        supplemental_draft = supplemental_provider.recommend(
            confirmation,
            candidate_set,
            tree,
        )
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=strict_miss_overlay.overlay_hash,
            oracle=strict_miss_overlay.oracle,
            retrieval_mode="BOUNDED_EVIDENCE",
        )

        result = score_calibration_observation(
            run,
            strict_miss_overlay.oracle,
            policy,
            observation_ref="R001-C001",
            candidate_set=candidate_set,
            recommendation_draft=supplemental_draft,
            semantic_observation_source="SUPPLEMENTAL_CALIBRATION",
        )

        self.assertEqual(result.semantic_status, "SAFE_ALTERNATIVE")
        self.assertEqual(
            result.semantic_observation_source,
            "SUPPLEMENTAL_CALIBRATION",
        )
        self.assertEqual(
            result.source_recommendation_draft_hash,
            supplemental_draft.draft_hash,
        )
        self.assertFalse(result.newly_semantic_eligible)

    def test_unpreferred_positive_action_is_unsafe_mismatch(self):
        _, _, _, _, _, _, _, _, overlay = _frozen_context()
        provider = CapturingSemanticProvider(action="ADD_NODE_FROM_CONTRACT")
        run, _, _, candidate_set = _run_with_provider(overlay, provider)
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=overlay.overlay_hash,
            oracle=overlay.oracle,
            retrieval_mode="TARGET_HIT",
        )

        result = score_calibration_observation(
            run,
            overlay.oracle,
            policy,
            observation_ref="R001-C001",
            candidate_set=candidate_set,
            recommendation_draft=provider.draft,
        )

        self.assertEqual(result.semantic_status, "UNSAFE_MISMATCH")

    def test_empty_result_mode_rejects_targeted_oracle(self):
        _, _, _, _, _, _, _, _, overlay = _frozen_context()
        with self.assertRaises(ValueError):
            ScenarioCalibrationPolicy.create(
                source_overlay_hash=overlay.overlay_hash,
                oracle=overlay.oracle,
                retrieval_mode="EMPTY_RESULT",
            )

    def test_policy_tamper_and_stale_source_are_rejected(self):
        _, _, _, _, _, _, _, _, overlay = _frozen_context()
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=overlay.overlay_hash,
            oracle=overlay.oracle,
            retrieval_mode="TARGET_HIT",
        )
        payload = policy.to_dict()
        payload["gate_eligible"] = True
        payload["policy_hash"] = canonical_digest(
            {key: value for key, value in payload.items() if key != "policy_hash"}
        )
        with self.assertRaises(ValueError):
            ScenarioCalibrationPolicy.from_dict(
                payload,
                oracle=overlay.oracle,
                expected_overlay_hash=overlay.overlay_hash,
            )
        with self.assertRaises(ValueError):
            ScenarioCalibrationPolicy.from_dict(
                policy.to_dict(),
                oracle=overlay.oracle,
                expected_overlay_hash="f" * 64,
            )

    def test_report_is_aggregate_only_immutable_and_marks_missing_coverage(self):
        observation = CalibrationObservationResult.create(
            observation_ref="R001-C001",
            source_run_hash="a" * 64,
            source_policy_hash="b" * 64,
            strict_full_path_status="MISMATCH",
            strict_retrieval_status="MISMATCH",
            calibrated_retrieval_status="MATCH",
            calibrated_retrieval_reason="CALIBRATION_BOUNDED_EVIDENCE_READY",
            semantic_status="NOT_OBSERVED",
            semantic_observation_source="NONE",
            source_recommendation_draft_hash=None,
            newly_semantic_eligible=True,
        )

        report = build_calibration_comparison_report((observation,))

        self.assertEqual(
            report.full_path_reassessment_status,
            "INCOMPLETE_SEMANTIC_COVERAGE",
        )
        self.assertEqual(report.newly_semantic_eligible_count, 1)
        with self.assertRaises(TypeError):
            report.semantic_counts["NOT_OBSERVED"] = 0
        payload = report.to_dict()
        canaries = (
            "requirement_text",
            "node_id",
            "source_run_hash",
            "source_policy_hash",
            "prompt",
            "trace",
        )
        rendered = json.dumps(payload, sort_keys=True)
        for canary in canaries:
            self.assertNotIn(canary, rendered)
        self.assertEqual(CalibrationComparisonReport.from_dict(payload), report)

    def test_report_rejects_duplicate_observations(self):
        observation = CalibrationObservationResult.create(
            observation_ref="R001-C001",
            source_run_hash="a" * 64,
            source_policy_hash="b" * 64,
            strict_full_path_status="MISMATCH",
            strict_retrieval_status="MISMATCH",
            calibrated_retrieval_status="MISMATCH",
            calibrated_retrieval_reason="CALIBRATION_RETRIEVAL_MISMATCH",
            semantic_status="NOT_OBSERVED",
            semantic_observation_source="NONE",
            source_recommendation_draft_hash=None,
            newly_semantic_eligible=False,
        )
        with self.assertRaises(ValueError):
            build_calibration_comparison_report((observation, observation))


if __name__ == "__main__":
    unittest.main()
