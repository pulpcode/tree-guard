from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_fire_m4_calibration_silver.py"
RECORDED_AT = "2030-01-02T03:06:00Z"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_calibration_silver_freeze",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4 Silver freeze")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SILVER = _load_module()


class FireM4CalibrationSilverTests(unittest.TestCase):
    def test_freeze_is_private_source_bound_and_non_gating(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "silver"
            report = SILVER.prepare(RECORDED_AT, output_dir)
            manifest = json.loads((output_dir / "manifest.json").read_text())
            authorizations = json.loads(
                (output_dir / "silver-authorizations.json").read_text()
            )

            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["accepted_count"], 8)
            self.assertEqual(report["execution_count"], 8)
            self.assertEqual(manifest["quality_tier"], "SILVER")
            self.assertTrue(manifest["execution_eligible"])
            self.assertFalse(manifest["gold_eligible"])
            self.assertFalse(manifest["gate_eligible"])
            self.assertFalse(manifest["patch_eligible"])
            self.assertIn("NO_AUTOMATIC_GOLD_UPGRADE", manifest["limitations"])
            self.assertEqual(len(authorizations["items"]), 8)
            self.assertEqual(
                sum(
                    item["authorization"]["oracle"]["expected_route"]
                    == "PROCEED"
                    for item in authorizations["items"]
                ),
                7,
            )
            self.assertEqual(stat.S_IMODE(output_dir.stat().st_mode), 0o700)
            self.assertTrue(
                all(
                    stat.S_IMODE(path.stat().st_mode) == 0o600
                    for path in output_dir.iterdir()
                )
            )

    def test_check_rejects_tampered_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "silver"
            SILVER.prepare(RECORDED_AT, output_dir)
            path = output_dir / "silver-authorizations.json"
            path.write_bytes(path.read_bytes() + b" ")

            with self.assertRaises(SILVER.M4SilverDataError) as caught:
                SILVER.validate_staging(output_dir)

            self.assertEqual(
                caught.exception.code,
                "SILVER_STAGING_DIGEST_MISMATCH",
            )

    def test_u005_limitation_does_not_promote_to_gold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "silver"
            SILVER.prepare(RECORDED_AT, output_dir)
            authorizations = json.loads(
                (output_dir / "silver-authorizations.json").read_text()
            )
            u005 = next(
                item
                for item in authorizations["items"]
                if item["plan_unit_ref"] == "U005"
            )

            self.assertEqual(
                u005["assessment_codes"],
                ["CLARIFICATION_QUALITY_NOT_SCORED"],
            )
            self.assertFalse(u005["authorization"]["gold_eligible"])
            self.assertFalse(u005["authorization"]["gate_eligible"])


if __name__ == "__main__":
    unittest.main()
