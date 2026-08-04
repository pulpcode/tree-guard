"""Deterministic clean-room data builder for the M5 assisted Shadow gate.

The vocabulary and structure in this module are independently fictional.  The
builder does not read any prior fixture, scenario, Oracle, model request, or
model response.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from treeguard.adapter import adapt_tree_document, load_tree_export
from treeguard.change_intent import (
    CONFIRMATION_SCHEMA_VERSION,
    IntentConfirmation,
    IntentContent,
    IntentRequest,
)
from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads
from treeguard.retrieval import build_candidate_set
from treeguard.scenario_capability_validation import (
    INTENT_FIELD_NAMES,
    CapabilityOracle,
    IntentFieldExpectation,
    IntentOracleProfile,
    RecommendationOracle,
    RecommendationOracleOutcome,
    RetrievalOracle,
    retrieval_matches_oracle,
)


DATASET_REF = "fictional-fire-m5-assisted-shadow"
DATASET_SCHEMA_VERSION = "m5-assisted-shadow-dataset-manifest.v1"
SCENARIO_SCHEMA_VERSION = "m5-assisted-shadow-scenario-candidates.v1"
ORACLE_SCHEMA_VERSION = "m5-assisted-shadow-oracle-sidecar.v1"
PREFLIGHT_SCHEMA_VERSION = "m5-assisted-shadow-data-preflight.v1"
SILVER_REVIEW_SCHEMA_VERSION = "m5-assisted-shadow-codex-silver-review.v1"
GENERATOR_VERSION = "treeguard.m5-fire-cleanroom-generator.v1"
ASSISTED_POLICY_VERSION = "treeguard.m5-assisted-shadow-admission.v1"

TREE_FILE = "tree.json"
SCENARIO_FILE = "scenario-candidates.json"
ORACLE_FILE = "oracle-sidecar.json"
MANIFEST_FILE = "manifest.json"
PREFLIGHT_FILE = "preflight-report.json"
SILVER_REVIEW_FILE = "codex-silver-review.json"

EXECUTION_COUNT = 24
RESERVE_COUNT = 6
PROCEED_COUNT = 18
CLARIFY_COUNT = 6
MIN_NODE_COUNT = 800
MAX_NODE_COUNT = 2_000
MIN_TOP_LEVEL_BRANCHES = 8
MAX_EXECUTION_SCENARIOS_PER_BRANCH = 3

_MANIFEST_KEYS = {
    "schema_version",
    "generator_version",
    "dataset_ref",
    "title",
    "source_class",
    "fictional",
    "derived_from_real",
    "domain",
    "benchmark_role",
    "variant",
    "resource_id",
    "version",
    "assisted_policy_version",
    "tree_file",
    "tree_file_sha256",
    "tree_canonical_digest",
    "node_count",
    "value_envelope_count",
    "scenario_file",
    "scenario_file_sha256",
    "oracle_file",
    "oracle_file_sha256",
    "candidate_count",
    "execution_count",
    "reserve_count",
    "proceed_count",
    "clarify_count",
    "model_exposed",
    "human_review_status",
    "limitations",
}
_SCENARIO_KEYS = {
    "scenario_ref",
    "selection_status",
    "coverage_cell",
    "expected_route",
    "primary_branch_ref",
    "primary_branch_name",
    "primary_risk",
    "analysis_tags",
    "request",
}
_REQUEST_KEYS = {
    "requirement_text",
    "proposed_parent_node_id",
    "node_kind_hint",
    "value_type_hint",
    "cardinality_hint",
}
_ORACLE_ITEM_KEYS = {
    "scenario_ref",
    "expected_route",
    "capability_oracle",
    "retrieval_seed",
    "safe_alternative",
    "evidence_node_ids",
}
_SAFE_ALTERNATIVE_KEYS = {"allowed_actions", "rationale_code"}
_RETRIEVAL_SEED_KEYS = {
    "subject",
    "role",
    "scenario",
    "lifecycle",
    "ownership",
    "node_kind",
    "value_type",
    "cardinality",
    "confirmed_facts",
    "assumptions",
    "evidence_gaps",
    "clarification_question",
}
_SELECTION_STATUSES = {"EXECUTION", "RESERVE"}
_EXPECTED_ROUTES = {"PROCEED", "CLARIFY"}
_NON_TARGETING_ACTIONS = {"ABSTAIN", "NEED_CLARIFICATION", "NEED_EVIDENCE"}
_FIXED_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_NUMBERED_NAME = re.compile(r"(?:^|[^0-9])[0-9]{2,}$")


BRANCH_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "协同任务域",
        (
            "接报分派",
            "先遣侦察",
            "警戒组织",
            "搜寻协作",
            "疏散引导",
            "供水联络",
            "排烟配合",
            "现场交接",
            "态势汇总",
            "终止确认",
        ),
    ),
    (
        "场所画像域",
        (
            "院落边界",
            "楼层分区",
            "通行节点",
            "竖向连通",
            "避难空间",
            "作业区域",
            "公众区域",
            "受限区域",
            "临时区域",
            "周边界面",
        ),
    ),
    (
        "风险描述域",
        (
            "可燃介质",
            "热源活动",
            "电气负荷",
            "压力容器",
            "受限空间",
            "高处作业",
            "动火作业",
            "储运环节",
            "季节影响",
            "相邻暴露",
        ),
    ),
    (
        "设施能力域",
        (
            "报警接入",
            "水源保障",
            "灭火接口",
            "排烟控制",
            "应急照明",
            "疏散指示",
            "防火分隔",
            "电源切换",
            "通信覆盖",
            "远程联动",
        ),
    ),
    (
        "巡检治理域",
        (
            "日常巡查",
            "专项检查",
            "交接核验",
            "缺陷登记",
            "复测确认",
            "停用管理",
            "维保协调",
            "抽查计划",
            "证据留存",
            "趋势观察",
        ),
    ),
    (
        "训练演练域",
        (
            "岗位训练",
            "桌面推演",
            "疏散演练",
            "联动演练",
            "夜间演练",
            "极端天气演练",
            "新员工熟悉",
            "承包商告知",
            "复盘改进",
            "能力评估",
        ),
    ),
    (
        "事件协作域",
        (
            "初始事件",
            "升级条件",
            "资源请求",
            "多方会商",
            "信息发布",
            "家属联络",
            "医疗衔接",
            "交通协调",
            "环境监测",
            "恢复移交",
        ),
    ),
    (
        "物资保障域",
        (
            "个人防护",
            "侦检器材",
            "照明器材",
            "通信器材",
            "破拆器材",
            "堵漏器材",
            "警戒器材",
            "急救物资",
            "备用能源",
            "运输周转",
        ),
    ),
    (
        "整改闭环域",
        (
            "问题归类",
            "原因分析",
            "临时控制",
            "整改方案",
            "责任确认",
            "时限管理",
            "验证抽样",
            "延期评估",
            "关闭条件",
            "经验反馈",
        ),
    ),
    (
        "外部衔接域",
        (
            "属地联络",
            "园区协同",
            "物业协作",
            "维保单位",
            "检测机构",
            "医疗资源",
            "交通资源",
            "供能单位",
            "社区沟通",
            "信息报送",
        ),
    ),
)

ATTRIBUTE_SUFFIXES: tuple[str, ...] = (
    "责任边界",
    "触发条件",
    "状态标识",
    "核验周期",
    "协同对象",
    "处置时限",
    "记录来源",
    "空间范围",
    "风险等级",
    "启停规则",
    "反馈渠道",
    "证据要求",
    "交接节点",
    "复核角色",
    "例外条件",
    "关联资源",
    "通知策略",
    "归档方式",
    "时间窗口",
    "维护主体",
    "容量上限",
    "访问约束",
    "变更原因",
    "生效范围",
    "观察指标",
    "失败处置",
    "依赖条件",
    "确认方式",
    "数据口径",
    "保留期限",
)

DETAIL_SUFFIXES: tuple[str, ...] = (
    "字段定义",
    "校验规则",
    "来源说明",
    "更新节奏",
    "异常标记",
)

VALUE_TYPES: tuple[str, ...] = (
    "string",
    "integer",
    "boolean",
    "time_code",
    "entity_code",
    "space_code",
    "float",
    "class",
)


class M5DataError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _TreeBuilder:
    def __init__(self) -> None:
        self.counter = 0
        self.records: list[dict[str, Any]] = []
        self.group_records: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self.group_nodes: dict[tuple[int, int], dict[str, Any]] = {}
        self.branch_nodes: dict[int, dict[str, Any]] = {}

    def add_node(
        self,
        name: str,
        *,
        node_type: str,
        parent: dict[str, Any] | None,
        order: int,
        value_type: str | None = None,
        is_list: bool = False,
    ) -> dict[str, Any]:
        self.counter += 1
        node_id = f"M5N{self.counter:04d}"
        label = f"m5l{self.counter:04d}"
        parent_metadata = parent["metadata"] if parent is not None else None
        parent_route = (
            parent_metadata["node_label_route"] if parent_metadata is not None else None
        )
        route = label if parent_route is None else f"{parent_route}/-/{label}"
        metadata: dict[str, Any] = {
            "node_id": node_id,
            "parent_node_id": (
                parent_metadata["node_id"] if parent_metadata is not None else None
            ),
            "node_label": label,
            "node_label_route": route,
            "node_name": name,
            "node_order": order,
            "node_type": node_type,
            "remark": None,
            "extension": {},
        }
        if node_type == "property":
            metadata.update(
                {
                    "value_type": value_type,
                    "is_list": is_list,
                    "value_constraints": {},
                    "value_placeholder": None,
                }
            )
        wrapper = {"metadata": metadata, "subnodes": {}}
        if parent is not None:
            parent["subnodes"][label] = wrapper
        record = {
            "node_id": node_id,
            "name": name,
            "node_type": node_type,
            "value_type": value_type,
            "cardinality": "MULTIPLE" if is_list else "SINGLE",
            "parent_node_id": metadata["parent_node_id"],
        }
        self.records.append(record)
        return wrapper


def _selected_suffixes(group_name: str, count: int) -> tuple[str, ...]:
    ranked = sorted(
        ATTRIBUTE_SUFFIXES,
        key=lambda suffix: canonical_digest([group_name, suffix]),
    )
    return tuple(ranked[:count])


def build_tree_document() -> tuple[dict[str, Any], dict[str, Any]]:
    builder = _TreeBuilder()
    root = builder.add_node(
        "岚岳协同防护字典",
        node_type="concept",
        parent=None,
        order=1,
    )
    for branch_index, (branch_name, groups) in enumerate(BRANCH_GROUPS):
        branch = builder.add_node(
            branch_name,
            node_type="concept",
            parent=root,
            order=branch_index + 1,
        )
        builder.branch_nodes[branch_index] = branch
        for group_index, group_name in enumerate(groups):
            group = builder.add_node(
                group_name,
                node_type="concept",
                parent=branch,
                order=group_index + 1,
            )
            key = (branch_index, group_index)
            builder.group_nodes[key] = group
            builder.group_records[key] = []
            global_index = branch_index * 10 + group_index
            suffix_count = 7 + global_index % 4
            for attribute_index, suffix in enumerate(
                _selected_suffixes(group_name, suffix_count)
            ):
                digest = canonical_digest([group_name, suffix, global_index])
                value_type = VALUE_TYPES[int(digest[:2], 16) % len(VALUE_TYPES)]
                is_list = int(digest[2:4], 16) % 5 == 0
                attribute = builder.add_node(
                    f"{group_name}{suffix}",
                    node_type="property",
                    parent=group,
                    order=attribute_index + 1,
                    value_type=value_type,
                    is_list=is_list,
                )
                record = builder.records[-1]
                record.update(
                    {
                        "branch_index": branch_index,
                        "branch_name": branch_name,
                        "group_index": group_index,
                        "group_name": group_name,
                        "group_node_id": group["metadata"]["node_id"],
                    }
                )
                builder.group_records[key].append(record)
                if value_type == "class":
                    detail_count = 2 + int(digest[4:6], 16) % 4
                    selected_details = sorted(
                        DETAIL_SUFFIXES,
                        key=lambda detail: canonical_digest(
                            [group_name, suffix, detail]
                        ),
                    )[:detail_count]
                    for detail_index, detail in enumerate(selected_details):
                        detail_digest = canonical_digest(
                            [group_name, suffix, detail, detail_index]
                        )
                        detail_type = VALUE_TYPES[
                            int(detail_digest[:2], 16) % (len(VALUE_TYPES) - 1)
                        ]
                        builder.add_node(
                            f"{group_name}{suffix}{detail}",
                            node_type="property",
                            parent=attribute,
                            order=detail_index + 1,
                            value_type=detail_type,
                            is_list=int(detail_digest[2:4], 16) % 7 == 0,
                        )
                        builder.records[-1].update(
                            {
                                "branch_index": branch_index,
                                "branch_name": branch_name,
                                "group_index": group_index,
                                "group_name": group_name,
                                "group_node_id": group["metadata"]["node_id"],
                            }
                        )

    document = {
        "metadata": {
            "map_id": "fictional-m5-lanyue-resource",
            "version": "FM5-V1",
            "id": "fictional-m5-lanyue-version-one",
            "map_type": "resource",
            "concurrent_version": 1,
        },
        "map_topology": {root["metadata"]["node_label"]: root},
    }
    catalog = {
        "records": builder.records,
        "group_records": builder.group_records,
        "group_nodes": builder.group_nodes,
        "branch_nodes": builder.branch_nodes,
    }
    return document, catalog


def _request(
    requirement_text: str,
    *,
    parent_node_id: str | None,
    node_kind: str,
    value_type: str | None,
    cardinality: str,
) -> dict[str, Any]:
    return {
        "requirement_text": requirement_text,
        "proposed_parent_node_id": parent_node_id,
        "node_kind_hint": node_kind,
        "value_type_hint": value_type,
        "cardinality_hint": cardinality,
    }


def _intent_expectations(request: dict[str, Any], expected_route: str) -> tuple[IntentFieldExpectation, ...]:
    expectations: list[IntentFieldExpectation] = []
    hints = {
        "node_kind": request["node_kind_hint"],
        "value_type": request["value_type_hint"],
        "cardinality": request["cardinality_hint"],
    }
    for field_name in sorted(INTENT_FIELD_NAMES):
        if field_name in {
            "subject",
            "role",
            "scenario",
            "lifecycle",
            "ownership",
            "confirmed_facts",
            "assumptions",
            "evidence_gaps",
        }:
            expectations.append(
                IntentFieldExpectation(field_name, "NOT_COMPARED", ())
            )
        elif field_name == "clarification_question":
            expectations.append(
                IntentFieldExpectation(
                    field_name,
                    "NON_EMPTY" if expected_route == "CLARIFY" else "EXACT_ONE_OF",
                    () if expected_route == "CLARIFY" else (None,),
                )
            )
        else:
            value = hints[field_name]
            if value is None or value == "UNKNOWN":
                expectations.append(
                    IntentFieldExpectation(field_name, "NOT_COMPARED", ())
                )
            else:
                expectations.append(
                    IntentFieldExpectation(field_name, "EXACT_ONE_OF", (value,))
                )
    return tuple(expectations)


def _intent_seed(
    request: dict[str, Any],
    *,
    subject: str,
    expected_route: str,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "role": None,
        "scenario": None,
        "lifecycle": None,
        "ownership": "UNKNOWN",
        "node_kind": request["node_kind_hint"],
        "value_type": request["value_type_hint"],
        "cardinality": request["cardinality_hint"],
        "confirmed_facts": [],
        "assumptions": [],
        "evidence_gaps": [],
        "clarification_question": (
            "请明确当前需求所指的结构范围。"
            if expected_route == "CLARIFY"
            else None
        ),
    }


def _capability_oracle(
    request: dict[str, Any],
    *,
    expected_route: str,
    acceptable_node_ids: tuple[str, ...],
    top_k: int | None,
    recommendation_outcomes: tuple[RecommendationOracleOutcome, ...],
    empty_retrieval_status: str | None = None,
) -> CapabilityOracle:
    profile = IntentOracleProfile(
        "P001",
        _intent_expectations(request, expected_route),
    )
    if expected_route == "CLARIFY":
        retrieval = RetrievalOracle(False, (), (), None)
        recommendation = RecommendationOracle(False, ())
    else:
        retrieval = RetrievalOracle(
            True,
            (
                (empty_retrieval_status,)
                if empty_retrieval_status is not None
                else ("CANDIDATES_READY",)
            ),
            acceptable_node_ids,
            top_k,
        )
        recommendation = RecommendationOracle(True, recommendation_outcomes)
    return CapabilityOracle(
        expected_route,
        (profile,),
        retrieval,
        recommendation,
    )


def _confirmation(
    request_payload: dict[str, Any],
    seed: dict[str, Any],
    tree: Any,
) -> IntentConfirmation:
    request = IntentRequest(
        requirement_text=request_payload["requirement_text"],
        proposed_parent_node_id=request_payload["proposed_parent_node_id"],
        node_kind_hint=request_payload["node_kind_hint"],
        value_type_hint=request_payload["value_type_hint"],
        cardinality_hint=request_payload["cardinality_hint"],
    )
    intent = IntentContent(
        subject=seed["subject"],
        role=seed["role"],
        scenario=seed["scenario"],
        lifecycle=seed["lifecycle"],
        ownership=seed["ownership"],
        node_kind=seed["node_kind"],
        value_type=seed["value_type"],
        cardinality=seed["cardinality"],
        confirmed_facts=tuple(seed["confirmed_facts"]),
        assumptions=tuple(seed["assumptions"]),
        evidence_gaps=tuple(seed["evidence_gaps"]),
        clarification_question=seed["clarification_question"],
    )
    source_draft_hash = canonical_digest(["m5", "preflight", "draft"])
    source_action_hash = canonical_digest(["m5", "preflight", "action"])
    payload = {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "status": "CONFIRMED_FOR_RETRIEVAL",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "semantic_approval": False,
        "patch_eligible": False,
        "source_request_hash": request.request_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": source_draft_hash,
        "source_action_hash": source_action_hash,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "reviewer_ref": "m5-data-preflight",
        "recorded_at": "2026-08-04T00:00:00Z",
        "intent": intent.to_dict(),
    }
    return IntentConfirmation(
        status="CONFIRMED_FOR_RETRIEVAL",
        source_request_hash=request.request_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=source_draft_hash,
        source_action_hash=source_action_hash,
        proposed_parent_node_id=request.proposed_parent_node_id,
        reviewer_ref="m5-data-preflight",
        recorded_at="2026-08-04T00:00:00Z",
        intent=intent,
        confirmation_hash=canonical_digest(payload),
    )


def _candidate_set_for(
    request_payload: dict[str, Any],
    seed: dict[str, Any],
    tree: Any,
) -> Any:
    return build_candidate_set(_confirmation(request_payload, seed, tree), tree)


def _record_for(
    catalog: dict[str, Any],
    branch_index: int,
    group_index: int,
    *,
    used_targets: set[str],
    forbidden_fragments: tuple[str, ...] = (),
) -> dict[str, Any]:
    records = catalog["group_records"][(branch_index, group_index)]
    for record in records:
        if (
            record["value_type"] != "class"
            and record["node_id"] not in used_targets
            and not any(fragment in record["name"] for fragment in forbidden_fragments)
        ):
            return record
    raise M5DataError("M5_TARGET_SELECTION_FAILED")


def _equivalent_records(
    catalog: dict[str, Any],
    branch_index: int,
    suffix: str,
    *,
    used_targets: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_contract: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (candidate_branch, _), records in catalog["group_records"].items():
        if candidate_branch != branch_index:
            continue
        for record in records:
            if (
                record["value_type"] != "class"
                and record["node_id"] not in used_targets
                and record["name"].endswith(suffix)
            ):
                by_contract[(record["value_type"], record["cardinality"])].append(
                    record
                )
    for contract in sorted(by_contract):
        records = sorted(by_contract[contract], key=lambda item: item["node_id"])
        if len(records) >= 2:
            return records[0], records[1]
    raise M5DataError("M5_EQUIVALENT_TARGET_SELECTION_FAILED")


def _positive_outcomes(node_ids: tuple[str, ...]) -> tuple[RecommendationOracleOutcome, ...]:
    return tuple(
        sorted(
            (
                RecommendationOracleOutcome(
                    "USE_EXISTING_NODE",
                    node_id,
                    "SEMANTICALLY_EQUIVALENT",
                )
                for node_id in node_ids
            ),
            key=lambda item: (
                item.action,
                item.target_node_id or "",
                item.relation or "",
            ),
        )
    )


def build_scenarios_and_oracle(
    tree: Any,
    catalog: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    oracle_items: list[dict[str, Any]] = []
    used_targets: set[str] = set()
    records_by_id = {item["node_id"]: item for item in catalog["records"]}

    def append_item(
        *,
        selection_status: str,
        coverage_cell: str,
        branch_index: int,
        primary_risk: str,
        analysis_tags: tuple[str, ...],
        request_payload: dict[str, Any],
        expected_route: str,
        subject: str,
        acceptable_node_ids: tuple[str, ...],
        top_k: int | None,
        recommendation_outcomes: tuple[RecommendationOracleOutcome, ...],
        safe_actions: tuple[str, ...],
        rationale_code: str,
        empty_retrieval_status: str | None = None,
    ) -> None:
        scenario_ref = f"M5S{len(scenarios) + 1:03d}"
        branch = catalog["branch_nodes"][branch_index]
        scenarios.append(
            {
                "scenario_ref": scenario_ref,
                "selection_status": selection_status,
                "coverage_cell": coverage_cell,
                "expected_route": expected_route,
                "primary_branch_ref": branch["metadata"]["node_id"],
                "primary_branch_name": branch["metadata"]["node_name"],
                "primary_risk": primary_risk,
                "analysis_tags": list(analysis_tags),
                "request": request_payload,
            }
        )
        seed = _intent_seed(
            request_payload,
            subject=subject,
            expected_route=expected_route,
        )
        oracle = _capability_oracle(
            request_payload,
            expected_route=expected_route,
            acceptable_node_ids=acceptable_node_ids,
            top_k=top_k,
            recommendation_outcomes=recommendation_outcomes,
            empty_retrieval_status=empty_retrieval_status,
        )
        oracle_items.append(
            {
                "scenario_ref": scenario_ref,
                "expected_route": expected_route,
                "capability_oracle": oracle.to_dict(),
                "retrieval_seed": seed,
                "safe_alternative": {
                    "allowed_actions": list(safe_actions),
                    "rationale_code": rationale_code,
                },
                "evidence_node_ids": list(acceptable_node_ids),
            }
        )

    # Reserve the two Top-K boundary target sets before choosing unique targets.
    boundary_specs: tuple[str, ...] = ("责任边界", "启停规则")
    boundary_payloads: list[tuple[dict[str, Any], dict[str, Any], tuple[str, ...], int]] = []
    for term in boundary_specs:
        request_payload = _request(
            f"需要在全域只读字典中复用任一现有{term}合同，不新增同义字段。",
            parent_node_id=None,
            node_kind="PROPERTY",
            value_type=None,
            cardinality="UNKNOWN",
        )
        seed = _intent_seed(request_payload, subject=term, expected_route="PROCEED")
        candidate_set = _candidate_set_for(request_payload, seed, tree)
        direct_candidates = [
            item
            for item in candidate_set.candidates
            if records_by_id[item.node_id].get("group_node_id")
            == records_by_id[item.node_id]["parent_node_id"]
        ]
        boundary = 8
        if not any(item.rank == boundary for item in direct_candidates):
            raise M5DataError("M5_TOP_K_BOUNDARY_NOT_AVAILABLE")
        acceptable_ids = tuple(
            sorted(item.node_id for item in direct_candidates if item.rank <= boundary)
        )
        if used_targets.intersection(acceptable_ids):
            raise M5DataError("M5_TARGET_REUSED")
        used_targets.update(acceptable_ids)
        boundary_payloads.append((request_payload, seed, acceptable_ids, boundary))

    coverage_cells = (
        ("P01", 5, "UNIQUE_EXISTING_TARGET"),
        ("P02", 3, "MULTIPLE_ACCEPTABLE_TARGETS"),
        ("P03", 3, "CROSS_BRANCH_INTERFERENCE"),
    )
    equivalent_suffixes = {
        5: "证据要求",
        6: "生效范围",
        7: "通知策略",
    }
    proceed_index = 0
    for coverage_cell, count, risk in coverage_cells:
        for _ in range(count):
            branch_index = proceed_index % len(BRANCH_GROUPS)
            group_index = (proceed_index * 3 + 2) % 10
            if coverage_cell == "P02":
                first, second = _equivalent_records(
                    catalog,
                    branch_index,
                    equivalent_suffixes[branch_index],
                    used_targets=used_targets,
                )
                target_records = [first, second]
                record = first
            else:
                record = _record_for(
                    catalog,
                    branch_index,
                    group_index,
                    used_targets=used_targets,
                    forbidden_fragments=("核验周期", "责任边界"),
                )
                target_records = [record]
            target_ids = tuple(sorted(item["node_id"] for item in target_records))
            used_targets.update(target_ids)
            group_node_id = record["group_node_id"]
            if coverage_cell == "P01":
                requirement = f"复用“{record['name']}”既有属性合同，不新增同义字段。"
                subject = record["name"]
                parent = group_node_id if proceed_index % 2 == 0 else None
                tags = ("EXACT_NAME",)
            elif coverage_cell == "P02":
                requirement = (
                    f"“{target_records[0]['name']}”或“{target_records[1]['name']}”"
                    "具有相同类型与基数，任一既有合同均可复用，不新增第三份定义。"
                )
                subject = " ".join(item["name"] for item in target_records)
                parent = None
                tags = ("EQUIVALENT_SCOPE",)
            else:
                distractor_branch = (branch_index + 1) % len(BRANCH_GROUPS)
                distractor = _record_for(
                    catalog,
                    distractor_branch,
                    group_index,
                    used_targets=used_targets,
                    forbidden_fragments=("核验周期", "责任边界"),
                )
                requirement = (
                    f"在“{record['branch_name']}”语境复用“{record['name']}”，"
                    f"不要误用另一分支的“{distractor['name']}”。"
                )
                subject = f"{record['name']} {distractor['name']}"
                parent = None
                tags = ("DISTRACTOR_PRESENT",)
            request_payload = _request(
                requirement,
                parent_node_id=parent,
                node_kind="PROPERTY",
                value_type=record["value_type"],
                cardinality=record["cardinality"],
            )
            append_item(
                selection_status="EXECUTION",
                coverage_cell=coverage_cell,
                branch_index=branch_index,
                primary_risk=risk,
                analysis_tags=tags,
                request_payload=request_payload,
                expected_route="PROCEED",
                subject=subject,
                acceptable_node_ids=target_ids,
                top_k=8,
                recommendation_outcomes=_positive_outcomes(target_ids),
                safe_actions=("NEED_CLARIFICATION", "ABSTAIN"),
                rationale_code="TARGET_UNCERTAINTY_REQUIRES_HUMAN",
            )
            proceed_index += 1

    for boundary_index, (request_payload, seed, acceptable_ids, boundary) in enumerate(
        boundary_payloads
    ):
        planned_branch_index = proceed_index % len(BRANCH_GROUPS)
        target_record = next(
            (
                records_by_id[node_id]
                for node_id in acceptable_ids
                if records_by_id[node_id]["branch_index"] == planned_branch_index
            ),
            records_by_id[acceptable_ids[-1]],
        )
        append_item(
            selection_status="EXECUTION",
            coverage_cell="P04",
            branch_index=target_record["branch_index"],
            primary_risk="TOP_K_BOUNDARY",
            analysis_tags=("EXACT_BOUNDARY",),
            request_payload=request_payload,
            expected_route="PROCEED",
            subject=seed["subject"],
            acceptable_node_ids=acceptable_ids,
            top_k=boundary,
            recommendation_outcomes=_positive_outcomes(acceptable_ids),
            safe_actions=("NEED_CLARIFICATION", "ABSTAIN"),
            rationale_code="BOUNDARY_TARGET_REQUIRES_HUMAN",
        )
        proceed_index += 1

    conflict_modes = ("KIND", "VALUE_TYPE", "CARDINALITY")
    for conflict_index, conflict_mode in enumerate(conflict_modes):
        branch_index = proceed_index % len(BRANCH_GROUPS)
        group_index = (proceed_index * 3 + 2) % 10
        record = _record_for(
            catalog,
            branch_index,
            group_index,
            used_targets=used_targets,
            forbidden_fragments=("核验周期", "责任边界"),
        )
        used_targets.add(record["node_id"])
        node_kind = "CONCEPT" if conflict_mode == "KIND" else "PROPERTY"
        value_type = record["value_type"]
        cardinality = record["cardinality"]
        if conflict_mode == "VALUE_TYPE":
            value_type = "boolean" if value_type != "boolean" else "string"
        if conflict_mode == "CARDINALITY":
            cardinality = "MULTIPLE" if cardinality == "SINGLE" else "SINGLE"
        request_payload = _request(
            f"复用“{record['name']}”，但请求中的{conflict_mode.lower()}提示与现有合同冲突。",
            parent_node_id=record["group_node_id"],
            node_kind=node_kind,
            value_type=value_type,
            cardinality=cardinality,
        )
        outcome = RecommendationOracleOutcome("NEED_CLARIFICATION", None, None)
        append_item(
            selection_status="EXECUTION",
            coverage_cell="P05",
            branch_index=branch_index,
            primary_risk=f"{conflict_mode}_CONFLICT",
            analysis_tags=("EXPLICIT_CONTRACT_CONFLICT",),
            request_payload=request_payload,
            expected_route="PROCEED",
            subject=record["name"],
            acceptable_node_ids=(record["node_id"],),
            top_k=8,
            recommendation_outcomes=(outcome,),
            safe_actions=("ABSTAIN",),
            rationale_code="CONTRACT_CONFLICT_REQUIRES_REVIEW",
        )
        proceed_index += 1

    for missing_index in range(2):
        branch_index = proceed_index % len(BRANCH_GROUPS)
        unique_subject = ("m5voidalpha", "m5voidbeta")[missing_index]
        request_payload = _request(
            f"需要定义“{unique_subject}”，当前树与外部来源均未提供可复用证据。",
            parent_node_id=None,
            node_kind="PROPERTY",
            value_type="string",
            cardinality="SINGLE",
        )
        preferred_action = ("NEED_EVIDENCE", "ABSTAIN")[missing_index]
        outcome = RecommendationOracleOutcome(preferred_action, None, None)
        append_item(
            selection_status="EXECUTION",
            coverage_cell="P06",
            branch_index=branch_index,
            primary_risk="INSUFFICIENT_EXTERNAL_EVIDENCE",
            analysis_tags=("HARD_NEGATIVE",),
            request_payload=request_payload,
            expected_route="PROCEED",
            subject=unique_subject,
            acceptable_node_ids=(),
            top_k=8,
            recommendation_outcomes=(outcome,),
            safe_actions=("NEED_CLARIFICATION", "NEED_EVIDENCE", "ABSTAIN"),
            rationale_code="EXTERNAL_EVIDENCE_REQUIRED",
            empty_retrieval_status="NO_CANDIDATES",
        )
        proceed_index += 1

    clarify_cells = (
        ("C01", "主体归属"),
        ("C01", "对象边界"),
        ("C02", "采用单体还是成员集合"),
        ("C02", "采用成员集合还是聚合口径"),
        ("C03", "决定动作的确认事实"),
        ("C03", "决定目标的确认事实"),
    )
    for clarify_index, (coverage_cell, risk) in enumerate(clarify_cells):
        branch_index = 4 + clarify_index
        branch_name = BRANCH_GROUPS[branch_index][0]
        request_payload = _request(
            f"请为{branch_name}补充一项协同定义，但当前描述没有说明{risk}。",
            parent_node_id=None,
            node_kind="UNKNOWN",
            value_type=None,
            cardinality="UNKNOWN",
        )
        append_item(
            selection_status="EXECUTION",
            coverage_cell=coverage_cell,
            branch_index=branch_index,
            primary_risk=risk,
            analysis_tags=("USER_ANSWERABLE",),
            request_payload=request_payload,
            expected_route="CLARIFY",
            subject=branch_name,
            acceptable_node_ids=(),
            top_k=None,
            recommendation_outcomes=(),
            safe_actions=("NEED_CLARIFICATION",),
            rationale_code="AMBIGUITY_REQUIRES_USER_INPUT",
        )

    reserve_specs = (
        ("P01", "UNIQUE_EXISTING_TARGET"),
        ("P03", "CROSS_BRANCH_INTERFERENCE"),
        ("P05", "VALUE_TYPE_CONFLICT"),
        ("P06", "INSUFFICIENT_EXTERNAL_EVIDENCE"),
        ("C01", "主体归属"),
        ("C03", "决定目标的确认事实"),
    )
    for reserve_index, (coverage_cell, risk) in enumerate(reserve_specs):
        branch_index = reserve_index % len(BRANCH_GROUPS)
        if coverage_cell.startswith("C"):
            request_payload = _request(
                f"请在{BRANCH_GROUPS[branch_index][0]}补充协同结构，但仍需用户明确{risk}。",
                parent_node_id=None,
                node_kind="UNKNOWN",
                value_type=None,
                cardinality="UNKNOWN",
            )
            append_item(
                selection_status="RESERVE",
                coverage_cell=coverage_cell,
                branch_index=branch_index,
                primary_risk=risk,
                analysis_tags=("BOUNDED_RESERVE",),
                request_payload=request_payload,
                expected_route="CLARIFY",
                subject=BRANCH_GROUPS[branch_index][0],
                acceptable_node_ids=(),
                top_k=None,
                recommendation_outcomes=(),
                safe_actions=("NEED_CLARIFICATION",),
                rationale_code="AMBIGUITY_REQUIRES_USER_INPUT",
            )
            continue
        if coverage_cell == "P06":
            unique_subject = "m5voidgamma"
            request_payload = _request(
                f"需要定义“{unique_subject}”，但没有现有树证据或外部来源。",
                parent_node_id=None,
                node_kind="PROPERTY",
                value_type="string",
                cardinality="SINGLE",
            )
            append_item(
                selection_status="RESERVE",
                coverage_cell=coverage_cell,
                branch_index=branch_index,
                primary_risk=risk,
                analysis_tags=("BOUNDED_RESERVE", "HARD_NEGATIVE"),
                request_payload=request_payload,
                expected_route="PROCEED",
                subject=unique_subject,
                acceptable_node_ids=(),
                top_k=8,
                recommendation_outcomes=(
                    RecommendationOracleOutcome("NEED_EVIDENCE", None, None),
                ),
                safe_actions=("NEED_CLARIFICATION", "ABSTAIN"),
                rationale_code="EXTERNAL_EVIDENCE_REQUIRED",
                empty_retrieval_status="NO_CANDIDATES",
            )
            continue
        group_index = (reserve_index * 2 + 1) % 10
        record = _record_for(
            catalog,
            branch_index,
            group_index,
            used_targets=used_targets,
            forbidden_fragments=("核验周期", "责任边界"),
        )
        used_targets.add(record["node_id"])
        requirement = f"备用验证：复用“{record['name']}”且不新增同义合同。"
        subject = record["name"]
        request_value_type = record["value_type"]
        if coverage_cell == "P03":
            distractor = _record_for(
                catalog,
                (branch_index + 1) % len(BRANCH_GROUPS),
                group_index,
                used_targets=used_targets,
                forbidden_fragments=("核验周期", "责任边界"),
            )
            requirement = (
                f"备用验证：在“{record['branch_name']}”复用“{record['name']}”，"
                f"不要误用“{distractor['name']}”。"
            )
            subject = f"{record['name']} {distractor['name']}"
        elif coverage_cell == "P05":
            request_value_type = (
                "boolean" if record["value_type"] != "boolean" else "string"
            )
            requirement = (
                f"备用验证：复用“{record['name']}”，但 value_type 提示与现有合同冲突。"
            )
        request_payload = _request(
            requirement,
            parent_node_id=None,
            node_kind="PROPERTY",
            value_type=request_value_type,
            cardinality=record["cardinality"],
        )
        outcome = (
            RecommendationOracleOutcome("NEED_CLARIFICATION", None, None)
            if coverage_cell == "P05"
            else RecommendationOracleOutcome(
                "USE_EXISTING_NODE",
                record["node_id"],
                "SEMANTICALLY_EQUIVALENT",
            )
        )
        append_item(
            selection_status="RESERVE",
            coverage_cell=coverage_cell,
            branch_index=branch_index,
            primary_risk=risk,
            analysis_tags=("BOUNDED_RESERVE",),
            request_payload=request_payload,
            expected_route="PROCEED",
            subject=subject,
            acceptable_node_ids=(record["node_id"],),
            top_k=8,
            recommendation_outcomes=(outcome,),
            safe_actions=("NEED_CLARIFICATION", "ABSTAIN"),
            rationale_code=(
                "CONTRACT_CONFLICT_REQUIRES_REVIEW"
                if coverage_cell == "P05"
                else "TARGET_UNCERTAINTY_REQUIRES_HUMAN"
            ),
        )

    scenario_payload = {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "dataset_ref": DATASET_REF,
        "source_tree_digest": tree.snapshot_hash,
        "candidates": scenarios,
    }
    scenario_payload["candidate_set_digest"] = canonical_digest(scenario_payload)
    oracle_payload = {
        "schema_version": ORACLE_SCHEMA_VERSION,
        "dataset_ref": DATASET_REF,
        "source_tree_digest": tree.snapshot_hash,
        "source_candidate_set_digest": scenario_payload["candidate_set_digest"],
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "PROPOSED",
        "review_authority": "NOT_REVIEWED",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "model_input_forbidden": True,
        "items": oracle_items,
    }
    oracle_payload["oracle_digest"] = canonical_digest(oracle_payload)
    return scenario_payload, oracle_payload


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_dataset(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise M5DataError("M5_OUTPUT_ALREADY_EXISTS")
    output_dir.mkdir(parents=True, mode=0o755)
    document, catalog = build_tree_document()
    imported = adapt_tree_document(document, source_hint="m5-cleanroom-generator")
    if not imported.is_valid or imported.tree is None:
        raise M5DataError("M5_GENERATED_TREE_INVALID")
    tree = imported.tree
    scenario_payload, oracle_payload = build_scenarios_and_oracle(tree, catalog)
    tree_bytes = _json_bytes(document)
    scenario_bytes = _json_bytes(scenario_payload)
    oracle_bytes = _json_bytes(oracle_payload)
    (output_dir / TREE_FILE).write_bytes(tree_bytes)
    (output_dir / SCENARIO_FILE).write_bytes(scenario_bytes)
    (output_dir / ORACLE_FILE).write_bytes(oracle_bytes)
    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "dataset_ref": DATASET_REF,
        "title": "完全虚构消防 M5 人工在环资格候选集",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "domain": "FICTIONAL_FIRE_GOVERNANCE",
        "benchmark_role": "ASSISTED_SHADOW_QUALIFICATION",
        "variant": "MEDIUM",
        "resource_id": "fictional-m5-lanyue-resource",
        "version": "FM5-V1",
        "assisted_policy_version": ASSISTED_POLICY_VERSION,
        "tree_file": TREE_FILE,
        "tree_file_sha256": _raw_sha256(tree_bytes),
        "tree_canonical_digest": tree.snapshot_hash,
        "node_count": len(tree.nodes),
        "value_envelope_count": imported.observed_value_count,
        "scenario_file": SCENARIO_FILE,
        "scenario_file_sha256": _raw_sha256(scenario_bytes),
        "oracle_file": ORACLE_FILE,
        "oracle_file_sha256": _raw_sha256(oracle_bytes),
        "candidate_count": len(scenario_payload["candidates"]),
        "execution_count": EXECUTION_COUNT,
        "reserve_count": RESERVE_COUNT,
        "proceed_count": PROCEED_COUNT,
        "clarify_count": CLARIFY_COUNT,
        "model_exposed": False,
        "human_review_status": "NOT_STARTED",
        "limitations": [
            "完全虚构数据，不代表真实消防字段或业务结构。",
            "候选与 Oracle 尚未经获授权人员审核，不具备执行资格。",
            "本资格集只验证当前消防领域人工在环 Shadow，不证明跨领域泛化。",
        ],
    }
    (output_dir / MANIFEST_FILE).write_bytes(_json_bytes(manifest))
    return manifest


def _load_json(path: Path, *, max_bytes: int) -> Any:
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise M5DataError("M5_FILE_TOO_LARGE")
    try:
        return strict_json_loads(data)
    except (UnicodeError, ValueError):
        raise M5DataError("M5_JSON_INVALID") from None


def _validate_exact_keys(payload: Any, keys: set[str], code: str) -> None:
    if not isinstance(payload, dict) or set(payload) != keys:
        raise M5DataError(code)


def _validate_intent_profile_support(
    oracle: CapabilityOracle,
    request: dict[str, Any],
) -> None:
    expected = IntentOracleProfile(
        "P001", _intent_expectations(request, oracle.expected_route)
    )
    if oracle.acceptable_intent_profiles != (expected,):
        raise M5DataError("M5_INTENT_PROFILE_NOT_REQUEST_BOUND")


def _structure_metrics(tree: Any) -> dict[str, int]:
    nodes = {node.node_id: node for node in tree.nodes}
    direct_suffix_sets: Counter[tuple[str, ...]] = Counter()
    structural_signatures: Counter[tuple[Any, ...]] = Counter()
    numbered_names = 0
    maximum_depth = 0
    maximum_children = 0
    for node in tree.nodes:
        maximum_depth = max(maximum_depth, len(node.path_labels) - 1)
        maximum_children = max(maximum_children, len(node.child_node_ids))
        if _NUMBERED_NAME.search(node.name):
            numbered_names += 1
        if node.kind != "CONCEPT" or len(node.path_labels) != 3:
            continue
        children = [nodes[node_id] for node_id in node.child_node_ids]
        suffixes = tuple(
            sorted(
                child.name.removeprefix(node.name)
                for child in children
                if child.name.startswith(node.name)
            )
        )
        direct_suffix_sets[suffixes] += 1
        signature = tuple(
            (
                child.kind,
                child.value_contract.value_type if child.value_contract else None,
                child.value_contract.cardinality if child.value_contract else None,
                len(child.child_node_ids),
            )
            for child in children
        )
        structural_signatures[signature] += 1
    return {
        "numbered_name_count": numbered_names,
        "maximum_depth": maximum_depth,
        "maximum_direct_child_count": maximum_children,
        "largest_repeated_suffix_set": max(direct_suffix_sets.values(), default=0),
        "largest_repeated_structural_signature": max(
            structural_signatures.values(), default=0
        ),
    }


def preflight_dataset(dataset_dir: Path) -> dict[str, Any]:
    manifest = _load_json(dataset_dir / MANIFEST_FILE, max_bytes=128_000)
    scenarios = _load_json(dataset_dir / SCENARIO_FILE, max_bytes=1_000_000)
    oracle_sidecar = _load_json(dataset_dir / ORACLE_FILE, max_bytes=2_000_000)
    _validate_exact_keys(manifest, _MANIFEST_KEYS, "M5_MANIFEST_FIELDS_INVALID")
    if (
        manifest["schema_version"] != DATASET_SCHEMA_VERSION
        or manifest["generator_version"] != GENERATOR_VERSION
        or manifest["dataset_ref"] != DATASET_REF
        or manifest["source_class"] != "CLEANROOM_SYNTHETIC"
        or manifest["fictional"] is not True
        or manifest["derived_from_real"] is not False
        or manifest["model_exposed"] is not False
        or manifest["human_review_status"] != "NOT_STARTED"
        or manifest["assisted_policy_version"] != ASSISTED_POLICY_VERSION
    ):
        raise M5DataError("M5_MANIFEST_POLICY_INVALID")
    for file_key, sha_key in (
        ("tree_file", "tree_file_sha256"),
        ("scenario_file", "scenario_file_sha256"),
        ("oracle_file", "oracle_file_sha256"),
    ):
        file_path = dataset_dir / manifest[file_key]
        if _raw_sha256(file_path.read_bytes()) != manifest[sha_key]:
            raise M5DataError("M5_FILE_DIGEST_MISMATCH")

    imported = load_tree_export(dataset_dir / manifest["tree_file"])
    if not imported.is_valid or imported.tree is None:
        raise M5DataError("M5_TREE_INVALID")
    tree = imported.tree
    if (
        len(tree.nodes) != manifest["node_count"]
        or tree.snapshot_hash != manifest["tree_canonical_digest"]
        or not MIN_NODE_COUNT <= len(tree.nodes) <= MAX_NODE_COUNT
        or imported.observed_value_count != 0
        or manifest["value_envelope_count"] != 0
    ):
        raise M5DataError("M5_TREE_POLICY_INVALID")
    structure = _structure_metrics(tree)
    if (
        structure["numbered_name_count"] != 0
        or structure["maximum_depth"] > 4
        or structure["maximum_direct_child_count"] > 12
        or structure["largest_repeated_suffix_set"] > 1
        or structure["largest_repeated_structural_signature"] > 4
    ):
        raise M5DataError("M5_TREE_COMBINATION_DENSITY_INVALID")

    if (
        not isinstance(scenarios, dict)
        or set(scenarios) != {
            "schema_version",
            "dataset_ref",
            "source_tree_digest",
            "candidates",
            "candidate_set_digest",
        }
        or scenarios["schema_version"] != SCENARIO_SCHEMA_VERSION
        or scenarios["dataset_ref"] != DATASET_REF
        or scenarios["source_tree_digest"] != tree.snapshot_hash
        or not isinstance(scenarios["candidates"], list)
    ):
        raise M5DataError("M5_SCENARIO_CONTRACT_INVALID")
    scenario_payload = dict(scenarios)
    candidate_set_digest = scenario_payload.pop("candidate_set_digest")
    if candidate_set_digest != canonical_digest(scenario_payload):
        raise M5DataError("M5_SCENARIO_DIGEST_MISMATCH")

    if (
        not isinstance(oracle_sidecar, dict)
        or set(oracle_sidecar) != {
            "schema_version",
            "dataset_ref",
            "source_tree_digest",
            "source_candidate_set_digest",
            "source_class",
            "fictional",
            "derived_from_real",
            "quality_tier",
            "review_authority",
            "gold_eligible",
            "gate_eligible",
            "patch_eligible",
            "model_input_forbidden",
            "items",
            "oracle_digest",
        }
        or oracle_sidecar["schema_version"] != ORACLE_SCHEMA_VERSION
        or oracle_sidecar["source_candidate_set_digest"] != candidate_set_digest
        or oracle_sidecar["source_tree_digest"] != tree.snapshot_hash
        or oracle_sidecar["source_class"] != "CLEANROOM_SYNTHETIC"
        or oracle_sidecar["fictional"] is not True
        or oracle_sidecar["derived_from_real"] is not False
        or oracle_sidecar["quality_tier"] != "PROPOSED"
        or oracle_sidecar["review_authority"] != "NOT_REVIEWED"
        or oracle_sidecar["gold_eligible"] is not False
        or oracle_sidecar["gate_eligible"] is not False
        or oracle_sidecar["patch_eligible"] is not False
        or oracle_sidecar["model_input_forbidden"] is not True
        or not isinstance(oracle_sidecar["items"], list)
    ):
        raise M5DataError("M5_ORACLE_CONTRACT_INVALID")
    oracle_payload = dict(oracle_sidecar)
    oracle_digest = oracle_payload.pop("oracle_digest")
    if oracle_digest != canonical_digest(oracle_payload):
        raise M5DataError("M5_ORACLE_DIGEST_MISMATCH")

    candidates = scenarios["candidates"]
    oracle_items = oracle_sidecar["items"]
    if len(candidates) != EXECUTION_COUNT + RESERVE_COUNT or len(oracle_items) != len(candidates):
        raise M5DataError("M5_SCENARIO_COUNT_INVALID")
    refs = tuple(item.get("scenario_ref") for item in candidates)
    if refs != tuple(f"M5S{index:03d}" for index in range(1, len(candidates) + 1)):
        raise M5DataError("M5_SCENARIO_ORDER_INVALID")
    oracle_by_ref: dict[str, dict[str, Any]] = {}
    for item in oracle_items:
        _validate_exact_keys(item, _ORACLE_ITEM_KEYS, "M5_ORACLE_ITEM_FIELDS_INVALID")
        _validate_exact_keys(
            item["retrieval_seed"],
            _RETRIEVAL_SEED_KEYS,
            "M5_RETRIEVAL_SEED_FIELDS_INVALID",
        )
        _validate_exact_keys(
            item["safe_alternative"],
            _SAFE_ALTERNATIVE_KEYS,
            "M5_SAFE_ALTERNATIVE_FIELDS_INVALID",
        )
        if item["scenario_ref"] in oracle_by_ref:
            raise M5DataError("M5_ORACLE_REFERENCE_DUPLICATE")
        oracle_by_ref[item["scenario_ref"]] = item
    if set(oracle_by_ref) != set(refs):
        raise M5DataError("M5_ORACLE_REFERENCE_MISMATCH")

    selection_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    execution_branch_counts: Counter[str] = Counter()
    execution_branches: set[str] = set()
    target_use: Counter[str] = Counter()
    retrieval_match_count = 0
    model_projection_count = 0
    tree_ids = {node.node_id for node in tree.nodes}
    for candidate in candidates:
        _validate_exact_keys(candidate, _SCENARIO_KEYS, "M5_SCENARIO_FIELDS_INVALID")
        _validate_exact_keys(candidate["request"], _REQUEST_KEYS, "M5_REQUEST_FIELDS_INVALID")
        if candidate["selection_status"] not in _SELECTION_STATUSES:
            raise M5DataError("M5_SELECTION_STATUS_INVALID")
        if candidate["expected_route"] not in _EXPECTED_ROUTES:
            raise M5DataError("M5_EXPECTED_ROUTE_INVALID")
        if (
            not isinstance(candidate["analysis_tags"], list)
            or not candidate["analysis_tags"]
            or len(candidate["analysis_tags"]) > 2
        ):
            raise M5DataError("M5_ANALYSIS_TAGS_INVALID")
        selection_counts[candidate["selection_status"]] += 1
        oracle_item = oracle_by_ref[candidate["scenario_ref"]]
        if oracle_item["expected_route"] != candidate["expected_route"]:
            raise M5DataError("M5_ROUTE_SOURCE_MISMATCH")
        try:
            capability_oracle = CapabilityOracle.from_dict(
                oracle_item["capability_oracle"]
            )
        except (TypeError, ValueError):
            raise M5DataError("M5_CAPABILITY_ORACLE_INVALID") from None
        _validate_intent_profile_support(capability_oracle, candidate["request"])
        actions = oracle_item["safe_alternative"]["allowed_actions"]
        rationale_code = oracle_item["safe_alternative"]["rationale_code"]
        if (
            not isinstance(actions, list)
            or not actions
            or len(actions) != len(set(actions))
            or any(action not in _NON_TARGETING_ACTIONS for action in actions)
            or not isinstance(rationale_code, str)
            or _FIXED_CODE.fullmatch(rationale_code) is None
        ):
            raise M5DataError("M5_SAFE_ALTERNATIVE_POLICY_INVALID")
        evidence_ids = oracle_item["evidence_node_ids"]
        if (
            not isinstance(evidence_ids, list)
            or evidence_ids != sorted(set(evidence_ids))
            or any(node_id not in tree_ids for node_id in evidence_ids)
        ):
            raise M5DataError("M5_EVIDENCE_NODE_SOURCE_MISMATCH")
        if candidate["selection_status"] == "EXECUTION":
            route_counts[candidate["expected_route"]] += 1
            execution_branch_counts[candidate["primary_branch_ref"]] += 1
            execution_branches.add(candidate["primary_branch_ref"])
            for node_id in evidence_ids:
                target_use[node_id] += 1
        request = IntentRequest(
            requirement_text=candidate["request"]["requirement_text"],
            proposed_parent_node_id=candidate["request"]["proposed_parent_node_id"],
            node_kind_hint=candidate["request"]["node_kind_hint"],
            value_type_hint=candidate["request"]["value_type_hint"],
            cardinality_hint=candidate["request"]["cardinality_hint"],
        )
        model_view = request.to_model_dict(tree)
        serialized_model_view = json.dumps(model_view, ensure_ascii=False, sort_keys=True)
        forbidden_values = (
            tree.tree_id,
            tree.version_record_id,
            oracle_digest,
            candidate_set_digest,
            *evidence_ids,
        )
        if any(value and value in serialized_model_view for value in forbidden_values):
            raise M5DataError("M5_MODEL_PROJECTION_LEAK")
        model_projection_count += 1
        if candidate["expected_route"] == "PROCEED":
            candidate_set = _candidate_set_for(
                candidate["request"], oracle_item["retrieval_seed"], tree
            )
            if not retrieval_matches_oracle(candidate_set, capability_oracle.retrieval):
                raise M5DataError("M5_RETRIEVAL_ORACLE_UNREPLAYABLE")
            semantic_candidate_ids = {
                item.node_id for item in candidate_set.candidates[:8]
            }
            if any(
                outcome.target_node_id is not None
                and outcome.target_node_id not in semantic_candidate_ids
                for outcome in capability_oracle.recommendation.acceptable_outcomes
            ):
                raise M5DataError("M5_SEMANTIC_TARGET_NOT_PROJECTABLE")
            retrieval_match_count += 1

    if (
        selection_counts != Counter({"EXECUTION": EXECUTION_COUNT, "RESERVE": RESERVE_COUNT})
        or route_counts != Counter({"PROCEED": PROCEED_COUNT, "CLARIFY": CLARIFY_COUNT})
        or len(execution_branches) < MIN_TOP_LEVEL_BRANCHES
        or max(execution_branch_counts.values(), default=0) > MAX_EXECUTION_SCENARIOS_PER_BRANCH
        or max(target_use.values(), default=0) > 1
    ):
        raise M5DataError("M5_COVERAGE_POLICY_INVALID")

    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "dataset_ref": DATASET_REF,
        "status": "PASS",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "node_count": len(tree.nodes),
        "value_envelope_count": imported.observed_value_count,
        "top_level_branch_count": len(tree.root_node_ids) and len(
            {node.path_labels[1] for node in tree.nodes if len(node.path_labels) > 1}
        ),
        "candidate_count": len(candidates),
        "execution_count": selection_counts["EXECUTION"],
        "reserve_count": selection_counts["RESERVE"],
        "proceed_count": route_counts["PROCEED"],
        "clarify_count": route_counts["CLARIFY"],
        "covered_execution_branch_count": len(execution_branches),
        "maximum_execution_scenarios_per_branch": max(
            execution_branch_counts.values(), default=0
        ),
        "retrieval_replay_match_count": retrieval_match_count,
        "model_projection_count": model_projection_count,
        "model_projection_leak_count": 0,
        "blocking_finding_count": 0,
        "structure_metrics": structure,
        "human_review_status": "NOT_STARTED",
        "model_called": False,
    }


def build_codex_silver_review(dataset_dir: Path) -> dict[str, Any]:
    report = preflight_dataset(dataset_dir)
    scenarios = _load_json(dataset_dir / SCENARIO_FILE, max_bytes=1_000_000)
    items = [
        {
            "scenario_ref": item["scenario_ref"],
            "status": "SILVER_ACCEPTED",
            "finding_codes": [],
        }
        for item in scenarios["candidates"]
    ]
    return {
        "schema_version": SILVER_REVIEW_SCHEMA_VERSION,
        "dataset_ref": DATASET_REF,
        "quality_tier": "SILVER",
        "assessment_authority": "CODEX_ASSISTED",
        "execution_eligible": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "reviewed_candidate_count": len(items),
        "accepted_candidate_count": len(items),
        "blocking_finding_count": report["blocking_finding_count"],
        "items": items,
    }


def build_review_rows(dataset_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return private human-review rows after full deterministic preflight."""

    preflight = preflight_dataset(dataset_dir)
    scenarios = _load_json(dataset_dir / SCENARIO_FILE, max_bytes=1_000_000)
    oracle_sidecar = _load_json(dataset_dir / ORACLE_FILE, max_bytes=2_000_000)
    imported = load_tree_export(dataset_dir / TREE_FILE)
    if imported.tree is None:
        raise M5DataError("M5_TREE_INVALID")
    node_names = {node.node_id: node.name for node in imported.tree.nodes}
    oracle_by_ref = {
        item["scenario_ref"]: item for item in oracle_sidecar["items"]
    }
    rows: list[dict[str, Any]] = []
    for candidate in scenarios["candidates"]:
        oracle_item = oracle_by_ref[candidate["scenario_ref"]]
        evidence_ids = oracle_item["evidence_node_ids"]
        rows.append(
            {
                "scenario_ref": candidate["scenario_ref"],
                "selection_status": candidate["selection_status"],
                "coverage_cell": candidate["coverage_cell"],
                "primary_branch_name": candidate["primary_branch_name"],
                "primary_risk": candidate["primary_risk"],
                "analysis_tags": candidate["analysis_tags"],
                "request": candidate["request"],
                "expected_route": oracle_item["expected_route"],
                "target_names": [node_names[node_id] for node_id in evidence_ids],
                "capability_oracle": oracle_item["capability_oracle"],
                "safe_alternative": oracle_item["safe_alternative"],
            }
        )
    return preflight, rows


def write_json_new(path: Path, payload: Any) -> None:
    """Write one deterministic public clean-room artifact without overwriting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(_json_bytes(payload))
    except FileExistsError:
        raise M5DataError("M5_OUTPUT_ALREADY_EXISTS") from None


__all__ = [
    "DATASET_REF",
    "MANIFEST_FILE",
    "ORACLE_FILE",
    "PREFLIGHT_FILE",
    "SCENARIO_FILE",
    "SILVER_REVIEW_FILE",
    "M5DataError",
    "build_codex_silver_review",
    "build_review_rows",
    "build_tree_document",
    "preflight_dataset",
    "write_json_new",
    "write_dataset",
]
