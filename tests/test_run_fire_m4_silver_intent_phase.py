from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_fire_m4_silver_intent_phase.py"
RECORDED_AT = "2030-01-02T03:06:00Z"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_intent_phase_run",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4 Silver Intent phase run")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_module()


class FireM4SilverIntentRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.silver_dir = cls.root / "silver"
        RUNNER.APPROVAL_PREP.SILVER_FREEZE.prepare(
            RECORDED_AT,
            cls.silver_dir,
        )
        cls.approval_path, cls.approval_sha256 = (
            RUNNER.APPROVAL_PREP.write_approval(cls.silver_dir, cls.root)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_approval_requires_exact_hash_and_fixed_policy(self) -> None:
        payload = RUNNER._read_approval(
            self.approval_path,
            self.approval_sha256,
        )

        self.assertEqual(payload["quality_tier"], "SILVER")
        self.assertFalse(payload["gold_eligible"])
        self.assertFalse(payload["gate_eligible"])
        expected_per_scenario = 1 + len(RUNNER.APPROVAL_PREP.RETRY_CODES)
        self.assertEqual(
            {
                item["plan_unit_ref"]: sum(
                    candidate["plan_unit_ref"] == item["plan_unit_ref"]
                    for candidate in payload["possible_requests"]
                )
                for item in payload["possible_requests"]
            },
            {
                item["plan_unit_ref"]: expected_per_scenario
                for item in payload["possible_requests"]
            },
        )
        with self.assertRaises(RUNNER.M4SilverIntentRunError) as caught:
            RUNNER._read_approval(self.approval_path, "0" * 64)
        self.assertEqual(caught.exception.code, "SILVER_INTENT_APPROVAL_INVALID")

    def test_provider_rejects_unapproved_body_before_network(self) -> None:
        provider = RUNNER.ApprovedIntentProvider(
            RUNNER.BailianConfig(
                api_key="NOT_USED",
                base_url=RUNNER.DEFAULT_BASE_URL,
                model=RUNNER.DEFAULT_MODEL,
            ),
            set(),
            [],
        )

        with self.assertRaises(RUNNER.M4SilverIntentRunError) as caught:
            provider._post_json({"outside": "approval"})

        self.assertEqual(caught.exception.code, "SILVER_INTENT_BODY_NOT_APPROVED")


if __name__ == "__main__":
    unittest.main()
