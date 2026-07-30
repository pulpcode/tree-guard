"""Deterministic clean-room fire-themed validation data.

The vocabulary, organizations, facilities, events, and hierarchy in this module
are invented for external-development tests. They are not derived from a real
fire-safety tree and do not claim engineering or regulatory correctness.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any


DATASET_SCHEMA_VERSION = "fictional-fire-validation-dataset.v1"
SCENARIO_SCHEMA_VERSION = "fictional-governance-scenarios.v1"
DATASET_ID = "fictional-starbay-fire-validation"
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
        "FORECAST",
        "ffv-branch-forecast",
        "虚构星湾焰安预见",
        (
            ("WATCH_PULSE", "虚构余温巡望节拍", "integer", False),
            ("HAZE_MARK", "虚构微烟映记状态", "string", False),
            ("EMBER_ZONE", "虚构隐烬区位标识", "string", False),
            ("QUIET_CHECK", "虚构静焰复核清单", "string", True),
        ),
    ),
    (
        "ALERT",
        "ffv-branch-alert",
        "虚构星湾鸣镜告警",
        (
            ("MIRROR_TONE", "虚构鸣镜提示音阶", "integer", False),
            ("GLOW_SIGNAL", "虚构辉纹告警状态", "string", False),
            ("ECHO_ORDER", "虚构回声联络序列", "string", True),
            ("NIGHT_BEACON", "虚构夜航信标方位", "string", False),
        ),
    ),
    (
        "GUIDANCE",
        "ffv-branch-guidance",
        "虚构星湾雾径引导",
        (
            ("MIST_ROUTE", "虚构雾径导向标记", "string", False),
            ("GATE_CLEAR", "虚构云门畅行状态", "string", False),
            ("LANTERN_PATH", "虚构星灯引导序列", "string", True),
            ("SHELTER_COUNT", "虚构静湾候行数量", "integer", False),
        ),
    ),
    (
        "EQUIPMENT",
        "ffv-branch-equipment",
        "虚构星湾泉幕器备",
        (
            ("SPRING_LEVEL", "虚构泉幕储量刻度", "float", False),
            ("FOAM_CASE", "虚构云沫器箱状态", "string", False),
            ("VEIL_PRESSURE", "虚构雾帘推力刻度", "float", False),
            ("TOOL_ROSTER", "虚构破障器备清单", "string", True),
        ),
    ),
    (
        "TRAINING",
        "ffv-branch-training",
        "虚构星湾练航值守",
        (
            ("DUTY_RHYTHM", "虚构值守轮换节拍", "integer", False),
            ("DRILL_STAGE", "虚构练航演练阶段", "string", False),
            ("GUIDE_ROLE", "虚构引航协同角色", "string", True),
            ("REVIEW_TIME", "虚构复盘记录时刻", "time_code", False),
        ),
    ),
    (
        "RESPONSE",
        "ffv-branch-response",
        "虚构星湾初焰协同",
        (
            ("FIRST_ACTION", "虚构初焰处置方式", "string", False),
            ("CALL_CHAIN", "虚构回声通联次序", "string", True),
            ("ZONE_GUARD", "虚构星界守望状态", "string", False),
            ("WATER_GUIDE", "虚构泉源引导方位", "string", False),
        ),
    ),
)

_AREAS = (
    "琥珀廊",
    "云穹厅",
    "青羽仓",
    "砂月站",
    "流光塔",
    "静潮庭",
    "银帆坊",
    "绯岚阁",
    "星井台",
    "雾桥舱",
    "霜铃院",
    "岚影亭",
    "澄光库",
    "月棱室",
    "风纹台",
    "蓝砂廊",
    "晨潮阁",
    "暮羽厅",
    "晶帆站",
    "虹湾庭",
)
_OBJECTS = (
    "巡望",
    "鸣镜",
    "雾径",
    "泉幕",
    "值守",
    "协同",
    "导向",
    "封界",
    "回声",
    "备援",
)
_FACETS = (
    "状态",
    "节拍",
    "等级",
    "数量",
    "记录",
    "方式",
    "时刻",
    "方位",
    "容量",
    "序列",
)
_VALUE_TYPES = (
    "string",
    "integer",
    "float",
    "boolean",
    "time_code",
)

_CORE_NODE_IDS = tuple(
    f"ffv-core-{index:03d}" for index in range(1, 25)
)


def build_fictional_fire_tree(tier: str) -> dict[str, Any]:
    """Build one deterministic source-format tree for the requested tier."""

    spec = _tier_spec(tier)
    root_label = "STAR_BAY_FIRE"
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
    generated_names = _generated_names()
    for index in range(extra_count):
        branch_index = index % len(_BRANCHES)
        label, branch_id, _, _ = _BRANCHES[branch_index]
        node_label = f"SYNTHETIC_{index + 1:04d}"
        node_name = f"虚构{generated_names[index]}"
        branch_subnodes = branch_wrappers[label]["subnodes"]
        branch_subnodes[node_label] = _property_wrapper(
            node_id=f"ffv-synthetic-{index + 1:04d}",
            parent_node_id=branch_id,
            name=node_name,
            label=node_label,
            route=f"{root_label}/-/{label}/-/{node_label}",
            order=len(branch_subnodes) + 1,
            value_type=_VALUE_TYPES[index % len(_VALUE_TYPES)],
            is_list=(index % 11 == 10),
        )

    return {
        "metadata": {
            "id": f"ffv-record-{tier}-v1",
            "map_id": f"ffv-map-{tier}",
            "map_type": "resource",
            "map_name": f"虚构星湾焰安{tier}验证树",
            "version": f"FFV-{tier.upper()}-V1",
            "concurrent_version": 1,
        },
        "map_topology": {
            root_label: _concept_wrapper(
                node_id=root_id,
                parent_node_id=None,
                name="虚构星湾焰安体系",
                label=root_label,
                route=root_label,
                order=1,
                subnodes=branch_wrappers,
            )
        },
    }


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
        "title": "虚构星湾消防功能形状验证数据",
        "fictional": True,
        "source_policy": "PUBLIC_CATEGORY_CLEAN_ROOM",
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "limitations": [
            "不代表真实消防信息树、工程规范或生产分布。",
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


def _generated_names() -> tuple[str, ...]:
    return tuple(
        f"{area}{object_name}{facet}"
        for area, object_name, facet in product(_AREAS, _OBJECTS, _FACETS)
    )


def _base_scenarios() -> tuple[dict[str, Any], ...]:
    return (
        _direct_scenario(
            "clear-intent",
            "CLEAR_INTENT",
            "虚构余温巡望节拍",
            parent_id="ffv-branch-forecast",
            required_first="ffv-core-001",
            semantic=_semantic_fixture("CONFIRM_RECOMMENDATION"),
            recommendation_status="CONFIRMED",
        ),
        _direct_scenario(
            "global-over-local",
            "GLOBAL_BEATS_LOCAL",
            "虚构余温巡望节拍",
            parent_id="ffv-branch-equipment",
            required_first="ffv-core-001",
            semantic=_semantic_fixture("REJECT_RECOMMENDATION"),
            recommendation_status="REJECTED",
        ),
        _direct_scenario(
            "type-conflict",
            "TYPE_CONFLICT",
            "虚构泉幕储量刻度",
            parent_id="ffv-branch-equipment",
            required_first="ffv-core-013",
            value_type="string",
        ),
        _direct_scenario(
            "no-candidates",
            "NO_CANDIDATES",
            "quasarflux",
            parent_id=None,
            required_first=None,
            expected_candidate_status="NO_CANDIDATES",
            node_kind="UNKNOWN",
            value_type=None,
            cardinality="UNKNOWN",
            include_context=False,
            include_fact=False,
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
) -> dict[str, Any]:
    return {
        "scenario_ref": scenario_ref,
        "purpose": purpose,
        "flow": "DIRECT",
        "request": _request(
            scenario_ref,
            parent_id,
            node_kind,
            value_type,
            cardinality,
        ),
        "initial_model_output": _model_output(
            subject,
            node_kind=node_kind,
            value_type=value_type,
            cardinality=cardinality,
            include_context=include_context,
            include_fact=include_fact,
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
    subject = "虚构雾径导向标记"
    clarified = _model_output(subject)
    clarified["clarification_question"] = (
        None if resolve else "仍需确认虚构引导标记的表现形式吗？"
    )
    if not resolve:
        clarified["evidence_gaps"] = ["仍缺少一个完全虚构的表现形式。"]
    return {
        "scenario_ref": scenario_ref,
        "purpose": (
            "CLARIFICATION_RESOLVES"
            if resolve
            else "CLARIFICATION_LIMIT"
        ),
        "flow": "CLARIFY",
        "request": _request(
            scenario_ref,
            "ffv-branch-guidance",
            "PROPERTY",
            "string",
            "SINGLE",
        ),
        "initial_model_output": _model_output(
            subject,
            clarification_question="虚构引导标记采用哪一种表现形式？",
            evidence_gaps=["尚未说明完全虚构的表现形式。"],
        ),
        "clarification": {
            "answer_text": "本次虚构验证使用星纹表现形式。",
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
            required_first_candidate_id="ffv-core-009" if resolve else None,
        ),
    }


def _reject_scenario() -> dict[str, Any]:
    scenario = _direct_scenario(
        "human-rejects",
        "HUMAN_REJECT",
        "虚构初焰处置方式",
        parent_id="ffv-branch-response",
        required_first=None,
    )
    scenario["review_decision"] = "REJECT_DRAFT"
    scenario["semantic"] = None
    scenario["oracle"] = _oracle(
        draft_status="READY_FOR_HUMAN_REVIEW",
        confirmation_status="REJECTED",
    )
    return scenario


def _generated_scenario(index: int) -> dict[str, Any]:
    generated_name = _generated_names()[index]
    subject = f"虚构{generated_name}"
    branch_id = _BRANCHES[index % len(_BRANCHES)][1]
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
        value_type=_VALUE_TYPES[index % len(_VALUE_TYPES)],
        cardinality="MULTIPLE" if index % 11 == 10 else "SINGLE",
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
    scenario_ref: str,
    parent_id: str | None,
    node_kind: str,
    value_type: str | None,
    cardinality: str,
) -> dict[str, Any]:
    return {
        "schema_version": "intent-request.v1",
        "requirement_text": (
            f"为完全虚构的星湾演练记录 {scenario_ref} 信息。"
        ),
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
) -> dict[str, Any]:
    has_subject = subject is not None
    has_context = has_subject and include_context
    return {
        "schema_version": "change-intent-model-output.v1",
        "subject": subject,
        "role": "虚构星湾演练信息" if has_context else None,
        "scenario": "完全虚构的星湾演练" if has_context else None,
        "lifecycle": "单次虚构演练周期" if has_context else None,
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
                    "reason": "已比较完全虚构的星湾候选。",
                }
                for index in range(1, 9)
            ],
            "recommended_action": "USE_EXISTING_NODE",
            "selected_candidate_ref": selected_candidate_ref,
            "rationale": "首个虚构候选与确认意图等价。",
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
