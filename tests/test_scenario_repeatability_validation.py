import json
import unittest
from pathlib import Path

from treeguard.hashing import canonical_digest
from treeguard.scenario_capability_validation import (
    CapabilityStageResult,
    ScenarioCapabilityError,
    ScenarioCapabilityRun,
)
from treeguard.scenario_repeatability_validation import (
    SEALED_REPEATABILITY_REPORT_SCHEMA_VERSION,
    ClarificationConfusionMatrix,
    ContractComplianceMetrics,
    SealedPreparationMetrics,
    SealedRepeatabilityReport,
    build_sealed_repeatability_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _digest(kind: str, index: int, round_index: int | None = None) -> str:
    payload = {"kind": kind, "index": index}
    if round_index is not None:
        payload["round"] = round_index
    return canonical_digest(payload)


def _run(index: int, round_index: int, *, full_path_status: str = "MATCH") -> ScenarioCapabilityRun:
    clarify = index > 18
    expected_route = "CLARIFY" if clarify else "PROCEED"
    intent_status = "MATCH"
    intent_reason = "INTENT_ORACLE_MATCH"
    if full_path_status != "MATCH":
        intent_status = full_path_status
        intent_reason = (
            "INTENT_ORACLE_MISMATCH"
            if full_path_status == "MISMATCH"
            else "INTENT_PROVIDER_FAILED"
        )
    intent = CapabilityStageResult(True, intent_status, intent_reason)
    if clarify:
        downstream_reason = (
            "EXPECTED_CLARIFICATION_SHORT_CIRCUIT"
            if intent_status == "MATCH"
            else f"UPSTREAM_INTENT_{intent_status}"
        )
        retrieval = CapabilityStageResult(False, "NOT_RUN", downstream_reason)
        recommendation = CapabilityStageResult(False, "NOT_RUN", downstream_reason)
        candidate_hash = None
        recommendation_hash = None
    elif intent_status != "MATCH":
        downstream_reason = f"UPSTREAM_INTENT_{intent_status}"
        retrieval = CapabilityStageResult(True, "NOT_RUN", downstream_reason)
        recommendation = CapabilityStageResult(True, "NOT_RUN", downstream_reason)
        candidate_hash = None
        recommendation_hash = None
    else:
        retrieval = CapabilityStageResult(True, "MATCH", "RETRIEVAL_ORACLE_MATCH")
        recommendation = CapabilityStageResult(True, "MATCH", "RECOMMENDATION_ORACLE_MATCH")
        candidate_hash = _digest("candidate", index, round_index)
        recommendation_hash = _digest("recommendation", index, round_index)
    return ScenarioCapabilityRun.create(
        source_overlay_hash=_digest("overlay", index),
        source_reviewed_hash=_digest("reviewed", index),
        source_snapshot_hash=_digest("snapshot", 1),
        source_request_hash=_digest("request", index),
        source_intent_draft_hash=(
            _digest("intent", index, round_index)
            if intent_status != "RUN_FAILED"
            else None
        ),
        source_candidate_set_hash=candidate_hash,
        source_recommendation_draft_hash=recommendation_hash,
        plan_unit_ref=f"U{index:03d}",
        candidate_ref=f"C{index:03d}",
        expected_route=expected_route,
        intent=intent,
        retrieval=retrieval,
        recommendation=recommendation,
    )


def _round(round_index: int, failures: tuple[int, ...] = ()) -> tuple[ScenarioCapabilityRun, ...]:
    return tuple(
        _run(
            index,
            round_index,
            full_path_status="MISMATCH" if index in failures else "MATCH",
        )
        for index in range(1, 25)
    )


def _retrieval_mismatch_run(index: int, round_index: int) -> ScenarioCapabilityRun:
    return ScenarioCapabilityRun.create(
        source_overlay_hash=_digest("overlay", index),
        source_reviewed_hash=_digest("reviewed", index),
        source_snapshot_hash=_digest("snapshot", 1),
        source_request_hash=_digest("request", index),
        source_intent_draft_hash=_digest("intent", index, round_index),
        source_candidate_set_hash=_digest("candidate", index, round_index),
        source_recommendation_draft_hash=None,
        plan_unit_ref=f"U{index:03d}",
        candidate_ref=f"C{index:03d}",
        expected_route="PROCEED",
        intent=CapabilityStageResult(True, "MATCH", "INTENT_ORACLE_MATCH"),
        retrieval=CapabilityStageResult(
            True,
            "MISMATCH",
            "RETRIEVAL_ORACLE_MISMATCH",
        ),
        recommendation=CapabilityStageResult(
            True,
            "NOT_RUN",
            "UPSTREAM_RETRIEVAL_MISMATCH",
        ),
    )


def _preparation() -> SealedPreparationMetrics:
    return SealedPreparationMetrics(
        candidate_count=30,
        reviewed_count=24,
        execution_count=24,
        accepted_count=24,
        revised_accepted_count=0,
        rejected_count=0,
        blocking_finding_count=0,
        review_minutes=180,
    )


def _clarification() -> ClarificationConfusionMatrix:
    return ClarificationConfusionMatrix(18, 0, 0, 54)


def _report(
    *,
    rounds: tuple[tuple[ScenarioCapabilityRun, ...], ...] | None = None,
    intent_contract: ContractComplianceMetrics | None = None,
    semantic_contract: ContractComplianceMetrics | None = None,
    unsafe_reuse_count: int = 0,
    hard_failure_codes: tuple[str, ...] = (),
) -> SealedRepeatabilityReport:
    run_rounds = rounds or (_round(1), _round(2), _round(3))
    executed_semantic_count = sum(
        run.recommendation.applicable and run.recommendation.status != "NOT_RUN"
        for round_runs in run_rounds
        for run in round_runs
    )
    return build_sealed_repeatability_report(
        _preparation(),
        run_rounds,
        intent_contract=intent_contract or ContractComplianceMetrics(72, 72, 72),
        semantic_contract=semantic_contract
        or ContractComplianceMetrics(
            executed_semantic_count,
            executed_semantic_count,
            executed_semantic_count,
        ),
        clarification=_clarification(),
        unsafe_reuse_count=unsafe_reuse_count,
        hard_failure_codes=hard_failure_codes,
    )


class ScenarioRepeatabilityValidationTests(unittest.TestCase):
    def test_three_round_report_passes_and_round_trips(self):
        report = _report()

        self.assertEqual(report.decision, "GO_SHADOW")
        self.assertEqual(report.stable_full_path_match_count, 24)
        self.assertEqual(report.executed_retrieval_count, 54)
        self.assertEqual(report.retrieval_match_count, 54)
        self.assertEqual(tuple(item.full_path_match_count for item in report.rounds), (24, 24, 24))
        self.assertEqual(SealedRepeatabilityReport.from_dict(report.to_dict()), report)
        self.assertEqual(report.to_dict()["schema_version"], SEALED_REPEATABILITY_REPORT_SCHEMA_VERSION)

    def test_round_order_is_normalized_but_duplicate_and_drift_fail_closed(self):
        reversed_rounds = tuple(tuple(reversed(_round(index))) for index in (1, 2, 3))
        self.assertEqual(_report(rounds=reversed_rounds).to_dict(), _report().to_dict())

        duplicate = list(_round(1))
        duplicate[-1] = duplicate[0]
        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(rounds=(tuple(duplicate), _round(2), _round(3)))
        self.assertEqual(caught.exception.code, "SEALED_RUN_SET_DUPLICATE")

        changed = list(_round(3))
        changed[-1] = ScenarioCapabilityRun.create(
            source_overlay_hash=_digest("other-overlay", 24),
            source_reviewed_hash=changed[-1].source_reviewed_hash,
            source_snapshot_hash=changed[-1].source_snapshot_hash,
            source_request_hash=changed[-1].source_request_hash,
            source_intent_draft_hash=changed[-1].source_intent_draft_hash,
            source_candidate_set_hash=None,
            source_recommendation_draft_hash=None,
            plan_unit_ref=changed[-1].plan_unit_ref,
            candidate_ref=changed[-1].candidate_ref,
            expected_route="CLARIFY",
            intent=changed[-1].intent,
            retrieval=changed[-1].retrieval,
            recommendation=changed[-1].recommendation,
        )
        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(rounds=(_round(1), _round(2), tuple(changed)))
        self.assertEqual(caught.exception.code, "SEALED_RUN_SET_SOURCE_MISMATCH")

        source_drift = list(_round(3))
        original = source_drift[0]
        source_drift[0] = ScenarioCapabilityRun.create(
            source_overlay_hash=original.source_overlay_hash,
            source_reviewed_hash=_digest("other-reviewed", 1),
            source_snapshot_hash=original.source_snapshot_hash,
            source_request_hash=original.source_request_hash,
            source_intent_draft_hash=original.source_intent_draft_hash,
            source_candidate_set_hash=original.source_candidate_set_hash,
            source_recommendation_draft_hash=(
                original.source_recommendation_draft_hash
            ),
            plan_unit_ref=original.plan_unit_ref,
            candidate_ref=original.candidate_ref,
            expected_route=original.expected_route,
            intent=original.intent,
            retrieval=original.retrieval,
            recommendation=original.recommendation,
        )
        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(rounds=(_round(1), _round(2), tuple(source_drift)))
        self.assertEqual(caught.exception.code, "SEALED_RUN_SET_SOURCE_MISMATCH")

    def test_contract_threshold_uses_exact_integer_ratio(self):
        one_intent_failure = _report(intent_contract=ContractComplianceMetrics(72, 70, 71))
        self.assertEqual(one_intent_failure.decision, "GO_SHADOW")

        two_intent_failures = _report(intent_contract=ContractComplianceMetrics(72, 70, 70))
        self.assertEqual(two_intent_failures.decision, "NO_GO")
        self.assertIn("SEALED_INTENT_CONTRACT_BELOW_MINIMUM", two_intent_failures.failure_codes)

        one_semantic_failure = _report(semantic_contract=ContractComplianceMetrics(54, 52, 53))
        self.assertEqual(one_semantic_failure.decision, "GO_SHADOW")

        two_semantic_failures = _report(semantic_contract=ContractComplianceMetrics(54, 52, 52))
        self.assertIn("SEALED_SEMANTIC_CONTRACT_BELOW_MINIMUM", two_semantic_failures.failure_codes)

    def test_round_and_stability_thresholds_are_independent(self):
        passing = _report(rounds=(_round(1, (1, 2, 3, 4, 5, 6)), _round(2), _round(3)))
        self.assertEqual(passing.decision, "GO_SHADOW")
        self.assertEqual(passing.stable_full_path_match_count, 18)

        below_round = _report(rounds=(_round(1, (1, 2, 3, 4, 5, 6, 7)), _round(2), _round(3)))
        self.assertIn("SEALED_ROUND_MATCH_BELOW_MINIMUM", below_round.failure_codes)
        self.assertIn("SEALED_STABLE_MATCH_BELOW_MINIMUM", below_round.failure_codes)

        unstable = _report(
            rounds=(
                _round(1, (1, 2, 3, 4, 5, 6)),
                _round(2, (7, 8, 9, 10, 11, 12)),
                _round(3, (13, 14, 15, 16, 17, 18)),
            )
        )
        self.assertNotIn("SEALED_ROUND_MATCH_BELOW_MINIMUM", unstable.failure_codes)
        self.assertIn("SEALED_STABLE_MATCH_BELOW_MINIMUM", unstable.failure_codes)

    def test_hard_failure_and_unsafe_reuse_force_no_go(self):
        unsafe = _report(unsafe_reuse_count=1)
        self.assertEqual(unsafe.decision, "NO_GO")
        self.assertIn("SEALED_UNSAFE_REUSE_PRESENT", unsafe.failure_codes)

        hard = _report(hard_failure_codes=("SOURCE_BINDING_FAILURE",))
        self.assertEqual(hard.decision, "NO_GO")
        self.assertEqual(hard.failure_codes, ())

    def test_preparation_and_retrieval_gates_report_failures(self):
        too_many = SealedPreparationMetrics(
            candidate_count=31,
            reviewed_count=24,
            execution_count=24,
            accepted_count=24,
            revised_accepted_count=0,
            rejected_count=0,
            blocking_finding_count=0,
            review_minutes=180,
        )
        report = build_sealed_repeatability_report(
            too_many,
            (_round(1), _round(2), _round(3)),
            intent_contract=ContractComplianceMetrics(72, 72, 72),
            semantic_contract=ContractComplianceMetrics(54, 54, 54),
            clarification=_clarification(),
            unsafe_reuse_count=0,
            hard_failure_codes=(),
        )
        self.assertIn("SEALED_CANDIDATE_COUNT_INVALID", report.failure_codes)
        self.assertEqual(SealedRepeatabilityReport.from_dict(report.to_dict()), report)

        first_round = list(_round(1))
        first_round[0] = _retrieval_mismatch_run(1, 1)
        retrieval_failed = _report(
            rounds=(tuple(first_round), _round(2), _round(3))
        )
        self.assertIn("SEALED_RETRIEVAL_NOT_PERFECT", retrieval_failed.failure_codes)

        with self.assertRaises(ValueError):
            SealedPreparationMetrics(True, 0, 0, 0, 0, 0, 0, 0)

    def test_public_report_is_allowlisted_and_schema_matches(self):
        report = _report()
        serialized = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "request",
            "oracle",
            "node_id",
            "source_overlay",
            "prompt",
            "model_text",
            "trace",
            "CANARY-HIDDEN-TARGET",
        ):
            self.assertNotIn(forbidden.lower(), serialized.lower())

        schema = json.loads(
            (PROJECT_ROOT / "contracts" / "scenario-repeatability-report.v1.schema.json").read_text()
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(report.to_dict()))
        self.assertEqual(set(schema["$defs"]["preparation"]["required"]), set(report.preparation.to_dict()))
        self.assertEqual(set(schema["$defs"]["round"]["required"]), set(report.rounds[0].to_dict()))
        self.assertEqual(
            set(schema["$defs"]["contractCompliance"]["required"]),
            set(report.intent_contract.to_dict()),
        )
        self.assertEqual(
            set(schema["$defs"]["clarification"]["required"]),
            set(report.clarification.to_dict()),
        )

    def test_tampering_and_invalid_fixed_counts_are_rejected(self):
        payload = _report().to_dict()
        payload["stable_full_path_match_count"] = 17
        with self.assertRaises(ScenarioCapabilityError) as caught:
            SealedRepeatabilityReport.from_dict(payload)
        self.assertEqual(caught.exception.code, "SEALED_REPORT_VALUE_INVALID")

        payload = _report().to_dict()
        payload["selected_scenario_count"] = 23
        with self.assertRaises(ScenarioCapabilityError) as caught:
            SealedRepeatabilityReport.from_dict(payload)
        self.assertEqual(caught.exception.code, "SEALED_REPORT_POLICY_INVALID")

        with self.assertRaises(ScenarioCapabilityError) as caught:
            _report(hard_failure_codes=("UNBOUNDED_CODE",))
        self.assertEqual(caught.exception.code, "SEALED_REPORT_INPUT_INVALID")


if __name__ == "__main__":
    unittest.main()
