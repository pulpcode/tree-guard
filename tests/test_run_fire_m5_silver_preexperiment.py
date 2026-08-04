import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from treeguard.ai_review import BailianConfig
from treeguard.change_intent import ChangeIntentDraft, MODEL_OUTPUT_SCHEMA_VERSION
from treeguard.private_io import read_private_json, write_private_json

from scripts.run_fire_m5_silver_preexperiment import (
    FIXTURE_DIR,
    GuardedIntentProvider,
    M5SilverExperimentError,
    _intent_request,
    _load_sources,
    build_plan,
    execute_plan,
    read_plan,
    score_private_result,
    write_plan,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _MismatchingIntentProvider:
    def __init__(self, config, forbidden_values, audit) -> None:
        self.validation_error_codes = []

    def draft(self, request, tree):
        return ChangeIntentDraft.from_model_dict(
            {
                "schema_version": MODEL_OUTPUT_SCHEMA_VERSION,
                "subject": "完全无关的虚构字段",
                "role": None,
                "scenario": None,
                "lifecycle": None,
                "ownership": "UNKNOWN",
                "node_kind": "UNKNOWN",
                "value_type": None,
                "cardinality": "UNKNOWN",
                "confirmed_facts": [],
                "assumptions": [],
                "evidence_gaps": [],
                "clarification_question": None,
            },
            request,
            tree,
            model_provider="TEST_PROVIDER",
            model_capability="TEST_INTENT",
            model_name="test-model",
            prompt_version="test-prompt.v1",
        )


class _PreferredRecommendation:
    recommended_action = "USE_EXISTING_NODE"

    def to_dict(self):
        return {"test_only": "preferred"}


class FireM5SilverPreexperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_plan_is_deterministic_non_qualifying_and_contains_no_answers(self) -> None:
        first = build_plan()
        second = build_plan()

        self.assertEqual(first, second)
        self.assertEqual(first["observation_count"], 72)
        self.assertEqual(first["quality_tier"], "SILVER")
        self.assertEqual(first["evaluation_role"], "CALIBRATION_ONLY")
        self.assertTrue(first["qualification_forfeited_on_first_call"])
        self.assertFalse(first["gate_eligible"])
        serialized = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("requirement_text", serialized)
        self.assertNotIn("capability_oracle", serialized)
        self.assertNotIn("M5N", serialized)

    def test_plan_replay_rejects_rehashed_policy_tampering(self) -> None:
        original = self.root / "plan.json"
        write_plan(original)
        payload = read_private_json(original, max_bytes=5_000_000)
        payload["model"] = "qwen-tampered"
        payload["plan_digest"] = "0" * 64
        tampered = self.root / "tampered.json"
        self.assertTrue(write_private_json(tampered, payload))

        with self.assertRaises(M5SilverExperimentError) as caught:
            read_plan(tampered, _sha256(tampered))
        self.assertEqual(caught.exception.code, "M5_SILVER_PLAN_INVALID")

    def test_transport_guard_rejects_stable_node_before_network(self) -> None:
        provider = GuardedIntentProvider(
            BailianConfig(api_key="test-key"),
            frozenset({"M5N0001"}),
            [],
        )

        with self.assertRaises(M5SilverExperimentError) as caught:
            provider._post_json({"messages": [{"content": "M5N0001"}]})
        self.assertEqual(caught.exception.code, "M5_SILVER_MODEL_INPUT_LEAK")

    def test_intent_mismatch_short_circuits_retrieval_and_semantic(self) -> None:
        plan_file = self.root / "plan.json"
        result_file = self.root / "result.json"
        exposure_file = self.root / "exposure.json"
        write_plan(plan_file)
        semantic_factory_calls = []

        def semantic_factory(*args):
            semantic_factory_calls.append(args)
            raise AssertionError("Semantic must not run after Intent mismatch")

        with (
            patch(
                "scripts.run_fire_m5_silver_preexperiment._validate_tls_trust"
            ),
            patch(
                "scripts.run_fire_m5_silver_preexperiment.BailianConfig.from_env",
                return_value=BailianConfig(api_key="test-key"),
            ),
        ):
            aggregate = execute_plan(
                plan_file=plan_file,
                plan_sha256=_sha256(plan_file),
                private_output=result_file,
                exposure_marker=exposure_file,
                intent_provider_factory=_MismatchingIntentProvider,
                semantic_provider_factory=semantic_factory,
            )

        self.assertEqual(semantic_factory_calls, [])
        self.assertEqual(aggregate["report"]["semantic_attempted_count"], 0)
        self.assertEqual(aggregate["report"]["executed_retrieval_count"], 0)
        self.assertEqual(aggregate["report"]["decision"], "EVALUATION_PENDING")
        self.assertTrue(aggregate["qualification_forfeited"])
        self.assertEqual(exposure_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result_file.stat().st_mode & 0o777, 0o600)

    def test_score_rejects_rehashed_short_circuit_tampering(self) -> None:
        plan_file = self.root / "plan.json"
        result_file = self.root / "result.json"
        exposure_file = self.root / "exposure.json"
        write_plan(plan_file)
        with (
            patch(
                "scripts.run_fire_m5_silver_preexperiment._validate_tls_trust"
            ),
            patch(
                "scripts.run_fire_m5_silver_preexperiment.BailianConfig.from_env",
                return_value=BailianConfig(api_key="test-key"),
            ),
        ):
            execute_plan(
                plan_file=plan_file,
                plan_sha256=_sha256(plan_file),
                private_output=result_file,
                exposure_marker=exposure_file,
                intent_provider_factory=_MismatchingIntentProvider,
                semantic_provider_factory=lambda *args: None,
            )
        payload = read_private_json(result_file, max_bytes=30_000_000)
        payload["results"][0]["retrieval_status"] = "MATCH"
        tampered = self.root / "tampered-result.json"
        self.assertTrue(write_private_json(tampered, payload))

        with self.assertRaises(M5SilverExperimentError) as caught:
            score_private_result(
                result_file=tampered,
                result_sha256=_sha256(tampered),
                plan_file=plan_file,
                plan_sha256=_sha256(plan_file),
                codex_safe_reviewed=False,
            )
        self.assertEqual(
            caught.exception.code, "M5_SILVER_STAGE_SHORT_CIRCUIT_INVALID"
        )

    def test_ideal_fake_run_exercises_all_three_stages_with_pending_decision(self) -> None:
        plan_file = self.root / "plan.json"
        result_file = self.root / "result.json"
        exposure_file = self.root / "exposure.json"
        write_plan(plan_file)
        _, formal, oracle_by_ref, _ = _load_sources()
        seed_by_request_hash = {
            _intent_request(item["request"]).request_hash: oracle_by_ref[
                item["scenario_ref"]
            ]["retrieval_seed"]
            for item in formal
        }

        class MatchingIntentProvider:
            def __init__(self, config, forbidden_values, audit) -> None:
                self.validation_error_codes = []

            def draft(self, request, tree):
                seed = seed_by_request_hash[request.request_hash]
                return ChangeIntentDraft.from_model_dict(
                    {"schema_version": MODEL_OUTPUT_SCHEMA_VERSION, **seed},
                    request,
                    tree,
                    model_provider="TEST_PROVIDER",
                    model_capability="TEST_INTENT",
                    model_name="test-model",
                    prompt_version="test-prompt.v1",
                )

        class MatchingSemanticProvider:
            validation_error_codes = []

            def __init__(self, config, forbidden_values, audit) -> None:
                pass

            def recommend(self, confirmation, candidate_set, tree):
                return _PreferredRecommendation()

        with (
            patch(
                "scripts.run_fire_m5_silver_preexperiment._validate_tls_trust"
            ),
            patch(
                "scripts.run_fire_m5_silver_preexperiment.BailianConfig.from_env",
                return_value=BailianConfig(api_key="test-key"),
            ),
            patch(
                "scripts.run_fire_m5_silver_preexperiment.recommendation_matches_oracle",
                return_value=True,
            ),
        ):
            aggregate = execute_plan(
                plan_file=plan_file,
                plan_sha256=_sha256(plan_file),
                private_output=result_file,
                exposure_marker=exposure_file,
                intent_provider_factory=MatchingIntentProvider,
                semantic_provider_factory=MatchingSemanticProvider,
            )

        report = aggregate["report"]
        self.assertEqual(report["executed_retrieval_count"], 54)
        self.assertEqual(report["retrieval_match_count"], 54)
        self.assertEqual(report["semantic_attempted_count"], 54)
        self.assertEqual(report["clarification_match_count"], 18)
        self.assertEqual(
            [item["safe_full_path_count"] for item in report["rounds"]],
            [24, 24, 24],
        )
        self.assertEqual(
            [item["preferred_full_path_count"] for item in report["rounds"]],
            [18, 18, 18],
        )
        self.assertEqual(report["decision"], "EVALUATION_PENDING")
        self.assertEqual(
            report["qualification_codes"], ["ASSISTED_ORACLE_NOT_HUMAN_REVIEWED"]
        )


if __name__ == "__main__":
    unittest.main()
