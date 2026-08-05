from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from generate_fire_h2_local_embedding_calibration import (  # noqa: E402
    CANDIDATE_COUNTS,
    EXECUTION_COUNTS,
    H2DataError,
    NON_LITERAL_EXECUTION_COUNTS,
    build_candidate_artifacts,
    build_frozen_artifacts,
    build_review,
    freeze_dataset,
    generate_candidates,
)


class H2LocalEmbeddingGeneratorTest(unittest.TestCase):
    def test_candidate_generation_is_deterministic_and_exact(self) -> None:
        first = build_candidate_artifacts()
        second = build_candidate_artifacts()
        self.assertEqual(first, second)
        candidates = first["scenario-candidates.v1.json"]
        self.assertEqual(candidates["candidate_count"], 36)
        self.assertEqual(candidates["category_counts"], CANDIDATE_COUNTS)
        self.assertEqual(
            dict(Counter(item["category"] for item in candidates["candidates"])),
            CANDIDATE_COUNTS,
        )
        self.assertNotIn('"value":', json.dumps(first["tree.v1.json"], ensure_ascii=False))

    def test_freeze_selects_exact_execution_quotas(self) -> None:
        frozen = build_frozen_artifacts(build_review())
        scenarios = frozen["scenarios.v1.json"]
        self.assertEqual(scenarios["execution_count"], 28)
        self.assertEqual(scenarios["category_counts"], EXECUTION_COUNTS)
        self.assertEqual(
            scenarios["non_literal_subtype_counts"],
            NON_LITERAL_EXECUTION_COUNTS,
        )
        review = frozen["silver-review.v1.json"]
        self.assertEqual(review["review_status"], "CODEX_SILVER_REVIEWED")
        self.assertFalse(review["gold_eligible"])
        self.assertFalse(review["production_qualification"])
        self.assertFalse(review["patch_eligible"])
        self.assertEqual(frozen["manifest.v1.json"]["a_baseline_status"], "NOT_RUN")

    def test_rejection_that_exhausts_a_quota_stops_without_replacement(self) -> None:
        review = build_review({"H2C-001": "REJECT", "H2C-002": "REJECT"})
        with self.assertRaisesRegex(H2DataError, "H2_SILVER_QUOTA_INSUFFICIENT"):
            build_frozen_artifacts(review)

    def test_two_phase_files_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = Path(first_tmp) / "dataset"
            second = Path(second_tmp) / "dataset"
            for target in (first, second):
                generate_candidates(target)
                freeze_dataset(target)
            first_files = {path.name: path.read_bytes() for path in first.iterdir()}
            second_files = {path.name: path.read_bytes() for path in second.iterdir()}
            self.assertEqual(first_files, second_files)


if __name__ == "__main__":
    unittest.main()
