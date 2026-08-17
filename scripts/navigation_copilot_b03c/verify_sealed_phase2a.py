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


SCHEMA_VERSION = "treeguard.navigation-copilot-b03c-phase2a-preflight.v1"
CATEGORY_ORDER = (
    "LITERAL_UNIQUE", "NONLITERAL_UNIQUE", "STRUCTURAL_INTERFERENCE",
    "MULTI_ACCEPTABLE", "CLARIFICATION", "WEAK_EVIDENCE", "TARGET_ABSENT",
)
CANDIDATE_QUOTAS = dict(zip(CATEGORY_ORDER, (11, 12, 10, 4, 7, 5, 7), strict=True))
FINAL_QUOTAS = dict(zip(CATEGORY_ORDER, (10, 10, 8, 4, 6, 4, 6), strict=True))
BRANCH_QUOTAS = {
    "project": (81, 18, 50, 13), "workstation": (87, 19, 54, 14),
    "tools": (92, 20, 57, 15), "materials": (86, 19, 53, 14),
    "maintenance": (96, 21, 59, 16), "sample": (88, 19, 55, 14),
    "safety": (101, 22, 62, 17), "handoff": (104, 21, 66, 17),
}
MULTI_GROUPS = {
    "b03c:034": "工位预约对象", "b03c:035": "设备维护对象",
    "b03c:036": "安全检查范围", "b03c:037": "成果附件说明",
}
CLARIFICATION_RULES = {
    "b03c:038": (("激光切割台预约", "三维打印台预约", "木工台预约", "电子焊接台预约"), "三维打印台预约"),
    "b03c:039": (("手持钻借用", "热风枪借用", "万用表借用", "雕刻刀借用"), "万用表借用"),
    "b03c:040": (("板材登记", "线材登记", "涂料登记", "紧固件登记"), "涂料登记"),
    "b03c:041": (("漏液报告", "异响报告", "冒烟报告"), "冒烟报告"),
    "b03c:042": (("返工要求", "报废申请", "移交准备"), "报废申请"),
    "b03c:043": (("实际归还", "工具归还"), "实际归还"),
    "b03c:044": (("完成时间", "完成摘要"), "完成摘要"),
}
RANDOM_RECHECKS = ("b03c:002", "b03c:009", "b03c:016", "b03c:023", "b03c:030", "b03c:037", "b03c:044", "b03c:051")


class Phase2AError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject(code: str) -> None:
    raise Phase2AError(code)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _tree_index(tree: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    by_id: dict[str, dict[str, Any]] = {}
    children: dict[str, list[str]] = defaultdict(list)
    stack = list(tree["map_topology"].values())
    while stack:
        entry = stack.pop()
        metadata = entry["metadata"]
        node_id = metadata["node_id"]
        if node_id in by_id:
            _reject("DATASET_REFERENCE_INVALID")
        by_id[node_id] = metadata
        parent_id = metadata.get("parent_node_id")
        if parent_id is not None:
            children[parent_id].append(node_id)
        if "value" in entry:
            _reject("DATASET_VALUE_ENVELOPE_PRESENT")
        stack.extend(entry.get("subnodes", {}).values())
    return by_id, children


def _label_index(by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    result = {metadata["node_name"]: node_id for node_id, metadata in by_id.items()}
    if len(result) != len(by_id):
        _reject("DATASET_REPEATED_VECTOR")
    return result


def _validate_tree(tree: dict[str, Any], blueprint: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], str]:
    imported = adapt_tree_document(tree)
    if not imported.is_valid or imported.tree is None:
        _reject("DATASET_REFERENCE_INVALID")
    if imported.observed_node_count != 736 or imported.observed_value_count != 0:
        _reject("DATASET_COUNT_MISMATCH")
    if blueprint.get("source_class") != "CLEANROOM_SYNTHETIC" or blueprint.get("fictional") is not True:
        _reject("DATASET_SOURCE_CLASS_INVALID")
    if blueprint.get("derived_from_real") is not False or blueprint.get("gold_eligible") is not False:
        _reject("DATASET_SOURCE_CLASS_INVALID")
    by_id, children = _tree_index(tree)
    roles = Counter(metadata["extension"]["dataset_role"] for metadata in by_id.values())
    if roles != Counter({"curated": 160, "background": 456, "filler": 120}):
        _reject("DATASET_COUNT_MISMATCH")
    branch_roles: dict[str, Counter[str]] = defaultdict(Counter)
    for metadata in by_id.values():
        branch = metadata["extension"]["branch_key"]
        if branch != "root":
            branch_roles[branch][metadata["extension"]["dataset_role"]] += 1
    for branch, (total, curated, background, filler) in BRANCH_QUOTAS.items():
        actual = branch_roles[branch]
        if (sum(actual.values()), actual["curated"], actual["background"], actual["filler"]) != (total, curated, background, filler):
            _reject("DATASET_COUNT_MISMATCH")
    for branch in blueprint.get("branches", []):
        denominator = len(branch.get("background_subjects", [])) * blueprint["background_pairing"]["facet_count"]
        numerator = branch.get("background_pair_count")
        if not isinstance(numerator, int) or denominator <= 0 or numerator * 10_000 // denominator > 3_500:
            _reject("DATASET_CARTESIAN_DENSITY_HIGH")
    return by_id, children, imported.tree.snapshot_hash


def _validate_review(
    decisions_doc: dict[str, Any], candidates: list[SealedScenario], by_id: dict[str, dict[str, Any]],
    children: dict[str, list[str]], tree_bytes: bytes, candidate_bytes: bytes, packet_bytes: bytes,
) -> dict[str, dict[str, Any]]:
    if decisions_doc.get("producer_module") != "record_sealed_reviews":
        _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    if (
        decisions_doc.get("source_tree_sha256") != _sha256(tree_bytes)
        or decisions_doc.get("source_candidates_sha256") != _sha256(candidate_bytes)
        or decisions_doc.get("source_review_packet_sha256") != _sha256(packet_bytes)
    ):
        _reject("DATASET_NONDETERMINISTIC")
    if decisions_doc.get("elapsed_minutes") not in range(1, 721) or decisions_doc.get("dual_review_count") != 0:
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")
    reviewed_nodes = decisions_doc.get("reviewed_node_ids")
    curated = sorted(
        node_id for node_id, metadata in by_id.items()
        if metadata["extension"]["dataset_role"] == "curated"
    )
    boundary: list[str] = []
    for branch_key in sorted(BRANCH_QUOTAS):
        background = sorted(
            node_id for node_id, metadata in by_id.items()
            if metadata["extension"]["branch_key"] == branch_key
            and metadata["extension"]["dataset_role"] == "background"
        )
        filler = sorted(
            node_id for node_id, metadata in by_id.items()
            if metadata["extension"]["branch_key"] == branch_key
            and metadata["extension"]["dataset_role"] == "filler"
        )
        boundary.extend(background[:3])
        boundary.extend(filler[:1])
    if reviewed_nodes != sorted(curated + boundary):
        _reject("DATASET_REFERENCE_INVALID")
    rechecks = decisions_doc.get("random_recheck_scenario_refs")
    if rechecks != list(RANDOM_RECHECKS):
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")
    decision_items = decisions_doc.get("decisions")
    if not isinstance(decision_items, list) or len(decision_items) != 56:
        _reject("DATASET_COUNT_MISMATCH")
    if [item.get("scenario_ref") for item in decision_items] != [item.scenario_ref for item in candidates]:
        _reject("DATASET_REFERENCE_INVALID")
    rationales = [item.get("rationale") for item in decision_items]
    if any(not isinstance(value, str) or len(value) < 16 for value in rationales) or len(set(rationales)) != 56:
        _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    label_index = _label_index(by_id)
    labels_and_aliases = [
        text for metadata in by_id.values()
        for text in [metadata["node_name"], *metadata["extension"].get("aliases", [])]
    ]
    by_ref: dict[str, dict[str, Any]] = {}
    for scenario, decision in zip(candidates, decision_items, strict=True):
        if decision.get("decision") != "SILVER_ACCEPTED" or decision.get("finding_codes") != []:
            _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
        reviewed = decision.get("reviewed_target_ids")
        compatible = decision.get("compatible_target_ids")
        if not isinstance(reviewed, list) or not isinstance(compatible, list):
            _reject("DATASET_REFERENCE_INVALID")
        if any(node_id not in by_id for node_id in reviewed + compatible):
            _reject("DATASET_REFERENCE_INVALID")
        if any(by_id[node_id]["extension"]["dataset_role"] == "filler" for node_id in reviewed + compatible):
            _reject("DATASET_FILLER_TARGETED")
        try:
            if scenario.category == "MULTI_ACCEPTABLE":
                group_id = label_index[MULTI_GROUPS[scenario.scenario_ref]]
                expected = sorted(
                    node_id for node_id in children[group_id]
                    if by_id[node_id]["extension"]["dataset_role"] == "curated"
                )
                verify_target_set_exhaustiveness(compatible, expected)
                verify_target_set_exhaustiveness(reviewed, expected)
            elif scenario.category == "CLARIFICATION":
                contrast_labels, resolved_label = CLARIFICATION_RULES[scenario.scenario_ref]
                expected_contrast = sorted(label_index[label] for label in contrast_labels)
                expected_resolved = [label_index[resolved_label]]
                if decision.get("contrast_node_ids") != expected_contrast or decision.get("resolved_target_ids") != expected_resolved:
                    _reject("DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT")
                verify_clarification_contrast(expected_contrast, expected_resolved)
            elif scenario.category == "TARGET_ABSENT":
                verify_absence_contract(
                    scenario.requirement_text, labels_and_aliases, reviewed,
                    decision.get("satisfiable_supertype_ids", []),
                )
            elif scenario.category == "WEAK_EVIDENCE":
                if reviewed or compatible or not decision.get("evidence_gap"):
                    _reject("DATASET_ORACLE_OVERCLAIM")
            elif len(reviewed) != 1 or reviewed != compatible:
                _reject("DATASET_SCENARIO_COVERAGE_DUPLICATE")
        except ContractViolation as exc:
            _reject(exc.code)
        by_ref[scenario.scenario_ref] = decision
    return by_ref


def _select(candidates: list[SealedScenario], decisions: dict[str, dict[str, Any]]) -> list[SealedScenario]:
    used: Counter[str] = Counter()
    selected: list[SealedScenario] = []
    for scenario in candidates:
        if decisions[scenario.scenario_ref]["decision"] != "SILVER_ACCEPTED":
            continue
        if used[scenario.category] < FINAL_QUOTAS[scenario.category]:
            selected.append(scenario)
            used[scenario.category] += 1
    if used != Counter(FINAL_QUOTAS) or len(selected) != 48:
        _reject("DATASET_COUNT_MISMATCH")
    return selected


def verify_and_freeze(
    blueprint_path: Path, tree_path: Path, candidates_path: Path, packet_path: Path,
    decisions_path: Path, scenarios_output: Path, report_output: Path,
) -> dict[str, Any]:
    directory = tree_path.parent
    if any(directory.glob("*oracle*")):
        _reject("DATASET_ORACLE_OVERCLAIM")
    blueprint_bytes = blueprint_path.read_bytes()
    tree_bytes = tree_path.read_bytes()
    candidate_bytes = candidates_path.read_bytes()
    packet_bytes = packet_path.read_bytes()
    decision_bytes = decisions_path.read_bytes()
    blueprint = strict_json_loads(blueprint_bytes)
    tree = strict_json_loads(tree_bytes)
    raw_candidates = strict_json_loads(candidate_bytes)
    packet = strict_json_loads(packet_bytes)
    decisions_doc = strict_json_loads(decision_bytes)
    by_id, children, tree_digest = _validate_tree(tree, blueprint)
    candidates = [SealedScenario.from_dict(item) for item in raw_candidates]
    if len(candidates) != 56 or Counter(item.category for item in candidates) != Counter(CANDIDATE_QUOTAS):
        _reject("DATASET_COUNT_MISMATCH")
    if any(item.tree_digest != tree_digest for item in candidates):
        _reject("DATASET_REFERENCE_INVALID")
    if (
        packet.get("producer_module") != "author_sealed_data"
        or packet.get("source_tree_sha256") != _sha256(tree_bytes)
        or packet.get("source_candidates_sha256") != _sha256(candidate_bytes)
        or any(item.get("review_state") != "PENDING" for item in packet.get("items", []))
    ):
        _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    decisions = _validate_review(decisions_doc, candidates, by_id, children, tree_bytes, candidate_bytes, packet_bytes)
    selected = _select(candidates, decisions)
    if sum(item.wrong_context_challenge for item in selected) != 8 or sum(item.repeat_challenge for item in selected) != 16:
        _reject("DATASET_COUNT_MISMATCH")
    if sum(item.category != "TARGET_ABSENT" for item in selected) != 42:
        _reject("DATASET_COUNT_MISMATCH")
    forbidden_absent_hints = ("树中没有", "不存在", "找不到", "未收录")
    if any(any(hint in item.requirement_text for hint in forbidden_absent_hints) for item in selected if item.category == "TARGET_ABSENT"):
        _reject("DATASET_ORACLE_OVERCLAIM")
    scenario_bytes = _json_bytes([item.to_dict() for item in selected])
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW",
        "dataset_ref": blueprint["dataset_ref"],
        "batch_ref": blueprint["batch_ref"],
        "function_commit": blueprint["function_commit"],
        "source_class": blueprint["source_class"],
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "nodes": 736,
        "value_envelope_count": 0,
        "candidates": 56,
        "accepted": 56,
        "execution_scenarios": 48,
        "target_present": 42,
        "target_absent": 6,
        "wrong_context": 8,
        "repeat_subset": 16,
        "category_counts": dict(sorted(Counter(item.category for item in selected).items())),
        "reviewed_nodes": 192,
        "random_rechecks": 8,
        "dual_reviews": 0,
        "oracle_status": "ABSENT_PHASE2B_NOT_APPROVED",
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
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--scenarios-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    report = verify_and_freeze(
        args.blueprint, args.tree, args.candidates, args.packet, args.decisions,
        args.scenarios_output, args.report_output,
    )
    print(
        "B03C_PHASE2A_VERIFIED "
        f"nodes={report['nodes']} candidates={report['candidates']} execution={report['execution_scenarios']} oracle=ABSENT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
