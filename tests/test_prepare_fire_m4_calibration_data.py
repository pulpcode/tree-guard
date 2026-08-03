from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/prepare_fire_m4_calibration_data.py"
SOURCE_FIXTURE_DIR = (
    PROJECT_ROOT / "tests/fixtures/fictional/fire_validation_m4_blind"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_calibration_preparation", SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4 calibration preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREPARATION = _load_module()


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class FireM4CalibrationPreparationTests(unittest.TestCase):
    def test_prepare_is_deterministic_private_and_preserves_blind_source(self) -> None:
        source_before = {
            path.name: _digest(path) for path in SOURCE_FIXTURE_DIR.iterdir()
        }
        with tempfile.TemporaryDirectory() as temporary:
            first_dir = Path(temporary) / "calibration-first"
            second_dir = Path(temporary) / "calibration-second"
            first_report = PREPARATION.prepare(first_dir)
            first_bytes = {
                path.name: path.read_bytes() for path in first_dir.iterdir()
            }
            second_report = PREPARATION.prepare(second_dir)
            second_bytes = {
                path.name: path.read_bytes() for path in second_dir.iterdir()
            }

            self.assertEqual(first_report, second_report)
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(set(first_bytes), PREPARATION.OUTPUT_FILES)
            self.assertEqual(first_report["status"], "PASS")
            self.assertEqual(first_report["candidate_count"], 8)
            self.assertEqual(first_report["changed_expectation_count"], 59)
            self.assertEqual(first_report["bound_evidence_count"], 29)
            self.assertEqual(first_report["unbound_evidence_count"], 67)
            self.assertEqual(
                stat.S_IMODE(first_dir.stat().st_mode),
                0o700,
            )
            for path in first_dir.iterdir():
                self.assertEqual(
                    stat.S_IMODE(path.stat().st_mode),
                    0o600,
                )
            with self.assertRaises(PREPARATION.M4CalibrationDataError) as caught:
                PREPARATION.prepare(first_dir)
            self.assertEqual(
                caught.exception.code,
                "CALIBRATION_STAGING_ALREADY_EXISTS",
            )

        source_after = {
            path.name: _digest(path) for path in SOURCE_FIXTURE_DIR.iterdir()
        }
        self.assertEqual(source_before, source_after)

    def test_candidates_only_narrow_unbound_intent_fields(self) -> None:
        source = _read(SOURCE_FIXTURE_DIR / "oracle-sidecar.json")
        source_by_ref = {
            item["scenario_ref"]: item
            for item in source["items"]
            if item["execution_eligible"]
        }
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "calibration"
            PREPARATION.prepare(output_dir)
            candidate_batch = _read(output_dir / "scenario-candidates.json")
            manifest = _read(output_dir / "manifest.json")
            critic = _read(output_dir / "critic-report.json")
            human_review = _read(output_dir / "human-review.json")

            self.assertEqual(candidate_batch["evaluation_role"], "CALIBRATION")
            self.assertFalse(candidate_batch["execution_eligible"])
            self.assertFalse(candidate_batch["gate_eligible"])
            self.assertEqual(candidate_batch["exposure_status"], "EXPOSED")
            self.assertEqual(
                candidate_batch["review_status"], "PENDING_HUMAN_REVIEW"
            )
            self.assertFalse(manifest["gate_eligible"])
            self.assertFalse(manifest["execution_eligible"])
            self.assertEqual(manifest["intended_use"], "CALIBRATION_ONLY")
            self.assertEqual(
                critic["status"], "PASS_WITH_REVIEW_REQUIRED"
            )
            self.assertEqual(critic["blocking_finding_count"], 0)
            self.assertEqual(
                human_review["human_review_packet_sha256"],
                manifest["human_review_packet_sha256"],
            )
            self.assertNotIn('"overlay":', json.dumps(candidate_batch))
            self.assertEqual(len(candidate_batch["items"]), 8)
            for candidate in candidate_batch["items"]:
                source_item = source_by_ref[candidate["scenario_ref"]]
                source_oracle = source_item["overlay"]["oracle"]
                proposed = candidate["proposed_oracle"]
                request = source_item["reviewed"]["request"]
                bindings = candidate["field_evidence_bindings"]
                self.assertEqual(
                    candidate["candidate_item_sha256"],
                    PREPARATION.canonical_digest(
                        {
                            key: value
                            for key, value in candidate.items()
                            if key != "candidate_item_sha256"
                        }
                    ),
                )
                expected_bound = (
                    1
                    if proposed["expected_route"] == "CLARIFY"
                    else 4
                )
                self.assertEqual(
                    sum(
                        binding["evidence_status"] == "PROPOSED_BOUND"
                        for binding in bindings
                    ),
                    expected_bound,
                )
                self.assertEqual(
                    sum(
                        binding["evidence_status"] == "PROPOSED_UNBOUND"
                        for binding in bindings
                    ),
                    12 - expected_bound,
                )
                self.assertEqual(
                    proposed["expected_route"], source_oracle["expected_route"]
                )
                self.assertEqual(
                    proposed["retrieval"], source_oracle["retrieval"]
                )
                self.assertEqual(
                    proposed["recommendation"], source_oracle["recommendation"]
                )
                for profile in proposed["acceptable_intent_profiles"]:
                    fields = {
                        item["field_name"]: item
                        for item in profile["field_expectations"]
                    }
                    for field_name in PREPARATION.UNBOUND_V1_FIELDS & fields.keys():
                        self.assertEqual(fields[field_name]["policy"], "NOT_COMPARED")
                        self.assertEqual(fields[field_name]["acceptable_values"], [])
                    for field_name, request_field in PREPARATION.STRUCTURED_FIELDS.items():
                        request_value = request[request_field]
                        if request_value is None or request_value == "UNKNOWN":
                            self.assertEqual(
                                fields[field_name]["policy"],
                                "NOT_COMPARED",
                            )
                            self.assertEqual(
                                fields[field_name]["acceptable_values"],
                                [],
                            )
                        else:
                            self.assertEqual(
                                fields[field_name]["policy"],
                                "EXACT_ONE_OF",
                            )
                            self.assertEqual(
                                fields[field_name]["acceptable_values"],
                                [request_value],
                            )
                    self.assertEqual(set(fields), PREPARATION.INTENT_FIELDS)
                    question = fields["clarification_question"]
                    if proposed["expected_route"] == "CLARIFY":
                        self.assertEqual(question["policy"], "NON_EMPTY")
                    else:
                        self.assertEqual(question["policy"], "EXACT_ONE_OF")
                        self.assertEqual(question["acceptable_values"], [None])

    def test_tampered_staging_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "calibration"
            PREPARATION.prepare(output_dir)
            candidate_path = output_dir / "scenario-candidates.json"
            candidate_path.write_bytes(candidate_path.read_bytes() + b" ")
            with self.assertRaises(PREPARATION.M4CalibrationDataError) as caught:
                PREPARATION.validate_staging(output_dir)
            self.assertEqual(
                caught.exception.code,
                "CALIBRATION_STAGING_DIGEST_MISMATCH",
            )

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "calibration"
            PREPARATION.prepare(output_dir)
            (output_dir / "manifest.json").chmod(0o644)
            with self.assertRaises(PREPARATION.M4CalibrationDataError) as caught:
                PREPARATION.validate_staging(output_dir)
            self.assertEqual(
                caught.exception.code,
                "CALIBRATION_STAGING_FILES_INVALID",
            )

    def test_partial_write_failure_publishes_no_staging_directory(self) -> None:
        original_writer = PREPARATION.write_private_json
        write_count = 0

        def fail_second_write(path, payload):
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                return False
            return original_writer(path, payload)

        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            output_dir = parent / "calibration"
            with mock.patch.object(
                PREPARATION,
                "write_private_json",
                side_effect=fail_second_write,
            ):
                with self.assertRaises(
                    PREPARATION.M4CalibrationDataError
                ) as caught:
                    PREPARATION.prepare(output_dir)
            self.assertEqual(
                caught.exception.code,
                "CALIBRATION_STAGING_WRITE_FAILED",
            )
            self.assertFalse(output_dir.exists())
            self.assertEqual(tuple(parent.iterdir()), ())

    def test_cli_output_is_aggregate_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--output-dir",
                    str(Path(temporary) / "calibration"),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["review_status"], "PENDING_HUMAN_REVIEW")
        for forbidden in (
            "requirement_text",
            "proposed_oracle",
            "source_overlay_hash",
            "acceptable_node_ids",
        ):
            self.assertNotIn(forbidden, completed.stdout)
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
