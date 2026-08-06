import json
import unittest
from pathlib import Path

from treeguard.navigation_copilot_sealed_validation import (
    SealedCaseOracle,
    SealedCaseTrace,
    SealedEvaluationError,
    SealedEvaluationManifest,
    SealedScenario,
    StructuralProfile,
    TerminalExpectation,
    public_sealed_aggregate,
    replay_public_sealed_aggregate,
    score_sealed_case,
    validate_sealed_plan,
)


TREE_DIGEST = "1" * 64
REQUEST_DIGEST = "2" * 64
REVIEW_DIGEST = "3" * 64
ROOT = Path(__file__).resolve().parents[1]


def _validate_schema(name, payload):
    schema = json.loads(
        (ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    if set(schema["required"]) != set(payload):
        raise AssertionError(f"{name} fields do not match its schema")
    if schema["properties"]["schema_version"]["const"] != payload["schema_version"]:
        raise AssertionError(f"{name} version does not match its schema")


def _scenario_categories():
    return {
        **{f"L{i:02d}": "LITERAL_UNIQUE" for i in range(10)},
        **{f"N{i:02d}": "NONLITERAL_UNIQUE" for i in range(10)},
        **{f"I{i:02d}": "STRUCTURAL_INTERFERENCE" for i in range(8)},
        **{f"M{i:02d}": "MULTI_ACCEPTABLE" for i in range(4)},
        **{f"C{i:02d}": "CLARIFICATION" for i in range(6)},
        **{f"W{i:02d}": "WEAK_EVIDENCE" for i in range(4)},
        **{f"A{i:02d}": "TARGET_ABSENT" for i in range(6)},
    }


CATEGORIES = _scenario_categories()
SCENARIO_REFS = tuple(sorted(CATEGORIES))
REPEAT_REFS = tuple(
    sorted(
        [f"N{i:02d}" for i in range(4)]
        + [f"I{i:02d}" for i in range(4)]
        + [f"C{i:02d}" for i in range(4)]
        + [f"W{i:02d}" for i in range(4)]
    )
)
WRONG_CONTEXT_REFS = {f"L{i:02d}" for i in range(8)}


def _manifest():
    return SealedEvaluationManifest.create(
        function_commit="a" * 40,
        data_commit="b" * 40,
        tree_sha256="c" * 64,
        scenarios_sha256="d" * 64,
        oracle_sha256="e" * 64,
        model_name="qwen-plus",
        understanding_prompt_version="treeguard.navigation-copilot-understanding.zh.v1",
        clarification_prompt_version="treeguard.navigation-copilot-understanding-clarification.zh.v1",
        semantic_prompt_version="treeguard.navigation-copilot-semantic.zh.v1",
        endpoint_class="OFFICIAL_BAILIAN_COMPATIBLE",
        scenario_refs=SCENARIO_REFS,
        repeat_scenario_refs=REPEAT_REFS,
        wire_attempt_limit=320,
    )


def _oracle(ref, *, request_digest=REQUEST_DIGEST, wrong_context=None):
    category = CATEGORIES[ref]
    absent = category == "TARGET_ABSENT"
    clarify = category == "CLARIFICATION"
    weak_evidence = category == "WEAK_EVIDENCE"
    target = f"node-{ref}"
    targets = (
        ()
        if absent
        else ((target, f"{target}-alternate") if category == "MULTI_ACCEPTABLE" else (target,))
    )
    terminals = (
        (TerminalExpectation("REJECT_ALL", None, "ABSENT"),)
        if absent
        else (TerminalExpectation("EXIT", None, "PRESENT_NOT_FOUND"),)
        if weak_evidence
        else tuple(
            TerminalExpectation("SELECT_CANDIDATE", node_id, "FOUND_TOP8")
            for node_id in targets
        )
    )
    return SealedCaseOracle.create(
        scenario_ref=ref,
        tree_digest=TREE_DIGEST,
        request_digest=request_digest,
        category=category,
        expected_route="CLARIFY" if clarify else ("LIMIT" if weak_evidence else "PROCEED"),
        acceptable_profiles=(
            StructuralProfile("PROPERTY", "TEXT", "SINGLE"),
        ),
        target_status="TARGET_ABSENT" if absent else "TARGET_PRESENT",
        acceptable_node_ids=targets,
        forbidden_node_ids=() if absent else (f"distractor-{ref}",),
        clarification_policy=(
            "CLARIFICATION_REQUIRED" if clarify else "NOT_APPLICABLE"
        ),
        frozen_clarification_answer="选择治理记录" if clarify else None,
        acceptable_policy_statuses=(
            ("NONE",)
            if absent
            else (("NEED_EVIDENCE",) if weak_evidence else ("CANDIDATES_AVAILABLE",))
        ),
        acceptable_terminals=terminals,
        wrong_context_challenge=(
            ref in WRONG_CONTEXT_REFS if wrong_context is None else wrong_context
        ),
        review_status="CODEX_SILVER_REVIEWED",
        reviewed_bytes_digest=REVIEW_DIGEST,
        execution_eligible=True,
    )


def _scenario(ref):
    category = CATEGORIES[ref]
    return SealedScenario.create(
        scenario_ref=ref,
        tree_digest=TREE_DIGEST,
        category=category,
        requirement_text=f"请定位 {ref} 对应的治理结构",
        proposed_parent_ref="N000001" if ref in WRONG_CONTEXT_REFS else None,
        node_kind_hint="UNKNOWN",
        value_type_hint=None,
        cardinality_hint="UNKNOWN",
        frozen_clarification_answer=(
            "选择治理记录" if category == "CLARIFICATION" else None
        ),
        wrong_context_challenge=ref in WRONG_CONTEXT_REFS,
        repeat_challenge=ref in REPEAT_REFS,
    )


def _trace(
    ref,
    round_index=1,
    *,
    c1_rank=1,
    r0_rank=1,
    degraded=False,
    highlighted_node=None,
):
    oracle = _oracle(ref)
    absent = oracle.target_status == "TARGET_ABSENT"
    weak_evidence = oracle.category == "WEAK_EVIDENCE"
    target = f"node-{ref}"

    def candidates(rank):
        if absent:
            return (f"other-{ref}",)
        values = [f"other-{ref}-{i:02d}" for i in range(max(rank or 1, 1))]
        if rank is not None:
            values[rank - 1] = target
        return tuple(values)

    highlighted = (
        None if absent or weak_evidence else target
    ) if highlighted_node is None else highlighted_node
    return SealedCaseTrace.create(
        scenario_ref=ref,
        round_index=round_index,
        tree_digest=TREE_DIGEST,
        request_digest=REQUEST_DIGEST,
        provider_mode="BAILIAN_LIVE",
        run_status="COMPLETE",
        failure_code=None,
        failure_stage=None,
        logical_model_stage_count=2,
        wire_attempt_count=2,
        sidecar_complete=True,
        interpretation_status="MODEL_DEGRADED" if degraded else "MODEL_VALID",
        observed_route=oracle.expected_route,
        observed_profile=StructuralProfile("PROPERTY", "TEXT", "SINGLE"),
        r0_candidate_node_ids=candidates(r0_rank),
        c1_candidate_node_ids=candidates(c1_rank),
        policy_status=(
            "NONE" if absent else ("NEED_EVIDENCE" if weak_evidence else "CANDIDATES_AVAILABLE")
        ),
        highlighted_node_id=highlighted,
        outcome=oracle.acceptable_terminals[0],
    )


def _observations(trace_factory=_trace):
    result = [
        score_sealed_case(_oracle(ref), trace_factory(ref, 1))
        for ref in SCENARIO_REFS
    ]
    for ref in REPEAT_REFS:
        result.extend(
            score_sealed_case(_oracle(ref), trace_factory(ref, round_index))
            for round_index in (2, 3)
        )
    return tuple(result)


class SealedContractTests(unittest.TestCase):
    def test_manifest_round_trips_and_rejects_contract_drift(self):
        manifest = _manifest()
        self.assertEqual(
            SealedEvaluationManifest.from_dict(manifest.to_dict()), manifest
        )
        tampered = manifest.to_dict()
        tampered["main_case_count"] = True
        with self.assertRaises(SealedEvaluationError) as caught:
            SealedEvaluationManifest.from_dict(tampered)
        self.assertEqual(caught.exception.code, "SEALED_MANIFEST_CONSTANT_INVALID")

    def test_oracle_round_trips_and_rejects_extra_fields(self):
        oracle = _oracle("N00")
        self.assertEqual(SealedCaseOracle.from_dict(oracle.to_dict()), oracle)
        tampered = oracle.to_dict()
        tampered["model_answer"] = "forbidden"
        with self.assertRaises(SealedEvaluationError) as caught:
            SealedCaseOracle.from_dict(tampered)
        self.assertEqual(caught.exception.code, "SEALED_ORACLE_FIELDS_INVALID")

    def test_oracle_rejects_overlapping_targets(self):
        payload = _oracle("N00").to_dict()
        payload["forbidden_node_ids"] = payload["acceptable_node_ids"]
        with self.assertRaises(SealedEvaluationError):
            SealedCaseOracle.from_dict(payload)

    def test_weak_evidence_target_can_exit_without_selection(self):
        oracle = _oracle("W00")
        self.assertEqual(oracle.expected_route, "LIMIT")
        self.assertEqual(
            oracle.acceptable_terminals,
            (TerminalExpectation("EXIT", None, "PRESENT_NOT_FOUND"),),
        )
        self.assertEqual(SealedCaseOracle.from_dict(oracle.to_dict()), oracle)

    def test_present_target_exit_is_rejected_outside_weak_evidence(self):
        values = _oracle("N00").to_dict()
        values["acceptable_terminals"] = [
            TerminalExpectation("EXIT", None, "PRESENT_NOT_FOUND").to_dict()
        ]
        with self.assertRaises(SealedEvaluationError) as caught:
            SealedCaseOracle.from_dict(values)
        self.assertEqual(caught.exception.code, "SEALED_ORACLE_INVALID")

    def test_trace_rejects_bool_as_count(self):
        values = _trace("N00").to_dict()
        values.pop("schema_version")
        values.pop("trace_hash")
        values["logical_model_stage_count"] = True
        values["observed_profile"] = StructuralProfile.from_dict(values["observed_profile"])
        values["r0_candidate_node_ids"] = tuple(values["r0_candidate_node_ids"])
        values["c1_candidate_node_ids"] = tuple(values["c1_candidate_node_ids"])
        values["outcome"] = TerminalExpectation.from_dict(values["outcome"])
        with self.assertRaises(ValueError):
            SealedCaseTrace.create(**values)

    def test_trace_and_observation_replay_from_trusted_sources(self):
        oracle = _oracle("N00")
        trace = _trace("N00")
        rebuilt_trace = SealedCaseTrace.from_dict(trace.to_dict())
        observation = score_sealed_case(oracle, rebuilt_trace)
        self.assertEqual(
            type(observation).from_dict(
                observation.to_dict(), oracle=oracle, trace=rebuilt_trace
            ),
            observation,
        )

    def test_public_scenario_model_request_excludes_oracle_fields(self):
        scenario = _scenario("N00")
        self.assertEqual(SealedScenario.from_dict(scenario.to_dict()), scenario)
        model_input = json.dumps(scenario.model_request_dict(), ensure_ascii=False)
        for forbidden in (
            "acceptable_node_ids", "target_status", "expected_route",
            "acceptable_policy_statuses", "oracle_hash",
        ):
            self.assertNotIn(forbidden, model_input)
        _validate_schema("navigation-copilot-sealed-scenario.v2", scenario.to_dict())

    def test_wrong_context_challenge_requires_an_executable_parent_ref(self):
        scenario = _scenario(sorted(WRONG_CONTEXT_REFS)[0])
        values = scenario.to_dict()
        values.pop("schema_version")
        values.pop("scenario_hash")
        values["proposed_parent_ref"] = None
        with self.assertRaises(ValueError):
            SealedScenario.create(**values)

    def test_versioned_schemas_accept_trusted_artifacts(self):
        manifest = _manifest()
        oracle = _oracle("N00")
        scenario = _scenario("N00")
        trace = _trace("N00")
        observation = score_sealed_case(oracle, trace)
        _validate_schema("navigation-copilot-sealed-evaluation-manifest.v2", manifest.to_dict())
        _validate_schema("navigation-copilot-sealed-scenario.v2", scenario.to_dict())
        _validate_schema("navigation-copilot-sealed-oracle.v2", oracle.to_dict())
        _validate_schema("navigation-copilot-sealed-trace.v1", trace.to_dict())
        _validate_schema("navigation-copilot-sealed-observation.v1", observation.to_dict())

    def test_complete_plan_round_trips_before_execution(self):
        scenarios = tuple(_scenario(ref) for ref in SCENARIO_REFS)
        oracles = tuple(
            _oracle(ref, request_digest=scenario.request_digest)
            for ref, scenario in zip(SCENARIO_REFS, scenarios)
        )
        validate_sealed_plan(_manifest(), scenarios, oracles)

    def test_plan_rejects_wrong_context_quota_drift(self):
        scenarios = list(_scenario(ref) for ref in SCENARIO_REFS)
        index = next(
            index for index, scenario in enumerate(scenarios)
            if scenario.wrong_context_challenge
        )
        values = scenarios[index].to_dict()
        values.pop("schema_version")
        values.pop("scenario_hash")
        values["wrong_context_challenge"] = False
        scenarios[index] = SealedScenario.create(**values)
        oracles = tuple(
            _oracle(
                ref,
                request_digest=scenario.request_digest,
                wrong_context=scenario.wrong_context_challenge,
            )
            for ref, scenario in zip(SCENARIO_REFS, scenarios)
        )
        with self.assertRaises(SealedEvaluationError) as caught:
            validate_sealed_plan(_manifest(), tuple(scenarios), oracles)
        self.assertEqual(caught.exception.code, "SEALED_PLAN_QUOTA_INVALID")


class SealedScoringTests(unittest.TestCase):
    def test_scores_help_and_harm_without_changing_retrieval_denominator(self):
        oracle = _oracle("N00")
        helped = score_sealed_case(
            oracle, _trace("N00", r0_rank=9, c1_rank=1)
        )
        harmed = score_sealed_case(
            oracle, _trace("N00", r0_rank=1, c1_rank=9)
        )
        self.assertIn("SEALED_C1_HELPED_TOP8", helped.finding_codes)
        self.assertIn("SEALED_C1_HARMED_TOP8", harmed.finding_codes)
        self.assertEqual(harmed.first_failure_stage, "RETRIEVAL")

    def test_rejects_oracle_trace_source_mismatch(self):
        with self.assertRaises(SealedEvaluationError) as caught:
            score_sealed_case(_oracle("N00"), _trace("N01"))
        self.assertEqual(caught.exception.code, "SEALED_SCORING_SOURCE_MISMATCH")

    def test_absent_confident_recommendation_is_semantic_failure(self):
        trace = _trace("A00", highlighted_node="wrong-node")
        observation = score_sealed_case(_oracle("A00"), trace)
        self.assertTrue(observation.absent_confident_error)
        self.assertEqual(observation.first_failure_stage, "SEMANTIC")

    def test_failed_run_stays_in_denominator_and_is_understanding_failure(self):
        trace = SealedCaseTrace.create(
            scenario_ref="N00",
            round_index=1,
            tree_digest=TREE_DIGEST,
            request_digest=REQUEST_DIGEST,
            provider_mode="BAILIAN_LIVE",
            run_status="PROVIDER_FAILED",
            failure_code="BAILIAN_TIMEOUT",
            failure_stage="UNDERSTANDING",
            logical_model_stage_count=1,
            wire_attempt_count=2,
            sidecar_complete=False,
            interpretation_status=None,
            observed_route=None,
            observed_profile=None,
            r0_candidate_node_ids=("node-N00",),
            c1_candidate_node_ids=(),
            policy_status=None,
            highlighted_node_id=None,
            outcome=None,
        )
        observation = score_sealed_case(_oracle("N00"), trace)
        self.assertEqual(observation.first_failure_stage, "UNDERSTANDING")
        self.assertFalse(observation.joint_match)


class SealedAggregateTests(unittest.TestCase):
    def test_all_passing_observations_are_ready_and_public(self):
        aggregate = public_sealed_aggregate(
            _manifest(), _observations(), run_integrity_valid=True
        )
        self.assertEqual(
            aggregate["qualification_status"], "READY_FOR_PROTECTED_SHADOW"
        )
        self.assertEqual(aggregate["c1_top8_hit_count"], 42)
        self.assertEqual(aggregate["repeat_stable_count"], 16)
        encoded = json.dumps(aggregate, sort_keys=True)
        self.assertNotIn("node-", encoded)
        self.assertNotIn("scenario_ref", encoded)
        _validate_schema("navigation-copilot-sealed-aggregate.v1", aggregate)

    def test_missing_repeat_round_is_inconclusive(self):
        observations = _observations()[:-1]
        aggregate = public_sealed_aggregate(
            _manifest(), observations, run_integrity_valid=True
        )
        self.assertEqual(aggregate["qualification_status"], "INCONCLUSIVE")

    def test_retrieval_failures_hold_retrieval(self):
        def misses(ref, round_index=1):
            rank = 9 if CATEGORIES[ref] != "TARGET_ABSENT" else None
            return _trace(ref, round_index, c1_rank=rank)

        aggregate = public_sealed_aggregate(
            _manifest(), _observations(misses), run_integrity_valid=True
        )
        self.assertEqual(aggregate["qualification_status"], "HOLD_RETRIEVAL")

    def test_model_degradation_precedes_other_capability_holds(self):
        def degraded(ref, round_index=1):
            return _trace(ref, round_index, degraded=ref in SCENARIO_REFS[:5])

        aggregate = public_sealed_aggregate(
            _manifest(), _observations(degraded), run_integrity_valid=True
        )
        self.assertEqual(
            aggregate["qualification_status"], "HOLD_MODEL_CONTRACT"
        )

    def test_integrity_failure_invalidates_run(self):
        aggregate = public_sealed_aggregate(
            _manifest(), _observations(), run_integrity_valid=False
        )
        self.assertEqual(aggregate["qualification_status"], "DATA_OR_RUN_INVALID")

    def test_aggregate_requires_exact_replay(self):
        manifest = _manifest()
        observations = _observations()
        aggregate = public_sealed_aggregate(
            manifest, observations, run_integrity_valid=True
        )
        self.assertEqual(
            replay_public_sealed_aggregate(
                aggregate, manifest, observations, run_integrity_valid=True
            ),
            aggregate,
        )
        aggregate["c1_top8_hit_count"] = 41
        with self.assertRaises(SealedEvaluationError):
            replay_public_sealed_aggregate(
                aggregate, manifest, observations, run_integrity_valid=True
            )


if __name__ == "__main__":
    unittest.main()
