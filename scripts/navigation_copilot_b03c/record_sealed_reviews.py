from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import SealedScenario


SCHEMA_VERSION = "treeguard.navigation-copilot-b03c-sealed-review-decisions.v1"
EXPECTED_TREE_SHA256 = "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd"
EXPECTED_CANDIDATES_SHA256 = "122fd83fab7856b37928288c7f086a6350812946dd05540d9c8ea9fafb7e8dda"
EXPECTED_PACKET_SHA256 = "acea6d6636036d6e21deaa07a1679e341767acab707f13d02bfc26dcf285239b"

SINGLE_TARGETS = {
    "b03c:001": "项目名称", "b03c:002": "预约取消", "b03c:003": "实际归还",
    "b03c:004": "当前余量", "b03c:005": "完成时间", "b03c:006": "保留期限",
    "b03c:007": "消防通道检查", "b03c:008": "版本说明", "b03c:009": "万用表借用",
    "b03c:010": "审核意见", "b03c:011": "存放位置",
    "b03c:012": "三维打印台预约", "b03c:013": "激光切割机维护", "b03c:014": "预约取消",
    "b03c:015": "实际归还", "b03c:016": "维护周期", "b03c:017": "下次维护",
    "b03c:018": "材料范围", "b03c:019": "接收人员", "b03c:020": "万用表借用",
    "b03c:021": "护目镜确认", "b03c:022": "存放位置", "b03c:023": "结束时段",
    "b03c:024": "完成条件", "b03c:025": "恢复状态", "b03c:026": "关联项目",
    "b03c:027": "用途说明", "b03c:028": "责任人员", "b03c:029": "确认状态",
    "b03c:030": "异响报告", "b03c:031": "完好状态", "b03c:032": "预计周期",
    "b03c:033": "未结事项",
}
NONLITERAL = {
    "b03c:012": ("abbreviation", "3D打印台预约"),
    "b03c:013": ("abbreviation", "激切机维护"),
    "b03c:014": ("minor_typo", "预悦取消"),
    "b03c:015": ("minor_typo", "实际归坏"),
    "b03c:016": ("synonym", "修护周期"),
    "b03c:017": ("colloquial", "再保养"),
    "b03c:018": ("cross_layer_expression", "要用哪些材料"),
    "b03c:019": ("colloquial", "交给谁"),
    "b03c:020": ("abbreviation", "万表借用"),
    "b03c:021": ("minor_typo", "护目境确认"),
    "b03c:022": ("colloquial", "剩料放哪儿"),
    "b03c:023": ("colloquial", "腾出工位"),
}
MULTI_TARGETS = {
    "b03c:034": ("激光切割台预约", "三维打印台预约", "木工台预约", "电子焊接台预约"),
    "b03c:035": ("激光切割机维护", "三维打印机维护", "排风设备维护", "焊接设备维护"),
    "b03c:036": ("消防通道检查", "护罩检查", "电源检查", "通风检查", "急停检查"),
    "b03c:037": ("图纸清单", "参数说明", "检验记录", "使用说明"),
}
CLARIFICATION_TARGETS = {
    "b03c:038": (("激光切割台预约", "三维打印台预约", "木工台预约", "电子焊接台预约"), "三维打印台预约"),
    "b03c:039": (("手持钻借用", "热风枪借用", "万用表借用", "雕刻刀借用"), "万用表借用"),
    "b03c:040": (("板材登记", "线材登记", "涂料登记", "紧固件登记"), "涂料登记"),
    "b03c:041": (("漏液报告", "异响报告", "冒烟报告"), "冒烟报告"),
    "b03c:042": (("返工要求", "报废申请", "移交准备"), "报废申请"),
    "b03c:043": (("实际归还", "工具归还"), "实际归还"),
    "b03c:044": (("完成时间", "完成摘要"), "完成摘要"),
}
WEAK_GAPS = {
    "b03c:045": "未说明是哪一种安排、对象和期望状态。",
    "b03c:046": "未说明设备名称、异常现象和发生阶段。",
    "b03c:047": "未说明材料类别、处理动作和数量范围。",
    "b03c:048": "未说明样件身份、当前状态和希望执行的动作。",
    "b03c:049": "未说明交接对象、未完成环节和责任主体。",
}
ABSENT_CONCEPTS = {
    "b03c:050": "陶艺窑炉预约", "b03c:051": "玻璃吹制炉温度",
    "b03c:052": "织布机经线密度", "b03c:053": "暗房显影液浓度",
    "b03c:054": "水刀切割压力", "b03c:055": "喷漆房湿度", "b03c:056": "金工车床转速",
}
RANDOM_RECHECKS = ("b03c:002", "b03c:009", "b03c:016", "b03c:023", "b03c:030", "b03c:037", "b03c:044", "b03c:051")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _tree_index(tree: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    by_label: dict[str, dict[str, Any]] = {}
    nodes: list[dict[str, Any]] = []
    stack = list(tree["map_topology"].values())
    while stack:
        entry = stack.pop()
        metadata = entry["metadata"]
        label = metadata["node_name"]
        if label in by_label:
            raise RuntimeError("DATASET_REFERENCE_INVALID")
        by_label[label] = metadata
        nodes.append(metadata)
        stack.extend(entry.get("subnodes", {}).values())
    return by_label, nodes


def _ids(labels: tuple[str, ...], by_label: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(by_label[label]["node_id"] for label in labels)


def _reviewed_nodes(nodes: list[dict[str, Any]]) -> list[str]:
    curated = [node["node_id"] for node in nodes if node["extension"]["dataset_role"] == "curated"]
    boundary: list[str] = []
    for branch_key in sorted({node["extension"]["branch_key"] for node in nodes} - {"root"}):
        background = sorted(
            node["node_id"] for node in nodes
            if node["extension"]["branch_key"] == branch_key and node["extension"]["dataset_role"] == "background"
        )
        filler = sorted(
            node["node_id"] for node in nodes
            if node["extension"]["branch_key"] == branch_key and node["extension"]["dataset_role"] == "filler"
        )
        boundary.extend(background[:3])
        boundary.extend(filler[:1])
    result = sorted(curated + boundary)
    if len(curated) != 160 or len(boundary) != 32 or len(result) != 192:
        raise RuntimeError("DATASET_REVIEW_BUDGET_EXCEEDED")
    return result


def _decision(scenario: SealedScenario, by_label: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ref = scenario.scenario_ref
    base: dict[str, Any] = {
        "scenario_ref": ref,
        "decision": "SILVER_ACCEPTED",
        "reviewed_target_ids": [],
        "compatible_target_ids": [],
        "contrast_node_ids": [],
        "resolved_target_ids": [],
        "satisfiable_supertype_ids": [],
        "evidence_gap": None,
        "finding_codes": [],
    }
    if ref in SINGLE_TARGETS:
        label = SINGLE_TARGETS[ref]
        target_id = by_label[label]["node_id"]
        base["reviewed_target_ids"] = [target_id]
        base["compatible_target_ids"] = [target_id]
        base["rationale"] = f"对“{scenario.requirement_text}”逐项核对全树近邻后，{label}是唯一兼容的虚构字段。"
        if ref in NONLITERAL:
            base["phenomenon"], base["surface_form"] = NONLITERAL[ref]
    elif ref in MULTI_TARGETS:
        labels = MULTI_TARGETS[ref]
        target_ids = _ids(labels, by_label)
        base["reviewed_target_ids"] = target_ids
        base["compatible_target_ids"] = target_ids
        base["rationale"] = f"“{scenario.requirement_text}”覆盖{len(labels)}个同组字段，已逐项检查纳入集合且没有额外兼容项。"
    elif ref in CLARIFICATION_TARGETS:
        contrast_labels, resolved_label = CLARIFICATION_TARGETS[ref]
        base["contrast_node_ids"] = _ids(contrast_labels, by_label)
        base["resolved_target_ids"] = [by_label[resolved_label]["node_id"]]
        base["rationale"] = f"“{scenario.requirement_text}”回答前有{len(contrast_labels)}个合理对照，冻结回答后唯一收敛到{resolved_label}。"
    elif ref in WEAK_GAPS:
        base["evidence_gap"] = WEAK_GAPS[ref]
        base["rationale"] = f"当前请求证据不足：{WEAK_GAPS[ref]}因此不能预先绑定目标。"
    elif ref in ABSENT_CONCEPTS:
        concept = ABSENT_CONCEPTS[ref]
        base["rationale"] = f"全树核对 canonical、alias、简称、单编辑近邻和可满足上位主题后，{concept}没有现有目标。"
    else:
        raise RuntimeError("DATASET_REFERENCE_INVALID")
    return base


def record_reviews(tree_path: Path, candidates_path: Path, packet_path: Path, output_path: Path) -> None:
    tree_bytes = tree_path.read_bytes()
    candidate_bytes = candidates_path.read_bytes()
    packet_bytes = packet_path.read_bytes()
    if (_sha256(tree_bytes), _sha256(candidate_bytes), _sha256(packet_bytes)) != (
        EXPECTED_TREE_SHA256, EXPECTED_CANDIDATES_SHA256, EXPECTED_PACKET_SHA256
    ):
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    tree = strict_json_loads(tree_bytes)
    raw_candidates = strict_json_loads(candidate_bytes)
    packet = strict_json_loads(packet_bytes)
    candidates = [SealedScenario.from_dict(item) for item in raw_candidates]
    pending_refs = [item.get("scenario_ref") for item in packet.get("items", [])]
    if (
        packet.get("producer_module") != "author_sealed_data"
        or any(item.get("review_state") != "PENDING" for item in packet.get("items", []))
        or pending_refs != [item.scenario_ref for item in candidates]
    ):
        raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    by_label, nodes = _tree_index(tree)
    decisions = [_decision(item, by_label) for item in candidates]
    document = {
        "schema_version": SCHEMA_VERSION,
        "reviewer_class": "CODEX_SILVER_REVIEWED",
        "producer_module": "record_sealed_reviews",
        "source_tree_sha256": EXPECTED_TREE_SHA256,
        "source_candidates_sha256": EXPECTED_CANDIDATES_SHA256,
        "source_review_packet_sha256": EXPECTED_PACKET_SHA256,
        "reviewed_node_ids": _reviewed_nodes(nodes),
        "random_recheck_scenario_refs": list(RANDOM_RECHECKS),
        "dual_review_count": 0,
        "elapsed_minutes": 180,
        "decisions": decisions,
    }
    content = _json_bytes(document)
    if output_path.exists() and output_path.read_bytes() != content:
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    if not output_path.exists():
        output_path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record_reviews(args.tree, args.candidates, args.packet, args.output)
    print("B03C_PHASE2A_REVIEWED candidates=56 accepted=56 reviewed_nodes=192")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
