from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_fire_h2_local_embedding_b import (
    build_b_report,
    load_h2_b_sources,
    preflight_h2_b,
)
class H2LocalEmbeddingBRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = load_h2_b_sources()

    def test_preflight_is_aggregate_only_and_does_not_execute_b(self) -> None:
        report = preflight_h2_b(self.sources)
        self.assertEqual(report["status"], "PREFLIGHT_READY")
        self.assertFalse(report["model_called"])
        self.assertFalse(report["formal_b_executed"])
        self.assertEqual(report["scenario_count"], 28)
        self.assertEqual(report["node_count"], 733)
        self.assertEqual(
            report["lexical_baseline_recall_at_8"]["total"], 4
        )
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("source_manifest_hash", serialized)
        self.assertNotIn("source_profile_hash", serialized)
        self.assertNotIn("source_index_hash", serialized)
        self.assertNotIn("data_commit", serialized)

    def test_gate_requires_absolute_and_relative_improvements(self) -> None:
        scored = {
            "recall_at_20": {"hits": 18, "total": 20, "value": 0.9},
            "recall_at_8": {"hits": 16, "total": 20, "value": 0.8},
            "mrr_at_20": 0.775,
            "non_literal_recall_at_20": {"hits": 8, "total": 10, "value": 0.8},
            "hard_negative_top_8": {"hits": 4, "total": 4, "value": 1.0},
            "explicit_empty": {"hits": 4, "total": 4, "value": 1.0},
        }
        report = build_b_report(
            self.sources.lexical_a,
            scored,
            inference_call_count=50,
            lexical_baseline_a_at_8=4,
            lexical_baseline_b_at_8=3,
            runtime={"query_count": 29},
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["failure_codes"], [])
        scored["non_literal_recall_at_20"] = {
            "hits": 7,
            "total": 10,
            "value": 0.7,
        }
        report = build_b_report(
            self.sources.lexical_a,
            scored,
            inference_call_count=50,
            lexical_baseline_a_at_8=4,
            lexical_baseline_b_at_8=3,
            runtime={"query_count": 29},
        )
        self.assertIn("H2_NON_LITERAL_GATE_FAILED", report["failure_codes"])

    def test_lexical_baseline_may_drop_by_one_but_not_two(self) -> None:
        scored = {
            "recall_at_20": {"hits": 18, "total": 20, "value": 0.9},
            "recall_at_8": {"hits": 16, "total": 20, "value": 0.8},
            "mrr_at_20": 0.775,
            "non_literal_recall_at_20": {"hits": 8, "total": 10, "value": 0.8},
            "hard_negative_top_8": {"hits": 4, "total": 4, "value": 1.0},
            "explicit_empty": {"hits": 4, "total": 4, "value": 1.0},
        }
        report = build_b_report(
            self.sources.lexical_a,
            scored,
            inference_call_count=50,
            lexical_baseline_a_at_8=4,
            lexical_baseline_b_at_8=2,
            runtime={"query_count": 29},
        )
        self.assertIn("H2_LEXICAL_BASELINE_REGRESSION", report["failure_codes"])

    def test_cli_preflight_rejects_live_arguments_before_model_load(self) -> None:
        command = [
            sys.executable,
            str(ROOT / "scripts/run_fire_h2_local_embedding_b.py"),
            "--preflight-only",
            "--snapshot-dir",
            "/not/used",
        ]
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(report["error_code"], "H2_B_PREFLIGHT_OUTPUT_FORBIDDEN")
        self.assertFalse(report["model_called"])

    def test_corrupt_a_report_is_rejected(self) -> None:
        from run_fire_h2_local_embedding_b import _valid_a_report

        self.assertFalse(_valid_a_report({}))


if __name__ == "__main__":
    unittest.main()
