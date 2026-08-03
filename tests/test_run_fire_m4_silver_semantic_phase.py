from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_fire_m4_silver_semantic_phase.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_semantic_phase_run",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4 Silver Semantic phase run")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_module()


class FireM4SilverSemanticRunTests(unittest.TestCase):
    def test_provider_records_only_failed_validation_codes(self) -> None:
        provider = RUNNER.ApprovedSemanticProvider(
            RUNNER.BailianConfig(api_key="NOT_USED"),
            set(),
            [],
        )

        provider._capture_validation_trace(
            SimpleNamespace(
                validation_status="FAILED",
                validation_error_code="SEMANTIC_ACTION_POLICY_INVALID",
            )
        )
        provider._capture_validation_trace(
            SimpleNamespace(
                validation_status="PASSED",
                validation_error_code=None,
            )
        )
        provider._capture_validation_trace(
            SimpleNamespace(
                validation_status="FAILED",
                validation_error_code="BAILIAN_CONNECTION_FAILED",
            )
        )

        self.assertEqual(
            provider.validation_error_codes,
            ["SEMANTIC_ACTION_POLICY_INVALID"],
        )

    def test_validation_error_counts_are_sorted_and_aggregated(self) -> None:
        self.assertEqual(
            RUNNER._validation_error_code_counts(
                [
                    {"validation_error_codes": ["SEMANTIC_Z", "SEMANTIC_A"]},
                    {"validation_error_codes": ["SEMANTIC_Z"]},
                ]
            ),
            {"SEMANTIC_A": 1, "SEMANTIC_Z": 2},
        )


if __name__ == "__main__":
    unittest.main()
