#!/usr/bin/env python3
"""Generate the independent H2 local-embedding clean-room calibration data."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from treeguard.hashing import canonical_digest


SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
CANDIDATE_SCHEMA_VERSION = "treeguard.h2-local-candidates.v1"
CANDIDATE_ORACLE_SCHEMA_VERSION = "treeguard.h2-local-candidate-oracle.v1"
SILVER_REVIEW_SCHEMA_VERSION = "treeguard.h2-local-silver-review.v1"
SCENARIO_SCHEMA_VERSION = "treeguard.h2-local-scenarios.v1"
ORACLE_SCHEMA_VERSION = "treeguard.h2-local-oracle-sidecar.v1"
MANIFEST_SCHEMA_VERSION = "treeguard.h2-local-manifest.v1"
GENERATOR_VERSION = "treeguard.h2-local-cleanroom-generator.v1"
GENERATOR_SEED = "zhuqiong-h2-local-20260805-v1"
TREE_NODE_COUNT = 733

CANDIDATE_COUNTS = {
    "NON_LITERAL": 12,
    "LEXICAL_BASELINE": 5,
    "BOUNDARY_VARIATION": 4,
    "CROSS_BRANCH_INTERFERENCE": 5,
    "HARD_NEGATIVE": 5,
    "EXPLICIT_EMPTY": 5,
}
EXECUTION_COUNTS = {
    "NON_LITERAL": 10,
    "LEXICAL_BASELINE": 4,
    "BOUNDARY_VARIATION": 3,
    "CROSS_BRANCH_INTERFERENCE": 3,
    "HARD_NEGATIVE": 4,
    "EXPLICIT_EMPTY": 4,
}
NON_LITERAL_EXECUTION_COUNTS = {
    "SYNONYM": 2,
    "ABBREVIATION": 2,
    "COLLOQUIAL_PURPOSE": 2,
    "MINOR_TYPO": 2,
    "CROSS_LEVEL": 2,
}
SILVER_PASS_CODES = (
    "PROVENANCE_VALID",
    "CATEGORY_EXCLUSIVE",
    "ORACLE_DETERMINATE",
    "TEXT_UNAMBIGUOUS",
    "DISTRACTOR_JUSTIFIED",
    "NO_ANSWER_LEAK",
    "CONTRACT_VALID",
)

DOMAIN_LABELS = (
    "晨堤巡守编组",
    "澜芯供水维护",
    "羽门疏导组织",
    "砾幕分隔巡检",
    "云匣排烟养护",
    "微昼照明保障",
    "鸣链通信协同",
    "甲舟装备轮护",
    "练序演训调度",
    "火票作业管控",
    "阔径通行维护",
    "墨栈档案复核",
)


class H2DataError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _special_nodes() -> dict[str, dict[str, Any]]:
    rows = (
        ("T01", 1, "余烬复看间隔", "integer", False),
        ("T02", 2, "泵组静置复启标记", "string", False),
        ("T03", 4, "隔烟帘归位确认", "boolean", False),
        ("T04", 6, "微昼应急灯自检周期", "integer", False),
        ("T05", 7, "鸣链手台联测状态", "string", False),
        ("T06", 8, "甲舟气瓶轮换序号", "string", False),
        ("T07", 3, "羽门集合点容纳量", "integer", False),
        ("T08", 11, "阔径转弯净空记录", "float", False),
        ("T09", 2, "澜芯取水口启闭状态", "boolean", False),
        ("T10", 10, "火票监护人到场确认", "boolean", False),
        ("T11", 4, "砾幕防火门闭合反馈", "boolean", False),
        ("T12", 9, "练序复盘意见归档位", "string", True),
        ("T13", 1, "晨堤交接班确认时刻", "time_code", False),
        ("T14", 2, "澜芯稳压泵巡查状态", "boolean", False),
        ("T15", 3, "羽门疏导员编组编号", "string", True),
        ("T16", 5, "云匣排烟窗启闭反馈", "boolean", False),
        ("T17", 6, "微昼备用照明续航时长", "integer", False),
        ("T18", 2, "泵房阀组试转结果", "string", False),
        ("T19", 4, "分隔带门扇闭合率", "float", False),
        ("T20", 5, "排烟口联动响应码", "string", False),
        ("T21", 8, "器材架位复核批次", "string", True),
        ("T22", 11, "阔径主通路状态", "string", False),
        ("X22", 3, "羽门疏散通路状态", "string", False),
        ("T23", 12, "墨栈归档复核时间", "time_code", False),
        ("X23", 1, "晨堤值守复核时间", "time_code", False),
        ("T24", 7, "鸣链调度联络状态", "string", False),
        ("X24", 9, "练序导演联络状态", "string", False),
        ("T25", 4, "砾幕分区封闭状态", "boolean", False),
        ("X25", 10, "火票作业区封闭状态", "boolean", False),
        ("T26", 2, "澜芯水源补给记录", "string", True),
        ("X26", 8, "甲舟器材补给记录", "string", True),
        ("T27", 5, "云匣排烟复位确认", "boolean", False),
        ("T28", 6, "微昼灯带旁路标记", "boolean", False),
        ("T29", 7, "鸣链备用频道编号", "string", False),
        ("T30", 10, "火票临时隔离时限", "integer", False),
        ("T31", 11, "阔径临停区占用状态", "boolean", False),
    )
    positions: dict[int, int] = defaultdict(int)
    result: dict[str, dict[str, Any]] = {}
    for key, domain, label, value_type, is_list in rows:
        positions[domain] += 1
        ordinal = positions[domain]
        result[key] = {
            "domain": domain,
            "program": (ordinal - 1) // 11 + 1,
            "slot": (ordinal - 1) % 11 + 1,
            "label": label,
            "value_type": value_type,
            "is_list": is_list,
        }
    return result


SPECIAL_NODES = _special_nodes()


def _scenario_rows() -> tuple[dict[str, Any], ...]:
    rows = (
        ("H2C-001", "NON_LITERAL", "SYNONYM", "请登记复查残火的等待时长。", "复查残火", "等待时长", None, "T01"),
        ("H2C-002", "NON_LITERAL", "SYNONYM", "水泵歇停后再开机的记号需要留存。", "再开机的记号", "水泵歇停", None, "T02"),
        ("H2C-003", "NON_LITERAL", "SYNONYM", "核验挡烟软幕回到原处的结果。", "回到原处", "挡烟软幕", None, "T03"),
        ("H2C-004", "NON_LITERAL", "ABBREVIATION", "补充WZ灯检周期。", "WZ灯检周期", None, None, "T04"),
        ("H2C-005", "NON_LITERAL", "ABBREVIATION", "记录ML手台联测是否通过。", "ML手台联测", None, None, "T05"),
        ("H2C-006", "NON_LITERAL", "ABBREVIATION", "登记JZ气瓶轮换号。", "JZ气瓶轮换号", None, None, "T06"),
        ("H2C-007", "NON_LITERAL", "COLLOQUIAL_PURPOSE", "人都撤出来以后往哪儿站得下，需要留个容量数。", "往哪儿站得下", "人都撤出来以后", None, "T07"),
        ("H2C-008", "NON_LITERAL", "COLLOQUIAL_PURPOSE", "大车拐弯别被挡住要看哪项，把测量结果记下来。", "拐弯别被挡住", "大车", None, "T08"),
        ("H2C-009", "NON_LITERAL", "MINOR_TYPO", "登记取水囗启闭状态。", "取水囗启闭状态", None, None, "T09"),
        ("H2C-010", "NON_LITERAL", "MINOR_TYPO", "补充监户人到场确认。", "监户人到场确认", None, None, "T10"),
        ("H2C-011", "NON_LITERAL", "CROSS_LEVEL", "分隔单元下游的门扇闭合回执需要归集。", "门扇闭合回执", "分隔单元下游", None, "T11"),
        ("H2C-012", "NON_LITERAL", "CROSS_LEVEL", "演训收尾层里的意见存放处需要登记。", "意见存放处", "演训收尾层", None, "T12"),
        ("H2C-013", "LEXICAL_BASELINE", None, "登记晨堤交接班确认时刻。", "晨堤交接班确认时刻", None, None, "T13"),
        ("H2C-014", "LEXICAL_BASELINE", None, "更新澜芯稳压泵巡查状态。", "澜芯稳压泵巡查状态", None, None, "T14"),
        ("H2C-015", "LEXICAL_BASELINE", None, "维护羽门疏导员编组编号。", "羽门疏导员编组编号", None, None, "T15"),
        ("H2C-016", "LEXICAL_BASELINE", None, "记录云匣排烟窗启闭反馈。", "云匣排烟窗启闭反馈", None, None, "T16"),
        ("H2C-017", "LEXICAL_BASELINE", None, "填写微昼备用照明续航时长。", "微昼备用照明续航时长", None, None, "T17"),
        ("H2C-018", "BOUNDARY_VARIATION", None, "补充泵房-阀组的试转结果。", "泵房-阀组", "试转结果", None, "T18"),
        ("H2C-019", "BOUNDARY_VARIATION", None, "登记分隔带／门扇闭合率。", "分隔带／门扇", "闭合率", None, "T19"),
        ("H2C-020", "BOUNDARY_VARIATION", None, "保存排烟口_联动响应码。", "排烟口_联动", "响应码", None, "T20"),
        ("H2C-021", "BOUNDARY_VARIATION", None, "维护器材架位·复核批次。", "器材架位·复核", "批次", None, "T21"),
        ("H2C-022", "CROSS_BRANCH_INTERFERENCE", None, "在阔径车辆转向范围登记通路状态。", "通路状态", "阔径车辆转向", None, "T22"),
        ("H2C-023", "CROSS_BRANCH_INTERFERENCE", None, "在墨栈卷宗范围维护复核时间。", "复核时间", "墨栈卷宗", None, "T23"),
        ("H2C-024", "CROSS_BRANCH_INTERFERENCE", None, "在鸣链调度范围确认联络状态。", "联络状态", "鸣链调度", None, "T24"),
        ("H2C-025", "CROSS_BRANCH_INTERFERENCE", None, "在砾幕分区范围记录封闭状态。", "封闭状态", "砾幕分区", None, "T25"),
        ("H2C-026", "CROSS_BRANCH_INTERFERENCE", None, "在澜芯水源范围归集补给记录。", "补给记录", "澜芯水源", None, "T26"),
        ("H2C-027", "HARD_NEGATIVE", None, "查找临时观测项，但排除云匣排烟复位确认。", "临时观测项", None, "云匣排烟复位确认", "T27"),
        ("H2C-028", "HARD_NEGATIVE", None, "查找临时照度项，但排除微昼灯带旁路标记。", "临时照度项", None, "微昼灯带旁路标记", "T28"),
        ("H2C-029", "HARD_NEGATIVE", None, "查找临时联络项，但排除鸣链备用频道编号。", "临时联络项", None, "鸣链备用频道编号", "T29"),
        ("H2C-030", "HARD_NEGATIVE", None, "查找临时边界项，但排除火票临时隔离时限。", "临时边界项", None, "火票临时隔离时限", "T30"),
        ("H2C-031", "HARD_NEGATIVE", None, "查找临时通行项，但排除阔径临停区占用状态。", "临时通行项", None, "阔径临停区占用状态", "T31"),
        ("H2C-032", "EXPLICIT_EMPTY", None, "登记弦月浮桥温差回声。", "弦月浮桥温差回声", None, None, None),
        ("H2C-033", "EXPLICIT_EMPTY", None, "补充砂钟云梯折光序列。", "砂钟云梯折光序列", None, None, None),
        ("H2C-034", "EXPLICIT_EMPTY", None, "维护蓝礁风铃静默频次。", "蓝礁风铃静默频次", None, None, None),
        ("H2C-035", "EXPLICIT_EMPTY", None, "记录纸鹤水闸漂移刻度。", "纸鹤水闸漂移刻度", None, None, None),
        ("H2C-036", "EXPLICIT_EMPTY", None, "登记琥珀雨棚回旋等级。", "琥珀雨棚回旋等级", None, None, None),
    )
    category_order: Counter[str] = Counter()
    result = []
    for scenario_id, category, subtype, requirement, target, scope, exclusion, node_key in rows:
        category_order[category] += 1
        node = SPECIAL_NODES.get(node_key) if node_key is not None else None
        annotations = [{"role": "TARGET", "text": target}]
        if scope is not None:
            annotations.append({"role": "SCOPE", "text": scope})
        if exclusion is not None:
            annotations.append({"role": "EXCLUSION", "text": exclusion})
        result.append(
            {
                "scenario_id": scenario_id,
                "category": category,
                "subtype": subtype,
                "selection_order": category_order[category],
                "request": {
                    "schema_version": "intent-request.v1",
                    "requirement_text": requirement,
                    "proposed_parent_node_id": None,
                    "node_kind_hint": "PROPERTY",
                    "value_type_hint": node["value_type"] if node is not None else "string",
                    "cardinality_hint": "MULTIPLE" if node is not None and node["is_list"] else "SINGLE",
                },
                "role_annotations": annotations,
                "source_class": SOURCE_CLASS,
                "fictional": True,
                "derived_from_real": False,
                "gold_eligible": False,
                "patch_eligible": False,
            }
        )
    return tuple(result)


SCENARIO_ROWS = _scenario_rows()


def _node_id(domain: int, program: int, slot: int) -> str:
    return f"ZH-H2-D{domain:02d}-P{program:02d}-F{slot:02d}"


def _special_by_position() -> dict[tuple[int, int, int], dict[str, Any]]:
    return {
        (item["domain"], item["program"], item["slot"]): item
        for item in SPECIAL_NODES.values()
    }


def build_tree() -> dict[str, Any]:
    special = _special_by_position()
    root_id = "ZH-H2-ROOT"
    root_label = "烛穹城安织网"
    root = {
        "metadata": {
            "node_id": root_id,
            "parent_node_id": None,
            "node_label": root_label,
            "node_name": f"{root_label}根域",
            "node_label_route": root_label,
            "node_type": "concept",
            "node_order": 1,
            "extension": {},
        },
        "subnodes": {},
    }
    for domain_index, domain_label in enumerate(DOMAIN_LABELS, start=1):
        domain_id = f"ZH-H2-D{domain_index:02d}"
        domain_route = f"{root_label}/-/{domain_label}"
        domain = {
            "metadata": {
                "node_id": domain_id,
                "parent_node_id": root_id,
                "node_label": domain_label,
                "node_name": f"烛穹·{domain_label}",
                "node_label_route": domain_route,
                "node_type": "concept",
                "node_order": domain_index,
                "extension": {},
            },
            "subnodes": {},
        }
        for program_index in range(1, 6):
            program_id = f"ZH-H2-D{domain_index:02d}-P{program_index:02d}"
            program_label = f"{domain_label}·层序{program_index}"
            program_route = f"{domain_route}/-/{program_label}"
            program = {
                "metadata": {
                    "node_id": program_id,
                    "parent_node_id": domain_id,
                    "node_label": program_label,
                    "node_name": f"烛穹·{program_label}",
                    "node_label_route": program_route,
                    "node_type": "concept",
                    "node_order": program_index,
                    "extension": {},
                },
                "subnodes": {},
            }
            for slot in range(1, 12):
                selected = special.get((domain_index, program_index, slot))
                if selected is None:
                    label = f"{domain_label}·层序{program_index}·校核项{slot:02d}"
                    value_type = ("string", "boolean", "integer")[(slot - 1) % 3]
                    is_list = slot % 5 == 0
                else:
                    label = selected["label"]
                    value_type = selected["value_type"]
                    is_list = selected["is_list"]
                node_id = _node_id(domain_index, program_index, slot)
                program["subnodes"][label] = {
                    "metadata": {
                        "node_id": node_id,
                        "parent_node_id": program_id,
                        "node_label": label,
                        "node_name": f"烛穹·{label}字段",
                        "node_label_route": f"{program_route}/-/{label}",
                        "node_type": "property",
                        "node_order": slot,
                        "value_type": value_type,
                        "is_list": is_list,
                        "value_constraints": {},
                        "value_placeholder": None,
                        "extension": {},
                    },
                    "subnodes": {},
                }
            domain["subnodes"][program_label] = program
        root["subnodes"][domain_label] = domain
    return {
        "metadata": {
            "map_id": "ZH-H2-CLEANROOM-RESOURCE",
            "version": "H2.LOCAL.DATA.1",
            "id": "ZH-H2-CLEANROOM-RESOURCE-V1",
            "map_type": "resource",
            "concurrent_version": 1,
            "source_class": SOURCE_CLASS,
            "fictional": True,
            "derived_from_real": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "generator_version": GENERATOR_VERSION,
            "generator_seed": GENERATOR_SEED,
        },
        "map_topology": {root_label: root},
    }


def _artifact(payload: dict[str, Any], hash_field: str) -> dict[str, Any]:
    return {**payload, hash_field: canonical_digest(payload)}


def _oracle_entries() -> tuple[dict[str, Any], ...]:
    entries = []
    for scenario in SCENARIO_ROWS:
        scenario_id = scenario["scenario_id"]
        category = scenario["category"]
        ordinal = int(scenario_id.rsplit("-", 1)[1])
        if category in {
            "NON_LITERAL",
            "LEXICAL_BASELINE",
            "BOUNDARY_VARIATION",
            "CROSS_BRANCH_INTERFERENCE",
        }:
            key = f"T{ordinal:02d}"
            spec = SPECIAL_NODES[key]
            entry = {
                "scenario_id": scenario_id,
                "oracle_type": "TARGET",
                "target_node_id": _node_id(spec["domain"], spec["program"], spec["slot"]),
            }
        elif category == "HARD_NEGATIVE":
            key = f"T{ordinal:02d}"
            spec = SPECIAL_NODES[key]
            entry = {
                "scenario_id": scenario_id,
                "oracle_type": "HARD_NEGATIVE",
                "excluded_node_ids": [
                    _node_id(spec["domain"], spec["program"], spec["slot"])
                ],
            }
        else:
            entry = {
                "scenario_id": scenario_id,
                "oracle_type": "EXPLICIT_EMPTY",
                "expected_empty_status": "NO_CANDIDATES",
            }
        entries.append(entry)
    return tuple(entries)


def build_candidate_artifacts() -> dict[str, dict[str, Any]]:
    tree = build_tree()
    candidates_payload = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "generator_version": GENERATOR_VERSION,
        "generator_seed": GENERATOR_SEED,
        "candidate_count": len(SCENARIO_ROWS),
        "category_counts": dict(CANDIDATE_COUNTS),
        "candidates": list(SCENARIO_ROWS),
    }
    candidates = _artifact(candidates_payload, "candidate_set_hash")
    oracle_payload = {
        "schema_version": CANDIDATE_ORACLE_SCHEMA_VERSION,
        "source_candidate_set_hash": candidates["candidate_set_hash"],
        "local_scoring_only": True,
        "model_input_eligible": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "entry_count": len(SCENARIO_ROWS),
        "entries": list(_oracle_entries()),
    }
    return {
        "tree.v1.json": tree,
        "scenario-candidates.v1.json": candidates,
        "candidate-oracle-sidecar.v1.json": _artifact(
            oracle_payload, "oracle_hash"
        ),
    }


def build_review(decisions: Mapping[str, str] | None = None) -> dict[str, Any]:
    chosen = decisions or {}
    entries = []
    for scenario in SCENARIO_ROWS:
        decision = chosen.get(scenario["scenario_id"], "PASS")
        if decision not in {"PASS", "REJECT"}:
            raise H2DataError("H2_SILVER_DECISION_INVALID")
        entries.append(
            {
                "scenario_id": scenario["scenario_id"],
                "decision": decision,
                "reason_codes": list(SILVER_PASS_CODES) if decision == "PASS" else ["SILVER_REJECTED"],
            }
        )
    payload = {
        "schema_version": SILVER_REVIEW_SCHEMA_VERSION,
        "review_status": "CODEX_SILVER_REVIEWED",
        "reviewer_role": "CODEX_SILVER_REVIEWER",
        "source_candidate_set_hash": build_candidate_artifacts()["scenario-candidates.v1.json"]["candidate_set_hash"],
        "gold_eligible": False,
        "production_qualification": False,
        "patch_eligible": False,
        "decision_counts": dict(sorted(Counter(item["decision"] for item in entries).items())),
        "entries": entries,
    }
    return _artifact(payload, "review_hash")


def select_execution_ids(review: Mapping[str, Any]) -> tuple[str, ...]:
    decisions = {item["scenario_id"]: item["decision"] for item in review["entries"]}
    selected: list[str] = []
    for subtype, required in NON_LITERAL_EXECUTION_COUNTS.items():
        eligible = [
            item["scenario_id"]
            for item in SCENARIO_ROWS
            if item["category"] == "NON_LITERAL"
            and item["subtype"] == subtype
            and decisions.get(item["scenario_id"]) == "PASS"
        ]
        if len(eligible) < required:
            raise H2DataError("H2_SILVER_QUOTA_INSUFFICIENT")
        selected.extend(eligible[:required])
    for category in (
        "LEXICAL_BASELINE",
        "BOUNDARY_VARIATION",
        "CROSS_BRANCH_INTERFERENCE",
        "HARD_NEGATIVE",
        "EXPLICIT_EMPTY",
    ):
        required = EXECUTION_COUNTS[category]
        eligible = [
            item["scenario_id"]
            for item in SCENARIO_ROWS
            if item["category"] == category
            and decisions.get(item["scenario_id"]) == "PASS"
        ]
        if len(eligible) < required:
            raise H2DataError("H2_SILVER_QUOTA_INSUFFICIENT")
        selected.extend(eligible[:required])
    return tuple(sorted(selected))


def build_frozen_artifacts(review: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    candidates = build_candidate_artifacts()
    selected_ids = select_execution_ids(review)
    scenarios = [item for item in SCENARIO_ROWS if item["scenario_id"] in selected_ids]
    candidate_oracle = candidates["candidate-oracle-sidecar.v1.json"]
    oracle_entries = [
        item for item in candidate_oracle["entries"] if item["scenario_id"] in selected_ids
    ]
    scenario_payload = {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "source_candidate_set_hash": candidates["scenario-candidates.v1.json"]["candidate_set_hash"],
        "source_review_hash": review["review_hash"],
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "execution_count": len(scenarios),
        "category_counts": dict(EXECUTION_COUNTS),
        "non_literal_subtype_counts": dict(NON_LITERAL_EXECUTION_COUNTS),
        "scenarios": scenarios,
    }
    scenario_artifact = _artifact(scenario_payload, "scenario_set_hash")
    oracle_payload = {
        "schema_version": ORACLE_SCHEMA_VERSION,
        "source_scenario_set_hash": scenario_artifact["scenario_set_hash"],
        "local_scoring_only": True,
        "model_input_eligible": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "entry_count": len(oracle_entries),
        "entries": oracle_entries,
    }
    oracle_artifact = _artifact(oracle_payload, "oracle_hash")
    tree = candidates["tree.v1.json"]
    manifest_payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_status": "FROZEN_CODEX_SILVER",
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "production_qualification": False,
        "patch_eligible": False,
        "embedding_used": False,
        "a_baseline_status": "NOT_RUN",
        "generator_version": GENERATOR_VERSION,
        "generator_seed": GENERATOR_SEED,
        "tree_node_count": TREE_NODE_COUNT,
        "candidate_count": 36,
        "candidate_category_counts": dict(CANDIDATE_COUNTS),
        "execution_count": 28,
        "execution_category_counts": dict(EXECUTION_COUNTS),
        "non_literal_subtype_counts": dict(NON_LITERAL_EXECUTION_COUNTS),
        "artifact_hashes": {
            "tree": canonical_digest(tree),
            "scenario_candidates": candidates["scenario-candidates.v1.json"]["candidate_set_hash"],
            "candidate_oracle": candidate_oracle["oracle_hash"],
            "silver_review": review["review_hash"],
            "scenarios": scenario_artifact["scenario_set_hash"],
            "oracle": oracle_artifact["oracle_hash"],
        },
    }
    return {
        "silver-review.v1.json": dict(review),
        "scenarios.v1.json": scenario_artifact,
        "oracle-sidecar.v1.json": oracle_artifact,
        "manifest.v1.json": _artifact(manifest_payload, "manifest_hash"),
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_exclusive(path: Path, value: Any) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(_json_bytes(value))
    except FileExistsError:
        raise H2DataError("H2_OUTPUT_EXISTS") from None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise H2DataError("H2_FROZEN_SOURCE_INVALID") from None


def generate_candidates(output_dir: Path) -> None:
    if output_dir.exists():
        raise H2DataError("H2_OUTPUT_EXISTS")
    output_dir.mkdir(parents=True)
    for name, artifact in build_candidate_artifacts().items():
        _write_exclusive(output_dir / name, artifact)


def freeze_dataset(output_dir: Path) -> None:
    if not output_dir.is_dir():
        raise H2DataError("H2_FROZEN_SOURCE_INVALID")
    candidates = build_candidate_artifacts()
    for name, expected in candidates.items():
        if _read_json(output_dir / name) != expected:
            raise H2DataError("H2_FROZEN_SOURCE_INVALID")
    review = build_review()
    for name, artifact in build_frozen_artifacts(review).items():
        _write_exclusive(output_dir / name, artifact)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("candidates", "freeze"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.phase == "candidates":
            generate_candidates(args.output_dir)
            report = {"status": "CANDIDATES_FROZEN", "candidate_count": 36, "embedding_used": False}
        else:
            freeze_dataset(args.output_dir)
            report = {"status": "FROZEN_CODEX_SILVER", "execution_count": 28, "embedding_used": False}
    except H2DataError as exc:
        print(json.dumps({"valid": False, "error_code": exc.code}, sort_keys=True))
        return 2
    print(json.dumps({"valid": True, **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
