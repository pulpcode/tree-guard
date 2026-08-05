from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from treeguard.adapter import adapt_tree_document
from treeguard.hashing import canonical_digest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/fictional/fire_h1_hybrid_calibration"
SOURCE_FIXTURE = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow"
GENERATOR_PATH = ROOT / "scripts/generate_fire_h1_hybrid_calibration.py"
SPEC = importlib.util.spec_from_file_location("fire_h1_hybrid_calibration", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def _load(name: str):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


class FireH1HybridCalibrationDataTests(unittest.TestCase):
    def test_materialized_fixture_matches_generator_bytes(self) -> None:
        expected = GENERATOR.build_bundle()
        self.assertEqual({path.name for path in FIXTURE.iterdir()}, set(expected))
        for name, payload in expected.items():
            with self.subTest(name=name):
                self.assertEqual((FIXTURE / name).read_bytes(), payload)
        self.assertEqual(GENERATOR.validate_materialized(FIXTURE)["scenario_count"], 24)

    def test_manifest_binds_cleanroom_source_and_exact_counts(self) -> None:
        manifest = _load("manifest.json")
        source_manifest = json.loads(
            (SOURCE_FIXTURE / "manifest.json").read_text(encoding="utf-8")
        )
        source_bytes = (SOURCE_FIXTURE / "tree.json").read_bytes()
        imported = adapt_tree_document(json.loads(source_bytes), source_hint="h1-test")
        self.assertTrue(imported.is_valid)
        assert imported.tree is not None
        self.assertEqual(source_manifest["source_class"], "CLEANROOM_SYNTHETIC")
        self.assertIs(source_manifest["fictional"], True)
        self.assertIs(source_manifest["derived_from_real"], False)
        self.assertEqual(manifest["source_class"], "CLEANROOM_SYNTHETIC")
        self.assertIs(manifest["fictional"], True)
        self.assertIs(manifest["derived_from_real"], False)
        self.assertIs(manifest["gold_eligible"], False)
        self.assertIs(manifest["patch_eligible"], False)
        self.assertEqual(manifest["scenario_count"], 24)
        self.assertEqual(manifest["positive_count"], 16)
        self.assertEqual(manifest["hard_negative_count"], 4)
        self.assertEqual(manifest["explicit_empty_count"], 4)
        self.assertEqual(manifest["node_count"], 1357)
        self.assertEqual(manifest["value_envelope_count"], 0)
        self.assertEqual(manifest["source_tree_canonical_digest"], imported.tree.snapshot_hash)
        self.assertEqual(manifest["source_tree_file_sha256"], hashlib.sha256(source_bytes).hexdigest())
        for file_key, hash_key in (
            ("scenario_file", "scenario_file_sha256"),
            ("oracle_file", "oracle_file_sha256"),
        ):
            self.assertEqual(
                manifest[hash_key], hashlib.sha256((FIXTURE / manifest[file_key]).read_bytes()).hexdigest()
            )

    def test_scenarios_have_fixed_quota_and_source_bound_silver_roles(self) -> None:
        payload = _load("scenarios.json")
        digest = payload.pop("scenario_digest")
        self.assertEqual(digest, canonical_digest(payload))
        scenarios = payload["scenarios"]
        self.assertEqual([item["scenario_ref"] for item in scenarios], [f"H1S{i:03d}" for i in range(1, 25)])
        self.assertEqual(
            Counter(item["primary_category"] for item in scenarios),
            Counter(GENERATOR.CATEGORY_COUNTS),
        )
        self.assertEqual(len({item["request"]["requirement_text"] for item in scenarios}), 24)
        for scenario in scenarios:
            text = scenario["request"]["requirement_text"]
            roles = scenario["silver_roles"]
            with self.subTest(scenario_ref=scenario["scenario_ref"]):
                self.assertEqual(roles, sorted(roles, key=lambda item: (item["start"], item["end"], item["role"])))
                self.assertEqual(sum(item["role"] == "TARGET" for item in roles), 1)
                self.assertTrue(all(item["role"] in {"TARGET", "SCOPE", "EXCLUSION"} for item in roles))
                self.assertTrue(all(text[item["start"]:item["end"]] == item["text"] for item in roles))
                self.assertNotIn("M5N", text)

    def test_oracle_is_local_silver_and_category_bindings_are_exact(self) -> None:
        scenarios = {item["scenario_ref"]: item for item in _load("scenarios.json")["scenarios"]}
        payload = _load("oracle-sidecar.json")
        digest = payload.pop("oracle_digest")
        self.assertEqual(digest, canonical_digest(payload))
        self.assertEqual(payload["quality_tier"], "CODEX_SILVER_DEVELOPMENT")
        self.assertIs(payload["gold_eligible"], False)
        self.assertIs(payload["patch_eligible"], False)
        self.assertIs(payload["model_input_forbidden"], True)
        imported = adapt_tree_document(
            json.loads((SOURCE_FIXTURE / "tree.json").read_bytes()), source_hint="h1-oracle-test"
        )
        assert imported.tree is not None
        node_ids = {node.node_id for node in imported.tree.nodes}
        self.assertEqual(len(payload["entries"]), 24)
        for entry in payload["entries"]:
            category = entry["primary_category"]
            accepted = set(entry["acceptable_node_ids"])
            excluded = set(entry["excluded_node_ids"])
            with self.subTest(scenario_ref=entry["scenario_ref"]):
                self.assertEqual(category, scenarios[entry["scenario_ref"]]["primary_category"])
                self.assertTrue((accepted | excluded) <= node_ids)
                self.assertFalse(accepted & excluded)
                self.assertEqual(bool(accepted), category in GENERATOR.POSITIVE_CATEGORIES)
                self.assertEqual(bool(excluded) and not accepted, category == "EXCLUSION_HARD_NEGATIVE")
                if category == "EXPLICIT_EMPTY":
                    self.assertFalse(accepted | excluded)

    def test_materialized_validation_rejects_byte_or_file_set_tampering(self) -> None:
        expected = GENERATOR.build_bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in expected.items():
                (root / name).write_bytes(payload)
            changed = bytearray(expected["manifest.json"])
            changed[-2] = ord(" ")
            (root / "manifest.json").write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "materialized bytes are invalid"):
                GENERATOR.validate_materialized(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in expected.items():
                (root / name).write_bytes(payload)
            (root / "unexpected.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "materialized file set is invalid"):
                GENERATOR.validate_materialized(root)

    def test_builder_is_deterministic_and_detached(self) -> None:
        first = GENERATOR.build_bundle()
        second = GENERATOR.build_bundle()
        self.assertEqual(first, second)
        mutated = copy.deepcopy(first)
        mutated["manifest.json"] = b"changed"
        self.assertEqual(GENERATOR.build_bundle(), second)


if __name__ == "__main__":
    unittest.main()
