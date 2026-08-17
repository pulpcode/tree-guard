from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from treeguard.adapter import adapt_tree_document
from treeguard.navigation_copilot_sealed_validation import SealedScenario

from scripts.navigation_copilot_b03c.author_sealed_data import materialize
from scripts.navigation_copilot_b03c.record_sealed_reviews import record_reviews
from scripts.navigation_copilot_b03c.verify_sealed_phase2a import Phase2AError, verify_and_freeze


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/fictional/navigation_copilot_sealed_v3c_b03c"
AUTHOR = ROOT / "scripts/navigation_copilot_b03c/author_sealed_data.py"
REVIEW = ROOT / "scripts/navigation_copilot_b03c/record_sealed_reviews.py"
VERIFY = ROOT / "scripts/navigation_copilot_b03c/verify_sealed_phase2a.py"


class B03CSealedPhase2ATest(unittest.TestCase):
    def setUp(self) -> None:
        self.blueprint_path = FIXTURE / "blueprint.v1.json"
        self.tree_path = FIXTURE / "tree.json"
        self.candidates_path = FIXTURE / "candidate-scenarios.v2.json"
        self.packet_path = FIXTURE / "review-packet.v1.json"
        self.decisions_path = FIXTURE / "review-decisions.hidden.v1.json"

    def test_authoring_is_deterministic_and_contract_shaped(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_hashes = materialize(Path(first))
            second_hashes = materialize(Path(second))
            self.assertEqual(first_hashes, second_hashes)
            for name in first_hashes:
                self.assertEqual((Path(first) / name).read_bytes(), (Path(second) / name).read_bytes())
        tree = json.loads(self.tree_path.read_bytes())
        imported = adapt_tree_document(tree)
        self.assertTrue(imported.is_valid)
        self.assertEqual(736, imported.observed_node_count)
        self.assertEqual(0, imported.observed_value_count)
        candidates = [SealedScenario.from_dict(item) for item in json.loads(self.candidates_path.read_bytes())]
        self.assertEqual(
            Counter({"LITERAL_UNIQUE": 11, "NONLITERAL_UNIQUE": 12, "STRUCTURAL_INTERFERENCE": 10,
                     "MULTI_ACCEPTABLE": 4, "CLARIFICATION": 7, "WEAK_EVIDENCE": 5, "TARGET_ABSENT": 7}),
            Counter(item.category for item in candidates),
        )
        self.assertEqual(8, sum(item.wrong_context_challenge for item in candidates))
        self.assertEqual(16, sum(item.repeat_challenge for item in candidates))

    def test_sources_are_physically_separated_and_oracle_absent(self) -> None:
        self.assertNotIn("record_sealed_reviews", AUTHOR.read_text())
        self.assertNotIn("import author_sealed_data", REVIEW.read_text())
        self.assertNotIn("import record_sealed_reviews", VERIFY.read_text())
        packet_bytes = self.packet_path.read_bytes()
        candidate_bytes = self.candidates_path.read_bytes()
        for forbidden in (b"reviewed_target_ids", b"compatible_target_ids", b"finding_codes"):
            self.assertNotIn(forbidden, packet_bytes + candidate_bytes)
        self.assertFalse(any(FIXTURE.glob("*oracle*")))

    def test_review_is_bound_to_exact_authoring_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            changed_tree = directory_path / "tree.json"
            changed_tree.write_bytes(self.tree_path.read_bytes() + b" ")
            with self.assertRaisesRegex(RuntimeError, "^DATASET_NONDETERMINISTIC$"):
                record_reviews(
                    changed_tree,
                    self.candidates_path,
                    self.packet_path,
                    directory_path / "decisions.json",
                )

    def test_phase2a_freeze_rebuilds_exact_execution_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            report = verify_and_freeze(
                self.blueprint_path,
                self.tree_path,
                self.candidates_path,
                self.packet_path,
                self.decisions_path,
                directory_path / "scenarios.json",
                directory_path / "preflight.json",
            )
            self.assertEqual("PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW", report["status"])
            self.assertEqual(48, report["execution_scenarios"])
            self.assertEqual(42, report["target_present"])
            self.assertEqual(6, report["target_absent"])
            self.assertEqual(8, report["wrong_context"])
            self.assertEqual(16, report["repeat_subset"])
            self.assertEqual("ABSENT_PHASE2B_NOT_APPROVED", report["oracle_status"])
            self.assertEqual((FIXTURE / "scenarios.v2.json").read_bytes(), (directory_path / "scenarios.json").read_bytes())
            self.assertEqual((FIXTURE / "phase2a-preflight.v1.json").read_bytes(), (directory_path / "preflight.json").read_bytes())

    def _mutated_decision_code(self, mutate) -> str:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            decisions = json.loads(self.decisions_path.read_bytes())
            mutate(decisions)
            decision_path = directory_path / "decisions.json"
            decision_path.write_text(json.dumps(decisions, ensure_ascii=False))
            with self.assertRaises(Phase2AError) as caught:
                verify_and_freeze(
                    self.blueprint_path,
                    self.tree_path,
                    self.candidates_path,
                    self.packet_path,
                    decision_path,
                    directory_path / "scenarios.json",
                    directory_path / "preflight.json",
                )
            return caught.exception.code

    def test_blocking_review_mutations_fail_closed(self) -> None:
        decisions = json.loads(self.decisions_path.read_bytes())
        tree = json.loads(self.tree_path.read_bytes())
        stack = list(tree["map_topology"].values())
        filler_id = ""
        while stack and not filler_id:
            entry = stack.pop()
            if entry["metadata"]["extension"]["dataset_role"] == "filler":
                filler_id = entry["metadata"]["node_id"]
            stack.extend(entry.get("subnodes", {}).values())
        self.assertTrue(filler_id)
        cases = (
            ("source", "DATASET_REVIEW_SOURCE_NOT_INDEPENDENT", lambda doc: doc.__setitem__("producer_module", "author_sealed_data")),
            ("budget", "DATASET_REVIEW_BUDGET_EXCEEDED", lambda doc: doc.__setitem__("elapsed_minutes", 721)),
            ("review sample", "DATASET_REFERENCE_INVALID", lambda doc: doc["reviewed_node_ids"].pop()),
            ("multi missing", "DATASET_TARGET_SET_NOT_EXHAUSTIVE", lambda doc: doc["decisions"][33]["reviewed_target_ids"].pop()),
            ("multi extra", "DATASET_TARGET_SET_NOT_EXHAUSTIVE", lambda doc: doc["decisions"][33]["reviewed_target_ids"].append(doc["decisions"][0]["reviewed_target_ids"][0])),
            ("clarification", "DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT", lambda doc: doc["decisions"][37].__setitem__("contrast_node_ids", doc["decisions"][37]["contrast_node_ids"][:1])),
            ("absence", "DATASET_ORACLE_OVERCLAIM", lambda doc: doc["decisions"][49]["reviewed_target_ids"].append(doc["decisions"][0]["reviewed_target_ids"][0])),
            ("filler", "DATASET_FILLER_TARGETED", lambda doc: (doc["decisions"][0].__setitem__("reviewed_target_ids", [filler_id]), doc["decisions"][0].__setitem__("compatible_target_ids", [filler_id]))),
        )
        for name, expected, mutate in cases:
            with self.subTest(name=name):
                self.assertEqual(expected, self._mutated_decision_code(mutate))


if __name__ == "__main__":
    unittest.main()
