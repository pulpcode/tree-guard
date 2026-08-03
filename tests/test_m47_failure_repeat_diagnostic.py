from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_m47_failure_repeat_diagnostic.py"


def _load():
    spec = importlib.util.spec_from_file_location("treeguard_m47_repeat_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4.7 repeat diagnostic")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REPEAT = _load()


class M47FailureRepeatDiagnosticTests(unittest.TestCase):
    def test_repeat_plan_selects_only_two_run_failures(self) -> None:
        possible = [{"wire_sha256": "a", "wire_body_text": "{}"}]
        source_plan = {
            "schema_version": REPEAT.M47.PLAN_SCHEMA_VERSION,
            "model": "qwen",
            "prompt_version": "v4",
            "units": [
                {"observation_ref": ref, "possible_requests": possible}
                for ref in ("R:1", "R:2", "R:3")
            ],
        }
        source_result = {
            "schema_version": REPEAT.M47.RESULT_SCHEMA_VERSION,
            "plan_sha256": "p" * 64,
            "quality_tier": "SILVER",
            "evaluation_role": "CALIBRATION_ONLY",
            "gate_eligible": False,
            "gold_eligible": False,
            "results": [
                {
                    "observation_ref": "R:1",
                    "v4_status": "RUN_FAILED",
                    "failure_code": "SEMANTIC_MODEL_FIELDS_INVALID",
                },
                {
                    "observation_ref": "R:2",
                    "v4_status": "PREFERRED_MATCH",
                    "failure_code": None,
                },
                {
                    "observation_ref": "R:3",
                    "v4_status": "RUN_FAILED",
                    "failure_code": "BAILIAN_CONNECTION_FAILED",
                },
            ],
        }
        plan = REPEAT.build_repeat_plan(
            source_plan,
            source_result,
            source_plan_sha256="p" * 64,
            source_result_sha256="r" * 64,
        )
        self.assertEqual(
            [item["observation_ref"] for item in plan["units"]],
            ["R:1", "R:3"],
        )
        self.assertEqual(plan["maximum_actual_request_count"], 8)
        self.assertFalse(plan["rescores_main_result"])


if __name__ == "__main__":
    unittest.main()
