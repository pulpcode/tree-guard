"""Clean-room fictional cross-domain validation data for TreeGuard.

This module is deliberately self-contained. It does not import, inspect, or derive
from any existing domain dataset.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from treeguard.adapter import adapt_tree_document


DATASET_REF = "fictional-qinglan-library-control-v1"
RUN_REF = "qinglan-library-control-v1-run-004"
SEED = 20260730
TARGET_NODE_COUNT = 48
TARGET_SCENARIO_COUNT = 12
SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
PRIMARY_ROLE = "DOMAIN_CONTROL"
TREE_ID = "qinglan-library-control-tree"
TREE_VERSION = "QL-1.1"
VERSION_RECORD_ID = "qinglan-library-control-record-v2"

_ALLOWED_VALUE_TYPES = {"boolean", "integer", "string", "time_code"}
_EXPECTED_VALUE_TYPE_COUNTS = {
    "boolean": 4,
    "integer": 11,
    "string": 7,
    "time_code": 5,
}
_EXPECTED_CARDINALITY_COUNTS = {"MULTIPLE": 8, "SINGLE": 19}
_EXPECTED_OBSERVABLE_CATEGORIES = {
    "CONFLICT_VISIBLE",
    "NEED_CLARIFICATION",
    "NEED_EVIDENCE",
    "REFUSE_UNBOUNDED_COMBINATION",
    "STABLE_CANDIDATE",
    "STABLE_REPLAY_BASELINE",
}
_BOUNDARY_MARKERS = (
    "api_key",
    "authorization:",
    "bearer ",
    "password",
    "private_key",
)
_NUMBERED_NAME = re.compile(r"(?:^|[-_ ])\d+$")


@dataclass(frozen=True, slots=True)
class _NodeSpec:
    node_id: str
    label: str
    name: str
    parent_node_id: str | None
    kind: str
    family: str
    value_type: str | None = None
    is_list: bool | None = None


_NODES = (
    _NodeSpec("ql-001", "QINGLAN_COMMUNITY_LIBRARY", "青岚社区图书馆", None, "concept", "curated_core"),
    _NodeSpec("ql-002", "COLLECTION_RESOURCES", "馆藏资源", "ql-001", "concept", "curated_core"),
    _NodeSpec("ql-003", "SERVICE_SPACES", "服务空间", "ql-001", "concept", "curated_core"),
    _NodeSpec("ql-004", "READER_SERVICES", "读者服务", "ql-001", "concept", "curated_core"),
    _NodeSpec("ql-005", "PUBLIC_PROGRAMS", "公共活动", "ql-001", "concept", "curated_core"),
    _NodeSpec("ql-006", "PRINT_MATERIALS", "纸本文献", "ql-002", "concept", "curated_core"),
    _NodeSpec("ql-007", "SERIAL_PUBLICATIONS", "连载刊物", "ql-002", "concept", "curated_core"),
    _NodeSpec("ql-008", "DIGITAL_MATERIALS", "数字资料", "ql-002", "concept", "curated_core"),
    _NodeSpec("ql-009", "QUIET_READING_AREA", "静音阅览区", "ql-003", "concept", "curated_core"),
    _NodeSpec("ql-010", "GROUP_STUDY_ROOM", "小组研讨室", "ql-003", "concept", "curated_core"),
    _NodeSpec("ql-011", "MULTIPURPOSE_HALL", "多用途活动厅", "ql-003", "concept", "curated_core"),
    _NodeSpec("ql-012", "LENDING_SERVICE", "借阅办理", "ql-004", "concept", "curated_core"),
    _NodeSpec("ql-013", "SPACE_RESERVATION", "空间预约", "ql-004", "concept", "curated_core"),
    _NodeSpec("ql-014", "REFERENCE_HELP", "咨询协助", "ql-004", "concept", "curated_core"),
    _NodeSpec("ql-015", "READING_CIRCLE", "阅读分享会", "ql-005", "concept", "curated_core"),
    _NodeSpec("ql-016", "CRAFT_WORKSHOP", "手作工作坊", "ql-005", "concept", "curated_core"),
    _NodeSpec("ql-017", "COMMUNITY_EXHIBITION", "社区展览", "ql-005", "concept", "curated_core"),
    _NodeSpec("ql-018", "CIRCULATION_RULES", "流通规则", "ql-006", "concept", "blueprint_background"),
    _NodeSpec("ql-019", "USE_ARRANGEMENT", "使用安排", "ql-009", "concept", "blueprint_background"),
    _NodeSpec("ql-020", "RESERVATION_WINDOW", "预约窗口", "ql-013", "concept", "blueprint_background"),
    _NodeSpec("ql-021", "GUIDE_ARRANGEMENT", "导览安排", "ql-017", "concept", "blueprint_background"),
    _NodeSpec("ql-022", "MEDIA_CATEGORY", "载体类别", "ql-006", "property", "blueprint_background", "string", False),
    _NodeSpec("ql-023", "HOLDING_COUNT", "馆藏册数", "ql-006", "property", "curated_core", "integer", False),
    _NodeSpec("ql-024", "DEFAULT_LOAN_PERMISSION", "默认外借许可", "ql-018", "property", "blueprint_background", "boolean", False),
    _NodeSpec("ql-025", "ISSUE_PATTERN", "刊期", "ql-007", "property", "blueprint_background", "string", True),
    _NodeSpec("ql-026", "MISSING_ISSUE_FLAG", "缺期标记", "ql-007", "property", "blueprint_background", "boolean", False),
    _NodeSpec("ql-027", "FILE_FORMAT", "文件格式", "ql-008", "property", "blueprint_background", "string", True),
    _NodeSpec("ql-028", "CONCURRENT_SEATS", "并发席位", "ql-008", "property", "blueprint_background", "integer", False),
    _NodeSpec("ql-029", "OPEN_HOURS", "开放时间", "ql-009", "property", "curated_core", "time_code", True),
    _NodeSpec("ql-030", "SEAT_CAPACITY", "座位容量", "ql-009", "property", "blueprint_background", "integer", False),
    _NodeSpec("ql-031", "RESERVATION_REQUIRED", "预约要求", "ql-019", "property", "blueprint_background", "boolean", False),
    _NodeSpec("ql-032", "OPEN_HOURS", "开放时间", "ql-010", "property", "curated_core", "time_code", True),
    _NodeSpec("ql-033", "EQUIPMENT_LIST", "设备清单", "ql-010", "property", "blueprint_background", "string", True),
    _NodeSpec("ql-034", "EVENT_CAPACITY", "活动容量", "ql-011", "property", "curated_core", "integer", False),
    _NodeSpec("ql-035", "ACCESSIBLE_ENTRANCE", "无障碍入口", "ql-011", "property", "blueprint_background", "boolean", False),
    _NodeSpec("ql-036", "LOAN_LIMIT", "借阅册数", "ql-012", "property", "curated_core", "integer", False),
    _NodeSpec("ql-037", "LOAN_PERIOD", "借阅期限", "ql-012", "property", "blueprint_background", "integer", False),
    _NodeSpec("ql-038", "RESERVATION_SLOT", "预约时段", "ql-020", "property", "curated_core", "time_code", False),
    _NodeSpec("ql-039", "PARTICIPANT_COUNT", "参与人数", "ql-013", "property", "curated_core", "integer", False),
    _NodeSpec("ql-040", "QUESTION_TOPIC", "咨询主题", "ql-014", "property", "blueprint_background", "string", False),
    _NodeSpec("ql-041", "RESPONSE_CHANNEL", "回复渠道", "ql-014", "property", "blueprint_background", "string", True),
    _NodeSpec("ql-042", "SESSION_COUNT", "活动场次", "ql-015", "property", "curated_core", "integer", False),
    _NodeSpec("ql-043", "REGISTRATION_COUNT", "报名人数", "ql-015", "property", "blueprint_background", "integer", False),
    _NodeSpec("ql-044", "SESSION_COUNT", "活动场次", "ql-016", "property", "blueprint_background", "integer", False),
    _NodeSpec("ql-045", "MATERIAL_LIST", "材料清单", "ql-016", "property", "blueprint_background", "string", True),
    _NodeSpec("ql-046", "EXHIBITION_PERIOD", "展览周期", "ql-017", "property", "blueprint_background", "time_code", False),
    _NodeSpec("ql-047", "EXHIBIT_COUNT", "展项数量", "ql-017", "property", "blueprint_background", "integer", False),
    _NodeSpec("ql-048", "GUIDE_SLOT", "导览时段", "ql-021", "property", "blueprint_background", "time_code", True),
)

ALLOWED_FACETS_BY_SUBJECT = {
    "ql-006": ("ql-022", "ql-023", "ql-024"),
    "ql-007": ("ql-025", "ql-026"),
    "ql-008": ("ql-027", "ql-028"),
    "ql-009": ("ql-029", "ql-030", "ql-031"),
    "ql-010": ("ql-032", "ql-033"),
    "ql-011": ("ql-034", "ql-035"),
    "ql-012": ("ql-036", "ql-037"),
    "ql-013": ("ql-038", "ql-039"),
    "ql-014": ("ql-040", "ql-041"),
    "ql-015": ("ql-042", "ql-043"),
    "ql-016": ("ql-044", "ql-045"),
    "ql-017": ("ql-046", "ql-047", "ql-048"),
}


def _scenario(
    ref: str,
    primary_risk: str,
    challenge_tags: tuple[str, ...],
    requirement_text: str,
    proposed_parent_node_id: str | None,
    node_kind_hint: str,
    value_type_hint: str | None,
    cardinality_hint: str,
    expected_observable_category: str,
) -> dict[str, Any]:
    return {
        "scenario_ref": ref,
        "source_class": SOURCE_CLASS,
        "candidate_source": "AI_SYNTHETIC",
        "fictional": True,
        "gold_eligible": False,
        "patch_eligible": False,
        "primary_risk": primary_risk,
        "challenge_tags": list(challenge_tags),
        "request": {
            "requirement_text": requirement_text,
            "proposed_parent_node_id": proposed_parent_node_id,
            "node_kind_hint": node_kind_hint,
            "value_type_hint": value_type_hint,
            "cardinality_hint": cardinality_hint,
        },
        "proposed_observable_state": {
            "authority": "PROVISIONAL_HUMAN_REVIEW_REQUIRED",
            "category": expected_observable_category,
        },
    }


_SCENARIOS = (
    _scenario(
        "QL-C01",
        "CLEAR_INTENT",
        ("clear_intent", "category_scope"),
        "需要在纸本文献的流通规则中记录该类文献默认是否允许外借。",
        "ql-018",
        "PROPERTY",
        "boolean",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QL-C02",
        "HOMONYM",
        ("homonym", "type_signal"),
        "需要记录开放时间。",
        None,
        "PROPERTY",
        "time_code",
        "MULTIPLE",
        "NEED_CLARIFICATION",
    ),
    _scenario(
        "QL-C03",
        "CROSS_BRANCH",
        ("cross_branch",),
        "在公共活动下面记录读者预约空间的时段。",
        "ql-005",
        "PROPERTY",
        "time_code",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QL-C04",
        "KIND_CONFLICT",
        ("kind_conflict",),
        "把小组研讨室作为一个文本字段记录。",
        "ql-003",
        "PROPERTY",
        "string",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QL-C05",
        "CARDINALITY_CONFLICT",
        ("cardinality_conflict",),
        "材料清单只允许记录一个材料名称。",
        "ql-016",
        "PROPERTY",
        "string",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QL-C06",
        "WRONG_PARENT_HINT",
        ("wrong_parent_hint",),
        "在数字资料下面记录静音阅览区的座位容量。",
        "ql-008",
        "PROPERTY",
        "integer",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QL-C07",
        "NEAR_NAME_HARD_NEGATIVE",
        ("near_name_negative",),
        "记录多用途活动厅可以容纳的人数。",
        "ql-011",
        "PROPERTY",
        "integer",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QL-C08",
        "INSUFFICIENT_EVIDENCE",
        ("insufficient_evidence", "judgment_requires_evidence"),
        "请判断最适合社区需求的馆藏等级并记录结果；当前没有提供社区需求资料。",
        "ql-002",
        "PROPERTY",
        "string",
        "SINGLE",
        "NEED_EVIDENCE",
    ),
    _scenario(
        "QL-C09",
        "CLARIFICATION_REQUIRED",
        ("clarification_required",),
        "增加活动场次。",
        "ql-005",
        "PROPERTY",
        "integer",
        "SINGLE",
        "NEED_CLARIFICATION",
    ),
    _scenario(
        "QL-C10",
        "REFUSAL",
        ("cartesian_request", "refusal"),
        "为每一种馆藏、空间、服务和活动统一添加全部属性字段。",
        "ql-001",
        "UNKNOWN",
        None,
        "UNKNOWN",
        "REFUSE_UNBOUNDED_COMBINATION",
    ),
    _scenario(
        "QL-C11",
        "STRUCTURAL_ANOMALY_JUDGMENT",
        ("near_duplicate_subtree", "unusual_depth"),
        "小组研讨室和静音阅览区有相近属性，请直接把其中一个分支判定为重复并删除。",
        "ql-003",
        "UNKNOWN",
        None,
        "UNKNOWN",
        "NEED_EVIDENCE",
    ),
    _scenario(
        "QL-C12",
        "REPLAY_BASELINE_ANCHOR",
        ("small_tree_replay_baseline",),
        "记录空间预约的参与人数。",
        "ql-013",
        "PROPERTY",
        "integer",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
)


def _children_by_parent() -> dict[str | None, tuple[_NodeSpec, ...]]:
    children: dict[str | None, list[_NodeSpec]] = defaultdict(list)
    for spec in _NODES:
        children[spec.parent_node_id].append(spec)
    return {parent: tuple(items) for parent, items in children.items()}


def _build_wrapper(
    spec: _NodeSpec,
    *,
    children: dict[str | None, tuple[_NodeSpec, ...]],
    path_labels: tuple[str, ...],
    order: int,
) -> dict[str, Any]:
    current_path = path_labels + (spec.label,)
    metadata: dict[str, Any] = {
        "node_id": spec.node_id,
        "parent_node_id": spec.parent_node_id,
        "node_label": spec.label,
        "node_name": spec.name,
        "node_label_route": "/-/".join(current_path),
        "node_order": order,
        "node_type": spec.kind,
        "extension": {"dataset_family": spec.family},
    }
    if spec.kind == "property":
        metadata.update(
            {
                "value_type": spec.value_type,
                "is_list": spec.is_list,
                "value_constraints": {},
                "value_placeholder": None,
            }
        )
    subnodes = {
        child.label: _build_wrapper(
            child,
            children=children,
            path_labels=current_path,
            order=child_order,
        )
        for child_order, child in enumerate(children.get(spec.node_id, ()), start=1)
    }
    return {"metadata": metadata, "subnodes": subnodes}


def build_qinglan_library_tree() -> dict[str, Any]:
    """Build the approved 48-node clean-room source tree."""

    children = _children_by_parent()
    roots = children.get(None, ())
    if len(roots) != 1:
        raise AssertionError("Qinglan blueprint must have exactly one root")
    root = roots[0]
    return {
        "metadata": {
            "map_id": TREE_ID,
            "version": TREE_VERSION,
            "id": VERSION_RECORD_ID,
            "map_type": "resource",
            "concurrent_version": 1,
            "source_class": SOURCE_CLASS,
            "fictional": True,
            "derived_from_real": False,
            "gold_eligible": False,
            "patch_eligible": False,
        },
        "map_topology": {
            root.label: _build_wrapper(
                root,
                children=children,
                path_labels=(),
                order=1,
            )
        },
    }


def build_qinglan_library_scenarios() -> list[dict[str, Any]]:
    """Return detached scenario candidates in stable order."""

    return json.loads(json.dumps(_SCENARIOS, ensure_ascii=False))


def build_qinglan_library_manifest() -> dict[str, Any]:
    return {
        "manifest_version": "fictional-validation-manifest.v1",
        "dataset_ref": DATASET_REF,
        "run_ref": RUN_REF,
        "primary_role": PRIMARY_ROLE,
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "seed": SEED,
        "state": "MACHINE_VALIDATED",
        "variant": {
            "variant_ref": "small",
            "category_id": "fictional-qinglan-library",
            "resource_id": TREE_ID,
            "version": TREE_VERSION,
            "benchmark_role": "cross_domain_control",
            "node_count": TARGET_NODE_COUNT,
            "scenario_count": TARGET_SCENARIO_COUNT,
        },
        "limitations": [
            "只验证完全虚构数据上的开发合同。",
            "不是图书馆领域 Gold，不能外推生产准确率。",
            "跨规模稳定性需在后续独立数据集上重放。",
        ],
    }


def build_dataset_charter_view() -> dict[str, Any]:
    return {
        "charter_version": "fictional-dataset-charter.v1",
        "dataset_ref": DATASET_REF,
        "primary_role": PRIMARY_ROLE,
        "purpose": [
            "检查通用实现是否依赖消防领域命名、分支或层级。",
            "验证独立数据生成、机器门禁和人工审阅流水线。",
            "为后续跨规模重放建立小型基线。",
        ],
        "non_goals": [
            "不验证真实图书馆行业正确性。",
            "不创建 Gold 或声明生产准确率。",
            "不承担性能或生产形状结论。",
        ],
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "seed": SEED,
        "target": {
            "nodes": TARGET_NODE_COUNT,
            "scenarios": TARGET_SCENARIO_COUNT,
            "value_envelopes": 0,
        },
        "review_budget": {
            "candidate_limit": 12,
            "human_screen_all": True,
            "random_sample": 4,
            "self_recheck": 4,
            "dual_review_limit": 0,
            "time_limit_minutes": 120,
        },
        "independence": {
            "generation_blind_to_legacy_fire_semantics": True,
            "legacy_similarity_audit_stage": "POST_FREEZE_ONLY",
            "audit_may_reject_but_must_not_guide_generation": True,
        },
    }


def build_coverage_matrix_view() -> dict[str, Any]:
    return {
        "coverage_version": "fictional-coverage-matrix.v1",
        "dataset_ref": DATASET_REF,
        "tree_size_bucket": "SMALL_40_60",
        "cells": [
            {
                "scenario_ref": item["scenario_ref"],
                "primary_role": PRIMARY_ROLE,
                "primary_risk": item["primary_risk"],
                "challenge_tags": item["challenge_tags"],
                "expected_observable_category": item[
                    "proposed_observable_state"
                ]["category"],
            }
            for item in build_qinglan_library_scenarios()
        ],
    }


def build_semantic_blueprint_view() -> dict[str, Any]:
    by_id = {spec.node_id: spec for spec in _NODES}
    return {
        "blueprint_version": "qinglan-library-blueprint.v2",
        "dataset_ref": DATASET_REF,
        "source_class": SOURCE_CLASS,
        "node_families": {
            "curated_core": [
                spec.node_id for spec in _NODES if spec.family == "curated_core"
            ],
            "blueprint_background": [
                spec.node_id
                for spec in _NODES
                if spec.family == "blueprint_background"
            ],
            "stress_only_filler": [],
        },
        "allowed_facets_by_subject": {
            subject_id: [
                {
                    "node_id": facet_id,
                    "name": by_id[facet_id].name,
                    "value_type": by_id[facet_id].value_type,
                    "cardinality": (
                        "MULTIPLE" if by_id[facet_id].is_list else "SINGLE"
                    ),
                }
                for facet_id in facet_ids
            ]
            for subject_id, facet_ids in ALLOWED_FACETS_BY_SUBJECT.items()
        },
    }


def _iter_wrappers(document: dict[str, Any]) -> Iterable[dict[str, Any]]:
    pending = list(document["map_topology"].values())
    while pending:
        wrapper = pending.pop()
        yield wrapper
        pending.extend(wrapper.get("subnodes", {}).values())


def _is_descendant_of(
    node_id: str,
    ancestor_id: str,
    parent_by_id: dict[str, str | None],
) -> bool:
    current = parent_by_id.get(node_id)
    while current is not None:
        if current == ancestor_id:
            return True
        current = parent_by_id.get(current)
    return False


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def build_human_review_checklist() -> dict[str, Any]:
    refs = [item["scenario_ref"] for item in _SCENARIOS]
    random_sample = sorted(random.Random(SEED).sample(refs, 4))
    return {
        "review_contract_version": "fictional-human-review.v1",
        "dataset_ref": DATASET_REF,
        "status": "PENDING",
        "time_limit_minutes": 120,
        "screen_all": refs,
        "random_sample": random_sample,
        "self_recheck": ["QL-C01", "QL-C08", "QL-C10", "QL-C12"],
        "dual_review": [],
        "stop_rules": [
            "DATASET_BOUNDARY_CANARY_FOUND",
            "DATASET_ORACLE_OVERCLAIM",
            "TWO_MATERIAL_RANDOM_SAMPLE_ERRORS",
            "REPEATED_ERROR_ACROSS_TWO_CLUSTERS",
            "DATASET_REVIEW_BUDGET_EXCEEDED",
            "DATASET_CARTESIAN_DENSITY_HIGH",
            "POST_FREEZE_SIMILARITY_REJECTED",
        ],
    }


def run_qinglan_library_preflight(
    *,
    tree: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run aggregate-only L1 checks without emitting semantic payloads."""

    candidate_tree = build_qinglan_library_tree() if tree is None else tree
    candidate_scenarios = (
        build_qinglan_library_scenarios() if scenarios is None else scenarios
    )
    findings: Counter[str] = Counter()

    metadata = candidate_tree.get("metadata", {})
    required_flags = {
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }
    if any(metadata.get(key) != value for key, value in required_flags.items()):
        findings["DATASET_SOURCE_CLASS_INVALID"] += 1

    result = adapt_tree_document(candidate_tree)
    if not result.is_valid or result.tree is None:
        findings["DATASET_ADAPTER_INVALID"] += 1
        canonical_nodes = ()
    else:
        canonical_nodes = result.tree.nodes
    if (
        result.observed_node_count != TARGET_NODE_COUNT
        or result.observed_value_count != 0
        or len(candidate_scenarios) != TARGET_SCENARIO_COUNT
    ):
        findings["DATASET_COUNT_MISMATCH"] += 1

    node_ids = {node.node_id for node in canonical_nodes}
    scenario_refs = [item.get("scenario_ref") for item in candidate_scenarios]
    if (
        len(scenario_refs) != len(set(scenario_refs))
        or any(not isinstance(ref, str) or not ref for ref in scenario_refs)
    ):
        findings["DATASET_REFERENCE_INVALID"] += 1
    for item in candidate_scenarios:
        request = item.get("request", {})
        parent_id = request.get("proposed_parent_node_id")
        if parent_id is not None and parent_id not in node_ids:
            findings["DATASET_REFERENCE_INVALID"] += 1
        if (
            item.get("source_class") != SOURCE_CLASS
            or item.get("fictional") is not True
            or item.get("gold_eligible") is not False
            or item.get("patch_eligible") is not False
        ):
            findings["DATASET_SOURCE_CLASS_INVALID"] += 1
        proposed = item.get("proposed_observable_state", {})
        if (
            proposed.get("authority") != "PROVISIONAL_HUMAN_REVIEW_REQUIRED"
            or proposed.get("category") not in _EXPECTED_OBSERVABLE_CATEGORIES
            or "oracle" in item
            or "selected_node_id" in proposed
            or "semantic_approval" in proposed
        ):
            findings["DATASET_ORACLE_OVERCLAIM"] += 1

    primary_risks = [item.get("primary_risk") for item in candidate_scenarios]
    coverage_cells = {
        (
            PRIMARY_ROLE,
            tuple(item.get("challenge_tags", ())),
            "SMALL_40_60",
            item.get("proposed_observable_state", {}).get("category"),
        )
        for item in candidate_scenarios
    }
    if (
        len(primary_risks) != len(set(primary_risks))
        or len(coverage_cells) != len(candidate_scenarios)
    ):
        findings["DATASET_SCENARIO_COVERAGE_DUPLICATE"] += 1

    actual_property_ids = {
        node.node_id for node in canonical_nodes if node.kind == "PROPERTY"
    }
    allowed_property_ids = {
        facet_id
        for facet_ids in ALLOWED_FACETS_BY_SUBJECT.values()
        for facet_id in facet_ids
    }
    parent_by_id = {node.node_id: node.parent_node_id for node in canonical_nodes}
    if actual_property_ids != allowed_property_ids:
        findings["DATASET_COMBINATION_UNAPPROVED"] += 1
    for subject_id, facet_ids in ALLOWED_FACETS_BY_SUBJECT.items():
        for facet_id in facet_ids:
            if not _is_descendant_of(facet_id, subject_id, parent_by_id):
                findings["DATASET_COMBINATION_UNAPPROVED"] += 1

    property_nodes = [node for node in canonical_nodes if node.kind == "PROPERTY"]
    value_type_counts = Counter(
        node.value_contract.value_type
        for node in property_nodes
        if node.value_contract is not None
    )
    cardinality_counts = Counter(
        node.value_contract.cardinality
        for node in property_nodes
        if node.value_contract is not None
    )
    if (
        set(value_type_counts) - _ALLOWED_VALUE_TYPES
        or dict(sorted(value_type_counts.items())) != _EXPECTED_VALUE_TYPE_COUNTS
        or dict(sorted(cardinality_counts.items()))
        != _EXPECTED_CARDINALITY_COUNTS
    ):
        findings["DATASET_ROLE_MISMATCH"] += 1

    child_vectors = []
    by_id = {node.node_id: node for node in canonical_nodes}
    for node in canonical_nodes:
        if node.child_node_ids:
            child_vectors.append(
                tuple(by_id[child_id].name for child_id in node.child_node_ids)
            )
    if len(child_vectors) != len(set(child_vectors)):
        findings["DATASET_REPEATED_VECTOR"] += 1
    if any(_NUMBERED_NAME.search(node.name) for node in canonical_nodes):
        findings["DATASET_REPEATED_VECTOR"] += 1

    unique_facet_names = {node.name for node in property_nodes}
    possible_pairs = len(ALLOWED_FACETS_BY_SUBJECT) * len(unique_facet_names)
    combination_density = (
        len(allowed_property_ids) / possible_pairs if possible_pairs else 1.0
    )
    if combination_density >= 0.5:
        findings["DATASET_CARTESIAN_DENSITY_HIGH"] += 1

    for wrapper in _iter_wrappers(candidate_tree):
        if "value" in wrapper:
            findings["DATASET_BOUNDARY_CANARY_FOUND"] += 1
    encoded = _canonical_json_bytes(
        {
            "tree": candidate_tree,
            "scenarios": candidate_scenarios,
        }
    ).decode("utf-8").lower()
    if any(marker in encoded for marker in _BOUNDARY_MARKERS):
        findings["DATASET_BOUNDARY_CANARY_FOUND"] += 1

    if tree is None and scenarios is None:
        first = _canonical_json_bytes(build_candidate_core())
        second = _canonical_json_bytes(build_candidate_core())
        if first != second:
            findings["DATASET_NONDETERMINISTIC"] += 1

    return {
        "report_version": "fictional-dataset-l1.v1",
        "dataset_ref": DATASET_REF,
        "source_class": SOURCE_CLASS,
        "status": "PASS" if not findings else "FAIL",
        "counts": {
            "nodes": result.observed_node_count,
            "value_envelopes": result.observed_value_count,
            "scenarios": len(candidate_scenarios),
            "approved_subject_facet_pairs": len(allowed_property_ids),
        },
        "combination_density": round(combination_density, 6),
        "finding_code_counts": dict(sorted(findings.items())),
    }


def run_read_only_critic(
    *,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a non-authoritative, read-only L2 rules critique."""

    l1 = run_qinglan_library_preflight() if preflight is None else preflight
    findings = []
    if l1.get("status") != "PASS":
        findings.append(
            {
                "code": "L1_PASS_REQUIRED",
                "severity": "blocking",
                "fictional_ref": DATASET_REF,
                "summary": "候选必须先通过确定性机器门禁。",
            }
        )
    findings.append(
        {
            "code": "HUMAN_SEMANTIC_REVIEW_REQUIRED",
            "severity": "informational",
            "fictional_ref": DATASET_REF,
            "summary": "规则检查不能证明虚构领域语义正确，十二个场景仍需人工筛查。",
        }
    )
    return {
        "critic_contract_version": "fictional-dataset-critic.v1",
        "critic_authority": "NON_AUTHORITATIVE",
        "method": "DETERMINISTIC_READ_ONLY",
        "source_class": SOURCE_CLASS,
        "dataset_ref": DATASET_REF,
        "blocking_count": sum(
            item["severity"] == "blocking" for item in findings
        ),
        "findings": findings,
    }


def build_candidate_core() -> dict[str, Any]:
    return {
        "manifest": build_qinglan_library_manifest(),
        "blueprint": build_semantic_blueprint_view(),
        "tree": build_qinglan_library_tree(),
        "scenarios": build_qinglan_library_scenarios(),
    }


def candidate_files() -> dict[str, Any]:
    preflight = run_qinglan_library_preflight()
    if preflight["status"] != "PASS":
        raise RuntimeError("Qinglan candidate failed deterministic preflight")
    return {
        "dataset-charter.json": build_dataset_charter_view(),
        "manifest.json": build_qinglan_library_manifest(),
        "coverage-matrix.json": build_coverage_matrix_view(),
        "semantic-blueprint.json": build_semantic_blueprint_view(),
        "tree.json": build_qinglan_library_tree(),
        "scenarios.json": build_qinglan_library_scenarios(),
        "l1-report.json": preflight,
        "l2-critic-findings.json": run_read_only_critic(preflight=preflight),
        "human-review-checklist.json": build_human_review_checklist(),
        "promotion-checklist.json": {
            "dataset_ref": DATASET_REF,
            "candidate_state": "MACHINE_VALIDATED",
            "gold_eligible": False,
            "patch_eligible": False,
            "human_screened": False,
            "review_protocol": "SINGLE_REVIEW_WITH_SELF_RECHECK",
            "self_rechecked": False,
            "frozen": False,
            "legacy_similarity_audited": False,
            "formal_fixture_promoted": False,
        },
    }


def write_qinglan_library_candidate(output_dir: str | Path) -> tuple[Path, ...]:
    """Write one new, non-overwriting candidate staging directory."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    written = []
    for filename, payload in candidate_files().items():
        path = target / filename
        path.write_bytes(_canonical_json_bytes(payload))
        written.append(path)
    return tuple(written)


__all__ = [
    "ALLOWED_FACETS_BY_SUBJECT",
    "DATASET_REF",
    "PRIMARY_ROLE",
    "RUN_REF",
    "SEED",
    "SOURCE_CLASS",
    "TARGET_NODE_COUNT",
    "TARGET_SCENARIO_COUNT",
    "build_candidate_core",
    "build_coverage_matrix_view",
    "build_dataset_charter_view",
    "build_human_review_checklist",
    "build_qinglan_library_manifest",
    "build_qinglan_library_scenarios",
    "build_qinglan_library_tree",
    "build_semantic_blueprint_view",
    "candidate_files",
    "run_qinglan_library_preflight",
    "run_read_only_critic",
    "write_qinglan_library_candidate",
]
