#!/usr/bin/env python3
"""Generate the sealed M4.9 clean-room candidate batch without model calls."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from treeguard.adapter import adapt_tree_document
from treeguard.change_intent import (
    MODEL_OUTPUT_SCHEMA_VERSION,
    ChangeIntentDraft,
    IntentContent,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.hashing import canonical_digest
from treeguard.private_io import write_private_json
from treeguard.retrieval import build_candidate_set
from treeguard.scenario_capability_validation import (
    CapabilityOracle,
    IntentFieldExpectation,
    IntentOracleProfile,
    RecommendationOracle,
    RecommendationOracleOutcome,
    RetrievalOracle,
)

DATASET_REF = "fictional-fire-m49-sealed-v1"
TREE_ID = "fictional-lanxuwan-fire-governance"
TREE_VERSION = "M49-SEALED-V1"
OUTPUT_DIR = ROOT / "artifacts" / "fictional-validation" / DATASET_REF
RECORDED_AT = "2026-08-04T00:00:00Z"


@dataclass(frozen=True, slots=True)
class Branch:
    name: str
    subjects: tuple[str, ...]
    facets: tuple[str, ...]


BRANCHES = (
    Branch("治理主体与职责", ("管理委员会", "消防责任人", "设施运维组", "夜间值守组", "商户协调组", "承包商管理", "安全联络员", "区域负责人", "监督检查组", "协同决策组"), ("职责边界", "授权状态", "覆盖区域", "响应时限", "替补机制", "联络方式", "审核周期", "升级条件", "证据要求")),
    Branch("建筑与防火分区", ("主楼防火分区", "裙楼共享空间", "地下设备区", "连廊接口区", "中庭边界", "竖向井道", "屋面作业区", "仓储隔间", "租户交界区", "临时封闭区"), ("边界类型", "空间编码", "分隔状态", "通行限制", "巡查频次", "风险等级", "相邻区域", "变更标识", "核验依据")),
    Branch("火情探测与报警", ("烟雾探测回路", "温度探测回路", "手动报警接口", "声光警报区域", "报警主机", "信号转发链路", "误报复核组", "故障监测区", "报警确认岗", "远端通知端"), ("监测范围", "运行状态", "信号类别", "确认时限", "故障标识", "联动目标", "测试周期", "复位条件", "责任角色")),
    Branch("疏散引导与避难", ("首层疏散路径", "地下疏散路径", "中庭引导点", "避难等候区", "无障碍转移组", "访客引导组", "夜间疏散岗", "临时绕行路线", "集合清点区", "疏散广播组"), ("服务区域", "通行状态", "容量等级", "引导角色", "替代路线", "启用条件", "检查周期", "障碍标识", "清点方式")),
    Branch("灭火介质与设施", ("室内消火栓组", "喷淋供水区", "气体灭火区", "灭火器配置点", "消防水池", "消防泵组", "泡沫接口区", "移动器材组", "备用介质库", "设施标识组"), ("设施状态", "覆盖空间", "介质类别", "容量标称", "启停模式", "检查周期", "备用状态", "责任班组", "异常等级")),
    Branch("排烟与通风控制", ("地下排烟区", "中庭排烟区", "楼梯加压区", "送风机组", "排烟风机组", "防火阀组", "风道接口段", "手动控制点", "自动联动组", "复位检查组"), ("控制范围", "运行模式", "联动状态", "阀门状态", "测试周期", "控制优先级", "故障标识", "责任班组", "复位条件")),
    Branch("消防供电与联动", ("消防主电源", "应急备用电源", "配电切换组", "联动控制柜", "电梯迫降接口", "门禁释放接口", "照明切换组", "广播联动接口", "远程控制链路", "联动复核组"), ("供电状态", "服务对象", "切换时限", "控制模式", "备用可用", "测试周期", "联动顺序", "责任班组", "异常来源")),
    Branch("日常巡检与维护", ("每日巡检组", "周度维护组", "月度复核组", "季度测试组", "缺陷工单组", "备件管理组", "服务商协同组", "夜间抽查组", "停用管理组", "恢复确认组"), ("执行周期", "覆盖对象", "责任角色", "完成状态", "逾期标识", "证据类型", "升级条件", "抽查比例", "关闭要求")),
    Branch("作业许可与风险控制", ("动火作业许可", "临时用电许可", "高处作业许可", "有限空间许可", "消防停用许可", "承包商入场", "隔离区域审批", "风险复核组", "现场监护组", "完工恢复组"), ("许可状态", "作业区域", "风险类别", "有效时段", "监护角色", "控制措施", "复核层级", "暂停条件", "恢复要求")),
    Branch("应急响应与协同", ("初期响应组", "现场指挥组", "外部联络组", "人员搜寻组", "医疗协助组", "交通管制组", "信息发布组", "物资保障组", "恢复评估组", "跨区支援组"), ("启动条件", "响应等级", "责任角色", "覆盖区域", "到场时限", "协同对象", "资源状态", "升级标识", "退出条件")),
    Branch("培训演练与能力", ("新员工培训", "值守岗位培训", "疏散引导演练", "报警处置演练", "联动控制演练", "承包商教育", "管理层桌面推演", "夜间联合演练", "专项补训组", "能力复核组"), ("适用角色", "训练主题", "计划周期", "完成状态", "合格阈值", "补训要求", "演练范围", "观察角色", "改进事项")),
    Branch("事件复盘与整改", ("事件登记组", "原因分析组", "影响评估组", "整改任务组", "责任复核组", "证据归档组", "趋势观察组", "重复问题组", "关闭验收组", "经验共享组"), ("事件类别", "影响区域", "责任角色", "原因层级", "整改状态", "完成时限", "复发标识", "验证方式", "共享范围")),
)

VALUE_TYPES = ("string", "space_code", "time_code", "entity_code", "boolean", "integer", "float")
RECORD_FACETS = ("记录时间", "执行角色", "检查结论", "关联区域", "凭证索引", "复核状态")
INTENT_FIELDS = tuple(sorted(("subject", "role", "scenario", "lifecycle", "ownership", "node_kind", "value_type", "cardinality", "confirmed_facts", "assumptions", "evidence_gaps", "clarification_question")))


def node_wrapper(node_id: str, name: str, parent_id: str | None, order: int, path: tuple[str, ...], kind: str, *, value_type: str | None = None, multiple: bool | None = None, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "node_id": node_id, "node_label": name, "node_name": name,
        "parent_node_id": parent_id, "node_type": kind.lower(), "node_order": order,
        "node_label_route": "/-/".join(path + (name,)), "extension": {},
    }
    if kind == "PROPERTY":
        metadata.update(value_type=value_type, is_list=multiple)
    return {
        "metadata": metadata,
        "subnodes": {
            item["metadata"]["node_label"]: item for item in (children or [])
        },
    }


def contract_for(facet: str, seed: int) -> tuple[str, bool]:
    if any(term in facet for term in ("标识", "可用", "逾期", "复发")):
        return "boolean", False
    if any(term in facet for term in ("时限", "时段", "时间", "周期", "频次")):
        return "time_code", "时段" in facet
    if any(term in facet for term in ("比例", "读数")):
        return "float", False
    if any(term in facet for term in ("容量", "计数", "层级", "次序", "顺序", "优先级", "阈值")):
        return "integer", False
    if any(term in facet for term in ("区域", "空间", "位置", "路线", "范围")):
        return "space_code", True
    if any(term in facet for term in ("类别", "等级", "对象", "回路")):
        return "entity_code", "对象" in facet
    multiple = any(term in facet for term in ("清单", "措施", "角色", "方式", "依据", "来源", "联络", "索引", "要求", "条件")) and seed % 3 == 0
    return "string", multiple


def build_tree_and_blueprint() -> tuple[dict[str, Any], dict[str, Any]]:
    branches: list[dict[str, Any]] = []
    subjects_blueprint: list[dict[str, Any]] = []
    node_classes = {"M49-ROOT": "APPROVED_BACKGROUND"}
    for bidx, branch in enumerate(BRANCHES, 1):
        branch_id = f"M49-B{bidx:02d}"
        node_classes[branch_id] = "APPROVED_BACKGROUND"
        subject_wrappers = []
        for sidx, subject in enumerate(branch.subjects, 1):
            subject_id = f"{branch_id}-S{sidx:02d}"
            semantic_class = "CURATED_CORE" if (bidx <= 6 and sidx <= 2) or (bidx > 6 and sidx == 1) else "APPROVED_BACKGROUND"
            node_classes[subject_id] = semantic_class
            scalar_count = 5 + ((bidx + sidx) % 3)
            record_count = 3 + ((bidx * 2 + sidx) % 3)
            properties = []
            scalar_specs = []
            for pidx in range(1, scalar_count + 1):
                facet = branch.facets[(sidx + pidx - 2) % len(branch.facets)]
                value_type, multiple = contract_for(facet, bidx * 17 + sidx * 7 + pidx)
                node_id = f"{subject_id}-P{pidx:02d}"
                name = f"{subject}{facet}"
                node_classes[node_id] = semantic_class
                properties.append(node_wrapper(node_id, name, subject_id, pidx, ("岚序湾综合体消防治理", branch.name, subject), "PROPERTY", value_type=value_type, multiple=multiple))
                scalar_specs.append({"node_id": node_id, "facet": facet, "owner_subject_id": subject_id, "scope_branch_id": branch_id, "value_type": value_type, "cardinality": "MULTIPLE" if multiple else "SINGLE"})
            collection_id = f"{subject_id}-R01"
            children = []
            for fidx in range(1, record_count + 1):
                facet = RECORD_FACETS[(bidx + sidx + fidx) % len(RECORD_FACETS)]
                value_type, multiple = contract_for(facet, bidx * 31 + sidx * 11 + fidx)
                child_id = f"{collection_id}-F{fidx:02d}"
                name = f"{subject}{facet}"
                node_classes[child_id] = semantic_class
                children.append(node_wrapper(child_id, name, collection_id, fidx, ("岚序湾综合体消防治理", branch.name, subject, f"{subject}治理记录"), "PROPERTY", value_type=value_type, multiple=multiple))
            node_classes[collection_id] = semantic_class
            properties.append(node_wrapper(collection_id, f"{subject}治理记录", subject_id, scalar_count + 1, ("岚序湾综合体消防治理", branch.name, subject), "PROPERTY", value_type="class", multiple=True, children=children))
            subject_wrappers.append(node_wrapper(subject_id, subject, branch_id, sidx, ("岚序湾综合体消防治理", branch.name), "CONCEPT", children=properties))
            subjects_blueprint.append({"subject_id": subject_id, "branch_id": branch_id, "semantic_class": semantic_class, "allowed_scalar_facets": scalar_specs, "record_collection_id": collection_id, "record_child_ids": [item["metadata"]["node_id"] for item in children], "owner_scope_status": "EXPLICIT"})
        branches.append(node_wrapper(branch_id, branch.name, "M49-ROOT", bidx, ("岚序湾综合体消防治理",), "CONCEPT", children=subject_wrappers))
    tree_doc = {"metadata": {"map_id": TREE_ID, "version": TREE_VERSION, "id": f"{TREE_ID}-v1", "map_type": "resource", "concurrent_version": 1}, "map_topology": {"岚序湾综合体消防治理": node_wrapper("M49-ROOT", "岚序湾综合体消防治理", None, 1, (), "CONCEPT", children=branches)}}
    result = adapt_tree_document(tree_doc)
    if not result.is_valid or result.tree is None:
        codes = [issue.code for issue in result.issues if issue.severity == "ERROR"]
        raise RuntimeError(f"generated tree failed the canonical adapter: {codes[:8]}")
    counts = {name: sum(value == name for value in node_classes.values()) for name in ("CURATED_CORE", "APPROVED_BACKGROUND", "STRESS_FILLER")}
    blueprint = {"schema_version": "fire-m49-sealed-blueprint.v1", "dataset_ref": DATASET_REF, "tree_snapshot_hash": result.tree.snapshot_hash, "construction_policy": "EXPLICIT_SUBJECT_BLUEPRINT_NO_CARTESIAN_PRODUCT", "filler_targetable": False, "class_counts": counts, "node_classes": dict(sorted(node_classes.items())), "subjects": subjects_blueprint}
    return tree_doc, blueprint


def request_payload(text: str, *, parent: str | None = None, kind: str = "PROPERTY", value_type: str | None = "string", cardinality: str = "SINGLE") -> dict[str, Any]:
    return {"schema_version": "intent-request.v1", "requirement_text": text, "proposed_parent_node_id": parent, "node_kind_hint": kind, "value_type_hint": value_type, "cardinality_hint": cardinality}


def intent_for(request: IntentRequest, clarify: bool = False) -> IntentContent:
    return IntentContent(
        subject=request.requirement_text,
        role=None,
        scenario=None,
        lifecycle=None,
        ownership="UNKNOWN",
        node_kind=request.node_kind_hint,
        value_type=request.value_type_hint,
        cardinality=request.cardinality_hint,
        confirmed_facts=(),
        assumptions=(),
        evidence_gaps=("需求边界尚未确定",) if clarify else (),
        clarification_question="请明确目标对象、适用范围与记录粒度。" if clarify else None,
    )


def intent_profile(request: IntentRequest, clarify: bool) -> IntentOracleProfile:
    exact: dict[str, tuple[str | None, ...]] = {"node_kind": (request.node_kind_hint,), "cardinality": (request.cardinality_hint,)}
    if request.value_type_hint is not None:
        exact["value_type"] = (request.value_type_hint,)
    expectations = []
    for field_name in INTENT_FIELDS:
        if field_name in exact:
            policy, values = "EXACT_ONE_OF", exact[field_name]
        elif field_name == "clarification_question":
            policy, values = ("NON_EMPTY", ()) if clarify else ("EXACT_ONE_OF", (None,))
        else:
            policy, values = "NOT_COMPARED", ()
        expectations.append(IntentFieldExpectation(field_name, policy, values))
    return IntentOracleProfile("P001", tuple(expectations))


def retrieval_preview(payload: dict[str, Any], tree: Any) -> Any:
    request = IntentRequest.from_dict(payload, tree)
    intent = intent_for(request)
    draft = ChangeIntentDraft.from_model_dict(
        {"schema_version": MODEL_OUTPUT_SCHEMA_VERSION, **intent.to_dict()},
        request,
        tree,
        model_provider="deterministic-fixture",
        model_capability="intent-preview",
        model_name="no-model-call",
        prompt_version="m49.preview.v1",
    )
    action = IntentReviewAction(draft.draft_hash, "CONFIRM_FOR_RETRIEVAL", "m49-fixture-builder", RECORDED_AT, intent)
    return build_candidate_set(apply_intent_review(request, draft, action, tree), tree, max_candidates=20)


def scalar_nodes(tree: Any, subject_id: str) -> list[Any]:
    return sorted(
        (node for node in tree.nodes if node.parent_node_id == subject_id and node.kind == "PROPERTY" and node.value_contract is not None and node.value_contract.value_type != "class"),
        key=lambda node: node.node_id,
    )


def make_spec(ref: str, route: str, risk: str, branch: int, request: dict[str, Any], *, target_ids: tuple[str, ...] = (), evidence_ids: tuple[str, ...] | None = None, tags: tuple[str, ...] = (), action: str = "USE_EXISTING_NODE") -> dict[str, Any]:
    return {
        "scenario_ref": ref,
        "expected_route": route,
        "primary_risk": risk,
        "secondary_tags": list(tags),
        "top_level_branch_ref": f"M49-B{branch:02d}",
        "request": request,
        "target_ids": list(target_ids),
        "evidence_ids": list(target_ids if evidence_ids is None else evidence_ids),
        "action": action,
    }


def build_specs(tree: Any) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    by_id = {node.node_id: node for node in tree.nodes}

    for index, (branch, subject) in enumerate(((1, 1), (2, 2), (3, 3), (4, 4)), 1):
        subject_id = f"M49-B{branch:02d}-S{subject:02d}"
        target = scalar_nodes(tree, subject_id)[index]
        contract = target.value_contract
        specs.append(make_spec(f"P{index:02d}", "PROCEED", "UNIQUE_TARGET", branch, request_payload(target.name, parent=subject_id, value_type=contract.value_type, cardinality=contract.cardinality), target_ids=(target.node_id,)))

    multi_groups = (
        (((1, 1), (1, 2)), "授权状态"),
        (((3, 1), (3, 2)), "运行状态"),
    )
    for index, (group, facet) in enumerate(multi_groups, 5):
        selected = []
        for branch, subject in group:
            selected.append(next(node for node in scalar_nodes(tree, f"M49-B{branch:02d}-S{subject:02d}") if node.name.endswith(facet)))
        names = "或".join(node.name for node in selected)
        specs.append(make_spec(f"P{index:02d}", "PROCEED", "MULTIPLE_ACCEPTABLE_TARGETS", group[0][0], request_payload(f"本次只识别复用候选，目标可落在{names}任一同构字段，后续上下文再选择", value_type=selected[0].value_contract.value_type, cardinality=selected[0].value_contract.cardinality), target_ids=tuple(node.node_id for node in selected)))

    for index, (branch, subject) in enumerate(((5, 3), (6, 4)), 7):
        subject_id = f"M49-B{branch:02d}-S{subject:02d}"
        evidence = scalar_nodes(tree, subject_id)[2]
        wrong_type = "integer" if evidence.value_contract.value_type != "integer" else "string"
        specs.append(make_spec(f"P{index:02d}", "PROCEED", "HARD_NEGATIVE", branch, request_payload(evidence.name, parent=subject_id, value_type=wrong_type, cardinality=evidence.value_contract.cardinality), evidence_ids=(evidence.node_id,), action="ABSTAIN"))

    top_k_requests = (
        (9, 10, "应急响应结束后的状态复核", "恢复评估组复核状态"),
        (10, 12, "事件整改任务状态核验", "整改任务组整改状态"),
    )
    for index, branch, text, target_name in top_k_requests:
        payload = request_payload(text)
        preview = retrieval_preview(payload, tree)
        target = next((candidate for candidate in preview.candidates if candidate.name == target_name), None)
        if target is None or target.rank < 2:
            raise RuntimeError("Top-K challenge target is not on a meaningful boundary")
        specs.append(make_spec(f"P{index:02d}", "PROCEED", "TOP_K_BOUNDARY", branch, payload, target_ids=(target.node_id,), tags=("LEXICAL_INTERFERENCE",)))

    for index, (branch, subject, wrong_branch) in enumerate(((1, 5, 12), (4, 6, 2), (8, 7, 3)), 11):
        subject_id = f"M49-B{branch:02d}-S{subject:02d}"
        target = scalar_nodes(tree, subject_id)[3]
        contract = target.value_contract
        wrong_parent = f"M49-B{wrong_branch:02d}-S01"
        specs.append(make_spec(f"P{index:02d}", "PROCEED", "CROSS_BRANCH_WRONG_PARENT", branch, request_payload(target.name, parent=wrong_parent, value_type=contract.value_type, cardinality=contract.cardinality), target_ids=(target.node_id,), tags=("PARENT_INTERFERENCE",)))

    for index, (branch, subject) in enumerate(((6, 8), (9, 8)), 14):
        subject_id = f"M49-B{branch:02d}-S{subject:02d}"
        evidence = scalar_nodes(tree, subject_id)[0]
        specs.append(make_spec(f"P{index:02d}", "PROCEED", "KIND_CONFLICT", branch, request_payload(evidence.name, parent=subject_id, kind="CONCEPT", value_type=None), evidence_ids=(evidence.node_id,), action="ABSTAIN"))

    for index, (branch, subject) in enumerate(((5, 9), (7, 9)), 16):
        subject_id = f"M49-B{branch:02d}-S{subject:02d}"
        evidence = scalar_nodes(tree, subject_id)[1]
        contract = evidence.value_contract
        wanted = "MULTIPLE" if contract.cardinality == "SINGLE" else "SINGLE"
        specs.append(make_spec(f"P{index:02d}", "PROCEED", "CARDINALITY_SCOPE_CONFLICT", branch, request_payload(evidence.name, parent=subject_id, value_type=contract.value_type, cardinality=wanted), evidence_ids=(evidence.node_id,), action="ABSTAIN"))

    subject_id = "M49-B10-S10"
    evidence = scalar_nodes(tree, subject_id)[0]
    specs.append(make_spec("P18", "PROCEED", "NO_SAFE_REUSE", 10, request_payload(f"参考{evidence.name}新增跨组织实时态势可信度联合指数", parent=subject_id, value_type="float"), evidence_ids=(evidence.node_id,), action="ABSTAIN"))

    clarifications = (
        ("C01", "SUBJECT_AMBIGUITY", 12, "需要增加事件责任状态，但没有说明对应哪一个复盘治理主体。"),
        ("C02", "OWNERSHIP_AMBIGUITY", 11, "请记录培训维护结论，但未说明由内部班组还是服务商负责。"),
        ("C03", "SCOPE_AMBIGUITY", 2, "需要标记分区状态，尚未说明针对单一区域还是全部区域。"),
        ("C04", "AGGREGATION_AMBIGUITY", 4, "需要统计疏散人数，未说明按路线、楼层还是整栋汇总。"),
        ("C05", "CARDINALITY_AMBIGUITY", 5, "需要记录灭火介质类别，未说明只能一个还是可以多个。"),
        ("C06", "COMBINATION_AMBIGUITY", 10, "需要建立应急协同记录，但参与角色和适用事件均未确定。"),
    )
    for ref, risk, branch, text in clarifications:
        specs.append(make_spec(ref, "CLARIFY", risk, branch, request_payload(text, kind="UNKNOWN", value_type=None, cardinality="UNKNOWN"), action="NEED_CLARIFICATION"))

    specs.append(make_spec("R01", "CLARIFY", "CLARIFICATION_RESERVE", 3, request_payload("需要补充报警确认信息，但未说明报警回路和确认主体。", kind="UNKNOWN", value_type=None, cardinality="UNKNOWN"), action="NEED_CLARIFICATION"))
    specs.append(make_spec("R02", "CLARIFY", "CLARIFICATION_RESERVE", 11, request_payload("需要补充演练结果，但未说明演练类型和适用人员。", kind="UNKNOWN", value_type=None, cardinality="UNKNOWN"), action="NEED_CLARIFICATION"))

    top_k_payload = request_payload("事件整改状态验证")
    top_k_preview = retrieval_preview(top_k_payload, tree)
    top_k_target = next(candidate for candidate in top_k_preview.candidates if candidate.name == "整改任务组整改状态")
    if top_k_target.rank < 2:
        raise RuntimeError("reserve Top-K target is not beyond rank one")
    specs.append(make_spec("R03", "PROCEED", "TOP_K_RESERVE", 12, top_k_payload, target_ids=(top_k_target.node_id,)))

    cross_subject = "M49-B06-S10"
    cross_target = scalar_nodes(tree, cross_subject)[0]
    cross_contract = cross_target.value_contract
    specs.append(make_spec("R04", "PROCEED", "CROSS_BRANCH_RESERVE", 6, request_payload(cross_target.name, parent="M49-B02-S01", value_type=cross_contract.value_type, cardinality=cross_contract.cardinality), target_ids=(cross_target.node_id,), tags=("PARENT_INTERFERENCE",)))

    kind_subject = "M49-B07-S10"
    kind_evidence = scalar_nodes(tree, kind_subject)[0]
    specs.append(make_spec("R05", "PROCEED", "KIND_CONFLICT_RESERVE", 7, request_payload(kind_evidence.name, parent=kind_subject, kind="CONCEPT", value_type=None), evidence_ids=(kind_evidence.node_id,), action="ABSTAIN"))

    cardinality_subject = "M49-B09-S10"
    cardinality_evidence = scalar_nodes(tree, cardinality_subject)[0]
    cardinality_contract = cardinality_evidence.value_contract
    opposite = "MULTIPLE" if cardinality_contract.cardinality == "SINGLE" else "SINGLE"
    specs.append(make_spec("R06", "PROCEED", "CARDINALITY_RESERVE", 9, request_payload(cardinality_evidence.name, parent=cardinality_subject, value_type=cardinality_contract.value_type, cardinality=opposite), evidence_ids=(cardinality_evidence.node_id,), action="ABSTAIN"))
    return specs


def build_payloads() -> dict[str, dict[str, Any]]:
    tree_doc, blueprint = build_tree_and_blueprint()
    adapted = adapt_tree_document(tree_doc)
    if not adapted.is_valid or adapted.tree is None:
        raise RuntimeError("generated tree is invalid")
    tree = adapted.tree
    candidates = []
    oracle_items = []
    for spec in build_specs(tree):
        ref = spec["scenario_ref"]
        reserve = ref.startswith("R")
        clarify = spec["expected_route"] == "CLARIFY"
        request = IntentRequest.from_dict(spec["request"], tree)
        preview_payload = None
        if clarify:
            retrieval = RetrievalOracle(False, (), (), None)
            recommendation = RecommendationOracle(False, ())
        else:
            preview = retrieval_preview(spec["request"], tree)
            evidence_ids = tuple(sorted(spec["evidence_ids"]))
            ranks = {item.node_id: item.rank for item in preview.candidates if item.node_id in evidence_ids}
            if evidence_ids and set(ranks) != set(evidence_ids):
                missing = sorted(set(evidence_ids) - set(ranks))
                raise RuntimeError(f"{ref} Oracle evidence missing from Top-20: {missing}")
            top_k = max(ranks.values()) if ranks else 20
            retrieval = RetrievalOracle(True, ("CANDIDATES_READY",), evidence_ids, top_k)
            if spec["action"] == "USE_EXISTING_NODE":
                outcomes = tuple(
                    RecommendationOracleOutcome("USE_EXISTING_NODE", node_id, "SEMANTICALLY_EQUIVALENT")
                    for node_id in sorted(spec["target_ids"])
                )
            else:
                outcomes = (RecommendationOracleOutcome(spec["action"], None, None),)
            recommendation = RecommendationOracle(True, outcomes)
            preview_payload = {
                "status": preview.status,
                "candidate_set_hash": preview.candidate_set_hash,
                "candidate_node_ids": [item.node_id for item in preview.candidates],
                "oracle_target_ranks": dict(sorted(ranks.items())),
            }
        oracle = CapabilityOracle(
            spec["expected_route"],
            (intent_profile(request, clarify),),
            retrieval,
            recommendation,
        )
        public_item = {
            "scenario_ref": ref,
            "batch": "RESERVE" if reserve else "FORMAL",
            "coverage_cell": ref,
            "primary_risk": spec["primary_risk"],
            "secondary_tags": spec["secondary_tags"],
            "top_level_branch_ref": spec["top_level_branch_ref"],
            "request": spec["request"],
            "review_status": "PENDING_SILVER_REVIEW",
            "execution_eligible": False,
        }
        public_item["candidate_digest"] = canonical_digest(public_item)
        candidates.append(public_item)
        oracle_item = {
            "scenario_ref": ref,
            "source_candidate_digest": public_item["candidate_digest"],
            "oracle": oracle.to_dict(),
            "retrieval_mode": "NOT_APPLICABLE" if clarify else ("TARGET_HIT" if spec["target_ids"] else "BOUNDED_EVIDENCE"),
            "clarification_rubric": {"required_distinctions": ["target_subject", "applicable_scope"], "minimum_question_count": 1} if clarify else None,
            "deterministic_preview": preview_payload,
        }
        oracle_item["oracle_item_digest"] = canonical_digest(oracle_item)
        oracle_items.append(oracle_item)

    candidate_batch = {
        "schema_version": "fire-m49-sealed-candidates.v1",
        "dataset_ref": DATASET_REF,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "formal_scenario_count": 24,
        "reserve_scenario_count": 6,
        "items": candidates,
    }
    oracle_sidecar = {
        "schema_version": "fire-m49-sealed-oracle-sidecar.v1",
        "dataset_ref": DATASET_REF,
        "quality_tier": "UNREVIEWED_CANDIDATE",
        "assessment_authority": "NONE",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "source_tree_snapshot_hash": tree.snapshot_hash,
        "source_candidate_batch_digest": canonical_digest(candidate_batch),
        "items": oracle_items,
    }
    review_packet = {
        "schema_version": "fire-m49-sealed-review-packet.v1",
        "dataset_ref": DATASET_REF,
        "review_tier_requested": "CODEX_ASSISTED_SILVER",
        "authoritative_gold_review": False,
        "batch_digest": canonical_digest(candidate_batch),
        "oracle_sidecar_digest": canonical_digest(oracle_sidecar),
        "formal_refs": [f"P{i:02d}" for i in range(1, 19)] + [f"C{i:02d}" for i in range(1, 7)],
        "reserve_refs": [f"R{i:02d}" for i in range(1, 7)],
        "review_status": "PENDING_SILVER_REVIEW",
        "blocking_findings": [],
    }
    manifest = {
        "schema_version": "fire-m49-sealed-manifest.v1",
        "dataset_ref": DATASET_REF,
        "dataset_role": "SEMANTIC_CHALLENGE",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "tree_id": TREE_ID,
        "tree_version": TREE_VERSION,
        "tree_snapshot_hash": tree.snapshot_hash,
        "node_count": len(tree.nodes),
        "root_count": len(tree.root_node_ids),
        "top_level_branch_count": 12,
        "maximum_depth": max(len(node.path_labels) for node in tree.nodes),
        "value_envelope_count": adapted.observed_value_count,
        "formal_scenario_count": 24,
        "formal_proceed_count": 18,
        "formal_clarify_count": 6,
        "reserve_scenario_count": 6,
        "tree_digest": canonical_digest(tree_doc),
        "blueprint_digest": canonical_digest(blueprint),
        "candidate_batch_digest": canonical_digest(candidate_batch),
        "oracle_sidecar_digest": canonical_digest(oracle_sidecar),
        "generation_status": "CANDIDATE_ONLY",
        "review_status": "PENDING_SILVER_REVIEW",
    }
    checklist = {
        "schema_version": "fire-m49-sealed-promotion-checklist.v1",
        "dataset_ref": DATASET_REF,
        "l1_machine_validation": "PENDING",
        "l2_semantic_review": "PENDING",
        "silver_authorization": "PENDING",
        "explicit_promotion_approval": False,
        "fixture_promoted": False,
        "experiment_executed": False,
    }
    return {
        "manifest.json": manifest,
        "tree.json": tree_doc,
        "semantic-blueprint.json": blueprint,
        "scenario-candidates.json": candidate_batch,
        "oracle-sidecar.json": oracle_sidecar,
        "review-packet.json": review_packet,
        "promotion-checklist.json": checklist,
    }


def write_payloads(output_dir: Path) -> None:
    if output_dir.exists():
        raise RuntimeError("candidate output directory already exists")
    output_dir.mkdir(mode=0o700, parents=True)
    try:
        for filename, payload in build_payloads().items():
            if not write_private_json(output_dir / filename, payload):
                raise RuntimeError(f"failed to publish {filename}")
    except Exception:
        for path in output_dir.iterdir():
            path.unlink()
        output_dir.rmdir()
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    write_payloads(args.output_dir.resolve())
    with (args.output_dir / "manifest.json").open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    print(json.dumps({"status": "GENERATED", "dataset_ref": manifest["dataset_ref"], "node_count": manifest["node_count"], "formal_scenarios": manifest["formal_scenario_count"], "reserve_scenarios": manifest["reserve_scenario_count"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
