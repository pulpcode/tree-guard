import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from treeguard.adapter import adapt_tree_document
from treeguard.hashing import canonical_digest

from scripts.fire_m5_data_common import (
    MANIFEST_FILE,
    ORACLE_FILE,
    SCENARIO_FILE,
    TREE_FILE,
    M5DataError,
    _candidate_set_for,
    build_codex_silver_review,
    preflight_dataset,
    write_dataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _raw_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rehash_scenarios(dataset_dir: Path, scenarios: dict) -> None:
    payload = dict(scenarios)
    payload.pop("candidate_set_digest", None)
    scenarios["candidate_set_digest"] = canonical_digest(payload)
    _write(dataset_dir / SCENARIO_FILE, scenarios)
    oracle = _read(dataset_dir / ORACLE_FILE)
    oracle["source_candidate_set_digest"] = scenarios["candidate_set_digest"]
    oracle_payload = dict(oracle)
    oracle_payload.pop("oracle_digest", None)
    oracle["oracle_digest"] = canonical_digest(oracle_payload)
    _write(dataset_dir / ORACLE_FILE, oracle)
    manifest = _read(dataset_dir / MANIFEST_FILE)
    manifest["scenario_file_sha256"] = _raw_sha(dataset_dir / SCENARIO_FILE)
    manifest["oracle_file_sha256"] = _raw_sha(dataset_dir / ORACLE_FILE)
    _write(dataset_dir / MANIFEST_FILE, manifest)


def _rehash_oracle(dataset_dir: Path, oracle: dict) -> None:
    payload = dict(oracle)
    payload.pop("oracle_digest", None)
    oracle["oracle_digest"] = canonical_digest(payload)
    _write(dataset_dir / ORACLE_FILE, oracle)
    manifest = _read(dataset_dir / MANIFEST_FILE)
    manifest["oracle_file_sha256"] = _raw_sha(dataset_dir / ORACLE_FILE)
    _write(dataset_dir / MANIFEST_FILE, manifest)


class FireM5AssistedShadowDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.dataset_dir = self.root / "dataset"
        self.manifest = write_dataset(self.dataset_dir)

    def test_generation_is_deterministic_and_preflight_passes(self) -> None:
        other_dir = self.root / "other"
        other_manifest = write_dataset(other_dir)

        self.assertEqual(self.manifest, other_manifest)
        for filename in (MANIFEST_FILE, "tree.json", SCENARIO_FILE, ORACLE_FILE):
            self.assertEqual(
                (self.dataset_dir / filename).read_bytes(),
                (other_dir / filename).read_bytes(),
            )

        report = preflight_dataset(self.dataset_dir)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["node_count"], 1357)
        self.assertEqual(report["value_envelope_count"], 0)
        self.assertEqual(report["candidate_count"], 30)
        self.assertEqual(report["execution_count"], 24)
        self.assertEqual(report["proceed_count"], 18)
        self.assertEqual(report["clarify_count"], 6)
        self.assertEqual(report["covered_execution_branch_count"], 10)
        self.assertEqual(report["maximum_execution_scenarios_per_branch"], 3)
        self.assertEqual(report["retrieval_replay_match_count"], 22)
        self.assertEqual(report["model_projection_leak_count"], 0)
        self.assertFalse(report["model_called"])
        self.assertEqual(
            report["structure_metrics"],
            {
                "numbered_name_count": 0,
                "maximum_depth": 4,
                "maximum_direct_child_count": 10,
                "largest_repeated_suffix_set": 1,
                "largest_repeated_structural_signature": 1,
            },
        )

    def test_dataset_is_unreviewed_and_oracle_is_not_execution_eligible(self) -> None:
        scenarios = _read(self.dataset_dir / SCENARIO_FILE)
        oracle = _read(self.dataset_dir / ORACLE_FILE)

        self.assertEqual(self.manifest["human_review_status"], "NOT_STARTED")
        self.assertFalse(self.manifest["model_exposed"])
        self.assertEqual(oracle["quality_tier"], "PROPOSED")
        self.assertEqual(oracle["review_authority"], "NOT_REVIEWED")
        self.assertFalse(oracle["gate_eligible"])
        self.assertTrue(oracle["model_input_forbidden"])
        self.assertNotIn("oracle", json.dumps(scenarios, ensure_ascii=False).lower())

    def test_codex_review_remains_silver_and_non_authoritative(self) -> None:
        review = build_codex_silver_review(self.dataset_dir)

        self.assertEqual(review["schema_version"], "m5-assisted-shadow-codex-silver-review.v1")
        self.assertEqual(review["quality_tier"], "SILVER")
        self.assertEqual(review["assessment_authority"], "CODEX_ASSISTED")
        self.assertFalse(review["execution_eligible"])
        self.assertFalse(review["gold_eligible"])
        self.assertEqual(review["reviewed_candidate_count"], 30)
        self.assertEqual(review["blocking_finding_count"], 0)

    def test_source_class_tampering_fails_closed(self) -> None:
        manifest = _read(self.dataset_dir / MANIFEST_FILE)
        manifest["derived_from_real"] = True
        _write(self.dataset_dir / MANIFEST_FILE, manifest)

        with self.assertRaises(M5DataError) as caught:
            preflight_dataset(self.dataset_dir)
        self.assertEqual(caught.exception.code, "M5_MANIFEST_POLICY_INVALID")

    def test_scenario_extra_field_is_rejected_after_rehash(self) -> None:
        scenarios = _read(self.dataset_dir / SCENARIO_FILE)
        scenarios["candidates"][0]["request"]["unexpected"] = True
        _rehash_scenarios(self.dataset_dir, scenarios)

        with self.assertRaises(M5DataError) as caught:
            preflight_dataset(self.dataset_dir)
        self.assertEqual(caught.exception.code, "M5_REQUEST_FIELDS_INVALID")

    def test_oracle_extra_field_is_rejected_after_rehash(self) -> None:
        oracle = _read(self.dataset_dir / ORACLE_FILE)
        oracle["items"][0]["unexpected"] = True
        _rehash_oracle(self.dataset_dir, oracle)

        with self.assertRaises(M5DataError) as caught:
            preflight_dataset(self.dataset_dir)
        self.assertEqual(caught.exception.code, "M5_ORACLE_ITEM_FIELDS_INVALID")

    def test_semantic_target_outside_runtime_top_eight_is_rejected(self) -> None:
        scenarios = _read(self.dataset_dir / SCENARIO_FILE)
        oracle = _read(self.dataset_dir / ORACLE_FILE)
        tree = adapt_tree_document(_read(self.dataset_dir / TREE_FILE)).tree
        scenario_index = next(
            index
            for index, item in enumerate(scenarios["candidates"])
            if item["coverage_cell"] == "P04"
        )
        candidate = scenarios["candidates"][scenario_index]
        oracle_item = oracle["items"][scenario_index]
        candidate_set = _candidate_set_for(
            candidate["request"], oracle_item["retrieval_seed"], tree
        )
        invisible_target = candidate_set.candidates[8].node_id
        outcomes = oracle_item["capability_oracle"]["recommendation"][
            "acceptable_outcomes"
        ]
        outcome = dict(outcomes[0])
        outcome["target_node_id"] = invisible_target
        oracle_item["capability_oracle"]["recommendation"][
            "acceptable_outcomes"
        ] = [outcome]
        retrieval = oracle_item["capability_oracle"]["retrieval"]
        retrieval["acceptable_node_ids"] = [invisible_target]
        retrieval["top_k"] = 9
        oracle_item["evidence_node_ids"] = [invisible_target]
        _rehash_oracle(self.dataset_dir, oracle)

        with self.assertRaises(M5DataError) as caught:
            preflight_dataset(self.dataset_dir)
        self.assertEqual(caught.exception.code, "M5_SEMANTIC_TARGET_NOT_PROJECTABLE")

    def test_branch_quota_tampering_is_rejected_after_rehash(self) -> None:
        scenarios = _read(self.dataset_dir / SCENARIO_FILE)
        execution = [
            item for item in scenarios["candidates"]
            if item["selection_status"] == "EXECUTION"
        ]
        for item in execution[:5]:
            item["primary_branch_ref"] = execution[0]["primary_branch_ref"]
            item["primary_branch_name"] = execution[0]["primary_branch_name"]
        _rehash_scenarios(self.dataset_dir, scenarios)

        with self.assertRaises(M5DataError) as caught:
            preflight_dataset(self.dataset_dir)
        self.assertEqual(caught.exception.code, "M5_COVERAGE_POLICY_INVALID")

    def test_strict_parser_rejects_duplicate_members(self) -> None:
        path = self.dataset_dir / SCENARIO_FILE
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("{", '{"schema_version":"duplicate",', 1), encoding="utf-8")

        with self.assertRaises(M5DataError) as caught:
            preflight_dataset(self.dataset_dir)
        self.assertEqual(caught.exception.code, "M5_JSON_INVALID")

    def test_private_html_contains_review_controls_without_stable_node_ids(self) -> None:
        output = self.root / "review.html"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(PROJECT_ROOT / "scripts" / "render_fire_m5_review_html.py"),
                "--dataset-dir",
                str(self.dataset_dir),
                "--output",
                str(output),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("M5 未见资格候选人工审核", rendered)
        self.assertIn("导出审核 JSON", rendered)
        self.assertNotIn("M5N0001", rendered)
        self.assertNotIn("oracle_digest", rendered)

    def test_generator_refuses_overwrite(self) -> None:
        with self.assertRaises(M5DataError) as caught:
            write_dataset(self.dataset_dir)
        self.assertEqual(caught.exception.code, "M5_OUTPUT_ALREADY_EXISTS")


if __name__ == "__main__":
    unittest.main()
