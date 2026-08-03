from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (
    PROJECT_ROOT / "tests/fixtures/fictional/fire_validation_m4_blind"
)
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/preflight_fire_m4_blind_validation_data.py"
)


def _load_preflight_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_m4_blind_data_preflight", SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4 blind data preflight")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREFLIGHT = _load_preflight_module()

from treeguard.hashing import canonical_digest


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
    target = Path(temporary.name) / "fire_validation_m4_blind"
    shutil.copytree(FIXTURE_DIR, target)
    return temporary, target


def _rewrite_sidecar(fixture_dir: Path, sidecar) -> None:
    sidecar_bytes = PREFLIGHT.canonical_json_bytes(sidecar)
    (fixture_dir / "oracle-sidecar.json").write_bytes(sidecar_bytes)
    manifest_path = fixture_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    manifest["oracle_sidecar_sha256"] = sha256(sidecar_bytes).hexdigest()
    manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))


class FireM4BlindValidationDataTests(unittest.TestCase):
    def test_fixture_preflight_rejects_known_unanswerable_oracle(self) -> None:
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(FIXTURE_DIR)

        self.assertEqual(
            caught.exception.code,
            "DATASET_CONTRACT_INTEGRITY_FAILURE",
        )

    def test_fixture_files_are_canonical_and_manifest_is_aggregate_only(self) -> None:
        self.assertEqual(
            {path.name for path in FIXTURE_DIR.iterdir()},
            {"manifest.json", "oracle-sidecar.json"},
        )
        manifest_path = FIXTURE_DIR / "manifest.json"
        sidecar_path = FIXTURE_DIR / "oracle-sidecar.json"
        manifest = _read_json(manifest_path)
        sidecar = _read_json(sidecar_path)
        self.assertEqual(
            manifest_path.read_bytes(),
            PREFLIGHT.canonical_json_bytes(manifest),
        )
        self.assertEqual(
            sidecar_path.read_bytes(),
            PREFLIGHT.canonical_json_bytes(sidecar),
        )
        self.assertEqual(
            manifest["oracle_sidecar_sha256"],
            sha256(sidecar_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(manifest["source_class"], "CLEANROOM_SYNTHETIC")
        self.assertTrue(manifest["fictional"])
        self.assertFalse(manifest["derived_from_real"])
        self.assertFalse(manifest["gold_eligible"])
        self.assertFalse(manifest["patch_eligible"])
        manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        for forbidden_key in (
            "requirement_text",
            "reviewer_ref",
            "candidate_ref",
            "plan_unit_ref",
            '"action"',
            '"reviewed"',
            '"overlay"',
            '"target_node_id"',
            '"acceptable_node_ids"',
        ):
            self.assertNotIn(forbidden_key, manifest_text)

    def test_execution_set_is_seven_full_paths_and_one_legal_clarification(self) -> None:
        sidecar = _read_json(FIXTURE_DIR / "oracle-sidecar.json")
        items = sidecar["items"]
        executable = [item for item in items if item["execution_eligible"]]
        reserves = [item for item in items if not item["execution_eligible"]]

        self.assertEqual(len(items), 11)
        self.assertEqual(len(executable), 8)
        self.assertEqual(len(reserves), 3)
        self.assertTrue(all(item["review_status"] == "ACCEPTED" for item in items))
        self.assertTrue(all(item["overlay"] is None for item in reserves))
        self.assertEqual(
            {item["execution_coverage_cell"] for item in executable},
            {f"B{index:02d}" for index in range(1, 9)},
        )
        routes = [item["overlay"]["oracle"]["expected_route"] for item in executable]
        self.assertEqual(routes.count("PROCEED"), 7)
        self.assertEqual(routes.count("CLARIFY"), 1)
        clarification = next(
            item for item in executable
            if item["overlay"]["oracle"]["expected_route"] == "CLARIFY"
        )
        self.assertEqual(clarification["execution_coverage_cell"], "B08")
        self.assertFalse(clarification["overlay"]["oracle"]["retrieval"]["applicable"])
        self.assertFalse(
            clarification["overlay"]["oracle"]["recommendation"]["applicable"]
        )

    def test_long_term_oracles_use_stable_targets_not_temporary_candidate_refs(self) -> None:
        sidecar = _read_json(FIXTURE_DIR / "oracle-sidecar.json")
        candidate_refs = {item["candidate_ref"] for item in sidecar["items"]}
        for item in sidecar["items"]:
            overlay = item["overlay"]
            if overlay is None:
                continue
            oracle = overlay["oracle"]
            targets = set(oracle["retrieval"]["acceptable_node_ids"])
            targets.update(
                outcome["target_node_id"]
                for outcome in oracle["recommendation"]["acceptable_outcomes"]
                if outcome["target_node_id"] is not None
            )
            self.assertTrue(targets.isdisjoint(candidate_refs))
            if oracle["expected_route"] == "PROCEED":
                self.assertEqual(oracle["retrieval"]["top_k"], 8)

    def test_unknown_fields_and_boundary_tampering_fail_closed(self) -> None:
        temporary, fixture_dir = _copy_fixture()
        self.addCleanup(temporary.cleanup)
        manifest_path = fixture_dir / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["unexpected"] = True
        manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir)
        self.assertEqual(caught.exception.code, "DATASET_MANIFEST_FIELDS_INVALID")

        temporary_two, fixture_dir_two = _copy_fixture()
        self.addCleanup(temporary_two.cleanup)
        sidecar = _read_json(fixture_dir_two / "oracle-sidecar.json")
        sidecar["source_class"] = "UNKNOWN"
        _rewrite_sidecar(fixture_dir_two, sidecar)
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_two)
        self.assertEqual(caught.exception.code, "DATASET_BOUNDARY_INVALID")

        temporary_three, fixture_dir_three = _copy_fixture()
        self.addCleanup(temporary_three.cleanup)
        sidecar = _read_json(fixture_dir_three / "oracle-sidecar.json")
        sidecar["unexpected"] = True
        _rewrite_sidecar(fixture_dir_three, sidecar)
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_three)
        self.assertEqual(
            caught.exception.code, "DATASET_SIDECAR_FIELDS_INVALID"
        )

        temporary_four, fixture_dir_four = _copy_fixture()
        self.addCleanup(temporary_four.cleanup)
        manifest_path = fixture_dir_four / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["fictional"] = 1
        manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_four)
        self.assertEqual(caught.exception.code, "DATASET_BOUNDARY_INVALID")

        temporary_five, fixture_dir_five = _copy_fixture()
        self.addCleanup(temporary_five.cleanup)
        sidecar = _read_json(fixture_dir_five / "oracle-sidecar.json")
        sidecar["derived_from_real"] = 0
        _rewrite_sidecar(fixture_dir_five, sidecar)
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_five)
        self.assertEqual(caught.exception.code, "DATASET_BOUNDARY_INVALID")

    def test_review_budget_and_execution_accounting_tampering_fail_closed(self) -> None:
        temporary, fixture_dir = _copy_fixture()
        self.addCleanup(temporary.cleanup)
        manifest_path = fixture_dir / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["human_review_elapsed_minutes"] = 151
        manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir)
        self.assertEqual(
            caught.exception.code, "DATASET_REVIEW_BUDGET_EXCEEDED"
        )

        temporary_exact, fixture_dir_exact = _copy_fixture()
        self.addCleanup(temporary_exact.cleanup)
        sidecar = _read_json(fixture_dir_exact / "oracle-sidecar.json")
        sidecar["human_review_elapsed_minutes"] = 21
        _rewrite_sidecar(fixture_dir_exact, sidecar)
        manifest_path = fixture_dir_exact / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["human_review_elapsed_minutes"] = 21
        manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_exact)
        self.assertEqual(
            caught.exception.code, "DATASET_REVIEW_BUDGET_EXCEEDED"
        )

        temporary_two, fixture_dir_two = _copy_fixture()
        self.addCleanup(temporary_two.cleanup)
        sidecar = _read_json(fixture_dir_two / "oracle-sidecar.json")
        executable = next(
            item for item in sidecar["items"] if item["execution_eligible"]
        )
        executable["overlay"] = None
        _rewrite_sidecar(fixture_dir_two, sidecar)
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_two)
        self.assertEqual(
            caught.exception.code, "DATASET_EXECUTION_ACCOUNTING_INVALID"
        )

        temporary_three, fixture_dir_three = _copy_fixture()
        self.addCleanup(temporary_three.cleanup)
        sidecar = _read_json(fixture_dir_three / "oracle-sidecar.json")
        sidecar["items"][0]["source_coverage_cell"] = "UNREVIEWED_CELL"
        _rewrite_sidecar(fixture_dir_three, sidecar)
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_three)
        self.assertEqual(
            caught.exception.code, "DATASET_EXECUTION_ACCOUNTING_INVALID"
        )

    def test_frozen_source_digests_reject_coordinated_rebinding(self) -> None:
        temporary, fixture_dir = _copy_fixture()
        self.addCleanup(temporary.cleanup)
        sidecar = _read_json(fixture_dir / "oracle-sidecar.json")
        sidecar["source_candidate_batch_sha256"] = "0" * 64
        sidecar["source_review_packet_sha256"] = "1" * 64
        _rewrite_sidecar(fixture_dir, sidecar)
        manifest_path = fixture_dir / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["source_candidate_batch_sha256"] = "0" * 64
        manifest["source_review_packet_sha256"] = "1" * 64
        manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir)
        self.assertEqual(caught.exception.code, "DATASET_SOURCE_BINDING_INVALID")

    def test_frozen_sidecar_digest_rejects_fully_rehashed_review_change(self) -> None:
        temporary, fixture_dir = _copy_fixture()
        self.addCleanup(temporary.cleanup)
        sidecar = _read_json(fixture_dir / "oracle-sidecar.json")
        reviewer_ref = "m4-authorized-reviewer-02"
        sidecar["reviewer_ref"] = reviewer_ref
        for item in sidecar["items"]:
            action = item["action"]
            action["reviewer_ref"] = reviewer_ref
            reviewed = item["reviewed"]
            reviewed["reviewer_ref"] = reviewer_ref
            reviewed["source_action_hash"] = canonical_digest(action)
            reviewed_payload = dict(reviewed)
            reviewed_payload.pop("reviewed_hash")
            reviewed["reviewed_hash"] = canonical_digest(reviewed_payload)
            overlay = item["overlay"]
            if overlay is None:
                continue
            overlay["reviewer_ref"] = reviewer_ref
            overlay["source_reviewed_hash"] = reviewed["reviewed_hash"]
            overlay["source_reviewed_content_hash"] = canonical_digest(
                {
                    "source_reviewed_hash": reviewed["reviewed_hash"],
                    "request": reviewed["request"],
                    "capability_oracle": overlay["oracle"],
                }
            )
            overlay_payload = dict(overlay)
            overlay_payload.pop("overlay_hash")
            overlay["overlay_hash"] = canonical_digest(overlay_payload)
        _rewrite_sidecar(fixture_dir, sidecar)
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir)
        self.assertEqual(caught.exception.code, "DATASET_FIXTURE_SHA_MISMATCH")

    def test_boolean_integer_tampering_fails_closed(self) -> None:
        temporary, fixture_dir = _copy_fixture()
        self.addCleanup(temporary.cleanup)
        sidecar = _read_json(fixture_dir / "oracle-sidecar.json")
        sidecar["dual_review_limit"] = False
        _rewrite_sidecar(fixture_dir, sidecar)
        manifest_path = fixture_dir / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["dual_review_limit"] = False
        manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir)
        self.assertEqual(
            caught.exception.code, "DATASET_REVIEW_BUDGET_EXCEEDED"
        )

        temporary_two, fixture_dir_two = _copy_fixture()
        self.addCleanup(temporary_two.cleanup)
        sidecar = _read_json(fixture_dir_two / "oracle-sidecar.json")
        sidecar["items"][0]["review_round"] = True
        _rewrite_sidecar(fixture_dir_two, sidecar)
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_two)
        self.assertEqual(
            caught.exception.code, "DATASET_EXECUTION_ACCOUNTING_INVALID"
        )

        temporary_three, fixture_dir_three = _copy_fixture()
        self.addCleanup(temporary_three.cleanup)
        manifest_path = fixture_dir_three / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["clarification_count"] = True
        manifest_path.write_bytes(PREFLIGHT.canonical_json_bytes(manifest))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir_three)
        self.assertEqual(
            caught.exception.code, "DATASET_EXECUTION_ACCOUNTING_INVALID"
        )

    def test_sidecar_byte_binding_rejects_unreviewed_change(self) -> None:
        temporary, fixture_dir = _copy_fixture()
        self.addCleanup(temporary.cleanup)
        sidecar_path = fixture_dir / "oracle-sidecar.json"
        sidecar = _read_json(sidecar_path)
        sidecar["items"][0]["finding_codes"] = ["POST_FREEZE_CHANGE"]
        sidecar_path.write_bytes(PREFLIGHT.canonical_json_bytes(sidecar))
        with self.assertRaises(PREFLIGHT.M4BlindDataError) as caught:
            PREFLIGHT.validate_fixture(fixture_dir)
        self.assertEqual(caught.exception.code, "DATASET_FIXTURE_SHA_MISMATCH")

    def test_cli_stdout_is_aggregate_only(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--fixture-dir",
                str(FIXTURE_DIR),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["finding_counts"],
            {"DATASET_CONTRACT_INTEGRITY_FAILURE": 1},
        )
        sidecar = _read_json(FIXTURE_DIR / "oracle-sidecar.json")
        hidden_canaries = {
            sidecar["tree_snapshot_hash"],
            sidecar["scenario_plan_hash"],
            sidecar["items"][0]["action"]["final_request"]["requirement_text"],
            sidecar["items"][0]["candidate_digest"],
        }
        hidden_canaries.update(
            target
            for item in sidecar["items"]
            if item["overlay"] is not None
            for target in item["overlay"]["oracle"]["retrieval"][
                "acceptable_node_ids"
            ]
        )
        for canary in hidden_canaries:
            self.assertNotIn(canary, completed.stdout)
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
