from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from treeguard import load_tree_export
from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import (
    SealedCaseOracle,
    SealedEvaluationManifest,
    SealedScenario,
    StructuralProfile,
    TerminalExpectation,
)
from treeguard.workbench import build_tree_reference_index
from scripts.run_navigation_copilot_sealed_eval import validate_input_collections


SCHEMA_VERSION = "treeguard.navigation-copilot-b03c3-freeze-report.v1"
DATA_COMMIT = "6693e5581bcb69e59ca09a26388816c84f816ad1"
FUNCTION_COMMIT = "40098afe985dfc81183c928a473a2e8a3c2176dc"
BATCH_REF = "NAVCOP_SEALED_V3C_B03_20260817_C3"
EXPECTED_SHA256 = {
    "blueprint.v1.json": "3fcb9294b55bac02f274dc90bb40713a18e2fadddec1a2fa35a7ece0d559366b",
    "tree.json": "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd",
    "candidate-scenarios.v2.json": "ec93ae389f239fd2590f2bdbb91244f26b548f20bf097c2c3fda00a6b6960cff",
    "review-packet.v1.json": "75bd760db98a0ae50b6a81389421efbe61a2c889f39b4bf9a9ac10ffed2f24c4",
    "review-decisions.hidden.v1.json": "8f30489068d05a63e0598b26543769149f301fcbcdfd47598813b6d86798a1cf",
    "scenarios.v2.json": "78d0955e8eaed5e7c0c2a224041c071f98b117744388dfbe64bbfc6b68e22e24",
    "phase2a-preflight.v1.json": "a92211ece66a2c4ac49e8589c0e7d30272ac7ea4fc55dc9d5752d38b92e46c46",
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


def _write_frozen_outputs(outputs: tuple[tuple[Path, bytes], ...]) -> None:
    missing: list[tuple[Path, bytes]] = []
    for path, content in outputs:
        if path.is_symlink():
            _reject("DATASET_REFERENCE_INVALID")
        if path.exists():
            if not path.is_file() or path.read_bytes() != content:
                _reject("DATASET_NONDETERMINISTIC")
        else:
            missing.append((path, content))
    created: list[Path] = []
    try:
        for path, content in missing:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        _reject("DATASET_PUBLISH_FAILED")


def reviewed_bytes_digest(
    tree_bytes: bytes,
    scenario: SealedScenario,
    decision: dict[str, Any],
) -> str:
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
    valid = (
        len(targets) >= 2
        if scenario.category == "MULTI_ACCEPTABLE"
        else not targets
        if scenario.category == "TARGET_ABSENT"
        else len(targets) == 1
    )
    if not valid:
        _reject(
            "DATASET_WEAK_EVIDENCE_TARGET_UNBOUND"
            if scenario.category == "WEAK_EVIDENCE"
            else "DATASET_ORACLE_OVERCLAIM"
        )
    return targets


def _oracle(
    scenario: SealedScenario,
    decision: dict[str, Any],
    tree_bytes: bytes,
    node_id_by_ref: dict[str, str],
) -> SealedCaseOracle:
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
    forbidden: tuple[str, ...] = ()
    if scenario.wrong_context_challenge and not absent:
        if scenario.proposed_parent_ref is None or scenario.proposed_parent_ref not in node_id_by_ref:
            _reject("DATASET_PARENT_REFERENCE_CONTRACT_MISMATCH")
        stable_forbidden = node_id_by_ref[scenario.proposed_parent_ref]
        if stable_forbidden in targets:
            _reject("DATASET_ORACLE_OVERCLAIM")
        forbidden = (stable_forbidden,)
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


def build_validation_manifest(
    source_bytes: dict[str, bytes],
    scenarios: tuple[SealedScenario, ...],
    oracles: tuple[SealedCaseOracle, ...],
) -> SealedEvaluationManifest:
    return SealedEvaluationManifest.create(
        function_commit=FUNCTION_COMMIT,
        data_commit=DATA_COMMIT,
        tree_sha256=_sha256(source_bytes["tree.json"]),
        scenarios_sha256=_sha256(source_bytes["scenarios.v2.json"]),
        oracle_sha256=_sha256(_json_bytes([item.to_dict() for item in oracles])),
        model_name="qwen3.6-35b-a3b",
        understanding_prompt_version="treeguard.navigation-copilot-understanding.zh.v2",
        clarification_prompt_version="treeguard.navigation-copilot-understanding-clarification.zh.v2",
        semantic_prompt_version="treeguard.navigation-copilot-semantic.zh.v2",
        endpoint_class="OFFICIAL_BAILIAN_COMPATIBLE",
        scenario_refs=[item.scenario_ref for item in scenarios],
        repeat_scenario_refs=[item.scenario_ref for item in scenarios if item.repeat_challenge],
        wire_attempt_limit=320,
    )


def freeze_phase2b(source_dir: Path, oracle_output: Path, report_output: Path) -> dict[str, Any]:
    if oracle_output.parent.resolve() != source_dir.resolve() or report_output.parent.resolve() != source_dir.resolve():
        _reject("DATASET_REFERENCE_INVALID")
    if any(source_dir.glob("*execution*manifest*")) or any(source_dir.glob("*model*response*")):
        _reject("DATASET_ORACLE_LEAK")
    source_bytes: dict[str, bytes] = {}
    for name, expected in EXPECTED_SHA256.items():
        path = source_dir / name
        if path.is_symlink() or not path.is_file():
            _reject("DATASET_REFERENCE_INVALID")
        source_bytes[name] = path.read_bytes()
        if _sha256(source_bytes[name]) != expected:
            _reject("DATASET_NONDETERMINISTIC")
    preflight = strict_json_loads(source_bytes["phase2a-preflight.v1.json"])
    if (
        preflight.get("status") != "C3_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW"
        or preflight.get("batch_ref") != BATCH_REF
        or preflight.get("execution_scenarios") != 48
        or preflight.get("oracle_status") != "ABSENT_PHASE2B_NOT_APPROVED"
    ):
        _reject("DATASET_SOURCE_CLASS_INVALID")
    result = load_tree_export(source_dir / "tree.json")
    if not result.is_valid or result.tree is None:
        _reject("DATASET_REFERENCE_INVALID")
    references = build_tree_reference_index(result.tree)
    raw_scenarios = strict_json_loads(source_bytes["scenarios.v2.json"])
    decisions_doc = strict_json_loads(source_bytes["review-decisions.hidden.v1.json"])
    if not isinstance(raw_scenarios, list) or not isinstance(decisions_doc, dict):
        _reject("DATASET_REFERENCE_INVALID")
    scenarios = tuple(SealedScenario.from_dict(item) for item in raw_scenarios)
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
    oracles = tuple(
        _oracle(item, decisions.get(item.scenario_ref, {}), source_bytes["tree.json"], references.node_id_by_ref)
        for item in scenarios
    )
    manifest = build_validation_manifest(source_bytes, scenarios, oracles)
    validate_input_collections(manifest, scenarios, oracles, result.tree)
    oracle_bytes = _json_bytes([item.to_dict() for item in oracles])
    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "C3_PHASE2B_FROZEN_AWAITING_EXECUTION_MANIFEST_APPROVAL",
        "dataset_ref": "navigation-copilot-sealed-v3c-b03-maker-lab-c",
        "batch_ref": BATCH_REF,
        "function_commit": FUNCTION_COMMIT,
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
        "wrong_context_forbidden_stable_ids": sum(bool(item.forbidden_node_ids) for item in oracles),
        "repeat_subset": 16,
        "weak_evidence": 4,
        "category_counts": dict(sorted(Counter(item.category for item in oracles).items())),
        "source_sha256": dict(sorted(EXPECTED_SHA256.items())),
        "oracle_sha256": _sha256(oracle_bytes),
        "runner_collection_validation": "PASS",
        "execution_manifest_status": "ABSENT_NOT_APPROVED",
        "model_execution_status": "NOT_RUN",
        "blocking_finding_codes": [],
    }
    report = {**report_payload, "freeze_report_hash": canonical_digest(report_payload)}
    report_bytes = _json_bytes(report)
    _write_frozen_outputs(
        ((oracle_output, oracle_bytes), (report_output, report_bytes))
    )
    return report


def materialize_private_preflight_bundle(source_dir: Path, private_root: Path) -> tuple[Path, Path]:
    """Create a disposable 0700/0600 bundle for the runner's inert preflight."""

    if os.path.lexists(private_root):
        _reject("DATASET_REFERENCE_INVALID")
    source_bytes: dict[str, bytes] = {}
    for name, expected in EXPECTED_SHA256.items():
        source_path = source_dir / name
        if source_path.is_symlink() or not source_path.is_file():
            _reject("DATASET_REFERENCE_INVALID")
        source_bytes[name] = source_path.read_bytes()
        if _sha256(source_bytes[name]) != expected:
            _reject("DATASET_NONDETERMINISTIC")
    scenarios = tuple(
        SealedScenario.from_dict(item)
        for item in strict_json_loads(source_bytes["scenarios.v2.json"])
    )
    oracle_bytes = (source_dir / "hidden-oracle.v2.json").read_bytes()
    oracles = tuple(
        SealedCaseOracle.from_dict(item) for item in strict_json_loads(oracle_bytes)
    )
    manifest = build_validation_manifest(source_bytes, scenarios, oracles)
    if manifest.oracle_sha256 != _sha256(oracle_bytes):
        _reject("DATASET_NONDETERMINISTIC")
    private_root.mkdir(mode=0o700)
    os.chmod(private_root, 0o700)
    manifest_path = private_root / "preflight-manifest.v2.json"
    oracle_path = private_root / "hidden-oracle.v2.json"
    for path, content in (
        (manifest_path, _json_bytes(manifest.to_dict())),
        (oracle_path, oracle_bytes),
    ):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(path, 0o600)
    return manifest_path, oracle_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--oracle-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--private-preflight-root", type=Path)
    args = parser.parse_args()
    report = freeze_phase2b(args.source_dir, args.oracle_output, args.report_output)
    if args.private_preflight_root is not None:
        materialize_private_preflight_bundle(args.source_dir, args.private_preflight_root)
    print(
        "B03C3_PHASE2B_FROZEN "
        f"scenarios={report['scenario_count']} oracles={report['oracle_count']} "
        "runner_validation=PASS execution_manifest=ABSENT model=NOT_RUN"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
