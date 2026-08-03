from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from test_scenario_validation import (
    FakeIntentDraftProvider,
    _action,
    _context,
)

from treeguard.change_intent import (
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.hashing import canonical_digest
from treeguard.retrieval import build_candidate_set
from treeguard.scenario_capability_validation import (
    CAPABILITY_OVERLAY_SCHEMA_VERSION,
    CAPABILITY_REPORT_SCHEMA_VERSION,
    CAPABILITY_RUN_SCHEMA_VERSION,
    CapabilityOracle,
    CapabilityStageResult,
    IntentFieldExpectation,
    IntentOracleProfile,
    RecommendationOracle,
    RecommendationOracleOutcome,
    RetrievalOracle,
    ScenarioCapabilityError,
    ScenarioCapabilityRun,
    ScenarioCapabilitySilverAuthorization,
    ScenarioPreparationMetrics,
    build_capability_gate_report,
    freeze_capability_overlay,
    freeze_silver_capability_authorization,
    run_reviewed_capability_scenario,
    run_silver_capability_scenario,
    verify_capability_oracle_against_reviewed_request,
)
from treeguard.scenario_validation import apply_scenario_review
from treeguard.semantic_recommendation import SemanticRecommendationDraft
from treeguard.tree_understanding import build_scenario_preparation_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeSemanticProvider:
    def __init__(self, *, selected_ref: str = "C002") -> None:
        self.selected_ref = selected_ref
        self.calls = 0

    def recommend(self, confirmation, candidate_set, tree):
        self.calls += 1
        assessments = []
        for candidate in candidate_set.candidates[:8]:
            candidate_ref = f"C{candidate.rank:03d}"
            assessments.append(
                {
                    "candidate_ref": candidate_ref,
                    "relation": (
                        "SEMANTICALLY_EQUIVALENT"
                        if candidate_ref == self.selected_ref
                        else "NOT_EQUIVALENT"
                    ),
                    "reason": "Bounded fictional validation comparison.",
                }
            )
        return SemanticRecommendationDraft.from_model_dict(
            {
                "schema_version": "semantic-recommendation-model-output.v1",
                "candidate_assessments": assessments,
                "recommended_action": "USE_EXISTING_NODE",
                "selected_candidate_ref": self.selected_ref,
                "rationale": "The fictional candidate matches the request.",
                "uncertainties": [],
                "evidence_gaps": [],
                "clarification_question": None,
            },
            confirmation,
            candidate_set,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-semantic-model",
            prompt_version="treeguard.semantic.test.v1",
        )


def _reviewed_context(*, draft_status: str = "READY_FOR_HUMAN_REVIEW"):
    tree, profile, plan, projection, batch, batch_candidate = _context("U004")
    action = _action(
        tree,
        profile,
        plan,
        projection,
        batch,
        batch_candidate,
        draft_status=draft_status,
    )
    if draft_status == "READY_FOR_HUMAN_REVIEW":
        action = replace(
            action,
            final_request=replace(
                action.final_request,
                node_kind_hint="PROPERTY",
                value_type_hint="string",
                cardinality_hint="MULTIPLE",
            ),
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
    return (
        tree,
        profile,
        plan,
        projection,
        batch,
        batch_candidate,
        action,
        reviewed,
    )


def _preview_candidate_set(reviewed, tree):
    request = IntentRequest(
        requirement_text=reviewed.request.requirement_text,
        proposed_parent_node_id=reviewed.request.proposed_parent_node_id,
        node_kind_hint=reviewed.request.node_kind_hint,
        value_type_hint=reviewed.request.value_type_hint,
        cardinality_hint=reviewed.request.cardinality_hint,
    )
    draft = FakeIntentDraftProvider().draft(request, tree)
    confirmation = apply_intent_review(
        request,
        draft,
        IntentReviewAction(
            expected_draft_hash=draft.draft_hash,
            decision="CONFIRM_FOR_RETRIEVAL",
            reviewer_ref="m4-validation-harness",
            recorded_at=reviewed.recorded_at,
            confirmed_intent=draft.intent,
        ),
        tree,
    )
    return build_candidate_set(confirmation, tree)


def _proceed_oracle(
    target_node_id: str,
    *,
    top_k: int = 1,
) -> CapabilityOracle:
    return CapabilityOracle(
        expected_route="PROCEED",
        acceptable_intent_profiles=(
            IntentOracleProfile(
                profile_ref="P001",
                field_expectations=(
                    IntentFieldExpectation("assumptions", "NOT_COMPARED", ()),
                    IntentFieldExpectation(
                        field_name="cardinality",
                        policy="EXACT_ONE_OF",
                        acceptable_values=("MULTIPLE",),
                    ),
                    IntentFieldExpectation(
                        field_name="clarification_question",
                        policy="EXACT_ONE_OF",
                        acceptable_values=(None,),
                    ),
                    IntentFieldExpectation(
                        "confirmed_facts", "NOT_COMPARED", ()
                    ),
                    IntentFieldExpectation("evidence_gaps", "NOT_COMPARED", ()),
                    IntentFieldExpectation("lifecycle", "NOT_COMPARED", ()),
                    IntentFieldExpectation(
                        field_name="node_kind",
                        policy="EXACT_ONE_OF",
                        acceptable_values=("PROPERTY",),
                    ),
                    IntentFieldExpectation("ownership", "NOT_COMPARED", ()),
                    IntentFieldExpectation("role", "NOT_COMPARED", ()),
                    IntentFieldExpectation("scenario", "NOT_COMPARED", ()),
                    IntentFieldExpectation(
                        field_name="subject",
                        policy="NOT_COMPARED",
                        acceptable_values=(),
                    ),
                    IntentFieldExpectation(
                        field_name="value_type",
                        policy="EXACT_ONE_OF",
                        acceptable_values=("string",),
                    ),
                ),
            ),
        ),
        retrieval=RetrievalOracle(
            applicable=True,
            allowed_statuses=("CANDIDATES_READY",),
            acceptable_node_ids=(target_node_id,),
            top_k=top_k,
        ),
        recommendation=RecommendationOracle(
            applicable=True,
            acceptable_outcomes=(
                RecommendationOracleOutcome(
                    action="USE_EXISTING_NODE",
                    target_node_id=target_node_id,
                    relation="SEMANTICALLY_EQUIVALENT",
                ),
            ),
        ),
    )


def _frozen_context():
    context = _reviewed_context()
    tree, _, plan, _, _, _, _, reviewed = context
    candidate_set = _preview_candidate_set(reviewed, tree)
    if not candidate_set.candidates:
        raise AssertionError("fictional test request produced no candidates")
    overlay = freeze_capability_overlay(
        reviewed,
        plan,
        tree,
        review_status="ACCEPTED",
        reviewer_ref="fictional-capability-reviewer",
        recorded_at="2030-01-02T03:05:00Z",
        review_round=1,
        oracle=_proceed_oracle(
            candidate_set.candidates[1].node_id,
            top_k=2,
        ),
    )
    return (*context, overlay)


class ScenarioCapabilityContractTests(unittest.TestCase):
    def test_silver_authorization_round_trip_is_non_gating_and_source_bound(self):
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
        authorization = freeze_silver_capability_authorization(
            reviewed,
            plan,
            tree,
            assessor_ref="codex-m4-calibration-review",
            recorded_at="2030-01-02T03:06:00Z",
            oracle=overlay.oracle,
        )

        rebuilt = ScenarioCapabilitySilverAuthorization.from_dict(
            authorization.to_dict(),
            reviewed,
            plan,
            tree,
        )

        self.assertEqual(rebuilt, authorization)
        self.assertFalse(rebuilt.gold_eligible)
        self.assertFalse(rebuilt.gate_eligible)
        self.assertFalse(rebuilt.patch_eligible)
        self.assertEqual(rebuilt.to_dict()["quality_tier"], "SILVER")
        self.assertEqual(
            rebuilt.to_dict()["assessment_authority"],
            "CODEX_ASSISTED",
        )

    def test_silver_authorization_cannot_claim_gold_or_human_authority(self):
        tree, _, plan, _, _, _, _, reviewed, overlay = _frozen_context()
        authorization = freeze_silver_capability_authorization(
            reviewed,
            plan,
            tree,
            assessor_ref="codex-m4-calibration-review",
            recorded_at="2030-01-02T03:06:00Z",
            oracle=overlay.oracle,
        )
        payload = authorization.to_dict()
        payload["gold_eligible"] = True

        with self.assertRaisesRegex(
            ScenarioCapabilityError,
            "fixed calibration policy",
        ):
            ScenarioCapabilitySilverAuthorization.from_dict(
                payload,
                reviewed,
                plan,
                tree,
            )

    def test_silver_authorization_runs_the_same_calibration_path(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            reviewed,
            overlay,
        ) = _frozen_context()
        authorization = freeze_silver_capability_authorization(
            reviewed,
            plan,
            tree,
            assessor_ref="codex-m4-calibration-review",
            recorded_at="2030-01-02T03:06:00Z",
            oracle=overlay.oracle,
        )

        result = run_silver_capability_scenario(
            authorization,
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            FakeIntentDraftProvider(),
            FakeSemanticProvider(),
        )

        self.assertEqual(result.source_overlay_hash, authorization.authorization_hash)
        self.assertEqual(result.full_path_status, "MATCH")

    def test_overlay_round_trip_binds_reviewed_bytes_tree_plan_and_oracle(self):
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

        rebuilt = type(overlay).from_dict(
            overlay.to_dict(),
            reviewed,
            plan,
            tree,
        )

        self.assertEqual(rebuilt, overlay)
        self.assertEqual(
            overlay.to_dict()["schema_version"],
            CAPABILITY_OVERLAY_SCHEMA_VERSION,
        )
        self.assertFalse(overlay.gold_eligible)
        self.assertFalse(overlay.patch_eligible)
        self.assertFalse(overlay.semantic_approval)

    def test_overlay_rejects_unknown_fields_and_tampered_reviewed_bytes(self):
        tree, profile, plan, _, _, _, _, reviewed, overlay = _frozen_context()
        unknown = overlay.to_dict()
        unknown["unexpected"] = True
        with self.assertRaises(ScenarioCapabilityError) as caught:
            type(overlay).from_dict(unknown, reviewed, plan, tree)
        self.assertEqual(caught.exception.code, "CAPABILITY_OVERLAY_FIELDS_INVALID")

        tampered_overlay = overlay.to_dict()
        tampered_overlay["source_reviewed_content_hash"] = "0" * 64
        tampered_overlay.pop("overlay_hash")
        tampered_overlay["overlay_hash"] = canonical_digest(tampered_overlay)
        with self.assertRaises(ScenarioCapabilityError) as caught:
            type(overlay).from_dict(
                tampered_overlay,
                reviewed,
                plan,
                tree,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_OVERLAY_SOURCE_MISMATCH")

        wrong_plan = build_scenario_preparation_plan(
            tree,
            profile,
            max_plan_units=1,
        )
        with self.assertRaises(ScenarioCapabilityError) as caught:
            type(overlay).from_dict(
                overlay.to_dict(),
                reviewed,
                wrong_plan,
                tree,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_OVERLAY_SOURCE_MISMATCH")

        wrong_tree = replace(tree, snapshot_hash="f" * 64)
        with self.assertRaises(ScenarioCapabilityError) as caught:
            type(overlay).from_dict(
                overlay.to_dict(),
                reviewed,
                plan,
                wrong_tree,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_OVERLAY_SOURCE_MISMATCH")

    def test_intent_profile_contract_is_ordered_and_policy_specific(self):
        with self.assertRaises(ValueError):
            IntentOracleProfile(
                profile_ref="P001",
                field_expectations=(
                    IntentFieldExpectation(
                        field_name="subject",
                        policy="NON_EMPTY",
                        acceptable_values=(),
                    ),
                    IntentFieldExpectation(
                        field_name="cardinality",
                        policy="EXACT_ONE_OF",
                        acceptable_values=("UNKNOWN",),
                    ),
                ),
            )
        with self.assertRaises(ValueError):
            IntentFieldExpectation(
                field_name="subject",
                policy="NON_EMPTY",
                acceptable_values=("must-not-be-present",),
            )
        IntentOracleProfile(
            profile_ref="P001",
            field_expectations=(
                IntentFieldExpectation(
                    field_name="evidence_gaps",
                    policy="EMPTY",
                    acceptable_values=(),
                ),
            ),
        )
        with self.assertRaises(ValueError):
            IntentFieldExpectation(
                field_name="evidence_gaps",
                policy="EXACT_ONE_OF",
                acceptable_values=("free text must not become scalar Gold",),
            )

    def test_full_chain_maps_run_local_ref_back_to_stable_node(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            reviewed,
            overlay,
        ) = _frozen_context()
        intent_provider = FakeIntentDraftProvider()
        semantic_provider = FakeSemanticProvider()

        result = run_reviewed_capability_scenario(
            overlay,
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            intent_provider,
            semantic_provider,
        )

        self.assertEqual(intent_provider.calls, 1)
        self.assertEqual(semantic_provider.calls, 1)
        self.assertEqual(result.intent.status, "MATCH")
        self.assertEqual(result.retrieval.status, "MATCH")
        self.assertEqual(result.recommendation.status, "MATCH")
        self.assertEqual(result.full_path_status, "MATCH")
        self.assertEqual(
            result.to_dict()["schema_version"], CAPABILITY_RUN_SCHEMA_VERSION
        )
        self.assertEqual(
            type(result).from_dict(
                result.to_dict(),
                overlay,
                reviewed,
                action,
                batch,
                batch_candidate,
                projection,
                plan,
                profile,
                tree,
            ),
            result,
        )
        tampered = result.to_dict()
        tampered["source_overlay_hash"] = "0" * 64
        tampered.pop("run_hash")
        tampered["run_hash"] = canonical_digest(tampered)
        with self.assertRaises(ScenarioCapabilityError) as caught:
            type(result).from_dict(
                tampered,
                overlay,
                reviewed,
                action,
                batch,
                batch_candidate,
                projection,
                plan,
                profile,
                tree,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_RUN_SOURCE_MISMATCH")

    def test_oracle_request_policy_rejects_unbound_or_conflicting_profiles(self):
        tree, _, plan, _, _, _, _, reviewed = _reviewed_context()
        candidate_set = _preview_candidate_set(reviewed, tree)
        base_oracle = _proceed_oracle(candidate_set.candidates[0].node_id)
        invalid_expectations = (
            IntentFieldExpectation("role", "NON_EMPTY", ()),
            IntentFieldExpectation("assumptions", "EMPTY", ()),
            IntentFieldExpectation("cardinality", "NOT_COMPARED", ()),
            IntentFieldExpectation("node_kind", "EXACT_ONE_OF", ("CONCEPT",)),
            IntentFieldExpectation("value_type", "NON_EMPTY", ()),
        )

        for expectation in invalid_expectations:
            with self.subTest(field=expectation.field_name):
                base_profile = base_oracle.acceptable_intent_profiles[0]
                invalid = replace(
                    base_oracle,
                    acceptable_intent_profiles=(
                        IntentOracleProfile(
                            "P001",
                            tuple(
                                expectation
                                if item.field_name == expectation.field_name
                                else item
                                for item in base_profile.field_expectations
                            ),
                        ),
                    ),
                )
                with self.assertRaises(ScenarioCapabilityError) as caught:
                    freeze_capability_overlay(
                        reviewed,
                        plan,
                        tree,
                        review_status="ACCEPTED",
                        reviewer_ref="fictional-capability-reviewer",
                        recorded_at="2030-01-02T03:05:00Z",
                        review_round=1,
                        oracle=invalid,
                    )
                self.assertEqual(
                    caught.exception.code,
                    "CAPABILITY_ORACLE_REQUEST_MISMATCH",
                )

        invalid_profile = IntentOracleProfile(
            "P002",
            (IntentFieldExpectation("scenario", "NON_EMPTY", ()),),
        )
        one_invalid_alternative = replace(
            base_oracle,
            acceptable_intent_profiles=(
                base_oracle.acceptable_intent_profiles[0],
                invalid_profile,
            ),
        )
        with self.assertRaises(ScenarioCapabilityError) as caught:
            freeze_capability_overlay(
                reviewed,
                plan,
                tree,
                review_status="ACCEPTED",
                reviewer_ref="fictional-capability-reviewer",
                recorded_at="2030-01-02T03:05:00Z",
                review_round=1,
                oracle=one_invalid_alternative,
            )
        self.assertEqual(
            caught.exception.code,
            "CAPABILITY_ORACLE_REQUEST_MISMATCH",
        )

    def test_oracle_request_policy_accepts_exact_explicit_hints(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            _,
        ) = _reviewed_context()
        explicit_action = replace(
            action,
            final_request=replace(
                action.final_request,
                node_kind_hint="PROPERTY",
                value_type_hint="string",
                cardinality_hint="MULTIPLE",
            ),
        )
        reviewed = apply_scenario_review(
            explicit_action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )
        candidate_set = _preview_candidate_set(reviewed, tree)
        oracle = _proceed_oracle(candidate_set.candidates[0].node_id)
        verify_capability_oracle_against_reviewed_request(
            oracle,
            reviewed,
            tree,
        )

        overlay = freeze_capability_overlay(
            reviewed,
            plan,
            tree,
            review_status="ACCEPTED",
            reviewer_ref="fictional-capability-reviewer",
            recorded_at="2030-01-02T03:05:00Z",
            review_round=1,
            oracle=oracle,
        )

        self.assertEqual(overlay.oracle, oracle)

    def test_legacy_unanswerable_overlay_is_readable_but_not_executable(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            reviewed,
            overlay,
        ) = _frozen_context()
        invalid_oracle = replace(
            overlay.oracle,
            acceptable_intent_profiles=(
                IntentOracleProfile(
                    "P001",
                    (IntentFieldExpectation("role", "NON_EMPTY", ()),),
                ),
            ),
        )
        payload = overlay.to_dict()
        payload["oracle"] = invalid_oracle.to_dict()
        payload["source_reviewed_content_hash"] = canonical_digest(
            {
                "source_reviewed_hash": reviewed.reviewed_hash,
                "request": {
                    "requirement_text": reviewed.request.requirement_text,
                    "proposed_parent_node_id": reviewed.request.proposed_parent_node_id,
                    "node_kind_hint": reviewed.request.node_kind_hint,
                    "value_type_hint": reviewed.request.value_type_hint,
                    "cardinality_hint": reviewed.request.cardinality_hint,
                },
                "capability_oracle": invalid_oracle.to_dict(),
            }
        )
        payload.pop("overlay_hash")
        payload["overlay_hash"] = canonical_digest(payload)
        legacy = type(overlay).from_dict(payload, reviewed, plan, tree)
        intent_provider = FakeIntentDraftProvider()
        semantic_provider = FakeSemanticProvider()

        with self.assertRaises(ScenarioCapabilityError) as caught:
            run_reviewed_capability_scenario(
                legacy,
                reviewed,
                action,
                batch,
                batch_candidate,
                projection,
                plan,
                profile,
                tree,
                intent_provider,
                semantic_provider,
            )

        self.assertEqual(
            caught.exception.code,
            "CAPABILITY_ORACLE_REQUEST_MISMATCH",
        )
        self.assertEqual(intent_provider.calls, 0)
        self.assertEqual(semantic_provider.calls, 0)

    def test_expected_clarification_matches_and_skips_later_stages(self):
        context = _reviewed_context(draft_status="NEEDS_CLARIFICATION")
        tree, profile, plan, projection, batch, batch_candidate, action, reviewed = (
            context
        )
        oracle = CapabilityOracle(
            expected_route="CLARIFY",
            acceptable_intent_profiles=(
                IntentOracleProfile(
                    profile_ref="P001",
                    field_expectations=(
                        IntentFieldExpectation(
                            "assumptions", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation(
                            "cardinality", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation(
                            field_name="clarification_question",
                            policy="NON_EMPTY",
                            acceptable_values=(),
                        ),
                        IntentFieldExpectation(
                            "confirmed_facts", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation(
                            "evidence_gaps", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation(
                            "lifecycle", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation(
                            "node_kind", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation(
                            "ownership", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation("role", "NOT_COMPARED", ()),
                        IntentFieldExpectation(
                            "scenario", "NOT_COMPARED", ()
                        ),
                        IntentFieldExpectation(
                            field_name="subject",
                            policy="NOT_COMPARED",
                            acceptable_values=(),
                        ),
                        IntentFieldExpectation(
                            "value_type", "NOT_COMPARED", ()
                        ),
                    ),
                ),
            ),
            retrieval=RetrievalOracle(False, (), (), None),
            recommendation=RecommendationOracle(False, ()),
        )
        overlay = freeze_capability_overlay(
            reviewed,
            plan,
            tree,
            review_status="ACCEPTED",
            reviewer_ref="fictional-capability-reviewer",
            recorded_at="2030-01-02T03:05:00Z",
            review_round=1,
            oracle=oracle,
        )
        semantic_provider = FakeSemanticProvider()

        result = run_reviewed_capability_scenario(
            overlay,
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            FakeIntentDraftProvider(clarification=True),
            semantic_provider,
        )

        self.assertEqual(result.full_path_status, "MATCH")
        self.assertFalse(result.retrieval.applicable)
        self.assertEqual(result.retrieval.status, "NOT_RUN")
        self.assertEqual(
            result.retrieval.reason_code,
            "EXPECTED_CLARIFICATION_SHORT_CIRCUIT",
        )
        self.assertEqual(semantic_provider.calls, 0)

        exact_unknown_profile = replace(
            oracle.acceptable_intent_profiles[0],
            field_expectations=tuple(
                IntentFieldExpectation(
                    "node_kind", "EXACT_ONE_OF", ("UNKNOWN",)
                )
                if item.field_name == "node_kind"
                else item
                for item in oracle.acceptable_intent_profiles[0].field_expectations
            ),
        )
        with self.assertRaises(ScenarioCapabilityError) as caught:
            freeze_capability_overlay(
                reviewed,
                plan,
                tree,
                review_status="ACCEPTED",
                reviewer_ref="fictional-capability-reviewer",
                recorded_at="2030-01-02T03:05:00Z",
                review_round=1,
                oracle=replace(
                    oracle,
                    acceptable_intent_profiles=(exact_unknown_profile,),
                ),
            )
        self.assertEqual(
            caught.exception.code,
            "CAPABILITY_ORACLE_REQUEST_MISMATCH",
        )

    def test_clarify_policy_cannot_ignore_the_required_question(self):
        tree, profile, plan, projection, batch, batch_candidate = _context("U004")
        action = _action(
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            draft_status="NEEDS_CLARIFICATION",
        )
        action = replace(
            action,
            final_request=replace(
                action.final_request,
                node_kind_hint="PROPERTY",
            ),
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
        field_expectations = tuple(
            IntentFieldExpectation(
                field_name=field_name,
                policy=(
                    "EXACT_ONE_OF"
                    if field_name == "node_kind"
                    else "NOT_COMPARED"
                ),
                acceptable_values=(
                    ("PROPERTY",) if field_name == "node_kind" else ()
                ),
            )
            for field_name in (
                "assumptions",
                "cardinality",
                "clarification_question",
                "confirmed_facts",
                "evidence_gaps",
                "lifecycle",
                "node_kind",
                "ownership",
                "role",
                "scenario",
                "subject",
                "value_type",
            )
        )
        oracle = CapabilityOracle(
            expected_route="CLARIFY",
            acceptable_intent_profiles=(
                IntentOracleProfile("P001", field_expectations),
            ),
            retrieval=RetrievalOracle(False, (), (), None),
            recommendation=RecommendationOracle(False, ()),
        )

        with self.assertRaises(ScenarioCapabilityError) as caught:
            freeze_capability_overlay(
                reviewed,
                plan,
                tree,
                review_status="ACCEPTED",
                reviewer_ref="fictional-capability-reviewer",
                recorded_at="2030-01-02T03:05:00Z",
                review_round=1,
                oracle=oracle,
            )
        self.assertEqual(
            caught.exception.code,
            "CAPABILITY_ORACLE_REQUEST_MISMATCH",
        )

    def test_overlay_cannot_contradict_reviewed_observable_route(self):
        tree, _, plan, _, _, _, _, reviewed = _reviewed_context()
        contradictory = CapabilityOracle(
            expected_route="CLARIFY",
            acceptable_intent_profiles=(
                IntentOracleProfile(
                    profile_ref="P001",
                    field_expectations=(
                        IntentFieldExpectation(
                            field_name="clarification_question",
                            policy="NON_EMPTY",
                            acceptable_values=(),
                        ),
                    ),
                ),
            ),
            retrieval=RetrievalOracle(False, (), (), None),
            recommendation=RecommendationOracle(False, ()),
        )
        with self.assertRaises(ScenarioCapabilityError) as caught:
            freeze_capability_overlay(
                reviewed,
                plan,
                tree,
                review_status="ACCEPTED",
                reviewer_ref="fictional-capability-reviewer",
                recorded_at="2030-01-02T03:05:00Z",
                review_round=1,
                oracle=contradictory,
            )
        self.assertEqual(
            caught.exception.code,
            "CAPABILITY_OVERLAY_OBSERVABLE_ORACLE_MISMATCH",
        )

        invalid_target_oracle = _proceed_oracle("fictional-missing-node")
        with self.assertRaises(ScenarioCapabilityError) as caught:
            freeze_capability_overlay(
                reviewed,
                plan,
                tree,
                review_status="ACCEPTED",
                reviewer_ref="fictional-capability-reviewer",
                recorded_at="2030-01-02T03:05:00Z",
                review_round=1,
                oracle=invalid_target_oracle,
            )
        self.assertEqual(
            caught.exception.code,
            "CAPABILITY_ORACLE_SOURCE_MISMATCH",
        )

    def test_retrieval_mismatch_short_circuits_recommendation(self):
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
        candidates = _preview_candidate_set(reviewed, tree).candidates
        self.assertGreaterEqual(len(candidates), 2)
        overlay = freeze_capability_overlay(
            reviewed,
            plan,
            tree,
            review_status="ACCEPTED",
            reviewer_ref="fictional-capability-reviewer",
            recorded_at="2030-01-02T03:05:00Z",
            review_round=1,
            oracle=replace(
                _proceed_oracle(candidates[1].node_id),
                retrieval=RetrievalOracle(
                    applicable=True,
                    allowed_statuses=("CANDIDATES_READY",),
                    acceptable_node_ids=(candidates[1].node_id,),
                    top_k=1,
                ),
            ),
        )
        semantic_provider = FakeSemanticProvider()

        result = run_reviewed_capability_scenario(
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
            semantic_provider,
        )

        self.assertEqual(result.retrieval.status, "MISMATCH")
        self.assertEqual(result.recommendation.status, "NOT_RUN")
        self.assertEqual(
            result.recommendation.reason_code,
            "UPSTREAM_RETRIEVAL_MISMATCH",
        )
        self.assertEqual(semantic_provider.calls, 0)

    def test_recommendation_joint_outcome_mismatch_is_attributed_once(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            reviewed,
            overlay,
        ) = _frozen_context()
        target = overlay.oracle.retrieval.acceptable_node_ids[0]
        oracle = replace(
            overlay.oracle,
            recommendation=RecommendationOracle(
                applicable=True,
                acceptable_outcomes=(
                    RecommendationOracleOutcome(
                        action="ADD_NODE_FROM_CONTRACT",
                        target_node_id=target,
                        relation="REUSES_CONTRACT",
                    ),
                ),
            ),
        )
        overlay = freeze_capability_overlay(
            reviewed,
            plan,
            tree,
            review_status="ACCEPTED",
            reviewer_ref="fictional-capability-reviewer",
            recorded_at="2030-01-02T03:05:00Z",
            review_round=1,
            oracle=oracle,
        )

        result = run_reviewed_capability_scenario(
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
            FakeSemanticProvider(),
        )

        self.assertEqual(result.intent.status, "MATCH")
        self.assertEqual(result.retrieval.status, "MATCH")
        self.assertEqual(result.recommendation.status, "MISMATCH")
        self.assertEqual(result.full_path_status, "MISMATCH")

    def test_intent_mismatch_short_circuits_without_duplicate_failures(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            reviewed,
            overlay,
        ) = _frozen_context()
        semantic_provider = FakeSemanticProvider()

        class WrongHintIntentProvider:
            def __init__(self):
                self.calls = 0

            def draft(self, request, source_tree):
                self.calls += 1
                original = FakeIntentDraftProvider().draft(request, source_tree)
                payload = {
                    "schema_version": "change-intent-model-output.v1",
                    **original.intent.to_dict(),
                    "node_kind": "CONCEPT",
                }
                return type(original).from_model_dict(
                    payload,
                    request,
                    source_tree,
                    model_provider="FICTIONAL_TEST_PROVIDER",
                    model_capability="JSON_OBJECT",
                    model_name="fictional-test-model",
                    prompt_version="treeguard.change-intent.test.v1",
                )

        intent_provider = WrongHintIntentProvider()

        result = run_reviewed_capability_scenario(
            overlay,
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            intent_provider,
            semantic_provider,
        )

        self.assertEqual(intent_provider.calls, 1)
        self.assertEqual(result.intent.status, "MISMATCH")
        self.assertTrue(result.retrieval.applicable)
        self.assertEqual(result.retrieval.status, "NOT_RUN")
        self.assertEqual(
            result.retrieval.reason_code, "UPSTREAM_INTENT_MISMATCH"
        )
        self.assertEqual(result.recommendation.status, "NOT_RUN")
        self.assertEqual(semantic_provider.calls, 0)

    def test_provider_failure_is_attributed_without_running_downstream(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            reviewed,
            overlay,
        ) = _frozen_context()
        semantic_provider = FakeSemanticProvider()

        class FailingIntentProvider:
            def draft(self, request, source_tree):
                raise RuntimeError("fictional provider failure")

        result = run_reviewed_capability_scenario(
            overlay,
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
            FailingIntentProvider(),
            semantic_provider,
        )

        self.assertEqual(result.intent.status, "RUN_FAILED")
        self.assertEqual(result.full_path_status, "RUN_FAILED")
        self.assertEqual(result.retrieval.status, "NOT_RUN")
        self.assertEqual(
            result.retrieval.reason_code,
            "UPSTREAM_INTENT_RUN_FAILED",
        )
        self.assertEqual(semantic_provider.calls, 0)

    def test_gate_requires_both_candidate_quality_and_execution(self):
        runs = tuple(_synthetic_run(index) for index in range(1, 9))
        report = build_capability_gate_report(
            ScenarioPreparationMetrics(
                planned_unit_count=11,
                accounted_unit_count=11,
                accepted_count=4,
                revised_accepted_count=4,
                rejected_count=2,
                generation_failure_count=1,
                blocking_finding_count=0,
                review_minutes=150,
            ),
            runs,
            clarification_coverage_status="NOT_APPLICABLE_WITH_BACKFILL",
            hard_failure_codes=(),
        )

        self.assertEqual(report.decision, "GO_SHADOW")
        self.assertEqual(report.candidate_preparation.status, "PASS")
        self.assertEqual(report.execution.status, "PASS")
        self.assertEqual(
            report.to_dict()["schema_version"], CAPABILITY_REPORT_SCHEMA_VERSION
        )

        failed = build_capability_gate_report(
            replace(
                report.candidate_preparation.source_metrics,
                accepted_count=3,
                revised_accepted_count=5,
            ),
            runs,
            clarification_coverage_status="NOT_APPLICABLE_WITH_BACKFILL",
            hard_failure_codes=(),
        )
        self.assertEqual(failed.decision, "NO_GO")
        self.assertIn(
            "CANDIDATE_DIRECT_ACCEPTED_BELOW_MINIMUM",
            failed.candidate_preparation.failure_codes,
        )
        self.assertEqual(
            type(report).from_dict(report.to_dict()),
            report,
        )

        hard_failed = build_capability_gate_report(
            report.candidate_preparation.source_metrics,
            runs,
            clarification_coverage_status="NOT_APPLICABLE_WITH_BACKFILL",
            hard_failure_codes=("SOURCE_BINDING_FAILURE",),
        )
        self.assertEqual(hard_failed.decision, "NO_GO")

        self.assertEqual(
            build_capability_gate_report(
                report.candidate_preparation.source_metrics,
                tuple(reversed(runs)),
                clarification_coverage_status=(
                    "NOT_APPLICABLE_WITH_BACKFILL"
                ),
                hard_failure_codes=(),
            ).to_dict(),
            report.to_dict(),
        )

        tampered = report.to_dict()
        tampered["candidate_preparation"]["accepted_count"] = 3
        tampered["candidate_preparation"]["revised_accepted_count"] = 5
        with self.assertRaises(ScenarioCapabilityError) as caught:
            type(report).from_dict(tampered)
        self.assertEqual(caught.exception.code, "CAPABILITY_REPORT_VALUE_INVALID")

        with self.assertRaises(ScenarioCapabilityError) as caught:
            build_capability_gate_report(
                report.candidate_preparation.source_metrics,
                runs,
                clarification_coverage_status=(
                    "NOT_APPLICABLE_WITH_BACKFILL"
                ),
                hard_failure_codes=("UNBOUNDED_EXTERNAL_CODE",),
            )
        self.assertEqual(
            caught.exception.code,
            "CAPABILITY_HARD_FAILURE_CODES_INVALID",
        )

    def test_two_intent_failures_exceed_only_the_intent_budget(self):
        runs = list(_synthetic_run(index) for index in range(1, 9))
        for offset in (0, 1):
            source = runs[offset]
            runs[offset] = ScenarioCapabilityRun.create(
                source_overlay_hash=source.source_overlay_hash,
                source_reviewed_hash=source.source_reviewed_hash,
                source_snapshot_hash=source.source_snapshot_hash,
                source_request_hash=source.source_request_hash,
                source_intent_draft_hash=source.source_intent_draft_hash,
                source_candidate_set_hash=None,
                source_recommendation_draft_hash=None,
                plan_unit_ref=source.plan_unit_ref,
                candidate_ref=source.candidate_ref,
                expected_route="PROCEED",
                intent=CapabilityStageResult(
                    True, "MISMATCH", "INTENT_ORACLE_MISMATCH"
                ),
                retrieval=CapabilityStageResult(
                    True, "NOT_RUN", "UPSTREAM_INTENT_MISMATCH"
                ),
                recommendation=CapabilityStageResult(
                    True, "NOT_RUN", "UPSTREAM_INTENT_MISMATCH"
                ),
            )
        report = build_capability_gate_report(
            ScenarioPreparationMetrics(11, 11, 4, 4, 2, 1, 0, 150),
            tuple(runs),
            clarification_coverage_status="NOT_APPLICABLE_WITH_BACKFILL",
            hard_failure_codes=(),
        )

        self.assertEqual(report.decision, "NO_GO")
        self.assertIn(
            "EXECUTION_INTENT_FAILURE_BUDGET_EXCEEDED",
            report.execution.failure_codes,
        )
        self.assertEqual(report.execution.retrieval.mismatch_count, 0)
        self.assertEqual(report.execution.retrieval.run_failed_count, 0)
        self.assertEqual(report.execution.retrieval.not_run_count, 2)

    def test_public_report_is_allowlisted_and_contains_no_hidden_canaries(self):
        report = build_capability_gate_report(
            ScenarioPreparationMetrics(
                planned_unit_count=11,
                accounted_unit_count=11,
                accepted_count=4,
                revised_accepted_count=4,
                rejected_count=2,
                generation_failure_count=1,
                blocking_finding_count=0,
                review_minutes=149,
            ),
            tuple(_synthetic_run(index) for index in range(1, 9)),
            clarification_coverage_status="NOT_APPLICABLE_WITH_BACKFILL",
            hard_failure_codes=(),
        )
        serialized = json.dumps(report.to_dict(), sort_keys=True)
        for forbidden in (
            "request",
            "oracle",
            "node_id",
            "source_",
            "prompt",
            "model_text",
            "trace",
            "CANARY-HIDDEN-TARGET",
        ):
            self.assertNotIn(forbidden.lower(), serialized.lower())

        for filename in (
            "scenario-capability-overlay.v1.schema.json",
            "scenario-capability-silver-authorization.v1.schema.json",
            "scenario-capability-run.v1.schema.json",
            "scenario-capability-report.v1.schema.json",
        ):
            schema = json.loads((PROJECT_ROOT / "contracts" / filename).read_text())
            self.assertFalse(schema["additionalProperties"])

    def test_schema_required_fields_match_each_serialized_contract_layer(self):
        (
            tree,
            profile,
            plan,
            projection,
            batch,
            batch_candidate,
            action,
            reviewed,
            overlay,
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
            FakeSemanticProvider(),
        )
        silver = freeze_silver_capability_authorization(
            reviewed,
            plan,
            tree,
            assessor_ref="codex-m4-calibration-review",
            recorded_at="2030-01-02T03:06:00Z",
            oracle=overlay.oracle,
        )
        report = build_capability_gate_report(
            ScenarioPreparationMetrics(11, 11, 4, 4, 2, 1, 0, 150),
            tuple(_synthetic_run(index) for index in range(1, 9)),
            clarification_coverage_status="NOT_APPLICABLE_WITH_BACKFILL",
            hard_failure_codes=(),
        )
        overlay_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "scenario-capability-overlay.v1.schema.json"
            ).read_text()
        )
        run_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "scenario-capability-run.v1.schema.json"
            ).read_text()
        )
        silver_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "scenario-capability-silver-authorization.v1.schema.json"
            ).read_text()
        )
        report_schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "scenario-capability-report.v1.schema.json"
            ).read_text()
        )

        self.assertEqual(set(overlay_schema["required"]), set(overlay.to_dict()))
        self.assertEqual(set(silver_schema["required"]), set(silver.to_dict()))
        self.assertEqual(
            set(overlay_schema["$defs"]["oracle"]["required"]),
            set(overlay.oracle.to_dict()),
        )
        self.assertEqual(set(run_schema["required"]), set(run.to_dict()))
        self.assertEqual(
            set(run_schema["$defs"]["stageResult"]["required"]),
            set(run.intent.to_dict()),
        )
        self.assertEqual(set(report_schema["required"]), set(report.to_dict()))
        self.assertEqual(
            set(
                report_schema["$defs"]["candidatePreparation"][
                    "required"
                ]
            ),
            set(report.candidate_preparation.to_dict()),
        )
        self.assertEqual(
            set(report_schema["$defs"]["execution"]["required"]),
            set(report.execution.to_dict()),
        )


def _synthetic_run(index: int) -> ScenarioCapabilityRun:
    digest = canonical_digest({"index": index})
    return ScenarioCapabilityRun.create(
        source_overlay_hash=digest,
        source_reviewed_hash=canonical_digest({"reviewed": index}),
        source_snapshot_hash=canonical_digest({"snapshot": index}),
        source_request_hash=canonical_digest({"request": index}),
        source_intent_draft_hash=canonical_digest({"intent": index}),
        source_candidate_set_hash=canonical_digest({"retrieval": index}),
        source_recommendation_draft_hash=canonical_digest(
            {"recommendation": index}
        ),
        plan_unit_ref=f"U{index:03d}",
        candidate_ref=f"C{index:03d}",
        expected_route="PROCEED",
        intent=CapabilityStageResult(
            applicable=True,
            status="MATCH",
            reason_code="INTENT_ORACLE_MATCH",
        ),
        retrieval=CapabilityStageResult(
            applicable=True,
            status="MATCH",
            reason_code="RETRIEVAL_ORACLE_MATCH",
        ),
        recommendation=CapabilityStageResult(
            applicable=True,
            status="MATCH",
            reason_code="RECOMMENDATION_ORACLE_MATCH",
        ),
    )


if __name__ == "__main__":
    unittest.main()
