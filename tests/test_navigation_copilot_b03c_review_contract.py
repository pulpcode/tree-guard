from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.navigation_copilot_b03c.author_review_contract_proof import materialize
from scripts.navigation_copilot_b03c.record_review_contract_decisions import record_decisions
from scripts.navigation_copilot_b03c.verify_review_contract_proof import (
    ContractViolation,
    verify_documents,
    verify_paths,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/fictional/navigation_copilot_b03c_review_contract_proof"
AUTHOR = ROOT / "scripts/navigation_copilot_b03c/author_review_contract_proof.py"
REVIEW = ROOT / "scripts/navigation_copilot_b03c/record_review_contract_decisions.py"
VERIFY = ROOT / "scripts/navigation_copilot_b03c/verify_review_contract_proof.py"


class ReviewContractProofTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tree_bytes = (FIXTURE / "tree.v1.json").read_bytes()
        self.scenario_bytes = (FIXTURE / "scenarios.v1.json").read_bytes()
        self.packet_bytes = (FIXTURE / "review-packet.v1.json").read_bytes()
        self.review_input_bytes = (FIXTURE / "review-input.silver.v1.json").read_bytes()
        self.tree = json.loads(self.tree_bytes)
        self.scenarios = json.loads(self.scenario_bytes)
        self.packet = json.loads(self.packet_bytes)
        self.decisions = json.loads((FIXTURE / "review-decisions.v1.json").read_bytes())

    def _verify(
        self,
        *,
        tree=None,
        scenarios=None,
        packet=None,
        decisions=None,
        tree_bytes=None,
        scenario_bytes=None,
        packet_bytes=None,
        review_input_bytes=None,
    ):
        return verify_documents(
            copy.deepcopy(self.tree if tree is None else tree),
            copy.deepcopy(self.scenarios if scenarios is None else scenarios),
            copy.deepcopy(self.packet if packet is None else packet),
            copy.deepcopy(self.decisions if decisions is None else decisions),
            tree_bytes=self.tree_bytes if tree_bytes is None else tree_bytes,
            scenario_bytes=self.scenario_bytes if scenario_bytes is None else scenario_bytes,
            packet_bytes=self.packet_bytes if packet_bytes is None else packet_bytes,
            review_input_bytes=(
                self.review_input_bytes if review_input_bytes is None else review_input_bytes
            ),
        )

    def assert_contract_code(self, expected: str, **changes) -> None:
        with self.assertRaises(ContractViolation) as caught:
            self._verify(**changes)
        self.assertEqual(expected, caught.exception.code)

    def test_authoring_is_deterministic_and_pending_only(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_hashes = materialize(Path(first))
            second_hashes = materialize(Path(second))
            self.assertEqual(first_hashes, second_hashes)
            for name in first_hashes:
                self.assertEqual((Path(first) / name).read_bytes(), (Path(second) / name).read_bytes())
        self.assertEqual(41, len(self.tree["nodes"]))
        self.assertEqual(8, len(self.scenarios["items"]))
        self.assertEqual({"PENDING"}, {item["review_state"] for item in self.packet["items"]})
        serialized_authoring = self.tree_bytes + self.scenario_bytes + self.packet_bytes
        for forbidden in (b"reviewed_target_ids", b"rationale", b"finding_codes"):
            self.assertNotIn(forbidden, serialized_authoring)

    def test_modules_are_physically_separated(self) -> None:
        author_source = AUTHOR.read_text()
        review_source = REVIEW.read_text()
        verify_source = VERIFY.read_text()
        for forbidden in ("SILVER_ACCEPTED", "SILVER_REJECTED", "manual_decision"):
            self.assertNotIn(forbidden, author_source)
        self.assertNotIn("import author_review_contract_proof", review_source)
        self.assertNotIn("import record_review_contract_decisions", verify_source)

    def test_recorder_binds_frozen_sources_without_modifying_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "decisions.json"
            before = (self.tree_bytes, self.scenario_bytes, self.packet_bytes)
            record_decisions(
                FIXTURE / "tree.v1.json",
                FIXTURE / "scenarios.v1.json",
                FIXTURE / "review-packet.v1.json",
                FIXTURE / "review-input.silver.v1.json",
                output,
            )
            recorded = json.loads(output.read_bytes())
            self.assertEqual(hashlib.sha256(self.tree_bytes).hexdigest(), recorded["source_tree_sha256"])
            self.assertEqual(
                hashlib.sha256(self.scenario_bytes).hexdigest(), recorded["source_scenarios_sha256"]
            )
            self.assertEqual(before, (self.tree_bytes, self.scenario_bytes, self.packet_bytes))

    def test_recorder_rejects_reviewer_source_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            review_input = json.loads((FIXTURE / "review-input.silver.v1.json").read_bytes())
            review_input["source_tree_sha256"] = "0" * 64
            review_input_path = directory_path / "review-input.json"
            review_input_path.write_text(json.dumps(review_input, ensure_ascii=False))
            with self.assertRaisesRegex(RuntimeError, "^DATASET_NONDETERMINISTIC$"):
                record_decisions(
                    FIXTURE / "tree.v1.json",
                    FIXTURE / "scenarios.v1.json",
                    FIXTURE / "review-packet.v1.json",
                    review_input_path,
                    directory_path / "decisions.json",
                )

    def test_eight_positive_contract_cases_pass(self) -> None:
        report = verify_paths(
            FIXTURE / "tree.v1.json",
            FIXTURE / "scenarios.v1.json",
            FIXTURE / "review-packet.v1.json",
            FIXTURE / "review-input.silver.v1.json",
            FIXTURE / "review-decisions.v1.json",
        )
        self.assertEqual("C0_REVIEW_CONTRACT_PROOF_PASSED", report["status"])
        self.assertEqual(8, report["accepted"])
        self.assertEqual(0, report["value_envelope_count"])

    def test_twelve_blocking_mutations_are_rejected_with_exact_codes(self) -> None:
        cases = []

        packet = copy.deepcopy(self.packet)
        packet["items"][0]["review_state"] = "SILVER_ACCEPTED"
        cases.append(("prefilled authoring", "DATASET_REVIEW_SOURCE_NOT_INDEPENDENT", {"packet": packet}))

        decisions = copy.deepcopy(self.decisions)
        decisions["producer_module"] = "author_review_contract_proof"
        cases.append(("same producer", "DATASET_REVIEW_SOURCE_NOT_INDEPENDENT", {"decisions": decisions}))

        decisions = copy.deepcopy(self.decisions)
        decisions["generated_by_verification"] = True
        cases.append(("verification generated", "DATASET_REVIEW_SOURCE_NOT_INDEPENDENT", {"decisions": decisions}))

        decisions = copy.deepcopy(self.decisions)
        decisions["decisions"][1]["rationale"] = decisions["decisions"][0]["rationale"]
        cases.append(("generic review", "DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED", {"decisions": decisions}))

        cases.append(("digest drift", "DATASET_NONDETERMINISTIC", {"tree_bytes": self.tree_bytes + b" "}))

        scenarios = copy.deepcopy(self.scenarios)
        scenarios["items"][6]["request_text"] = "洗衣机预约"
        cases.append(("absence canonical hit", "DATASET_ABSENCE_CLOSURE_INCOMPLETE", {"scenarios": scenarios}))

        decisions = copy.deepcopy(self.decisions)
        decisions["decisions"][6]["satisfiable_supertype_ids"] = ["c0n-041"]
        cases.append(("absence supertype", "DATASET_ORACLE_OVERCLAIM", {"decisions": decisions}))

        decisions = copy.deepcopy(self.decisions)
        decisions["decisions"][1]["surface_form"] = "无对应简称"
        cases.append(("abbreviation expansion", "DATASET_SCENARIO_COVERAGE_DUPLICATE", {"decisions": decisions}))

        decisions = copy.deepcopy(self.decisions)
        decisions["decisions"][1]["phenomenon"] = "minor_typo"
        decisions["decisions"][1]["surface_form"] = "完全无关"
        cases.append(("minor typo neighbors", "DATASET_SCENARIO_COVERAGE_DUPLICATE", {"decisions": decisions}))

        decisions = copy.deepcopy(self.decisions)
        decisions["decisions"][3]["reviewed_target_ids"] = ["c0n-023", "c0n-024"]
        cases.append(("multi missing", "DATASET_TARGET_SET_NOT_EXHAUSTIVE", {"decisions": decisions}))

        decisions = copy.deepcopy(self.decisions)
        decisions["decisions"][3]["reviewed_target_ids"].append("c0n-026")
        cases.append(("multi extra", "DATASET_TARGET_SET_NOT_EXHAUSTIVE", {"decisions": decisions}))

        decisions = copy.deepcopy(self.decisions)
        decisions["decisions"][4]["contrast_node_ids"] = ["c0n-004"]
        cases.append(("clarification contrast", "DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT", {"decisions": decisions}))

        self.assertEqual(12, len(cases))
        for name, expected, changes in cases:
            with self.subTest(name=name):
                self.assert_contract_code(expected, **changes)


if __name__ == "__main__":
    unittest.main()
