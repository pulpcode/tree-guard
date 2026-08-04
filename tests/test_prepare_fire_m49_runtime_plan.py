from __future__ import annotations

import copy
import json
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_fire_m49_runtime_plan import (
    FIXTURE_DIR,
    INTENT_RETRY_CODES,
    M49RuntimePlanError,
    OBSERVATION_COUNT,
    TOTAL_MAXIMUM_ACTUAL_REQUEST_COUNT,
    build_plan,
    validate_plan,
    write_plan,
)
from treeguard.hashing import canonical_digest


class FireM49RuntimePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_plan()

    def test_plan_is_deterministic_and_has_exact_three_round_accounting(self) -> None:
        self.assertEqual(self.plan, build_plan())
        self.assertEqual(3, self.plan["round_count"])
        self.assertEqual(24, self.plan["formal_scenario_count"])
        self.assertEqual(OBSERVATION_COUNT, len(self.plan["units"]))
        self.assertEqual(72, self.plan["intent_initial_request_count"])
        self.assertEqual(144, self.plan["intent_maximum_actual_request_count"])
        self.assertEqual(1_296, self.plan["intent_possible_request_body_count"])
        self.assertEqual(162, self.plan["semantic_maximum_actual_request_count"])
        self.assertEqual(
            TOTAL_MAXIMUM_ACTUAL_REQUEST_COUNT,
            self.plan["total_maximum_actual_request_count"],
        )

    def test_every_unit_freezes_first_and_all_retry_wire_bodies(self) -> None:
        for unit in self.plan["units"]:
            requests = unit["intent_possible_requests"]
            self.assertEqual(1 + len(INTENT_RETRY_CODES), len(requests))
            self.assertEqual((1, None), (requests[0]["attempt"], requests[0]["retry_code"]))
            self.assertEqual(
                list(INTENT_RETRY_CODES),
                [item["retry_code"] for item in requests[1:]],
            )
            self.assertEqual({2}, {item["attempt"] for item in requests[1:]})

    def test_same_scenario_reuses_identical_frozen_bodies_across_rounds(self) -> None:
        by_scenario: dict[str, list[list[str]]] = {}
        for unit in self.plan["units"]:
            by_scenario.setdefault(unit["scenario_ref"], []).append(
                [
                    request["wire_sha256"]
                    for request in unit["intent_possible_requests"]
                ]
            )
        self.assertEqual(24, len(by_scenario))
        for rounds in by_scenario.values():
            self.assertEqual(3, len(rounds))
            self.assertEqual(rounds[0], rounds[1])
            self.assertEqual(rounds[1], rounds[2])

    def test_plan_is_non_gating_and_stops_before_execution(self) -> None:
        self.assertFalse(self.plan["execution_authorized"])
        self.assertFalse(self.plan["gate_eligible"])
        self.assertFalse(self.plan["gold_eligible"])
        self.assertFalse(self.plan["patch_eligible"])
        self.assertFalse(self.plan["runtime_registered"])
        self.assertFalse(self.plan["experiment_executed"])
        self.assertEqual(
            "NOT_YET_CONSTRUCTIBLE", self.plan["semantic_request_plan_state"]
        )
        self.assertEqual(
            "EXPLICIT_INTENT_EXECUTION_APPROVAL", self.plan["next_gate"]
        )

    def test_plan_contains_no_oracle_or_credentials(self) -> None:
        text = json.dumps(self.plan, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            '"acceptable_node_ids"',
            '"acceptable_outcomes"',
            '"authorization"',
            '"capability_oracle"',
            '"oracle"',
            '"target_node_id"',
            '"expected_route"',
            '"api_key"',
        ):
            self.assertNotIn(forbidden, text)

    def test_private_plan_is_mode_0600_and_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-runtime-") as temp_dir:
            output = Path(temp_dir) / "runtime-plan.json"
            report = write_plan(output)
            self.assertEqual("PASS", report["status"])
            self.assertEqual(0o600, stat.S_IMODE(output.stat().st_mode))
            with self.assertRaisesRegex(
                M49RuntimePlanError, "M49_RUNTIME_OUTPUT_EXISTS"
            ):
                write_plan(output)

    def test_rehashed_wire_body_tamper_fails_trusted_replay(self) -> None:
        tampered = copy.deepcopy(self.plan)
        request = tampered["units"][0]["intent_possible_requests"][0]
        body = json.loads(request["wire_body_text"])
        body["temperature"] = 0.1
        request["wire_body_text"] = json.dumps(body, ensure_ascii=False)
        from hashlib import sha256

        request["wire_sha256"] = sha256(
            request["wire_body_text"].encode("utf-8")
        ).hexdigest()
        tampered["plan_digest"] = canonical_digest(
            {key: value for key, value in tampered.items() if key != "plan_digest"}
        )
        with self.assertRaisesRegex(
            M49RuntimePlanError, "M49_RUNTIME_PLAN_REPLAY_MISMATCH"
        ):
            validate_plan(tampered)

    def test_bool_as_int_accounting_tamper_is_rejected(self) -> None:
        tampered = copy.deepcopy(self.plan)
        tampered["round_count"] = True
        tampered["plan_digest"] = canonical_digest(
            {key: value for key, value in tampered.items() if key != "plan_digest"}
        )
        with self.assertRaisesRegex(
            M49RuntimePlanError, "M49_RUNTIME_PLAN_ACCOUNTING_INVALID"
        ):
            validate_plan(tampered, rebuild=False)

    def test_rehashed_model_config_tamper_is_rejected_without_replay(self) -> None:
        tampered = copy.deepcopy(self.plan)
        tampered["model"] = "different-model"
        tampered["plan_digest"] = canonical_digest(
            {key: value for key, value in tampered.items() if key != "plan_digest"}
        )
        with self.assertRaisesRegex(
            M49RuntimePlanError, "M49_RUNTIME_PLAN_POLICY_INVALID"
        ):
            validate_plan(tampered, rebuild=False)

    def test_fixture_source_tamper_stops_plan_before_any_execution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-runtime-source-") as temp_dir:
            fixture = Path(temp_dir) / "fixture"
            shutil.copytree(FIXTURE_DIR, fixture)
            manifest_path = fixture / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["fictional"] = False
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                M49RuntimePlanError, "M49_RUNTIME_FIXTURE_INVALID"
            ):
                build_plan(fixture)


if __name__ == "__main__":
    unittest.main()
