from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from generate_fire_h2_local_embedding_calibration import (  # noqa: E402
    freeze_dataset,
    generate_candidates,
)
from preflight_fire_h2_local_embedding_calibration import (  # noqa: E402
    H2PreflightError,
    validate_dataset,
)


class H2LocalEmbeddingPreflightTest(unittest.TestCase):
    def _dataset(self, root: Path) -> Path:
        target = root / "dataset"
        generate_candidates(target)
        freeze_dataset(target)
        return target

    def test_frozen_dataset_passes_without_oracle_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = self._dataset(Path(tmp))
            report = validate_dataset(dataset)
            self.assertTrue(report["valid"])
            self.assertEqual(report["tree_node_count"], 733)
            self.assertEqual(report["value_envelope_count"], 0)
            self.assertEqual(report["candidate_count"], 36)
            self.assertEqual(report["execution_count"], 28)
            self.assertFalse(report["embedding_used"])
            self.assertEqual(report["a_baseline_status"], "NOT_RUN")
            public = (
                (dataset / "scenario-candidates.v1.json").read_text(encoding="utf-8")
                + (dataset / "scenarios.v1.json").read_text(encoding="utf-8")
            )
            for forbidden in ("target_node_id", "excluded_node_ids", "expected_empty_status"):
                self.assertNotIn(forbidden, public)
            candidate_oracle = json.loads(
                (dataset / "candidate-oracle-sidecar.v1.json").read_text(encoding="utf-8")
            )
            for entry in candidate_oracle["entries"]:
                hidden_values = (
                    [entry["target_node_id"]]
                    if "target_node_id" in entry
                    else entry.get("excluded_node_ids", [entry.get("expected_empty_status")])
                )
                for hidden_value in hidden_values:
                    self.assertNotIn(hidden_value, public)

    def test_candidate_count_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = self._dataset(Path(tmp))
            path = dataset / "scenario-candidates.v1.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["candidate_count"] = 35
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(H2PreflightError, "H2_PREFLIGHT_HASH_INVALID"):
                validate_dataset(dataset)

    def test_value_envelope_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = self._dataset(Path(tmp))
            path = dataset / "tree.v1.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            root = next(iter(payload["map_topology"].values()))
            root["value"] = {"metadata": {}}
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(
                H2PreflightError, "H2_PREFLIGHT_VALUE_ENVELOPE_PRESENT"
            ):
                validate_dataset(dataset)


if __name__ == "__main__":
    unittest.main()
