from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.generate_fire_m49_sealed_data import build_payloads, write_payloads
from scripts.preflight_fire_m49_sealed_data import PreflightFailure, run_preflight, validate_payloads
from scripts.promote_fire_m49_sealed_data import (
    FIXTURE_DIR,
    PromotionError,
    promote,
    validate_fixture,
)
from scripts.review_fire_m49_sealed_data import build_review, promotion_readiness
from treeguard.adapter import adapt_tree_document
from treeguard.hashing import canonical_digest
from treeguard.private_io import write_private_json
from treeguard.scenario_capability_validation import CapabilityOracle


class FireM49SealedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payloads = build_payloads()

    def test_generation_is_deterministic(self) -> None:
        self.assertEqual(self.payloads, build_payloads())

    def test_generated_tree_is_valid_and_production_shaped(self) -> None:
        result = adapt_tree_document(self.payloads["tree.json"])
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.tree)
        self.assertEqual(1_453, len(result.tree.nodes))
        self.assertEqual(0, result.observed_value_count)

    def test_all_oracles_use_typed_capability_contract(self) -> None:
        items = self.payloads["oracle-sidecar.json"]["items"]
        self.assertEqual(30, len(items))
        for item in items:
            self.assertEqual(
                item["oracle"],
                CapabilityOracle.from_dict(item["oracle"]).to_dict(),
            )

    def test_private_staging_round_trip_passes_preflight(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-test-") as temp_dir:
            output = Path(temp_dir) / "candidate"
            write_payloads(output)
            report = run_preflight(output)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(216, report["curated_core_count"])
        self.assertEqual(0, report["stress_filler_count"])

    def test_silver_review_is_source_bound_and_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-review-") as temp_dir:
            output = Path(temp_dir) / "candidate"
            write_payloads(output)
            silver, critic = build_review(output)
        self.assertEqual("SILVER_ACCEPTED", silver["status"])
        self.assertEqual(30, silver["accepted_count"])
        self.assertFalse(silver["reviewer_independence"])
        self.assertFalse(silver["gold_eligible"])
        self.assertFalse(silver["gate_eligible"])
        self.assertFalse(silver["execution_eligible"])
        self.assertEqual("PASS", critic["status"])
        self.assertEqual(4, critic["final_review_round"])
        readiness = promotion_readiness(silver, critic)
        self.assertEqual("READY_FOR_EXPLICIT_PROMOTION_REVIEW", readiness["status"])
        self.assertFalse(readiness["explicit_promotion_approval"])

    def test_fixture_promotion_is_atomic_and_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-promote-") as temp_dir:
            root = Path(temp_dir)
            staging = root / "staging"
            fixture = root / "fixture"
            self._write_reviewed_staging(staging)
            report = promote(staging, fixture)
            self.assertEqual("PASS", report["status"])
            self.assertFalse(report["runtime_registered"])
            with self.assertRaises(PromotionError):
                promote(staging, fixture)

    def test_promoted_fixture_matches_frozen_sources(self) -> None:
        report = validate_fixture(FIXTURE_DIR)
        self.assertEqual("PASS", report["status"])
        fixture_files = {
            "tree.json": "tree.json",
            "scenario-candidates.json": "scenario-candidates.json",
            "oracle-sidecar.json": "oracle-sidecar.json",
        }
        for fixture_name, source_name in fixture_files.items():
            self.assertEqual(
                json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")),
                self.payloads[source_name],
            )

    def test_promoted_fixture_boundary_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-tamper-") as temp_dir:
            fixture = Path(temp_dir) / "fixture"
            shutil.copytree(FIXTURE_DIR, fixture)
            manifest_path = fixture / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["gate_eligible"] = True
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(PromotionError):
                validate_fixture(fixture)

    def test_promoted_fixture_rejects_rehashed_scenario_tampering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="treeguard-m49-rehash-") as temp_dir:
            fixture = Path(temp_dir) / "fixture"
            shutil.copytree(FIXTURE_DIR, fixture)
            scenario_path = fixture / "scenario-candidates.json"
            scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
            item = scenarios["items"][0]
            item["request"]["requirement_text"] = "完全不同的虚构需求"
            item["candidate_digest"] = canonical_digest(
                {key: value for key, value in item.items() if key != "candidate_digest"}
            )
            scenario_path.write_text(
                json.dumps(scenarios, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(PromotionError) as caught:
                validate_fixture(fixture)
            self.assertEqual(
                "FIXTURE_GENERATOR_REPLAY_MISMATCH",
                str(caught.exception),
            )

    @staticmethod
    def _write_reviewed_staging(staging: Path) -> None:
        write_payloads(staging)
        run_preflight(staging, write_report=True)
        silver, critic = build_review(staging)
        if not write_private_json(staging / "silver-review.json", silver):
            raise RuntimeError("unable to write test Silver review")
        if not write_private_json(staging / "critic-report.json", critic):
            raise RuntimeError("unable to write test critic report")
        if not write_private_json(
            staging / "promotion-readiness.json",
            promotion_readiness(silver, critic),
        ):
            raise RuntimeError("unable to write test promotion readiness")

    def test_source_policy_tamper_is_rejected(self) -> None:
        payloads = copy.deepcopy(self.payloads)
        payloads["manifest.json"]["derived_from_real"] = True
        with self.assertRaises(PreflightFailure):
            validate_payloads(payloads)

    def test_bool_as_int_count_tamper_is_rejected(self) -> None:
        payloads = copy.deepcopy(self.payloads)
        payloads["manifest.json"]["node_count"] = True
        with self.assertRaises(PreflightFailure):
            validate_payloads(payloads)

    def test_tree_digest_tamper_is_rejected(self) -> None:
        payloads = copy.deepcopy(self.payloads)
        payloads["manifest.json"]["tree_digest"] = "0" * 64
        with self.assertRaises(PreflightFailure):
            validate_payloads(payloads)

    def test_oracle_reference_tamper_is_rejected(self) -> None:
        payloads = copy.deepcopy(self.payloads)
        payloads["oracle-sidecar.json"]["items"][0]["scenario_ref"] = "P99"
        with self.assertRaises(PreflightFailure):
            validate_payloads(payloads)

    def test_cartesian_policy_tamper_is_rejected(self) -> None:
        payloads = copy.deepcopy(self.payloads)
        payloads["semantic-blueprint.json"]["construction_policy"] = "CARTESIAN_PRODUCT"
        with self.assertRaises(PreflightFailure):
            validate_payloads(payloads)

    def test_unreviewed_execution_gate_tamper_is_rejected(self) -> None:
        payloads = copy.deepcopy(self.payloads)
        payloads["scenario-candidates.json"]["items"][0]["execution_eligible"] = True
        with self.assertRaises(PreflightFailure):
            validate_payloads(payloads)

    def test_public_candidate_batch_contains_no_oracle_targets(self) -> None:
        public_text = json.dumps(
            self.payloads["scenario-candidates.json"],
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertNotIn("acceptable_node_ids", public_text)
        self.assertNotIn('"oracle"', public_text)

    def test_top_k_challenges_bind_exact_non_first_rank(self) -> None:
        items = {
            item["scenario_ref"]: item
            for item in self.payloads["oracle-sidecar.json"]["items"]
        }
        for ref, expected_rank in (("P09", 2), ("P10", 2)):
            ranks = items[ref]["deterministic_preview"]["oracle_target_ranks"]
            self.assertEqual(expected_rank, max(ranks.values()))


if __name__ == "__main__":
    unittest.main()
