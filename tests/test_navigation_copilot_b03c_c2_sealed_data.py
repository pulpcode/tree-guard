from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from treeguard.adapter import adapt_tree_document
from treeguard.navigation_copilot_sealed_validation import SealedScenario

from scripts.navigation_copilot_b03c_c2.author_sealed_data import materialize
from scripts.navigation_copilot_b03c_c2.record_sealed_reviews import record_reviews
from scripts.navigation_copilot_b03c_c2.verify_sealed_phase2a import (
    C1_CANARIES,
    Phase2AError,
    verify_and_freeze,
)
from scripts.navigation_copilot_b03c_c2.verify_sealed_phase2b import (
    DATA_COMMIT,
    Phase2BError,
    freeze_phase2b,
    reviewed_bytes_digest,
)


ROOT = Path(__file__).resolve().parents[1]
C1 = ROOT / "tests/fixtures/fictional/navigation_copilot_sealed_v3c_b03c"
C2 = ROOT / "tests/fixtures/fictional/navigation_copilot_sealed_v3c_b03c_c2"
AUTHOR = ROOT / "scripts/navigation_copilot_b03c_c2/author_sealed_data.py"
REVIEW = ROOT / "scripts/navigation_copilot_b03c_c2/record_sealed_reviews.py"
VERIFY = ROOT / "scripts/navigation_copilot_b03c_c2/verify_sealed_phase2a.py"


class B03C2SealedPhase2ATest(unittest.TestCase):
    def setUp(self) -> None:
        self.blueprint = C2 / "blueprint.v1.json"
        self.tree = C2 / "tree.json"
        self.candidates = C2 / "candidate-scenarios.v2.json"
        self.packet = C2 / "review-packet.v1.json"
        self.decisions = C2 / "review-decisions.hidden.v1.json"

    def _copy_phase2a_sources(self, destination: Path) -> Path:
        destination.mkdir()
        for name in (
            "blueprint.v1.json",
            "tree.json",
            "candidate-scenarios.v2.json",
            "review-packet.v1.json",
            "review-decisions.hidden.v1.json",
            "scenarios.v2.json",
            "phase2a-preflight.v1.json",
        ):
            shutil.copyfile(C2 / name, destination / name)
        return destination

    def _verify(
        self,
        output: Path,
        *,
        c1: Path = C1,
        decisions: Path | None = None,
        source: Path = C2,
    ):
        return verify_and_freeze(
            c1,
            source / "blueprint.v1.json",
            source / "tree.json",
            source / "candidate-scenarios.v2.json",
            source / "review-packet.v1.json",
            decisions or source / "review-decisions.hidden.v1.json",
            output / "scenarios.json",
            output / "preflight.json",
        )

    def test_authoring_is_deterministic_and_reuses_only_tree_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = Path(first)
            second_path = Path(second)
            self.assertEqual(materialize(C1, first_path), materialize(C1, second_path))
            for name in ("blueprint.v1.json", "tree.json", "candidate-scenarios.v2.json", "review-packet.v1.json"):
                self.assertEqual((first_path / name).read_bytes(), (second_path / name).read_bytes())
        self.assertEqual((C1 / "tree.json").read_bytes(), self.tree.read_bytes())
        self.assertNotEqual((C1 / "candidate-scenarios.v2.json").read_bytes(), self.candidates.read_bytes())
        imported = adapt_tree_document(json.loads(self.tree.read_bytes()))
        self.assertTrue(imported.is_valid)
        self.assertEqual((736, 0), (imported.observed_node_count, imported.observed_value_count))
        scenarios = [SealedScenario.from_dict(item) for item in json.loads(self.candidates.read_bytes())]
        self.assertEqual([f"b03c2:{index:03d}" for index in range(1, 57)], [item.scenario_ref for item in scenarios])
        self.assertEqual(
            Counter({"LITERAL_UNIQUE": 11, "NONLITERAL_UNIQUE": 12, "STRUCTURAL_INTERFERENCE": 10,
                     "MULTI_ACCEPTABLE": 4, "CLARIFICATION": 7, "WEAK_EVIDENCE": 5, "TARGET_ABSENT": 7}),
            Counter(item.category for item in scenarios),
        )

    def test_c1_rejection_evidence_remains_byte_identical(self) -> None:
        import hashlib

        for name, expected in C1_CANARIES.items():
            with self.subTest(name=name):
                self.assertEqual(expected, hashlib.sha256((C1 / name).read_bytes()).hexdigest())

    def test_sources_are_separated_and_phase2b_remains_unexecuted(self) -> None:
        self.assertNotIn("record_sealed_reviews", AUTHOR.read_text())
        self.assertNotIn("import author_sealed_data", REVIEW.read_text())
        self.assertNotIn("import record_sealed_reviews", VERIFY.read_text())
        public_bytes = self.candidates.read_bytes() + self.packet.read_bytes()
        for forbidden in (b"reviewed_target_ids", b"compatible_target_ids", b"evidence_gap", b"finding_codes"):
            self.assertNotIn(forbidden, public_bytes)
        self.assertTrue((C2 / "hidden-oracle.v2.json").is_file())
        self.assertTrue((C2 / "freeze-report.v1.json").is_file())
        self.assertFalse(any(C2.glob("*execution*manifest*")))
        self.assertFalse(any(C2.glob("*model*response*")))

    def test_review_is_bound_to_exact_c2_and_prior_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "tree.json"
            changed.write_bytes(self.tree.read_bytes() + b" ")
            with self.assertRaisesRegex(RuntimeError, "^DATASET_NONDETERMINISTIC$"):
                record_reviews(
                    changed,
                    self.candidates,
                    self.packet,
                    C1 / "review-decisions.hidden.v1.json",
                    Path(directory) / "decisions.json",
                )

    def test_all_weak_evidence_has_unique_reviewed_target_and_gap(self) -> None:
        candidates = {
            item["scenario_ref"]: item
            for item in json.loads(self.candidates.read_bytes())
        }
        decisions = json.loads(self.decisions.read_bytes())
        weak = [
            item for item in decisions["decisions"]
            if candidates[item["scenario_ref"]]["category"] == "WEAK_EVIDENCE"
        ]
        self.assertEqual(5, len(weak))
        for item in weak:
            with self.subTest(ref=item["scenario_ref"]):
                self.assertEqual(1, len(item["reviewed_target_ids"]))
                self.assertEqual(item["reviewed_target_ids"], item["compatible_target_ids"])
                self.assertGreaterEqual(len(item["evidence_gap"]), 20)
        self.assertTrue(set(item["scenario_ref"] for item in weak[:4]).issubset(decisions["random_recheck_scenario_refs"]))

    def test_phase2a_freeze_is_exact_and_oracle_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as source_directory:
            output = Path(directory)
            source = self._copy_phase2a_sources(Path(source_directory) / "phase2a")
            report = self._verify(output, source=source)
            self.assertEqual("C2_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW", report["status"])
            self.assertEqual((56, 48), (report["candidates"], report["execution_scenarios"]))
            self.assertEqual((42, 6), (report["target_present"], report["target_absent"]))
            self.assertEqual((8, 16), (report["wrong_context"], report["repeat_subset"]))
            self.assertEqual((5, 4), (report["weak_candidates_with_unique_target"], report["weak_execution_with_unique_target"]))
            self.assertEqual("ABSENT_PHASE2B_NOT_APPROVED", report["oracle_status"])
            self.assertEqual((C2 / "scenarios.v2.json").read_bytes(), (output / "scenarios.json").read_bytes())
            self.assertEqual((C2 / "phase2a-preflight.v1.json").read_bytes(), (output / "preflight.json").read_bytes())

    def test_empty_weak_target_fails_with_specific_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as source_directory:
            root = Path(directory)
            source = self._copy_phase2a_sources(Path(source_directory) / "phase2a")
            payload = json.loads((source / "review-decisions.hidden.v1.json").read_bytes())
            weak = payload["decisions"][44]
            weak["reviewed_target_ids"] = []
            weak["compatible_target_ids"] = []
            changed = root / "decisions.json"
            changed.write_text(json.dumps(payload, ensure_ascii=False))
            with self.assertRaises(Phase2AError) as caught:
                self._verify(root, decisions=changed, source=source)
            self.assertEqual("DATASET_WEAK_EVIDENCE_TARGET_UNBOUND", caught.exception.code)

    def test_oracle_leak_and_c1_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "c2"
            copied.mkdir()
            for source in C2.iterdir():
                shutil.copyfile(source, copied / source.name)
            (copied / "hidden-oracle.json").write_text("[]")
            with self.assertRaises(Phase2AError) as caught:
                verify_and_freeze(
                    C1,
                    copied / "blueprint.v1.json",
                    copied / "tree.json",
                    copied / "candidate-scenarios.v2.json",
                    copied / "review-packet.v1.json",
                    copied / "review-decisions.hidden.v1.json",
                    copied / "out-scenarios.json",
                    copied / "out-preflight.json",
                )
            self.assertEqual("DATASET_ORACLE_OVERCLAIM", caught.exception.code)
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as source_directory:
            changed_c1 = Path(directory)
            for name in C1_CANARIES:
                shutil.copyfile(C1 / name, changed_c1 / name)
            (changed_c1 / "tree.json").write_bytes((changed_c1 / "tree.json").read_bytes() + b" ")
            source = self._copy_phase2a_sources(Path(source_directory) / "phase2a")
            with tempfile.TemporaryDirectory() as output:
                with self.assertRaises(Phase2AError) as caught:
                    self._verify(Path(output), c1=changed_c1, source=source)
            self.assertEqual("DATASET_C1_SOURCE_DRIFT", caught.exception.code)


class B03C2SealedPhase2BTest(unittest.TestCase):
    def _freeze(self, source: Path, oracle: Path, report: Path):
        return freeze_phase2b(source, oracle, report)

    def test_phase2b_freeze_is_deterministic_and_exact(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_source = Path(first) / "fixture"
            second_source = Path(second) / "fixture"
            shutil.copytree(C2, first_source)
            shutil.copytree(C2, second_source)
            first_report = self._freeze(first_source, first_source / "hidden-oracle.v2.json", first_source / "freeze-report.v1.json")
            second_report = self._freeze(second_source, second_source / "hidden-oracle.v2.json", second_source / "freeze-report.v1.json")
            self.assertEqual(first_report, second_report)
            self.assertEqual(DATA_COMMIT, first_report["data_commit"])
            self.assertEqual((48, 48), (first_report["scenario_count"], first_report["oracle_count"]))
            self.assertEqual((42, 6, 4), (first_report["target_present"], first_report["target_absent"], first_report["weak_evidence"]))
            self.assertEqual("ABSENT_NOT_APPROVED", first_report["execution_manifest_status"])
            self.assertEqual("NOT_RUN", first_report["model_execution_status"])
            self.assertEqual(
                (first_source / "hidden-oracle.v2.json").read_bytes(),
                (second_source / "hidden-oracle.v2.json").read_bytes(),
            )

    def test_oracles_follow_category_contract_and_source_binding(self) -> None:
        from treeguard.json_utils import strict_json_loads
        from treeguard.navigation_copilot_sealed_validation import SealedCaseOracle

        scenarios = [SealedScenario.from_dict(item) for item in strict_json_loads((C2 / "scenarios.v2.json").read_bytes())]
        decisions = {
            item["scenario_ref"]: item
            for item in strict_json_loads((C2 / "review-decisions.hidden.v1.json").read_bytes())["decisions"]
        }
        oracles = [SealedCaseOracle.from_dict(item) for item in strict_json_loads((C2 / "hidden-oracle.v2.json").read_bytes())]
        self.assertEqual([item.scenario_ref for item in scenarios], [item.scenario_ref for item in oracles])
        for scenario, oracle in zip(scenarios, oracles, strict=True):
            with self.subTest(ref=scenario.scenario_ref):
                self.assertEqual(reviewed_bytes_digest((C2 / "tree.json").read_bytes(), scenario, decisions[scenario.scenario_ref]), oracle.reviewed_bytes_digest)
                if scenario.category == "WEAK_EVIDENCE":
                    self.assertEqual(("NEED_EVIDENCE",), oracle.acceptable_policy_statuses)
                    self.assertEqual(("EXIT", None, "PRESENT_NOT_FOUND"), (
                        oracle.acceptable_terminals[0].action,
                        oracle.acceptable_terminals[0].target_node_id,
                        oracle.acceptable_terminals[0].target_disposition,
                    ))
                elif scenario.category == "CLARIFICATION":
                    self.assertEqual(("NEED_EVIDENCE",), oracle.acceptable_policy_statuses)
                    self.assertEqual("CLARIFICATION_REQUIRED", oracle.clarification_policy)
                elif scenario.category == "TARGET_ABSENT":
                    self.assertEqual((), oracle.acceptable_node_ids)
                    self.assertEqual(("NONE",), oracle.acceptable_policy_statuses)

    def test_phase2b_rejects_source_drift_and_execution_leak(self) -> None:
        for name in (
            "blueprint.v1.json",
            "tree.json",
            "candidate-scenarios.v2.json",
            "review-packet.v1.json",
            "review-decisions.hidden.v1.json",
            "scenarios.v2.json",
            "phase2a-preflight.v1.json",
        ):
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "fixture"
                shutil.copytree(C2, copied)
                (copied / name).write_bytes((copied / name).read_bytes() + b" ")
                with self.assertRaises(Phase2BError) as caught:
                    self._freeze(copied, copied / "hidden-oracle.v2.json", copied / "freeze-report.v1.json")
                self.assertEqual("DATASET_NONDETERMINISTIC", caught.exception.code)
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "fixture"
            shutil.copytree(C2, copied)
            (copied / "execution-manifest.v2.json").write_text("{}")
            with self.assertRaises(Phase2BError) as caught:
                self._freeze(copied, copied / "hidden-oracle.v2.json", copied / "freeze-report.v1.json")
            self.assertEqual("DATASET_ORACLE_LEAK", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
