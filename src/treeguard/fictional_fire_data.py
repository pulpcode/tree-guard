"""Deterministic clean-room fire-themed validation data.

The vocabulary, organizations, facilities, events, and hierarchy in this module
are invented for external-development tests. They are not derived from a real
fire-safety tree and do not claim engineering or regulatory correctness.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATASET_SCHEMA_VERSION = "fictional-fire-validation-dataset.v1"
SCENARIO_SCHEMA_VERSION = "fictional-governance-scenarios.v1"
DATASET_ID = "fictional-fire-governance-validation"
FIRE_VALIDATION_CATEGORY_ID = "fictional-fire-validation-category"
FIRE_VALIDATION_TIERS = ("small", "medium", "large")
FIRE_VALIDATION_RESOURCE_IDS = {
    tier: f"fictional-fire-{index:02d}-{tier}"
    for index, tier in enumerate(FIRE_VALIDATION_TIERS, start=1)
}
TIER_SPECS = {
    "small": {
        "benchmark_role": "precision_contract",
        "node_count": 31,
        "scenario_count": 8,
    },
    "medium": {
        "benchmark_role": "semantic_interference",
        "node_count": 401,
        "scenario_count": 16,
    },
    "large": {
        "benchmark_role": "scale_stability",
        "node_count": 2_001,
        "scenario_count": 24,
    },
}

_BRANCHES = (
    (
        "TASK",
        "ffv-branch-task",
        "任务基本信息",
        (
            ("TASK_NAME", "任务名称", "string", False),
            ("TASK_TYPE", "任务类型", "string", False),
            ("TASK_LOCATION", "任务地点", "string", False),
            ("ALARM_TIME", "报警时间", "time_code", False),
        ),
    ),
    (
        "SITUATION",
        "ffv-branch-situation",
        "现场态势",
        (
            ("PLACE_TYPE", "事发场所类型", "string", False),
            ("FIRE_LOCATION", "起火部位", "string", False),
            ("BURNING_MATERIAL", "主要燃烧物", "string", True),
            ("FIRE_TREND", "火势发展状态", "string", False),
        ),
    ),
    (
        "PEOPLE",
        "ffv-branch-people",
        "人员与组织",
        (
            ("COMMANDER_NAME", "现场负责人姓名", "string", False),
            ("COMMANDER_ORG", "现场负责人所属单位", "string", False),
            ("PARTICIPATING_ORGS", "参与单位", "string", True),
            ("RESPONDER_COUNT", "参与人员数量", "integer", False),
        ),
    ),
    (
        "RESOURCES",
        "ffv-branch-resources",
        "救援力量与装备",
        (
            ("VEHICLE_COUNT", "救援车辆数量", "integer", False),
            ("EQUIPMENT_LIST", "救援装备清单", "string", True),
            ("WATER_SUPPLY", "现场供水条件", "string", False),
            ("SPECIAL_EQUIPMENT", "特种装备清单", "string", True),
        ),
    ),
    (
        "ACTIONS",
        "ffv-branch-actions",
        "处置过程",
        (
            ("ARRIVAL_TIME", "到场时间", "time_code", False),
            ("RESPONSE_STAGE", "当前处置阶段", "string", False),
            ("RESPONSE_MEASURES", "主要处置措施", "string", True),
            ("COMPLETION_STATUS", "任务完成状态", "string", False),
        ),
    ),
    (
        "SPECIAL",
        "ffv-branch-special",
        "特殊任务扩展",
        (
            ("SPECIAL_TASK_TYPE", "特殊任务类型", "string", False),
            (
                "SPECIAL_PERSONNEL_QUALIFICATION",
                "特殊任务人员资质要求",
                "string",
                True,
            ),
            (
                "SPECIAL_PROTECTION_REQUIREMENT",
                "特殊任务防护要求",
                "string",
                True,
            ),
            (
                "SPECIAL_RESPONSE_NOTE",
                "特殊任务处置说明",
                "string",
                False,
            ),
        ),
    ),
)

_GENERATED_SUBJECTS = {
    "TASK": (
        "报警信息",
        "任务调度",
        "任务地点",
        "任务时段",
        "任务级别",
        "任务来源",
        "任务单位",
        "任务批次",
        "任务计划",
        "任务进度",
        "任务联系人",
        "任务范围",
        "任务目标",
        "任务约束",
        "任务阶段",
        "任务交接",
        "任务变更",
        "任务附件",
        "任务审核",
        "任务复盘",
    ),
    "SITUATION": (
        "事发区域",
        "起火区域",
        "燃烧物",
        "烟气情况",
        "火势变化",
        "温度变化",
        "建筑环境",
        "周边环境",
        "人员被困",
        "疏散人员态势",
        "危险物质",
        "现场能见度",
        "现场风向",
        "蔓延方向",
        "坍塌风险",
        "爆炸风险",
        "次生风险",
        "警戒区域",
        "作业区域",
        "安全通行区域",
    ),
    "PEOPLE": (
        "现场负责人",
        "任务指挥人员",
        "一线救援人员",
        "安全观察人员",
        "通信联络人员",
        "医疗协作人员",
        "后勤保障人员",
        "车辆驾驶人员",
        "装备操作人员",
        "特种任务人员",
        "增援人员",
        "轮换人员",
        "待命人员",
        "撤离人员",
        "被困人员",
        "疏散人员",
        "受伤人员",
        "参与单位",
        "协作单位",
        "人员分组",
    ),
    "RESOURCES": (
        "增援车辆",
        "供水单元",
        "通信设备",
        "照明设备",
        "破拆装备",
        "检测装备",
        "防护装备",
        "医疗物资",
        "后勤物资",
        "指挥器材",
        "警戒器材",
        "排烟设备",
        "运输工具",
        "备用电源",
        "现场水源",
        "补给点",
        "装备保障组",
        "车辆保障组",
        "物资调派",
        "资源回收",
    ),
    "ACTIONS": (
        "接警确认",
        "任务调派",
        "出发准备",
        "途中联络",
        "现场侦察",
        "风险评估",
        "警戒设置",
        "人员搜寻",
        "人员疏散行动",
        "火势控制",
        "现场排烟",
        "供水组织",
        "装备部署",
        "协同联络",
        "医疗协作",
        "增援请求",
        "阶段转换",
        "现场移交",
        "任务结束",
        "复盘改进",
    ),
    "SPECIAL": (
        "高层任务",
        "地下空间任务",
        "有限空间任务",
        "危险物质任务",
        "大型综合体任务",
        "交通设施任务",
        "山地任务",
        "水域任务",
        "夜间任务",
        "极端天气任务",
        "人员密集场所任务",
        "重要设施任务",
        "跨区域协作任务",
        "多单位联合任务",
        "长时间持续任务",
        "远程区域任务",
        "通信受限任务",
        "供水受限任务",
        "特殊人员救援任务",
        "特殊装备作业任务",
    ),
}
_GENERATED_FACETS = (
    ("名称", "string", False),
    ("类型", "string", False),
    ("数量", "integer", False),
    ("状态", "string", False),
    ("发生时间", "time_code", False),
    ("所在位置", "string", False),
    ("负责人", "string", False),
    ("信息来源", "string", True),
    ("情况说明", "string", False),
    ("备注", "string", False),
    ("是否已确认", "boolean", False),
    ("更新时间", "time_code", False),
    ("关联阶段", "string", False),
    ("责任单位", "string", False),
    ("记录方式", "string", False),
    ("变更原因", "string", False),
    ("检查结果", "string", False),
    ("处置要求", "string", True),
    ("风险等级", "integer", False),
    ("优先级", "integer", False),
)

_CORE_NODE_IDS = tuple(
    f"ffv-core-{index:03d}" for index in range(1, 25)
)


def build_fictional_fire_tree(tier: str) -> dict[str, Any]:
    """Build one deterministic source-format tree for the requested tier."""

    spec = _tier_spec(tier)
    root_label = "FICTIONAL_FIRE_TASK"
    root_id = "ffv-root"
    branch_wrappers: dict[str, Any] = {}
    core_index = 0

    for branch_order, (label, branch_id, name, leaves) in enumerate(
        _BRANCHES,
        start=1,
    ):
        leaf_wrappers: dict[str, Any] = {}
        for leaf_order, (leaf_label, leaf_name, value_type, is_list) in enumerate(
            leaves,
            start=1,
        ):
            node_id = _CORE_NODE_IDS[core_index]
            core_index += 1
            leaf_wrappers[leaf_label] = _property_wrapper(
                node_id=node_id,
                parent_node_id=branch_id,
                name=leaf_name,
                label=leaf_label,
                route=f"{root_label}/-/{label}/-/{leaf_label}",
                order=leaf_order,
                value_type=value_type,
                is_list=is_list,
            )
        branch_wrappers[label] = _concept_wrapper(
            node_id=branch_id,
            parent_node_id=root_id,
            name=name,
            label=label,
            route=f"{root_label}/-/{label}",
            order=branch_order,
            subnodes=leaf_wrappers,
        )

    extra_count = spec["node_count"] - 31
    for index in range(extra_count):
        branch_index = index % len(_BRANCHES)
        label, branch_id, _, _ = _BRANCHES[branch_index]
        name, value_type, is_list, _ = _generated_property(
            label,
            index // len(_BRANCHES),
        )
        node_label = f"SYNTHETIC_{index + 1:04d}"
        branch_subnodes = branch_wrappers[label]["subnodes"]
        branch_subnodes[node_label] = _property_wrapper(
            node_id=f"ffv-synthetic-{index + 1:04d}",
            parent_node_id=branch_id,
            name=name,
            label=node_label,
            route=f"{root_label}/-/{label}/-/{node_label}",
            order=len(branch_subnodes) + 1,
            value_type=value_type,
            is_list=is_list,
        )

    return {
        "metadata": {
            "id": f"ffv-record-{tier}-v2",
            "map_id": f"ffv-map-{tier}",
            "map_type": "resource",
            "map_name": f"虚构消防任务治理{tier}验证树",
            "version": f"FFV-{tier.upper()}-V2",
            "concurrent_version": 2,
        },
        "map_topology": {
            root_label: _concept_wrapper(
                node_id=root_id,
                parent_node_id=None,
                name="虚构消防任务信息树样例",
                label=root_label,
                route=root_label,
                order=1,
                subnodes=branch_wrappers,
            )
        },
    }


def fire_validation_version(tier: str) -> str:
    """Return the sole business version for one fictional validation tier."""

    _tier_spec(tier)
    return f"FFV-{tier.upper()}-V2"


def fire_validation_record_id(tier: str) -> str:
    """Return the sole version-record identifier for one fictional tier."""

    _tier_spec(tier)
    return f"ffv-record-{tier}-v2"


def fire_validation_tree_id(tier: str) -> str:
    """Return the canonical tree identifier for one fictional tier."""

    _tier_spec(tier)
    return f"ffv-map-{tier}"


def build_fictional_fire_scenarios(tier: str) -> dict[str, Any]:
    """Build deterministic governance scenarios and explicit contract oracles."""

    spec = _tier_spec(tier)
    scenarios = list(_base_scenarios())
    for index in range(spec["scenario_count"] - len(scenarios)):
        scenarios.append(_generated_scenario(index))
    return {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "tier": tier,
        "benchmark_role": spec["benchmark_role"],
        "fictional": True,
        "gold_eligible": False,
        "scenario_count": len(scenarios),
        "items": scenarios,
    }


def build_fictional_fire_manifest() -> dict[str, Any]:
    """Return the dataset manifest and failure-oracle matrix."""

    tiers = []
    for tier, spec in TIER_SPECS.items():
        tiers.append(
            {
                "tier": tier,
                **spec,
                "tree_file": f"tree-{tier}.json",
                "scenarios_file": f"scenarios-{tier}.json",
            }
        )
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "title": "虚构消防任务治理验证数据",
        "fictional": True,
        "source_policy": "PUBLIC_CATEGORY_CLEAN_ROOM",
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "limitations": [
            "不代表真实消防信息树、工程规范或生产分布。",
            "仅使用外网独立构造的常识级概念，不声明行业标准完整性。",
            "大型档只用于规模、确定性和有界输出验证。",
            "oracle 是合同预期或可接受集合，不是生产 Gold。",
        ],
        "tiers": tiers,
        "model_fault_oracles": [
            _fault("invalid-json", "INTENT_MODEL_RESPONSE_INVALID", 2),
            _fault("extra-field", "INTENT_MODEL_FIELDS_INVALID", 2),
            _fault("missing-field", "INTENT_MODEL_FIELDS_INVALID", 2),
            _fault("http-429", "SIMULATOR_MODEL_HTTP_429", 1),
            _fault("http-500", "SIMULATOR_MODEL_HTTP_500", 1),
            _fault("timeout", "SIMULATOR_MODEL_CONNECTION_FAILED", 1),
            _fault(
                "response-too-large",
                "SIMULATOR_MODEL_RESPONSE_TOO_LARGE",
                1,
            ),
            _fault("retry-then-valid", None, 2, final_status="SUCCEEDED"),
            _fault(
                "trace-canary",
                None,
                1,
                final_status="REDACTED",
            ),
        ],
    }


def write_fictional_fire_dataset(directory: str | Path) -> tuple[Path, ...]:
    """Write all generated JSON files to a new or existing fixture directory."""

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[tuple[str, dict[str, Any]]] = [
        ("manifest.json", build_fictional_fire_manifest())
    ]
    for tier in TIER_SPECS:
        artifacts.extend(
            (
                (f"tree-{tier}.json", build_fictional_fire_tree(tier)),
                (
                    f"scenarios-{tier}.json",
                    build_fictional_fire_scenarios(tier),
                ),
            )
        )
    paths = []
    for filename, payload in artifacts:
        path = target / filename
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return tuple(paths)


def _tier_spec(tier: str) -> dict[str, Any]:
    try:
        return TIER_SPECS[tier]
    except (KeyError, TypeError):
        raise ValueError("unsupported fictional fire validation tier") from None


def _branch_name(branch_id: str | None) -> str | None:
    return next(
        (
            name
            for _, candidate_id, name, _ in _BRANCHES
            if candidate_id == branch_id
        ),
        None,
    )


def _concept_wrapper(
    *,
    node_id: str,
    parent_node_id: str | None,
    name: str,
    label: str,
    route: str,
    order: int,
    subnodes: dict[str, Any],
) -> dict[str, Any]:
    metadata = {
        "node_id": node_id,
        "node_type": "concept",
        "node_name": name,
        "node_label": label,
        "node_label_route": route,
        "node_order": order,
    }
    if parent_node_id is not None:
        metadata["parent_node_id"] = parent_node_id
    return {"metadata": metadata, "subnodes": subnodes}


def _property_wrapper(
    *,
    node_id: str,
    parent_node_id: str,
    name: str,
    label: str,
    route: str,
    order: int,
    value_type: str,
    is_list: bool,
) -> dict[str, Any]:
    return {
        "metadata": {
            "node_id": node_id,
            "parent_node_id": parent_node_id,
            "node_type": "property",
            "node_name": name,
            "node_label": label,
            "node_label_route": route,
            "node_order": order,
            "value_type": value_type,
            "is_list": is_list,
            "value_constraints": {"raw_constraints": {}},
        }
    }


def _generated_property(
    branch_label: str,
    index: int,
) -> tuple[str, str, bool, str]:
    subjects = _GENERATED_SUBJECTS[branch_label]
    subject_index, facet_index = divmod(
        index,
        len(_GENERATED_FACETS),
    )
    subject = subjects[subject_index]
    facet, value_type, is_list = _GENERATED_FACETS[facet_index]
    return f"{subject}{facet}", value_type, is_list, subject


def _base_scenarios() -> tuple[dict[str, Any], ...]:
    return (
        _direct_scenario(
            "clear-intent",
            "CLEAR_INTENT",
            "现场负责人所属单位",
            parent_id="ffv-branch-people",
            required_first="ffv-core-010",
            semantic=_semantic_fixture("CONFIRM_RECOMMENDATION"),
            recommendation_status="CONFIRMED",
        ),
        _direct_scenario(
            "global-over-local",
            "GLOBAL_BEATS_LOCAL",
            "现场负责人所属单位",
            parent_id="ffv-branch-special",
            required_first="ffv-core-010",
            requirement_text=(
                "该字段属于人员长期共享信息，不应因本次特殊任务重复新增，"
                "需要记录现场负责人所属单位。"
            ),
            context_role="人员与组织",
            semantic=_semantic_fixture("REJECT_RECOMMENDATION"),
            recommendation_status="REJECTED",
        ),
        _direct_scenario(
            "type-conflict",
            "TYPE_CONFLICT",
            "参与人员数量",
            parent_id="ffv-branch-people",
            required_first="ffv-core-012",
            value_type="string",
            requirement_text=(
                "用户暂时把数量描述成文本，但业务对象明确，"
                "需要记录参与人员数量。"
            ),
        ),
        _direct_scenario(
            "no-candidates",
            "NO_CANDIDATES",
            "OUT_OF_SCOPE_DRONE_BATTERY_CODE",
            parent_id=None,
            required_first=None,
            expected_candidate_status="NO_CANDIDATES",
            node_kind="UNKNOWN",
            value_type=None,
            cardinality="UNKNOWN",
            include_context=False,
            include_fact=False,
            requirement_text=(
                "为验证无候选分支，提出树中不存在的技术占位字段，"
                "需要记录 OUT_OF_SCOPE_DRONE_BATTERY_CODE。"
            ),
        ),
        _direct_scenario(
            "insufficient-signal",
            "INSUFFICIENT_SIGNAL",
            None,
            parent_id=None,
            required_first=None,
            expected_candidate_status="INSUFFICIENT_SIGNAL",
            node_kind="UNKNOWN",
            value_type=None,
            cardinality="UNKNOWN",
        ),
        _clarification_scenario(resolve=True),
        _clarification_scenario(resolve=False),
        _reject_scenario(),
    )


def _direct_scenario(
    scenario_ref: str,
    purpose: str,
    subject: str | None,
    *,
    parent_id: str | None,
    required_first: str | None,
    expected_candidate_status: str = "CANDIDATES_READY",
    node_kind: str = "PROPERTY",
    value_type: str | None = "string",
    cardinality: str = "SINGLE",
    include_context: bool = True,
    include_fact: bool = True,
    semantic: dict[str, Any] | None = None,
    recommendation_status: str | None = None,
    semantic_error_code: str | None = None,
    requirement_text: str | None = None,
    context_role: str | None = None,
) -> dict[str, Any]:
    return {
        "scenario_ref": scenario_ref,
        "purpose": purpose,
        "flow": "DIRECT",
        "request": _request(
            parent_id,
            node_kind,
            value_type,
            cardinality,
            subject,
            requirement_text=requirement_text,
        ),
        "initial_model_output": _model_output(
            subject,
            node_kind=node_kind,
            value_type=value_type,
            cardinality=cardinality,
            include_context=include_context,
            include_fact=include_fact,
            role=(
                context_role
                if context_role is not None
                else _branch_name(parent_id)
            ),
        ),
        "clarification": None,
        "review_decision": "CONFIRM_FOR_RETRIEVAL",
        "semantic": semantic,
        "oracle": _oracle(
            draft_status="READY_FOR_HUMAN_REVIEW",
            confirmation_status="CONFIRMED_FOR_RETRIEVAL",
            candidate_status=expected_candidate_status,
            required_first_candidate_id=required_first,
            recommendation_status=recommendation_status,
            semantic_error_code=semantic_error_code,
        ),
    }


def _clarification_scenario(*, resolve: bool) -> dict[str, Any]:
    scenario_ref = "clarify-resolves" if resolve else "clarify-stops"
    subject = "特殊任务人员资质要求"
    clarified = _model_output(
        subject,
        cardinality="MULTIPLE",
        role="特殊任务扩展",
    )
    clarified["clarification_question"] = (
        None if resolve else "该资质应属于人员主干还是特殊任务扩展？"
    )
    if not resolve:
        clarified["evidence_gaps"] = ["仍缺少适用范围和跨任务复用规则。"]
    return {
        "scenario_ref": scenario_ref,
        "purpose": (
            "CLARIFICATION_RESOLVES"
            if resolve
            else "CLARIFICATION_LIMIT"
        ),
        "flow": "CLARIFY",
        "request": _request(
            "ffv-branch-special",
            "PROPERTY",
            "string",
            "MULTIPLE",
            subject,
            requirement_text=(
                "特殊任务中的人员需要增加资质信息，但尚不确定它应属于"
                "通用人员信息还是本次任务扩展。"
            ),
        ),
        "initial_model_output": _model_output(
            subject,
            cardinality="MULTIPLE",
            clarification_question=(
                "该资质是人员长期属性，还是只在本次特殊任务中使用？"
            ),
            evidence_gaps=["尚未说明适用范围和跨任务复用规则。"],
            role="特殊任务扩展",
        ),
        "clarification": {
            "answer_text": (
                "只在本次完全虚构的高空救援演练中使用，"
                "应作为特殊任务扩展字段。"
                if resolve
                else "专家暂时无法判断，需要补充适用范围和跨任务复用规则。"
            ),
            "model_output": clarified,
        },
        "review_decision": (
            "CONFIRM_FOR_RETRIEVAL" if resolve else None
        ),
        "semantic": None,
        "oracle": _oracle(
            draft_status="NEEDS_CLARIFICATION",
            clarification_status=(
                "READY_FOR_HUMAN_REVIEW"
                if resolve
                else "CLARIFICATION_LIMIT_REACHED"
            ),
            confirmation_status=(
                "CONFIRMED_FOR_RETRIEVAL" if resolve else None
            ),
            candidate_status="CANDIDATES_READY" if resolve else None,
            required_first_candidate_id="ffv-core-022" if resolve else None,
        ),
    }


def _reject_scenario() -> dict[str, Any]:
    scenario = _direct_scenario(
        "human-rejects",
        "HUMAN_REJECT",
        "主要处置措施",
        parent_id="ffv-branch-actions",
        required_first=None,
        requirement_text=(
            "需求只提到要补充处置内容，但没有说明范围和复用边界，"
            "需要记录主要处置措施。"
        ),
    )
    scenario["review_decision"] = "REJECT_DRAFT"
    scenario["semantic"] = None
    scenario["oracle"] = _oracle(
        draft_status="READY_FOR_HUMAN_REVIEW",
        confirmation_status="REJECTED",
    )
    return scenario


def _generated_scenario(index: int) -> dict[str, Any]:
    branch_label, branch_id, _, _ = _BRANCHES[index % len(_BRANCHES)]
    subject, value_type, is_list, context_role = _generated_property(
        branch_label,
        index // len(_BRANCHES),
    )
    scenario = _direct_scenario(
        f"generated-{index + 1:02d}",
        (
            "SEMANTIC_HARD_NEGATIVE"
            if index < 8
            else "SCALE_TARGET"
        ),
        subject,
        parent_id=branch_id,
        required_first=f"ffv-synthetic-{index + 1:04d}",
        value_type=value_type,
        cardinality="MULTIPLE" if is_list else "SINGLE",
        context_role=context_role,
        semantic=(
            _semantic_fixture(
                None,
                selected_candidate_ref="C009",
            )
            if index == 0
            else None
        ),
        semantic_error_code=(
            "SEMANTIC_SELECTED_CANDIDATE_INVALID"
            if index == 0
            else None
        ),
    )
    if index == 0:
        scenario["purpose"] = "TOP8_OUT_OF_SCOPE"
    scenario["oracle"]["candidate_limit"] = 20
    scenario["oracle"]["semantic_projection_limit"] = 8
    return scenario


def _request(
    parent_id: str | None,
    node_kind: str,
    value_type: str | None,
    cardinality: str,
    subject: str | None,
    *,
    requirement_text: str | None = None,
) -> dict[str, Any]:
    if requirement_text is None:
        requirement_text = (
            f"在完全虚构的消防任务治理演练中，需要记录{subject}。"
            if subject is not None
            else (
                "希望补充一项信息，但尚未说明具体对象、所属子树"
                "或字段类型。"
            )
        )
    return {
        "schema_version": "intent-request.v1",
        "requirement_text": requirement_text,
        "proposed_parent_node_id": parent_id,
        "node_kind_hint": node_kind,
        "value_type_hint": value_type,
        "cardinality_hint": cardinality,
    }


def _model_output(
    subject: str | None,
    *,
    node_kind: str = "PROPERTY",
    value_type: str | None = "string",
    cardinality: str = "SINGLE",
    clarification_question: str | None = None,
    evidence_gaps: list[str] | None = None,
    include_context: bool = True,
    include_fact: bool = True,
    role: str | None = None,
) -> dict[str, Any]:
    has_subject = subject is not None
    has_context = has_subject and include_context
    return {
        "schema_version": "change-intent-model-output.v1",
        "subject": subject,
        "role": role if has_context else None,
        "scenario": "完全虚构的字段归属审查" if has_context else None,
        "lifecycle": "单次审查周期" if has_context else None,
        "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
        "node_kind": node_kind,
        "value_type": value_type,
        "cardinality": cardinality,
        "confirmed_facts": (
            [f"需要记录{subject}。"]
            if has_subject and include_fact
            else []
        ),
        "assumptions": [],
        "evidence_gaps": evidence_gaps or [],
        "clarification_question": clarification_question,
    }


def _oracle(
    *,
    draft_status: str,
    clarification_status: str | None = None,
    confirmation_status: str | None = None,
    candidate_status: str | None = None,
    required_first_candidate_id: str | None = None,
    recommendation_status: str | None = None,
    semantic_error_code: str | None = None,
) -> dict[str, Any]:
    return {
        "draft_status": draft_status,
        "clarification_status": clarification_status,
        "confirmation_status": confirmation_status,
        "candidate_status": candidate_status,
        "required_first_candidate_id": required_first_candidate_id,
        "candidate_limit": 20,
        "semantic_projection_limit": 8,
        "recommendation_status": recommendation_status,
        "semantic_error_code": semantic_error_code,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }


def _semantic_fixture(
    review_decision: str | None,
    *,
    selected_candidate_ref: str = "C001",
) -> dict[str, Any]:
    return {
        "model_output": {
            "schema_version": "semantic-recommendation-model-output.v1",
            "candidate_assessments": [
                {
                    "candidate_ref": f"C{index:03d}",
                    "relation": (
                        "SEMANTICALLY_EQUIVALENT"
                        if index == 1
                        else "NOT_EQUIVALENT"
                    ),
                    "reason": "已比较虚构需求与候选字段的业务对象和归属。",
                }
                for index in range(1, 9)
            ],
            "recommended_action": "USE_EXISTING_NODE",
            "selected_candidate_ref": selected_candidate_ref,
            "rationale": "首个候选与虚构需求中的字段名称和业务上下文一致。",
            "uncertainties": [],
            "evidence_gaps": [],
            "clarification_question": None,
        },
        "review_decision": review_decision,
    }


def _fault(
    fault: str,
    expected_error_code: str | None,
    expected_attempts: int,
    *,
    final_status: str = "FAILED",
) -> dict[str, Any]:
    return {
        "fault": fault,
        "stage": "INTENT_MODEL",
        "expected_error_code": expected_error_code,
        "expected_attempts": expected_attempts,
        "final_status": final_status,
        "public_view_must_exclude": [
            "authorization",
            "api_key",
            "internal_path",
            "stable_node_id",
            "full_tree",
            "raw_trace_canary",
        ],
    }


__all__ = [
    "DATASET_ID",
    "DATASET_SCHEMA_VERSION",
    "SCENARIO_SCHEMA_VERSION",
    "TIER_SPECS",
    "build_fictional_fire_manifest",
    "build_fictional_fire_scenarios",
    "build_fictional_fire_tree",
    "write_fictional_fire_dataset",
]
