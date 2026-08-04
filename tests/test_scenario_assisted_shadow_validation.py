import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard.scenario_assisted_shadow_validation import (
    ASSISTED_SHADOW_REPORT_SCHEMA_VERSION,
    AssistedShadowAdmissionReport,
    AssistedShadowEvidenceQualification,
    AssistedShadowRoundMetrics,
    SafeAlternativeReviewMetrics,
    SemanticOutcomeMetrics,
    build_assisted_shadow_admission_report,
)
from treeguard.scenario_capability_validation import ScenarioCapabilityError
from treeguard.scenario_repeatability_validation import ContractComplianceMetrics


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _qualified_evidence() -> AssistedShadowEvidenceQualification:
    return AssistedShadowEvidenceQualification(
        policy_frozen_before_execution=True,
        requests_unseen_at_first_execution=True,
        oracle_review_authority="HUMAN_AUTHORIZED",
        reviewed_scenario_count=24,
        runtime_configuration_frozen=True,
    )


def _report(
    *,
    evidence: AssistedShadowEvidenceQualification | None = None,
    rounds: tuple[AssistedShadowRoundMetrics, ...] | None = None,
    stable_safe_full_path_count: int = 18,
    stable_preferred_full_path_count: int = 6,
    executed_retrieval_count: int = 51,
    retrieval_match_count: int = 51,
    semantic_attempted_count: int = 51,
    intent_contract: ContractComplianceMetrics | None = None,
    semantic_contract: ContractComplianceMetrics | None = None,
    clarification_match_count: int = 15,
    semantic_outcomes: SemanticOutcomeMetrics | None = None,
    safe_alternative_review: SafeAlternativeReviewMetrics | None = None,
    hard_failure_codes: tuple[str, ...] = (),
) -> AssistedShadowAdmissionReport:
    return build_assisted_shadow_admission_report(
        evidence or _qualified_evidence(),
        rounds
        or (
            AssistedShadowRoundMetrics(1, 21, 6),
            AssistedShadowRoundMetrics(2, 23, 7),
            AssistedShadowRoundMetrics(3, 22, 6),
        ),
        stable_safe_full_path_count=stable_safe_full_path_count,
        stable_preferred_full_path_count=stable_preferred_full_path_count,
        executed_retrieval_count=executed_retrieval_count,
        retrieval_match_count=retrieval_match_count,
        semantic_attempted_count=semantic_attempted_count,
        intent_contract=intent_contract or ContractComplianceMetrics(72, 72, 72),
        semantic_contract=semantic_contract or ContractComplianceMetrics(51, 51, 51),
        clarification_match_count=clarification_match_count,
        semantic_outcomes=semantic_outcomes
        or SemanticOutcomeMetrics(
            preferred_match_count=19,
            safe_alternative_count=32,
            unsafe_mismatch_count=0,
            run_failed_count=0,
        ),
        safe_alternative_review=safe_alternative_review
        or SafeAlternativeReviewMetrics(
            distinct_output_count=32,
            reviewed_output_count=32,
            blocking_finding_count=0,
            reviewer_authority="HUMAN_AUTHORIZED",
        ),
        hard_failure_codes=hard_failure_codes,
    )


class ScenarioAssistedShadowValidationTests(unittest.TestCase):
    def test_qualified_report_is_ready_and_round_trips(self) -> None:
        report = _report()

        self.assertEqual(report.decision, "READY_FOR_ASSISTED_SHADOW")
        self.assertEqual(report.qualification_codes, ())
        self.assertEqual(report.failure_codes, ())
        self.assertEqual(
            AssistedShadowAdmissionReport.from_dict(report.to_dict()),
            report,
        )

    def test_exact_thresholds_pass_without_float_rounding(self) -> None:
        report = _report(
            rounds=(
                AssistedShadowRoundMetrics(1, 18, 12),
                AssistedShadowRoundMetrics(2, 18, 12),
                AssistedShadowRoundMetrics(3, 18, 11),
            ),
            stable_safe_full_path_count=18,
            stable_preferred_full_path_count=6,
            executed_retrieval_count=52,
            retrieval_match_count=52,
            semantic_attempted_count=52,
            intent_contract=ContractComplianceMetrics(72, 70, 71),
            semantic_contract=ContractComplianceMetrics(52, 50, 51),
            clarification_match_count=3,
            semantic_outcomes=SemanticOutcomeMetrics(35, 16, 0, 1),
            safe_alternative_review=SafeAlternativeReviewMetrics(
                16, 16, 0, "HUMAN_AUTHORIZED"
            ),
        )

        self.assertEqual(report.decision, "READY_FOR_ASSISTED_SHADOW")

    def test_each_metric_gate_fails_closed(self) -> None:
        cases = {
            "intent": (
                {"intent_contract": ContractComplianceMetrics(72, 70, 70)},
                "ASSISTED_INTENT_CONTRACT_BELOW_MINIMUM",
            ),
            "semantic": (
                {
                    "rounds": (
                        AssistedShadowRoundMetrics(1, 21, 6),
                        AssistedShadowRoundMetrics(2, 23, 6),
                        AssistedShadowRoundMetrics(3, 22, 6),
                    ),
                    "semantic_contract": ContractComplianceMetrics(51, 49, 49),
                    "semantic_outcomes": SemanticOutcomeMetrics(18, 31, 0, 2),
                    "clarification_match_count": 17,
                    "safe_alternative_review": SafeAlternativeReviewMetrics(
                        31, 31, 0, "HUMAN_AUTHORIZED"
                    ),
                },
                "ASSISTED_SEMANTIC_CONTRACT_BELOW_MINIMUM",
            ),
            "retrieval": (
                {"executed_retrieval_count": 52, "retrieval_match_count": 51},
                "ASSISTED_RETRIEVAL_NOT_PERFECT",
            ),
            "round": (
                {
                    "rounds": (
                        AssistedShadowRoundMetrics(1, 17, 6),
                        AssistedShadowRoundMetrics(2, 23, 7),
                        AssistedShadowRoundMetrics(3, 22, 6),
                    ),
                    "clarification_match_count": 11,
                    "stable_safe_full_path_count": 17,
                },
                "ASSISTED_ROUND_SAFE_PATH_BELOW_MINIMUM",
            ),
            "stable": (
                {"stable_safe_full_path_count": 17},
                "ASSISTED_STABLE_SAFE_PATH_BELOW_MINIMUM",
            ),
            "round_preferred": (
                {
                    "rounds": (
                        AssistedShadowRoundMetrics(1, 21, 5),
                        AssistedShadowRoundMetrics(2, 23, 7),
                        AssistedShadowRoundMetrics(3, 22, 7),
                    ),
                    "stable_preferred_full_path_count": 5,
                },
                "ASSISTED_ROUND_PREFERRED_PATH_BELOW_MINIMUM",
            ),
            "stable_preferred": (
                {"stable_preferred_full_path_count": 5},
                "ASSISTED_STABLE_PREFERRED_PATH_BELOW_MINIMUM",
            ),
            "unsafe": (
                {
                    "rounds": (
                        AssistedShadowRoundMetrics(1, 21, 6),
                        AssistedShadowRoundMetrics(2, 23, 6),
                        AssistedShadowRoundMetrics(3, 22, 6),
                    ),
                    "semantic_outcomes": SemanticOutcomeMetrics(18, 32, 1, 0),
                    "clarification_match_count": 16,
                },
                "ASSISTED_UNSAFE_MISMATCH_PRESENT",
            ),
            "review": (
                {
                    "safe_alternative_review": SafeAlternativeReviewMetrics(
                        32, 31, 0, "HUMAN_AUTHORIZED"
                    )
                },
                "ASSISTED_SAFE_ALTERNATIVE_REVIEW_INCOMPLETE",
            ),
            "blocking": (
                {
                    "safe_alternative_review": SafeAlternativeReviewMetrics(
                        32, 32, 1, "HUMAN_AUTHORIZED"
                    )
                },
                "ASSISTED_SAFE_ALTERNATIVE_BLOCKING_FINDING_PRESENT",
            ),
            "short_circuit": (
                {"semantic_attempted_count": 52},
                "ASSISTED_STAGE_SHORT_CIRCUIT_VIOLATION",
            ),
        }
        for name, (changes, expected_code) in cases.items():
            with self.subTest(name=name):
                report = _report(**changes)
                self.assertEqual(report.decision, "NOT_READY")
                self.assertIn(expected_code, report.failure_codes)

    def test_safe_but_always_non_targeting_is_not_useful_enough(self) -> None:
        report = _report(
            rounds=tuple(
                AssistedShadowRoundMetrics(index, 24, 0) for index in range(1, 4)
            ),
            stable_safe_full_path_count=24,
            stable_preferred_full_path_count=0,
            executed_retrieval_count=54,
            retrieval_match_count=54,
            semantic_attempted_count=54,
            semantic_contract=ContractComplianceMetrics(54, 54, 54),
            clarification_match_count=18,
            semantic_outcomes=SemanticOutcomeMetrics(0, 54, 0, 0),
            safe_alternative_review=SafeAlternativeReviewMetrics(
                54, 54, 0, "HUMAN_AUTHORIZED"
            ),
        )

        self.assertEqual(report.decision, "NOT_READY")
        self.assertEqual(
            report.failure_codes,
            (
                "ASSISTED_ROUND_PREFERRED_PATH_BELOW_MINIMUM",
                "ASSISTED_STABLE_PREFERRED_PATH_BELOW_MINIMUM",
            ),
        )

    def test_ineligible_evidence_is_evaluation_pending(self) -> None:
        report = _report(
            evidence=AssistedShadowEvidenceQualification(
                policy_frozen_before_execution=False,
                requests_unseen_at_first_execution=False,
                oracle_review_authority="CODEX_ASSISTED",
                reviewed_scenario_count=23,
                runtime_configuration_frozen=False,
            )
        )

        self.assertEqual(report.decision, "EVALUATION_PENDING")
        self.assertEqual(
            report.qualification_codes,
            (
                "ASSISTED_FORMAL_SCENARIO_REVIEW_INCOMPLETE",
                "ASSISTED_ORACLE_NOT_HUMAN_REVIEWED",
                "ASSISTED_POLICY_NOT_FROZEN_BEFORE_EXECUTION",
                "ASSISTED_REQUEST_SET_PREVIOUSLY_EXPOSED",
                "ASSISTED_RUNTIME_CONFIGURATION_NOT_FROZEN",
            ),
        )

    def test_hard_failure_overrides_pending_evidence(self) -> None:
        report = _report(
            evidence=AssistedShadowEvidenceQualification(
                False, False, "CODEX_ASSISTED", 24, False
            ),
            hard_failure_codes=("SOURCE_BINDING_FAILURE",),
        )

        self.assertEqual(report.decision, "NOT_READY")

    def test_m49_counterfactual_remains_diagnostic_only(self) -> None:
        report = _report(
            evidence=AssistedShadowEvidenceQualification(
                False, True, "CODEX_ASSISTED", 24, True
            ),
            executed_retrieval_count=53,
            retrieval_match_count=52,
            semantic_attempted_count=53,
            semantic_contract=ContractComplianceMetrics(52, 48, 51),
            semantic_outcomes=SemanticOutcomeMetrics(19, 32, 0, 1),
            stable_preferred_full_path_count=5,
            safe_alternative_review=SafeAlternativeReviewMetrics(
                32, 32, 0, "CODEX_ASSISTED"
            ),
        )

        self.assertEqual(report.decision, "EVALUATION_PENDING")
        self.assertIn("ASSISTED_RETRIEVAL_NOT_PERFECT", report.failure_codes)
        self.assertIn("ASSISTED_STAGE_SHORT_CIRCUIT_VIOLATION", report.failure_codes)
        self.assertIn(
            "ASSISTED_SAFE_ALTERNATIVE_REVIEW_INCOMPLETE",
            report.failure_codes,
        )
        self.assertIn(
            "ASSISTED_STABLE_PREFERRED_PATH_BELOW_MINIMUM",
            report.failure_codes,
        )

    def test_contract_rejects_tampering_and_invalid_accounting(self) -> None:
        payload = _report().to_dict()
        payload["decision"] = "NOT_READY"
        with self.assertRaises(ScenarioCapabilityError) as caught:
            AssistedShadowAdmissionReport.from_dict(payload)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_VALUE_INVALID")

        with self.assertRaises(ValueError):
            replace(_report(), stable_safe_full_path_count=True)

        with self.assertRaises(ValueError):
            replace(_report(), stable_preferred_full_path_count=True)

        with self.assertRaises(ValueError):
            AssistedShadowRoundMetrics(1, 21, True)

        with self.assertRaises(ValueError):
            AssistedShadowRoundMetrics(1, 5, 6)

        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(stable_preferred_full_path_count=7)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_INPUT_INVALID")

        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(clarification_match_count=14)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_INPUT_INVALID")

        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(semantic_attempted_count=50)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_INPUT_INVALID")

        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(
                rounds=(
                    AssistedShadowRoundMetrics(1, 21, 7),
                    AssistedShadowRoundMetrics(2, 23, 7),
                    AssistedShadowRoundMetrics(3, 22, 6),
                )
            )
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_INPUT_INVALID")

        with self.assertRaises(ValueError):
            SafeAlternativeReviewMetrics(2, 1, 2, "HUMAN_AUTHORIZED")

    def test_parser_rejects_fields_version_policy_and_order(self) -> None:
        payload = _report().to_dict()
        payload["extra"] = True
        with self.assertRaises(ScenarioCapabilityError) as caught:
            AssistedShadowAdmissionReport.from_dict(payload)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_FIELDS_INVALID")

        payload = _report().to_dict()
        payload["schema_version"] = "scenario-assisted-shadow-report.v2"
        with self.assertRaises(ScenarioCapabilityError) as caught:
            AssistedShadowAdmissionReport.from_dict(payload)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_VERSION_INVALID")

        payload = _report().to_dict()
        payload["automatic_action_enabled"] = True
        with self.assertRaises(ScenarioCapabilityError) as caught:
            AssistedShadowAdmissionReport.from_dict(payload)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_POLICY_INVALID")

        payload = _report().to_dict()
        payload["rounds"] = list(reversed(payload["rounds"]))
        with self.assertRaises(ScenarioCapabilityError) as caught:
            AssistedShadowAdmissionReport.from_dict(payload)
        self.assertEqual(caught.exception.code, "ASSISTED_SHADOW_REPORT_VALUE_INVALID")

    def test_public_report_is_allowlisted_and_schema_matches(self) -> None:
        report = _report()
        serialized = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "request_body",
            "request_text",
            "oracle_digest",
            "node_id",
            "source_overlay",
            "prompt",
            "model_text",
            "trace",
            "CANARY-HIDDEN-TARGET",
        ):
            self.assertNotIn(forbidden.lower(), serialized.lower())

        schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts"
                / "scenario-assisted-shadow-report.v1.schema.json"
            ).read_text()
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(report.to_dict()))
        self.assertEqual(
            set(schema["$defs"]["evidenceQualification"]["required"]),
            set(report.evidence.to_dict()),
        )
        self.assertEqual(
            set(schema["$defs"]["round"]["required"]),
            set(report.rounds[0].to_dict()),
        )
        self.assertEqual(
            set(schema["$defs"]["semanticOutcomes"]["required"]),
            set(report.semantic_outcomes.to_dict()),
        )
        self.assertEqual(
            set(schema["$defs"]["safeAlternativeReview"]["required"]),
            set(report.safe_alternative_review.to_dict()),
        )


if __name__ == "__main__":
    unittest.main()
