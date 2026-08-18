from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from treeguard.adapter import adapt_tree_document
from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import SealedScenario

from scripts.navigation_copilot_b03c.verify_review_contract_proof import (
    ContractViolation,
    verify_absence_contract,
    verify_clarification_contrast,
    verify_target_set_exhaustiveness,
)


SCHEMA_VERSION = "treeguard.navigation-copilot-b03c2-phase2a-preflight.v1"
SOURCE_DATA_COMMIT = "70675601e3d53649bee440935199f4cf9fbf3ff0"
SOURCE_TREE_SHA256 = "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd"
EXPECTED_BLUEPRINT_SHA256 = "dabee24cf311675b0bd184f492852797c629f161242c6c32c2cec6d48ba7074a"
EXPECTED_CANDIDATES_SHA256 = "1437568f07ea6c6a01a4d25a9c103f40718e37b3a505e6404dceaabb71c1c34e"
EXPECTED_PACKET_SHA256 = "ef1ce849444b1a9cee93c60f6a8567b15a002325ca0b79eb43a1a8f08215ac45"
EXPECTED_DECISIONS_SHA256 = "a34ca039ed74bae98dc166f6742b4cac7e3f82a212755648efd160ac09eb71d1"
C1_CANARIES = {
    "blueprint.v1.json": "72d8778d26ec2c2317d14c38a1843f014651e0cbd10aa0d0bc4ded729b01792d",
    "tree.json": SOURCE_TREE_SHA256,
    "candidate-scenarios.v2.json": "122fd83fab7856b37928288c7f086a6350812946dd05540d9c8ea9fafb7e8dda",
    "review-packet.v1.json": "acea6d6636036d6e21deaa07a1679e341767acab707f13d02bfc26dcf285239b",
    "review-decisions.hidden.v1.json": "3e6ed29cf499dc5207cfd8d79fee5584b75140bb9e1ac0416254e37f4a56bd7e",
    "scenarios.v2.json": "5277c698b6eac2ed21b1249f99b681bcde6daec9c2a5bdbead2621d99dac637f",
    "phase2a-preflight.v1.json": "76154abe2999ea030936e9989462f7c30b6e4af72d135ec120008a74d985ab25",
}
CATEGORY_ORDER = (
    "LITERAL_UNIQUE",
    "NONLITERAL_UNIQUE",
    "STRUCTURAL_INTERFERENCE",
    "MULTI_ACCEPTABLE",
    "CLARIFICATION",
    "WEAK_EVIDENCE",
    "TARGET_ABSENT",
)
CANDIDATE_QUOTAS = dict(zip(CATEGORY_ORDER, (11, 12, 10, 4, 7, 5, 7), strict=True))
FINAL_QUOTAS = dict(zip(CATEGORY_ORDER, (10, 10, 8, 4, 6, 4, 6), strict=True))
MULTI_GROUPS = {
    "b03c2:034": "工位预约对象",
    "b03c2:035": "设备维护对象",
    "b03c2:036": "安全检查范围",
    "b03c2:037": "成果附件说明",
}
CLARIFICATION_RULES = {
    "b03c2:038": (("激光切割台预约", "三维打印台预约", "木工台预约", "电子焊接台预约"), "三维打印台预约"),
    "b03c2:039": (("手持钻借用", "热风枪借用", "万用表借用", "雕刻刀借用"), "万用表借用"),
    "b03c2:040": (("板材登记", "线材登记", "涂料登记", "紧固件登记"), "涂料登记"),
    "b03c2:041": (("漏液报告", "异响报告", "冒烟报告"), "冒烟报告"),
    "b03c2:042": (("返工要求", "报废申请", "移交准备"), "报废申请"),
    "b03c2:043": (("实际归还", "工具归还"), "实际归还"),
    "b03c2:044": (("完成时间", "完成摘要"), "完成摘要"),
}
WEAK_TARGETS = {
    "b03c2:045": "三维打印台预约",
    "b03c2:046": "激光切割机维护",
    "b03c2:047": "涂料登记",
    "b03c2:048": "保留期限",
    "b03c2:049": "未结事项",
}
RANDOM_RECHECKS = (
    "b03c2:002",
    "b03c2:009",
    "b03c2:016",
    "b03c2:023",
    "b03c2:045",
    "b03c2:046",
    "b03c2:047",
    "b03c2:048",
)


class Phase2AError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject(code: str) -> None:
    raise Phase2AError(code)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _assert_c1_canaries(source_c1_dir: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for name, expected in C1_CANARIES.items():
        content = (source_c1_dir / name).read_bytes()
        if _sha256(content) != expected:
            _reject("DATASET_C1_SOURCE_DRIFT")
        result[name] = content
    return result


def _tree_index(
    tree: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], dict[str, str]]:
    by_id: dict[str, dict[str, Any]] = {}
    children: dict[str, list[str]] = defaultdict(list)
    by_label: dict[str, str] = {}
    stack = list(tree["map_topology"].values())
    while stack:
        entry = stack.pop()
        metadata = entry["metadata"]
        node_id = metadata["node_id"]
        label = metadata["node_name"]
        if node_id in by_id or label in by_label or "value" in entry:
            _reject("DATASET_REFERENCE_INVALID")
        by_id[node_id] = metadata
        by_label[label] = node_id
        parent_id = metadata.get("parent_node_id")
        if parent_id is not None:
            children[parent_id].append(node_id)
        stack.extend(entry.get("subnodes", {}).values())
    return by_id, children, by_label


def _validate_review(
    decisions_doc: dict[str, Any],
    candidates: list[SealedScenario],
    by_id: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
    by_label: dict[str, str],
    c1_decisions: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if (
        decisions_doc.get("producer_module") != "record_sealed_reviews_c2"
        or decisions_doc.get("reviewer_class") != "CODEX_SILVER_REVIEWED"
        or decisions_doc.get("review_mode")
        != "CODEX_SILVER_FULL_REBIND_WITH_WEAK_REAUTHORING"
        or decisions_doc.get("source_tree_sha256") != SOURCE_TREE_SHA256
        or decisions_doc.get("source_candidates_sha256") != EXPECTED_CANDIDATES_SHA256
        or decisions_doc.get("source_review_packet_sha256") != EXPECTED_PACKET_SHA256
        or decisions_doc.get("prior_review_basis_sha256") != C1_CANARIES["review-decisions.hidden.v1.json"]
    ):
        _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    elapsed = decisions_doc.get("elapsed_minutes")
    if not isinstance(elapsed, int) or isinstance(elapsed, bool) or not 1 <= elapsed <= 360:
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")
    if decisions_doc.get("dual_review_count") != 0:
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")
    if decisions_doc.get("reviewed_node_ids") != c1_decisions.get("reviewed_node_ids"):
        _reject("DATASET_REFERENCE_INVALID")
    if decisions_doc.get("random_recheck_scenario_refs") != list(RANDOM_RECHECKS):
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")
    if decisions_doc.get("high_risk_scenario_refs") != sorted(WEAK_TARGETS):
        _reject("DATASET_WEAK_EVIDENCE_TARGET_UNBOUND")
    items = decisions_doc.get("decisions")
    if not isinstance(items, list) or len(items) != 56:
        _reject("DATASET_COUNT_MISMATCH")
    if [item.get("scenario_ref") for item in items] != [item.scenario_ref for item in candidates]:
        _reject("DATASET_REFERENCE_INVALID")
    rationales = [item.get("rationale") for item in items]
    if any(not isinstance(item, str) or len(item) < 20 for item in rationales) or len(set(rationales)) != 56:
        _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    labels_and_aliases = [
        text
        for metadata in by_id.values()
        for text in (metadata["node_name"], *metadata["extension"].get("aliases", []))
    ]
    by_ref: dict[str, dict[str, Any]] = {}
    for scenario, decision in zip(candidates, items, strict=True):
        if decision.get("decision") != "SILVER_ACCEPTED" or decision.get("finding_codes") != []:
            _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
        target_fields = (
            "reviewed_target_ids",
            "compatible_target_ids",
            "contrast_node_ids",
            "resolved_target_ids",
            "satisfiable_supertype_ids",
        )
        if any(not isinstance(decision.get(name), list) for name in target_fields):
            _reject("DATASET_REFERENCE_INVALID")
        named_ids = [node_id for name in target_fields for node_id in decision[name]]
        if any(node_id not in by_id for node_id in named_ids):
            _reject("DATASET_REFERENCE_INVALID")
        if any(by_id[node_id]["extension"]["dataset_role"] == "filler" for node_id in named_ids):
            _reject("DATASET_FILLER_TARGETED")
        reviewed = decision["reviewed_target_ids"]
        compatible = decision["compatible_target_ids"]
        try:
            if scenario.category == "MULTI_ACCEPTABLE":
                group_id = by_label[MULTI_GROUPS[scenario.scenario_ref]]
                expected = sorted(
                    node_id
                    for node_id in children[group_id]
                    if by_id[node_id]["extension"]["dataset_role"] == "curated"
                )
                verify_target_set_exhaustiveness(reviewed, expected)
                verify_target_set_exhaustiveness(compatible, expected)
            elif scenario.category == "CLARIFICATION":
                contrast_labels, resolved_label = CLARIFICATION_RULES[scenario.scenario_ref]
                expected_contrast = sorted(by_label[label] for label in contrast_labels)
                expected_resolved = [by_label[resolved_label]]
                if decision["contrast_node_ids"] != expected_contrast or decision["resolved_target_ids"] != expected_resolved:
                    _reject("DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT")
                verify_clarification_contrast(expected_contrast, expected_resolved)
            elif scenario.category == "WEAK_EVIDENCE":
                target_label = WEAK_TARGETS[scenario.scenario_ref]
                expected = [by_label[target_label]]
                if reviewed != expected or compatible != expected:
                    _reject("DATASET_WEAK_EVIDENCE_TARGET_UNBOUND")
                verify_target_set_exhaustiveness(reviewed, expected)
                verify_target_set_exhaustiveness(compatible, expected)
                gap = decision.get("evidence_gap")
                if target_label not in scenario.requirement_text or not isinstance(gap, str) or len(gap) < 20:
                    _reject("DATASET_WEAK_EVIDENCE_TARGET_UNBOUND")
            elif scenario.category == "TARGET_ABSENT":
                verify_absence_contract(
                    scenario.requirement_text,
                    labels_and_aliases,
                    reviewed,
                    decision["satisfiable_supertype_ids"],
                )
            elif len(reviewed) != 1 or reviewed != compatible:
                _reject("DATASET_SCENARIO_COVERAGE_DUPLICATE")
        except ContractViolation as exc:
            _reject(exc.code)
        by_ref[scenario.scenario_ref] = decision
    return by_ref


def _select(candidates: list[SealedScenario]) -> list[SealedScenario]:
    used: Counter[str] = Counter()
    selected: list[SealedScenario] = []
    for scenario in candidates:
        if used[scenario.category] < FINAL_QUOTAS[scenario.category]:
            selected.append(scenario)
            used[scenario.category] += 1
    if used != Counter(FINAL_QUOTAS) or len(selected) != 48:
        _reject("DATASET_COUNT_MISMATCH")
    return selected


def verify_and_freeze(
    source_c1_dir: Path,
    blueprint_path: Path,
    tree_path: Path,
    candidates_path: Path,
    packet_path: Path,
    decisions_path: Path,
    scenarios_output: Path,
    report_output: Path,
) -> dict[str, Any]:
    if source_c1_dir.resolve() == tree_path.parent.resolve():
        _reject("DATASET_C1_SOURCE_DRIFT")
    if any(tree_path.parent.glob("*oracle*")) or any(tree_path.parent.glob("*manifest*")) or any(tree_path.parent.glob("*freeze*")):
        _reject("DATASET_ORACLE_OVERCLAIM")
    c1_files = _assert_c1_canaries(source_c1_dir)
    blueprint_bytes = blueprint_path.read_bytes()
    tree_bytes = tree_path.read_bytes()
    candidate_bytes = candidates_path.read_bytes()
    packet_bytes = packet_path.read_bytes()
    decision_bytes = decisions_path.read_bytes()
    if (
        _sha256(blueprint_bytes),
        _sha256(tree_bytes),
        _sha256(candidate_bytes),
        _sha256(packet_bytes),
    ) != (
        EXPECTED_BLUEPRINT_SHA256,
        SOURCE_TREE_SHA256,
        EXPECTED_CANDIDATES_SHA256,
        EXPECTED_PACKET_SHA256,
    ):
        _reject("DATASET_NONDETERMINISTIC")
    if tree_bytes != c1_files["tree.json"]:
        _reject("DATASET_C1_SOURCE_DRIFT")
    blueprint = strict_json_loads(blueprint_bytes)
    tree = strict_json_loads(tree_bytes)
    raw_candidates = strict_json_loads(candidate_bytes)
    packet = strict_json_loads(packet_bytes)
    decisions_doc = strict_json_loads(decision_bytes)
    c1_decisions = strict_json_loads(c1_files["review-decisions.hidden.v1.json"])
    if (
        blueprint.get("schema_version") != "treeguard.navigation-copilot-b03c2-blueprint.v1"
        or blueprint.get("batch_ref") != "NAVCOP_SEALED_V3C_B03_20260817_C2"
        or blueprint.get("source_data_commit") != SOURCE_DATA_COMMIT
        or blueprint.get("source_tree_sha256") != SOURCE_TREE_SHA256
        or blueprint.get("c1_disposition") != "REJECTED_PREEXECUTION_ORACLE_CONTRACT_MISMATCH"
        or blueprint.get("source_class") != "CLEANROOM_SYNTHETIC"
        or blueprint.get("fictional") is not True
        or blueprint.get("derived_from_real") is not False
        or blueprint.get("gold_eligible") is not False
        or blueprint.get("patch_eligible") is not False
    ):
        _reject("DATASET_SOURCE_CLASS_INVALID")
    imported = adapt_tree_document(tree)
    if not imported.is_valid or imported.tree is None or imported.observed_node_count != 736 or imported.observed_value_count != 0:
        _reject("DATASET_COUNT_MISMATCH")
    by_id, children, by_label = _tree_index(tree)
    roles = Counter(metadata["extension"]["dataset_role"] for metadata in by_id.values())
    if roles != Counter({"curated": 160, "background": 456, "filler": 120}):
        _reject("DATASET_COUNT_MISMATCH")
    candidates = [SealedScenario.from_dict(item) for item in raw_candidates]
    if (
        len(candidates) != 56
        or [item.scenario_ref for item in candidates] != [f"b03c2:{index:03d}" for index in range(1, 57)]
        or Counter(item.category for item in candidates) != Counter(CANDIDATE_QUOTAS)
        or any(item.tree_digest != imported.tree.snapshot_hash for item in candidates)
        or sum(item.wrong_context_challenge for item in candidates) != 8
        or sum(item.repeat_challenge for item in candidates) != 16
    ):
        _reject("DATASET_COUNT_MISMATCH")
    if (
        packet.get("producer_module") != "author_sealed_data_c2"
        or packet.get("source_tree_sha256") != SOURCE_TREE_SHA256
        or packet.get("source_candidates_sha256") != EXPECTED_CANDIDATES_SHA256
        or [item.get("scenario_ref") for item in packet.get("items", [])]
        != [item.scenario_ref for item in candidates]
        or any(item.get("review_state") != "PENDING" for item in packet.get("items", []))
    ):
        _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    decisions = _validate_review(decisions_doc, candidates, by_id, children, by_label, c1_decisions)
    if _sha256(decision_bytes) != EXPECTED_DECISIONS_SHA256:
        _reject("DATASET_NONDETERMINISTIC")
    selected = _select(candidates)
    selected_weak = [item for item in selected if item.category == "WEAK_EVIDENCE"]
    if (
        len(selected_weak) != 4
        or any(len(decisions[item.scenario_ref]["reviewed_target_ids"]) != 1 for item in selected_weak)
        or sum(item.category != "TARGET_ABSENT" for item in selected) != 42
        or sum(item.wrong_context_challenge for item in selected) != 8
        or sum(item.repeat_challenge for item in selected) != 16
    ):
        _reject("DATASET_COUNT_MISMATCH")
    scenario_bytes = _json_bytes([item.to_dict() for item in selected])
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "C2_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW",
        "dataset_ref": blueprint["dataset_ref"],
        "batch_ref": blueprint["batch_ref"],
        "function_commit": blueprint["function_commit"],
        "source_data_commit": SOURCE_DATA_COMMIT,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "c1_disposition": "REJECTED_PREEXECUTION_ORACLE_CONTRACT_MISMATCH",
        "nodes": 736,
        "value_envelope_count": 0,
        "candidates": 56,
        "accepted": 56,
        "execution_scenarios": 48,
        "target_present": 42,
        "target_absent": 6,
        "wrong_context": 8,
        "repeat_subset": 16,
        "weak_candidates_with_unique_target": 5,
        "weak_execution_with_unique_target": 4,
        "category_counts": dict(sorted(Counter(item.category for item in selected).items())),
        "reviewed_scenarios": 56,
        "random_rechecks": 8,
        "dual_reviews": 0,
        "elapsed_minutes": decisions_doc["elapsed_minutes"],
        "oracle_status": "ABSENT_PHASE2B_NOT_APPROVED",
        "c1_tree_sha256": SOURCE_TREE_SHA256,
        "blueprint_sha256": _sha256(blueprint_bytes),
        "tree_sha256": _sha256(tree_bytes),
        "candidates_sha256": _sha256(candidate_bytes),
        "review_packet_sha256": _sha256(packet_bytes),
        "review_decisions_sha256": _sha256(decision_bytes),
        "scenarios_sha256": _sha256(scenario_bytes),
    }
    report_bytes = _json_bytes(report)
    for path, content in ((scenarios_output, scenario_bytes), (report_output, report_bytes)):
        if path.exists() and path.read_bytes() != content:
            _reject("DATASET_NONDETERMINISTIC")
        if not path.exists():
            path.write_bytes(content)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-c1-dir", type=Path, required=True)
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--scenarios-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    report = verify_and_freeze(
        args.source_c1_dir,
        args.blueprint,
        args.tree,
        args.candidates,
        args.packet,
        args.decisions,
        args.scenarios_output,
        args.report_output,
    )
    print(
        "B03C2_PHASE2A_VERIFIED "
        f"nodes={report['nodes']} candidates={report['candidates']} "
        f"execution={report['execution_scenarios']} weak_targets=5 oracle=ABSENT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
