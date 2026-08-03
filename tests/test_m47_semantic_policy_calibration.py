from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_m47_semantic_policy_calibration.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_m47_semantic_policy_calibration_test", SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4.7 calibration script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


M47 = _load_module()


class M47SemanticPolicyCalibrationTests(unittest.TestCase):
    def _results(self, v4_statuses: list[str]) -> list[dict[str, str]]:
        baseline = (
            ["PREFERRED_MATCH"] * 12
            + ["SAFE_ALTERNATIVE"] * 23
            + ["UNSAFE_MISMATCH"] * 7
            + ["RUN_FAILED"] * 2
        )
        return [
            {"baseline_status": old, "v4_status": new, "calls": [{}]}
            for old, new in zip(baseline, v4_statuses, strict=True)
        ]

    def test_aggregate_marks_only_threshold_satisfying_result_promising(self) -> None:
        statuses = (
            ["PREFERRED_MATCH"] * 12
            + ["SAFE_ALTERNATIVE"] * 25
            + ["UNSAFE_MISMATCH"] * 6
            + ["RUN_FAILED"]
        )
        aggregate = M47.build_aggregate(self._results(statuses))
        self.assertEqual(aggregate["decision"], "PROMISING_FOR_SEALED_VALIDATION")
        self.assertEqual(aggregate["contract_legal_count"], 43)
        self.assertEqual(aggregate["first_pass_count"], 44)
        self.assertEqual(aggregate["retry_observation_count"], 0)
        self.assertEqual(aggregate["actual_request_count"], 44)

    def test_aggregate_rejects_regression_to_unsafe(self) -> None:
        statuses = (
            ["UNSAFE_MISMATCH"]
            + ["PREFERRED_MATCH"] * 12
            + ["SAFE_ALTERNATIVE"] * 25
            + ["UNSAFE_MISMATCH"] * 5
            + ["RUN_FAILED"]
        )
        aggregate = M47.build_aggregate(self._results(statuses))
        self.assertEqual(aggregate["decision"], "NOT_PROMISING")
        self.assertEqual(
            aggregate["baseline_preferred_or_safe_to_unsafe_count"], 1
        )

    def test_provider_rejects_unplanned_body_before_transport(self) -> None:
        provider = M47.ApprovedV4Provider(
            M47.BailianConfig(api_key="NOT_USED"), set(), [], []
        )
        with self.assertRaisesRegex(M47.M47Error, "M47_BODY_NOT_PLANNED"):
            provider._post_json({"model": "qwen", "messages": []})


if __name__ == "__main__":
    unittest.main()
