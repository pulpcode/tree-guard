from __future__ import annotations

import copy
import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_fire_m49_runtime_plan import (
    FIXTURE_DIR,
    build_plan,
    load_formal_intent_contexts,
    write_plan,
)
from scripts.run_fire_m49_intent_phase import (
    M49IntentRunError,
    PlannedIntentProvider,
    read_approved_plan,
    run_live,
    validate_result,
)
from treeguard.ai_review import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianAIReviewProvider,
    BailianConfig,
)
class FireM49IntentRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_plan()

    def _private_plan(self, root: Path) -> tuple[Path, str]:
        plan_path = root / "runtime-plan.json"
        write_plan(plan_path)
        import hashlib

        return plan_path, hashlib.sha256(plan_path.read_bytes()).hexdigest()

    @staticmethod
    def _valid_response(body: dict[str, object]) -> dict[str, object]:
        messages = body["messages"]
        assert isinstance(messages, list)
        user = json.loads(messages[1]["content"])
        output = copy.deepcopy(user["output_contract"]["exact_object_template"])
        hints = user["intent_request"]["hints"]
        output["subject"] = "虚构治理信息项"
        output["node_kind"] = hints["node_kind"]
        output["value_type"] = hints["value_type"]
        output["cardinality"] = hints["cardinality"]
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(output, ensure_ascii=False)},
                }
            ]
        }

    def test_plan_hash_and_mode_are_verified_before_execution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-intent-plan-") as temp_dir:
            plan_path, plan_sha = self._private_plan(Path(temp_dir))
            self.assertEqual(self.plan, read_approved_plan(plan_path, plan_sha))
            with self.assertRaisesRegex(
                M49IntentRunError, "M49_INTENT_PLAN_INVALID"
            ):
                read_approved_plan(plan_path, "0" * 64)
            plan_path.chmod(0o644)
            with self.assertRaisesRegex(
                M49IntentRunError, "M49_INTENT_PLAN_INVALID"
            ):
                read_approved_plan(plan_path, plan_sha)

    def test_provider_rejects_unplanned_body_before_transport(self) -> None:
        provider = PlannedIntentProvider(
            BailianConfig(api_key="NOT_USED", model=DEFAULT_MODEL),
            set(),
            [],
        )
        with patch.object(
            BailianAIReviewProvider,
            "_post_json",
            side_effect=AssertionError("transport must not run"),
        ):
            with self.assertRaisesRegex(
                M49IntentRunError, "M49_INTENT_BODY_NOT_PLANNED"
            ):
                provider._post_json({"model": DEFAULT_MODEL, "messages": []})

    def test_execution_flag_is_required_before_plan_or_environment_read(self) -> None:
        with patch(
            "scripts.run_fire_m49_intent_phase.read_approved_plan",
            side_effect=AssertionError("plan must not be read"),
        ):
            with self.assertRaisesRegex(
                M49IntentRunError, "M49_INTENT_EXECUTION_NOT_APPROVED"
            ):
                run_live(
                    plan_file=Path("not-read"),
                    approved_plan_sha256="0" * 64,
                    private_output=Path("not-written"),
                    execution_approved=False,
                )

    def test_mock_live_run_writes_private_replayable_results(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-intent-live-") as temp_dir:
            root = Path(temp_dir)
            plan_path, plan_sha = self._private_plan(root)
            output = root / "intent-results.json"
            config = BailianConfig(
                api_key="NOT_USED",
                base_url=DEFAULT_BASE_URL,
                model=DEFAULT_MODEL,
            )
            with (
                patch.object(BailianConfig, "from_env", return_value=config),
                patch(
                    "scripts.run_fire_m49_intent_phase.validate_tls_trust",
                    return_value=None,
                ),
                patch.object(
                    BailianAIReviewProvider,
                    "_post_json",
                    side_effect=lambda body: self._valid_response(body),
                ),
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    aggregate = run_live(
                        plan_file=plan_path,
                        approved_plan_sha256=plan_sha,
                        private_output=output,
                        fixture_dir=FIXTURE_DIR,
                        execution_approved=True,
                    )
            self.assertEqual("", stdout.getvalue())
            self.assertEqual(72, aggregate["draft_ready_count"])
            self.assertEqual(72, aggregate["actual_request_count"])
            self.assertEqual(0, aggregate["run_failed_count"])
            self.assertEqual(0o600, stat.S_IMODE(output.stat().st_mode))
            stored = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(aggregate, validate_result(stored, self.plan))

    def test_missing_tls_roots_stop_before_environment_and_transport(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-intent-tls-") as temp_dir:
            root = Path(temp_dir)
            plan_path, plan_sha = self._private_plan(root)
            with (
                patch(
                    "scripts.run_fire_m49_intent_phase.ssl.create_default_context"
                ) as create_context,
                patch.object(
                    BailianConfig,
                    "from_env",
                    side_effect=AssertionError("environment must not be read"),
                ),
            ):
                create_context.return_value.get_ca_certs.return_value = []
                with self.assertRaisesRegex(
                    M49IntentRunError, "M49_INTENT_TLS_TRUST_UNAVAILABLE"
                ):
                    run_live(
                        plan_file=plan_path,
                        approved_plan_sha256=plan_sha,
                        private_output=root / "not-written.json",
                        execution_approved=True,
                    )

    def test_contract_failure_uses_only_the_planned_retry_body(self) -> None:
        unit = self.plan["units"][0]
        context = load_formal_intent_contexts()[0]
        allowed = {
            request["wire_sha256"] for request in unit["intent_possible_requests"]
        }
        audit: list[dict[str, object]] = []
        provider = PlannedIntentProvider(
            BailianConfig(api_key="NOT_USED", model=DEFAULT_MODEL),
            allowed,
            audit,
        )
        calls = 0

        def response(body: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": "{}"}}
                    ]
                }
            return self._valid_response(body)

        with patch.object(BailianAIReviewProvider, "_post_json", side_effect=response):
            draft = provider.draft(context.request, context.tree)
        self.assertIsNotNone(draft)
        self.assertEqual([1, 2], [call["attempt"] for call in audit])
        planned_retry = {
            request["wire_sha256"]
            for request in unit["intent_possible_requests"]
            if request["retry_code"] == "INTENT_MODEL_FIELDS_INVALID"
        }
        self.assertEqual(planned_retry, {audit[1]["wire_sha256"]})

    def test_rehashed_result_call_tamper_is_rejected(self) -> None:
        unit_results = []
        for unit in self.plan["units"]:
            unit_results.append(
                {
                    "observation_ref": unit["observation_ref"],
                    "round_index": unit["round_index"],
                    "scenario_ref": unit["scenario_ref"],
                    "source_candidate_digest": unit["source_candidate_digest"],
                    "request_hash": "0" * 64,
                    "status": "RUN_FAILED",
                    "failure_code": "BAILIAN_CONNECTION_FAILED",
                    "calls": [
                        {
                            "attempt": 1,
                            "wire_sha256": unit["intent_possible_requests"][0][
                                "wire_sha256"
                            ],
                        }
                    ],
                    "draft": None,
                }
            )
        payload = {
            "schema_version": "fire-m49-sealed-intent-results.v1",
            "purpose": "M49_SEALED_SILVER_INTENT_ONLY",
            "dataset_ref": self.plan["dataset_ref"],
            "source_class": "CLEANROOM_SYNTHETIC",
            "fictional": True,
            "derived_from_real": False,
            "quality_tier": "CODEX_ASSISTED_SILVER",
            "evaluation_role": "CALIBRATION_ONLY",
            "gold_eligible": False,
            "gate_eligible": False,
            "patch_eligible": False,
            "contains_oracle": False,
            "contains_credentials": False,
            "plan_file_sha256": "0" * 64,
            "model": DEFAULT_MODEL,
            "prompt_version": "treeguard.change-intent.zh.v4",
            "round_count": 3,
            "observation_count": 72,
            "actual_request_count": 72,
            "first_pass_count": 72,
            "retry_observation_count": 0,
            "draft_ready_count": 0,
            "run_failed_count": 72,
            "failure_code_counts": {"BAILIAN_CONNECTION_FAILED": 72},
            "results": unit_results,
            "next_gate": "FREEZE_EXACT_SEMANTIC_REQUEST_PLAN",
        }
        self.assertEqual("PASS", validate_result(payload, self.plan)["status"])
        payload["results"][0]["calls"][0]["wire_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            M49IntentRunError, "M49_INTENT_RESULT_ITEM_INVALID"
        ):
            validate_result(payload, self.plan)


if __name__ == "__main__":
    unittest.main()
