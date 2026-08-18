from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import (
    SealedCaseOracle,
    SealedScenario,
    StructuralProfile,
    TerminalExpectation,
)


SCHEMA_VERSION = "treeguard.navigation-copilot-b03c2-freeze-report.v1"
DATA_COMMIT = "efa026d4edbb35db5fbe19a638888f481a4df6b5"
BATCH_REF = "NAVCOP_SEALED_V3C_B03_20260817_C2"
EXPECTED_SHA256 = {
    "blueprint.v1.json": "dabee24cf311675b0bd184f492852797c629f161242c6c32c2cec6d48ba7074a",
    "tree.json": "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd",
    "candidate-scenarios.v2.json": "1437568f07ea6c6a01a4d25a9c103f40718e37b3a505e6404dceaabb71c1c34e",
    "review-packet.v1.json": "ef1ce849444b1a9cee93c60f6a8567b15a002325ca0b79eb43a1a8f08215ac45",
    "review-decisions.hidden.v1.json": "a34ca039ed74bae98dc166f6742b4cac7e3f82a212755648efd160ac09eb71d1",
    "scenarios.v2.json": "3b52502c145e065c24418c3688e1019ee2637839279fb2ccd75d61fe9b3ef513",
    "phase2a-preflight.v1.json": "adc8371d27bd6eb0d3e82c3b8fba804cfcafa40f433a27237734958f09d1ccc2",
}
FINAL_QUOTAS = {
    "LITERAL_UNIQUE": 10,
    "NONLITERAL_UNIQUE": 10,
    "STRUCTURAL_INTERFERENCE": 8,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 6,
    "WEAK_EVIDENCE": 4,
    "TARGET_ABSENT": 6,
}


class Phase2BError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject(code: str) -> None:
    raise Phase2BError(code)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def reviewed_bytes_digest(tree_bytes: bytes, scenario: SealedScenario, decision: dict[str, Any]) -> str:
    """Bind the exact tree bytes and canonical per-item source bytes."""

    return canonical_digest(
        {
            "tree_raw_bytes_sha256": _sha256(tree_bytes),
            "scenario_canonical_bytes_sha256": _sha256(_json_bytes(scenario.to_dict())),
            "silver_decision_canonical_bytes_sha256": _sha256(_json_bytes(decision)),
        }
    )


def _targets(scenario: SealedScenario, decision: dict[str, Any]) -> tuple[str, ...]:
    if scenario.category == "TARGET_ABSENT":
        values: Any = []
    elif scenario.category == "CLARIFICATION":
        values = decision.get("resolved_target_ids")
    else:
        values = decision.get("compatible_target_ids")
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        _reject("DATASET_REFERENCE_INVALID")
    targets = tuple(sorted(values))
    if scenario.category == "MULTI_ACCEPTABLE":
        valid = len(targets) >= 2
    elif scenario.category == "TARGET_ABSENT":
        valid = not targets
    else:
        valid = len(targets) == 1
    if not valid:
        _reject(
            "DATASET_WEAK_EVIDENCE_TARGET_UNBOUND"
            if scenario.category == "WEAK_EVIDENCE"
            else "DATASET_ORACLE_OVERCLAIM"
        )
    return targets


def _oracle(scenario: SealedScenario, decision: dict[str, Any], tree_bytes: bytes) -> SealedCaseOracle:
    targets = _targets(scenario, decision)
    absent = scenario.category == "TARGET_ABSENT"
    clarify = scenario.category == "CLARIFICATION"
    weak = scenario.category == "WEAK_EVIDENCE"
    if decision.get("decision") != "SILVER_ACCEPTED" or decision.get("finding_codes") != []:
        _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    if weak and (not isinstance(decision.get("evidence_gap"), str) or len(decision["evidence_gap"]) < 20):
        _reject("DATASET_WEAK_EVIDENCE_TARGET_UNBOUND")
    if absent:
        terminals = (TerminalExpectation("REJECT_ALL", None, "ABSENT"),)
    elif weak:
        terminals = (TerminalExpectation("EXIT", None, "PRESENT_NOT_FOUND"),)
    else:
        terminals = tuple(
            TerminalExpectation("SELECT_CANDIDATE", node_id, "FOUND_TOP8")
            for node_id in targets
        )
    forbidden = (
        (scenario.proposed_parent_ref,)
        if scenario.wrong_context_challenge
        and scenario.proposed_parent_ref is not None
        and scenario.proposed_parent_ref not in targets
        and not absent
        else ()
    )
    return SealedCaseOracle.create(
        scenario_ref=scenario.scenario_ref,
        tree_digest=scenario.tree_digest,
        request_digest=scenario.request_digest,
        category=scenario.category,
        expected_route="CLARIFY" if clarify else ("LIMIT" if weak else "PROCEED"),
        acceptable_profiles=(
            StructuralProfile(
                scenario.node_kind_hint,
                scenario.value_type_hint,
                scenario.cardinality_hint,
            ),
        ),
        target_status="TARGET_ABSENT" if absent else "TARGET_PRESENT",
        acceptable_node_ids=targets,
        forbidden_node_ids=forbidden,
        clarification_policy="CLARIFICATION_REQUIRED" if clarify else "NOT_APPLICABLE",
        frozen_clarification_answer=scenario.frozen_clarification_answer if clarify else None,
        acceptable_policy_statuses=(
            ("NONE",) if absent else (("NEED_EVIDENCE",) if weak or clarify else ("CANDIDATES_AVAILABLE",))
        ),
        acceptable_terminals=terminals,
        wrong_context_challenge=scenario.wrong_context_challenge,
        review_status="CODEX_SILVER_REVIEWED",
        reviewed_bytes_digest=reviewed_bytes_digest(tree_bytes, scenario, decision),
        execution_eligible=True,
    )


def freeze_phase2b(source_dir: Path, oracle_output: Path, report_output: Path) -> dict[str, Any]:
    if oracle_output.parent.resolve() != source_dir.resolve() or report_output.parent.resolve() != source_dir.resolve():
        _reject("DATASET_REFERENCE_INVALID")
    if any(source_dir.glob("*execution*manifest*")) or any(source_dir.glob("*model*response*")):
        _reject("DATASET_ORACLE_LEAK")
    source_bytes: dict[str, bytes] = {}
    for name, expected in EXPECTED_SHA256.items():
        path = source_dir / name
        if not path.is_file():
            _reject("DATASET_REFERENCE_INVALID")
        source_bytes[name] = path.read_bytes()
        if _sha256(source_bytes[name]) != expected:
            _reject("DATASET_NONDETERMINISTIC")
    preflight = strict_json_loads(source_bytes["phase2a-preflight.v1.json"])
    if (
        preflight.get("status") != "C2_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW"
        or preflight.get("batch_ref") != BATCH_REF
        or preflight.get("execution_scenarios") != 48
        or preflight.get("oracle_status") != "ABSENT_PHASE2B_NOT_APPROVED"
    ):
        _reject("DATASET_SOURCE_CLASS_INVALID")
    raw_scenarios = strict_json_loads(source_bytes["scenarios.v2.json"])
    decisions_doc = strict_json_loads(source_bytes["review-decisions.hidden.v1.json"])
    if not isinstance(raw_scenarios, list) or not isinstance(decisions_doc, dict):
        _reject("DATASET_REFERENCE_INVALID")
    scenarios = [SealedScenario.from_dict(item) for item in raw_scenarios]
    decisions_raw = decisions_doc.get("decisions")
    if not isinstance(decisions_raw, list) or len(decisions_raw) != 56:
        _reject("DATASET_COUNT_MISMATCH")
    decisions = {item.get("scenario_ref"): item for item in decisions_raw if isinstance(item, dict)}
    if len(decisions) != 56:
        _reject("DATASET_REFERENCE_INVALID")
    if (
        len(scenarios) != 48
        or Counter(item.category for item in scenarios) != Counter(FINAL_QUOTAS)
        or sum(item.wrong_context_challenge for item in scenarios) != 8
        or sum(item.repeat_challenge for item in scenarios) != 16
    ):
        _reject("DATASET_COUNT_MISMATCH")
    oracles = [_oracle(item, decisions.get(item.scenario_ref, {}), source_bytes["tree.json"]) for item in scenarios]
    if (
        [item.scenario_ref for item in oracles] != [item.scenario_ref for item in scenarios]
        or sum(item.target_status == "TARGET_PRESENT" for item in oracles) != 42
        or sum(item.category == "WEAK_EVIDENCE" for item in oracles) != 4
    ):
        _reject("DATASET_COUNT_MISMATCH")
    oracle_bytes = _json_bytes([item.to_dict() for item in oracles])
    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "C2_PHASE2B_FROZEN_AWAITING_EXECUTION_MANIFEST_APPROVAL",
        "dataset_ref": preflight["dataset_ref"],
        "batch_ref": BATCH_REF,
        "function_commit": preflight["function_commit"],
        "data_commit": DATA_COMMIT,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "scenario_count": 48,
        "oracle_count": 48,
        "target_present": 42,
        "target_absent": 6,
        "wrong_context": 8,
        "repeat_subset": 16,
        "weak_evidence": 4,
        "category_counts": dict(sorted(Counter(item.category for item in oracles).items())),
        "source_sha256": dict(sorted(EXPECTED_SHA256.items())),
        "oracle_sha256": _sha256(oracle_bytes),
        "execution_manifest_status": "ABSENT_NOT_APPROVED",
        "model_execution_status": "NOT_RUN",
        "blocking_finding_codes": [],
    }
    report = {**report_payload, "freeze_report_hash": canonical_digest(report_payload)}
    report_bytes = _json_bytes(report)
    for path, content in ((oracle_output, oracle_bytes), (report_output, report_bytes)):
        if path.exists() and path.read_bytes() != content:
            _reject("DATASET_NONDETERMINISTIC")
        if not path.exists():
            path.write_bytes(content)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--oracle-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    report = freeze_phase2b(args.source_dir, args.oracle_output, args.report_output)
    print(
        "B03C2_PHASE2B_FROZEN "
        f"scenarios={report['scenario_count']} oracles={report['oracle_count']} "
        "execution_manifest=ABSENT model=NOT_RUN"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
