"""Deterministic clean-room Qinglan production-shape dataset."""

from __future__ import annotations

import json
import random
import re
from hashlib import sha256
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from treeguard.adapter import adapt_tree_document
from treeguard.fictional_qinglan_library_semantic_data import (
    build_qinglan_library_semantic_scenarios,
    build_qinglan_library_semantic_tree,
)


DATASET_REF = "fictional-qinglan-library-production-shape-v1"
RUN_REF = "qinglan-library-production-shape-v1-run-003"
SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
PRIMARY_ROLE = "PRODUCTION_SHAPE"
SEED = 2026073101
TARGET_NODE_COUNT = 2001
TARGET_SCENARIO_COUNT = 8
TARGET_FAMILY_COUNTS = {
    "curated_core": 40,
    "approved_blueprint_background": 1561,
    "stress_only_filler": 400,
}
TARGET_DEPTH_COUNTS = {
    0: 1,
    1: 6,
    2: 44,
    3: 270,
    4: 760,
    5: 700,
    6: 220,
}
TARGET_ANCHOR_COUNT = 24
TARGET_REPLAY_SCENARIO_COUNT = 4
TREE_ID = "qinglan-library-production-shape-tree"
TREE_VERSION = "QP-1.0"
VERSION_RECORD_ID = "qinglan-library-production-shape-record-v1"

_ALLOWED_VALUE_TYPES = {
    "boolean",
    "class",
    "integer",
    "string",
    "time_code",
}
_ALLOWED_OBSERVABLE_CATEGORIES = {
    "CONFLICT_VISIBLE",
    "NEED_CLARIFICATION",
    "NEED_EVIDENCE",
    "STABLE_CANDIDATE",
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
class _FacetTemplate:
    name: str
    value_type: str
    multiple: bool = False


@dataclass(frozen=True, slots=True)
class _NodeSpec:
    node_id: str
    label: str
    name: str
    parent_node_id: str | None
    kind: str
    family: str
    value_type: str | None = None
    multiple: bool | None = None
    semantic_role: str | None = None
    semantic_target_eligible: bool = False
    lineage_role: str = "new"
    represents: str | None = None
    parent_relation: str | None = None
    entity_scope: str | None = None
    record_profile: str | None = None


@dataclass(frozen=True, slots=True)
class _GroupSpec:
    node_id: str
    label: str
    name: str
    parent_node_id: str
    branch_ref: str
    family: str


def _f(
    name: str,
    value_type: str = "string",
    multiple: bool = False,
) -> _FacetTemplate:
    return _FacetTemplate(name, value_type, multiple)


ANCHOR_NODE_IDS = (
    "ql-001",
    "ql-002",
    "ql-003",
    "ql-004",
    "ql-005",
    "ql-009",
    "qs-ops",
    "ql-007",
    "ql-015",
    "qs-g010",
    "qs-s013",
    "qs-s004",
    "qs-s014",
    "qs-s029",
    "qs-s032",
    "qs-b017",
    "qs-b018",
    "qs-b019",
    "qs-b020",
    "qs-b057",
    "qs-b058",
    "qs-b059",
    "qs-b117",
    "qs-b125",
)

REPLAY_SCENARIO_MAP = {
    "QP-C01": "QS-C01",
    "QP-C02": "QS-C02",
    "QP-C03": "QS-C08",
    "QP-C04": "QS-C06",
}
ALLOWED_REPEATED_VECTOR_PARENT_SETS = (
    frozenset({"qs-s029", "qs-s032"}),
)

_GROUP_NAMES_BY_BRANCH = {
    "ql-002": (
        "载体与版本",
        "主题与分类",
        "整理与保存",
        "借阅与归还",
        "替代格式",
        "展示与推荐",
        "来源与授权",
        "修复与复核",
    ),
    "ql-003": (
        "开放与预约",
        "座位与布局",
        "照明与声环境",
        "辅助设施",
        "使用例外",
        "清洁与维护",
        "导引与标识",
        "空间调整",
    ),
    "ql-004": (
        "到馆协助",
        "远程咨询",
        "预约提醒",
        "借阅支持",
        "无障碍服务",
        "成员活动",
        "意见处理",
        "学习陪伴",
    ),
    "ql-005": (
        "课程安排",
        "展览组织",
        "分享活动",
        "亲子项目",
        "共学小组",
        "志愿协作",
        "材料准备",
        "活动回顾",
    ),
    "qs-ops": (
        "开闭馆交接",
        "设备巡查",
        "网络维护",
        "安全提醒",
        "物资补充",
        "人员排班",
        "异常处置",
        "可达检查",
    ),
}

_BACKGROUND_RECORD_FIELD_POOL = (
    _f("记录标题"),
    _f("记录类别"),
    _f("当前状态"),
    _f("生效日期", "time_code"),
    _f("失效日期", "time_code"),
    _f("责任分组"),
    _f("适用对象", multiple=True),
    _f("适用范围", multiple=True),
    _f("复核日期", "time_code"),
    _f("公开标记", "boolean"),
    _f("备注类别"),
    _f("保留期限", "integer"),
    _f("关联对象类别", multiple=True),
    _f("完成标记", "boolean"),
    _f("变更原因"),
    _f("核验方式", multiple=True),
    _f("通知方式", multiple=True),
    _f("优先级别"),
)

_NESTED_RECORD_NAMES = (
    "执行细节",
    "时段设置",
    "关联说明",
    "状态变化",
    "检查结果",
    "适用范围",
    "处理步骤",
    "参与安排",
    "使用条件",
    "维护信息",
    "提醒设置",
    "复核记录",
)

_DEEP_FIELD_POOL = (
    _f("说明名称"),
    _f("开始时刻", "time_code"),
    _f("结束时刻", "time_code"),
    _f("持续分钟", "integer"),
    _f("启用状态", "boolean"),
    _f("适用类别", multiple=True),
    _f("处理方式", multiple=True),
    _f("责任角色"),
    _f("复查标记", "boolean"),
    _f("顺序位置", "integer"),
    _f("提醒时段", "time_code", True),
    _f("限制说明", multiple=True),
    _f("确认状态"),
    _f("记录日期", "time_code"),
    _f("关联数量", "integer"),
    _f("补充要求", multiple=True),
    _f("可选方式", multiple=True),
    _f("完成条件"),
    _f("例外状态", "boolean"),
    _f("更新次数", "integer"),
    _f("使用说明"),
    _f("调整日期", "time_code"),
    _f("检查级别"),
    _f("公开标记", "boolean"),
)

_DEEP_CLASS_NAMES = (
    "时间窗口",
    "适用条件",
    "处理结果",
    "关联对象",
    "复查要求",
    "提醒规则",
    "例外安排",
    "状态轨迹",
    "使用限制",
    "完成记录",
    "调整信息",
    "确认明细",
)

_STRESS_SUBJECT_NAMES = (
    "开馆前核对记录",
    "闭馆后交接清单",
    "周末开放复查",
    "节假日值守说明",
    "临时开放调整单",
    "设备停用跟进记录",
    "场地调整确认单",
    "活动结束复核表",
    "借阅高峰分流记录",
    "资料整理交接单",
    "清洁作业复查表",
    "网络维护恢复记录",
    "照明切换确认单",
    "座位调整检查表",
    "临时通道状态单",
    "物资补充核对表",
    "讲解设备交接单",
    "预约异常跟进单",
    "标识更新复查表",
    "门禁状态确认单",
    "志愿排班交接单",
    "雨天入口检查表",
    "夜间巡查记录",
    "早班设备核对单",
    "晚班场地确认单",
    "高峰时段观察表",
    "临时展台复查单",
    "移动座椅核对表",
    "辅助设备状态单",
    "备用网络确认单",
    "清点差异跟进表",
    "开放延迟说明单",
    "闭馆提前确认单",
    "课程改期复查表",
    "展览撤场核对单",
    "音响停用确认单",
    "投影恢复记录",
    "入口导引复查单",
    "临时区域隔离检查",
    "临时储物核对单",
    "资料转架确认表",
    "读者分流观察单",
    "服务台交班记录",
    "备用照明检查单",
    "设备借用归还单",
    "异常解除确认表",
)

_STRESS_FIELD_POOL = (
    _f("检查状态"),
    _f("执行日期", "time_code"),
    _f("恢复标记", "boolean"),
    _f("复查次数", "integer"),
    _f("影响类别", multiple=True),
    _f("交接方式"),
    _f("确认时段", "time_code", True),
    _f("异常说明", multiple=True),
    _f("责任分组"),
    _f("完成标记", "boolean"),
    _f("跟进日期", "time_code"),
    _f("调整数量", "integer"),
    _f("提醒渠道", multiple=True),
    _f("值守状态"),
    _f("补充要求", multiple=True),
    _f("处理级别"),
    _f("公开状态", "boolean"),
    _f("记录说明"),
)


def _medium_nodes_by_id() -> dict[str, Any]:
    result = adapt_tree_document(build_qinglan_library_semantic_tree())
    if not result.is_valid or result.tree is None:
        raise AssertionError("frozen Qinglan semantic tree must adapt")
    return {node.node_id: node for node in result.tree.nodes}


_MEDIUM_NODES_BY_ID = _medium_nodes_by_id()


def _anchor_spec(node_id: str) -> _NodeSpec:
    node = _MEDIUM_NODES_BY_ID[node_id]
    contract = node.value_contract
    return _NodeSpec(
        node_id=node.node_id,
        label=node.label,
        name=node.name,
        parent_node_id=node.parent_node_id,
        kind=node.kind,
        family="curated_core",
        value_type=None if contract is None else contract.value_type,
        multiple=(
            None
            if contract is None
            else contract.cardinality == "MULTIPLE"
        ),
        semantic_role=node.extension.get("semantic_role"),
        semantic_target_eligible=bool(
            node.extension.get("semantic_target_eligible")
        ),
        lineage_role="replay_anchor",
        represents=(
            f"一条冻结重放锚点中的“{node.name}”记录"
            if contract is not None and contract.value_type == "class"
            else (
                f"其父锚点记录的“{node.name}”字段值"
                if contract is not None
                else None
            )
        ),
        parent_relation=(
            "沿冻结锚点合同保留的父子关系"
            if contract is not None
            else None
        ),
        entity_scope=(
            "COLLECTION_ITEM"
            if contract is not None
            else None
        ),
        record_profile=(
            "REPLAY_ANCHOR_RECORD"
            if contract is not None and contract.value_type == "class"
            else None
        ),
    )


def _group_specs() -> tuple[_GroupSpec, ...]:
    specs = []
    index = 1
    for branch_ref, names in _GROUP_NAMES_BY_BRANCH.items():
        for name in names:
            specs.append(
                _GroupSpec(
                    node_id=f"qlp-g{index:03d}",
                    label=f"QP_GROUP_{index:03d}",
                    name=name,
                    parent_node_id=branch_ref,
                    branch_ref=branch_ref,
                    family=(
                        "curated_core"
                        if index <= 8
                        else "approved_blueprint_background"
                    ),
                )
            )
            index += 1
    if len(specs) != 40:
        raise AssertionError("production blueprint requires 40 groups")
    return tuple(specs)


_GROUPS = _group_specs()

# Frozen before generation.  Each tuple is bound to exactly one organizational
# group; names are not sampled from a branch-wide pool.
_RECORD_NAMES_BY_GROUP_ID = {
    "qlp-g001": (
        "馆藏载体版本条目",
        "单册装帧版本条目",
        "数字文件版本条目",
        "有声版本条目",
        "大字版本条目",
        "修订版本条目",
    ),
    "qlp-g002": (
        "主题标引记录",
        "分类定位记录",
        "主题词复核记录",
        "读者层级标引",
        "内容形式标引",
        "索引调整记录",
    ),
    "qlp-g003": (
        "馆藏整理批次",
        "保存状态记录",
        "装盒作业记录",
        "温湿复查记录",
        "转架作业记录",
        "修复前检查",
    ),
    "qlp-g004": (
        "借阅规则版本",
        "归还规则版本",
        "续借条件记录",
        "外借例外规则",
        "逾期处置规则",
        "借阅范围说明",
    ),
    "qlp-g005": (
        "无障碍格式条目",
        "文本替代格式条目",
        "音频替代格式条目",
        "触读替代格式条目",
        "简明版条目",
        "格式转换记录",
    ),
    "qlp-g006": (
        "展示单元记录",
        "推荐书目单元",
        "主题陈列单元",
        "新到馆推荐单元",
        "读者荐购展示",
        "轮换展示记录",
    ),
    "qlp-g007": (
        "采购来源声明",
        "捐赠来源声明",
        "自制资料来源声明",
        "授权使用声明",
        "访问权限声明",
        "权限复核记录",
    ),
    "qlp-g008": (
        "修复作业单",
        "修复验收单",
        "缺损复核单",
        "装订复核单",
        "数字文件校验单",
        "修复回架确认",
    ),
    "qlp-g009": (
        "空间开放周期",
        "临时开放窗口",
        "团体预约规则",
        "个人预约规则",
        "预约例外记录",
        "开放变更记录",
    ),
    "qlp-g010": (
        "阅览座位区记录",
        "独立座位区记录",
        "团体座位区记录",
        "可移动座位组",
        "轮椅停靠位记录",
        "座位调整批次",
    ),
    "qlp-g011": (
        "照明区域配置",
        "静音区域配置",
        "交流声区配置",
        "自然光区域记录",
        "辅助照明配置",
        "声环境复查记录",
    ),
    "qlp-g012": (
        "入口辅助设施",
        "阅读辅助设备",
        "移动辅助设备",
        "听觉辅助设备",
        "视觉辅助设备",
        "设施借用记录",
    ),
    "qlp-g013": (
        "安静要求例外",
        "临时占用许可",
        "陪同进入许可",
        "饮水使用例外",
        "设备使用例外",
        "例外复核记录",
    ),
    "qlp-g014": (
        "日常清洁作业",
        "深度清洁作业",
        "座椅维护作业",
        "地面维护作业",
        "通风维护作业",
        "清洁验收记录",
    ),
    "qlp-g015": (
        "入口导引牌",
        "楼层导引牌",
        "区域名称牌",
        "无障碍导引牌",
        "临时提示牌",
        "标识巡检记录",
    ),
    "qlp-g016": (
        "座位调整方案",
        "通道调整方案",
        "展架调整方案",
        "照明调整方案",
        "分区调整方案",
        "调整验收记录",
    ),
    "qlp-g017": (
        "到馆协助申请",
        "入馆引导任务",
        "取书协助任务",
        "设备使用协助",
        "离馆引导任务",
        "协助回访记录",
    ),
    "qlp-g018": (
        "线上咨询会话",
        "电话咨询会话",
        "资料查询委托",
        "远程操作指引",
        "咨询跟进记录",
    ),
    "qlp-g019": (
        "开放预约提醒",
        "活动预约提醒",
        "取书到期提醒",
        "变更通知记录",
        "提醒失败跟进",
    ),
    "qlp-g020": (
        "借阅协助工单",
        "续借协助工单",
        "归还协助工单",
        "借阅异常工单",
        "支持回访记录",
    ),
    "qlp-g021": (
        "阅读辅助申请",
        "行动协助申请",
        "沟通辅助申请",
        "资料转换申请",
        "服务复核记录",
    ),
    "qlp-g022": (
        "成员报名记录",
        "成员签到记录",
        "分组协作记录",
        "成员任务记录",
        "活动反馈记录",
    ),
    "qlp-g023": (
        "意见受理单",
        "意见分类单",
        "处理跟进单",
        "回复确认单",
        "意见复盘记录",
    ),
    "qlp-g024": (
        "学习陪伴申请",
        "陪伴时段安排",
        "学习目标记录",
        "陪伴过程记录",
        "陪伴回访记录",
    ),
    "qlp-g025": (
        "课程场次记录",
        "课程报名批次",
        "课程材料包",
        "课程讲解安排",
        "课程反馈记录",
    ),
    "qlp-g026": (
        "展览单元记录",
        "展品布置任务",
        "展览讲解场次",
        "展览巡检记录",
        "撤展验收记录",
    ),
    "qlp-g027": (
        "分享会场次",
        "分享主题登记",
        "分享嘉宾安排",
        "现场提问记录",
        "分享反馈记录",
    ),
    "qlp-g028": (
        "亲子活动场次",
        "家庭报名记录",
        "亲子材料包",
        "陪同规则记录",
        "亲子反馈记录",
    ),
    "qlp-g029": (
        "共学小组档案",
        "共学场次安排",
        "小组任务记录",
        "成果展示记录",
        "小组复盘记录",
    ),
    "qlp-g030": (
        "志愿任务单",
        "志愿报名记录",
        "志愿排班记录",
        "任务交接记录",
        "志愿反馈记录",
    ),
    "qlp-g031": (
        "活动材料包",
        "材料领取记录",
        "材料补充任务",
        "材料回收记录",
        "材料清点记录",
    ),
    "qlp-g032": (
        "活动回顾单",
        "影像整理记录",
        "参与反馈汇总",
        "改进事项记录",
        "回顾发布记录",
    ),
    "qlp-g033": (
        "开馆交接单",
        "闭馆交接单",
        "钥匙交接记录",
        "设备交接记录",
        "交接复核记录",
    ),
    "qlp-g034": (
        "设备巡查任务",
        "空间巡查任务",
        "通道巡查任务",
        "标识巡查任务",
        "巡查复核记录",
    ),
    "qlp-g035": (
        "网络维护窗口",
        "终端维护任务",
        "连接异常工单",
        "网络恢复确认",
        "维护复盘记录",
    ),
    "qlp-g036": (
        "开放安全提醒",
        "活动安全提醒",
        "设备安全提醒",
        "通行安全提醒",
        "提醒确认记录",
    ),
    "qlp-g037": (
        "耗材补充任务",
        "清洁物资补充",
        "活动物资补充",
        "辅助用品补充",
        "补充复核记录",
    ),
    "qlp-g038": (
        "服务台排班",
        "巡查排班",
        "活动值守排班",
        "维护值守排班",
        "排班变更记录",
    ),
    "qlp-g039": (
        "异常受理单",
        "异常分派单",
        "临时处置任务",
        "恢复确认单",
        "异常复盘记录",
    ),
    "qlp-g040": (
        "入口可达检查",
        "通道可达检查",
        "空间可达检查",
        "设备可达检查",
        "可达复核记录",
    ),
}


def _choose_facets(
    pool: tuple[_FacetTemplate, ...],
    *,
    count: int,
    choice_index: int,
) -> tuple[_FacetTemplate, ...]:
    options = tuple(combinations(pool, count))
    return options[(choice_index * 37) % len(options)]


def _build_node_specs() -> tuple[_NodeSpec, ...]:
    nodes = [_anchor_spec(node_id) for node_id in ANCHOR_NODE_IDS]

    for group in _GROUPS:
        nodes.append(
            _NodeSpec(
                node_id=group.node_id,
                label=group.label,
                name=group.name,
                parent_node_id=group.parent_node_id,
                kind="CONCEPT",
                family=group.family,
                semantic_role="ORGANIZATIONAL_CONCEPT",
            )
        )

    special_nodes = (
        _NodeSpec(
            "qp-s001",
            "QP_COLLECTION_VERSION_RECORD",
            "馆藏版本",
            "qlp-g001",
            "PROPERTY",
            "curated_core",
            "class",
            True,
            "COMPOSITE_RECORD",
            True,
            represents="一条馆藏载体及其版本信息",
            parent_relation="作为“载体与版本”分组中的可重复成员",
            entity_scope="COLLECTION_ITEM",
            record_profile="CARRIER_VERSION_RECORD",
        ),
        _NodeSpec(
            "qp-f001",
            "QP_VERSION_DESCRIPTION",
            "版本说明",
            "qp-s001",
            "PROPERTY",
            "curated_core",
            "string",
            False,
            "SCALAR_FIELD",
            True,
            represents="其父馆藏版本记录的版本说明值",
            parent_relation="作为父记录的标量字段",
        ),
        _NodeSpec(
            "qp-f002",
            "QP_VERSION_MARKER",
            "版本标记",
            "qp-s001",
            "PROPERTY",
            "curated_core",
            "string",
            False,
            "SCALAR_FIELD",
            True,
            represents="其父馆藏版本记录的版本标记值",
            parent_relation="作为父记录的标量字段",
        ),
        _NodeSpec(
            "qp-s002",
            "QP_OPENING_ARRANGEMENT",
            "开放安排",
            "qlp-g009",
            "PROPERTY",
            "curated_core",
            "class",
            True,
            "COMPOSITE_RECORD",
            True,
            represents="一条空间开放安排",
            parent_relation="作为“开放与预约”分组中的可重复成员",
            entity_scope="COLLECTION_ITEM",
            record_profile="SPACE_OPENING_RECORD",
        ),
        _NodeSpec(
            "qp-f003",
            "QP_OPENING_PERIOD",
            "开放时段",
            "qp-s002",
            "PROPERTY",
            "curated_core",
            "time_code",
            True,
            "SCALAR_FIELD",
            True,
            represents="其父开放安排记录的开放时段值",
            parent_relation="作为父记录的标量字段",
        ),
        _NodeSpec(
            "qp-s003",
            "QP_SERVICE_WAIT_RECORD",
            "服务等候记录",
            "qlp-g017",
            "PROPERTY",
            "curated_core",
            "class",
            True,
            "COMPOSITE_RECORD",
            True,
            represents="一条读者服务等候记录",
            parent_relation="作为“到馆协助”分组中的可重复成员",
            entity_scope="COLLECTION_ITEM",
            record_profile="SERVICE_WAIT_RECORD",
        ),
        _NodeSpec(
            "qp-f004",
            "QP_WAIT_DURATION",
            "等候时长",
            "qp-s003",
            "PROPERTY",
            "curated_core",
            "integer",
            False,
            "SCALAR_FIELD",
            True,
            represents="其父服务等候记录的等候时长值",
            parent_relation="作为父记录的标量字段",
        ),
        _NodeSpec(
            "qp-f005",
            "QP_REMINDER_METHOD",
            "提醒方式",
            "qp-s003",
            "PROPERTY",
            "curated_core",
            "string",
            True,
            "SCALAR_FIELD",
            True,
            represents="其父服务等候记录的提醒方式值",
            parent_relation="作为父记录的标量字段",
        ),
    )
    nodes.extend(special_nodes)

    background_subjects = []
    subject_index = 1
    for group_index, group in enumerate(_GROUPS):
        subject_count = 6 if group_index < 17 else 5
        names = _RECORD_NAMES_BY_GROUP_ID[group.node_id]
        if len(names) != subject_count:
            raise AssertionError(
                f"{group.node_id} record blueprint count mismatch"
            )
        for name in names:
            spec = _NodeSpec(
                node_id=f"qlp-bg-s{subject_index:03d}",
                label=f"QP_BG_SUBJECT_{subject_index:03d}",
                name=name,
                parent_node_id=group.node_id,
                kind="PROPERTY",
                family="approved_blueprint_background",
                value_type="class",
                multiple=True,
                semantic_role="COMPOSITE_RECORD",
                represents=f"一条具体的“{name}”业务记录",
                parent_relation=(
                    f"作为“{group.name}”分组中的可重复成员"
                ),
                entity_scope="COLLECTION_ITEM",
                record_profile=f"GROUP_{group.node_id.removeprefix('qlp-g')}",
            )
            background_subjects.append(spec)
            nodes.append(spec)
            subject_index += 1
    if len(background_subjects) != 217:
        raise AssertionError("production blueprint requires 217 background owners")

    stress_subjects = []
    stress_index = 1
    for group_index, group in enumerate(_GROUPS):
        subject_count = 2 if group_index < 6 else 1
        for _ in range(subject_count):
            spec = _NodeSpec(
                node_id=f"qlp-st-s{stress_index:03d}",
                label=f"QP_STRESS_SUBJECT_{stress_index:03d}",
                name=_STRESS_SUBJECT_NAMES[stress_index - 1],
                parent_node_id=group.node_id,
                kind="PROPERTY",
                family="stress_only_filler",
                value_type="class",
                multiple=True,
                semantic_role="COMPOSITE_RECORD",
                represents=f"一条具体的“{_STRESS_SUBJECT_NAMES[stress_index - 1]}”核查记录",
                parent_relation=(
                    f"作为“{group.name}”分组中的非目标压力成员"
                ),
                entity_scope="COLLECTION_ITEM",
                record_profile="STRESS_OPERATION_RECORD",
            )
            stress_subjects.append(spec)
            nodes.append(spec)
            stress_index += 1
    if len(stress_subjects) != 46:
        raise AssertionError("production blueprint requires 46 stress owners")

    background_level_four_classes = []
    background_field_index = 1
    for index, subject in enumerate(
        background_subjects,
        start=1,
    ):
        child_count = 3 if index <= 161 else 2
        has_nested_record = index <= 140
        scalar_count = child_count - int(has_nested_record)
        if has_nested_record:
            nested_name = _NESTED_RECORD_NAMES[
                (index - 1) % len(_NESTED_RECORD_NAMES)
            ]
            nested = _NodeSpec(
                node_id=f"qlp-bg-c4-{index:03d}",
                label=f"QP_BG_LEVEL4_RECORD_{index:03d}",
                name=nested_name,
                parent_node_id=subject.node_id,
                kind="PROPERTY",
                family="approved_blueprint_background",
                value_type="class",
                multiple=False,
                semantic_role="COMPOSITE_RECORD",
                represents=(
                    f"{subject.represents}中的单一“{nested_name}”组成记录"
                ),
                parent_relation="作为该重复成员记录的单一组成部分",
                entity_scope="COLLECTION_ITEM",
                record_profile=subject.record_profile,
            )
            background_level_four_classes.append(nested)
            nodes.append(nested)
        facets = _choose_facets(
            _BACKGROUND_RECORD_FIELD_POOL,
            count=scalar_count,
            choice_index=index - 1,
        )
        for facet in facets:
            nodes.append(
                _NodeSpec(
                    node_id=f"qlp-bg-f4-{background_field_index:04d}",
                    label=f"QP_BG_LEVEL4_FIELD_{background_field_index:04d}",
                    name=facet.name,
                    parent_node_id=subject.node_id,
                    kind="PROPERTY",
                    family="approved_blueprint_background",
                    value_type=facet.value_type,
                    multiple=facet.multiple,
                    semantic_role="SCALAR_FIELD",
                    represents=(
                        f"{subject.represents}的“{facet.name}”字段值"
                    ),
                    parent_relation="作为该记录的标量字段",
                )
            )
            background_field_index += 1
    if background_field_index - 1 != 455:
        raise AssertionError("production blueprint requires 455 background level-4 fields")

    stress_level_four_classes = []
    stress_field_index = 1
    for index, subject in enumerate(stress_subjects, start=1):
        child_count = 4 if index <= 13 else 3
        has_nested_record = index <= 35
        scalar_count = child_count - int(has_nested_record)
        if has_nested_record:
            nested_name = _NESTED_RECORD_NAMES[
                (index + 4) % len(_NESTED_RECORD_NAMES)
            ]
            nested = _NodeSpec(
                node_id=f"qlp-st-c4-{index:03d}",
                label=f"QP_STRESS_LEVEL4_RECORD_{index:03d}",
                name=nested_name,
                parent_node_id=subject.node_id,
                kind="PROPERTY",
                family="stress_only_filler",
                value_type="class",
                multiple=False,
                semantic_role="COMPOSITE_RECORD",
                represents=(
                    f"{subject.represents}中的单一“{nested_name}”组成记录"
                ),
                parent_relation="作为该重复成员记录的单一组成部分",
                entity_scope="COLLECTION_ITEM",
                record_profile="STRESS_OPERATION_RECORD",
            )
            stress_level_four_classes.append(nested)
            nodes.append(nested)
        facets = _choose_facets(
            _STRESS_FIELD_POOL,
            count=scalar_count,
            choice_index=index - 1,
        )
        for facet in facets:
            nodes.append(
                _NodeSpec(
                    node_id=f"qlp-st-f4-{stress_field_index:04d}",
                    label=f"QP_STRESS_LEVEL4_FIELD_{stress_field_index:04d}",
                    name=facet.name,
                    parent_node_id=subject.node_id,
                    kind="PROPERTY",
                    family="stress_only_filler",
                    value_type=facet.value_type,
                    multiple=facet.multiple,
                    semantic_role="SCALAR_FIELD",
                    represents=(
                        f"{subject.represents}的“{facet.name}”字段值"
                    ),
                    parent_relation="作为该记录的标量字段",
                )
            )
            stress_field_index += 1
    if stress_field_index - 1 != 116:
        raise AssertionError("production blueprint requires 116 stress level-4 fields")

    background_level_five_classes = []
    background_deep_field_index = 1
    for index, parent in enumerate(background_level_four_classes, start=1):
        child_count = 4 if index <= 130 else 3
        has_nested_record = index <= 42
        scalar_count = child_count - int(has_nested_record)
        if has_nested_record:
            nested_name = _DEEP_CLASS_NAMES[
                (index - 1) % len(_DEEP_CLASS_NAMES)
            ]
            nested = _NodeSpec(
                node_id=f"qlp-bg-c5-{index:03d}",
                label=f"QP_BG_LEVEL5_RECORD_{index:03d}",
                name=nested_name,
                parent_node_id=parent.node_id,
                kind="PROPERTY",
                family="approved_blueprint_background",
                value_type="class",
                multiple=False,
                semantic_role="COMPOSITE_RECORD",
                represents=(
                    f"{parent.represents}中的单一“{nested_name}”组成记录"
                ),
                parent_relation="作为父组成记录的单一明细",
                entity_scope="COLLECTION_ITEM",
                record_profile=parent.record_profile,
            )
            background_level_five_classes.append(nested)
            nodes.append(nested)
        facets = _choose_facets(
            _DEEP_FIELD_POOL,
            count=scalar_count,
            choice_index=index - 1,
        )
        for facet in facets:
            nodes.append(
                _NodeSpec(
                    node_id=f"qlp-bg-f5-{background_deep_field_index:04d}",
                    label=f"QP_BG_LEVEL5_FIELD_{background_deep_field_index:04d}",
                    name=facet.name,
                    parent_node_id=parent.node_id,
                    kind="PROPERTY",
                    family="approved_blueprint_background",
                    value_type=facet.value_type,
                    multiple=facet.multiple,
                    semantic_role="SCALAR_FIELD",
                    represents=(
                        f"{parent.represents}的“{facet.name}”字段值"
                    ),
                    parent_relation="作为该组成记录的标量字段",
                )
            )
            background_deep_field_index += 1
    if background_deep_field_index - 1 != 508:
        raise AssertionError("production blueprint requires 508 background level-5 fields")

    stress_level_five_classes = []
    stress_deep_field_index = 1
    for index, parent in enumerate(stress_level_four_classes, start=1):
        child_count = 5 if index <= 10 else 4
        has_nested_record = index <= 13
        scalar_count = child_count - int(has_nested_record)
        if has_nested_record:
            nested_name = _DEEP_CLASS_NAMES[
                (index + 5) % len(_DEEP_CLASS_NAMES)
            ]
            nested = _NodeSpec(
                node_id=f"qlp-st-c5-{index:03d}",
                label=f"QP_STRESS_LEVEL5_RECORD_{index:03d}",
                name=nested_name,
                parent_node_id=parent.node_id,
                kind="PROPERTY",
                family="stress_only_filler",
                value_type="class",
                multiple=False,
                semantic_role="COMPOSITE_RECORD",
                represents=(
                    f"{parent.represents}中的单一“{nested_name}”组成记录"
                ),
                parent_relation="作为父组成记录的单一明细",
                entity_scope="COLLECTION_ITEM",
                record_profile="STRESS_OPERATION_RECORD",
            )
            stress_level_five_classes.append(nested)
            nodes.append(nested)
        facets = _choose_facets(
            _DEEP_FIELD_POOL,
            count=scalar_count,
            choice_index=index + 180,
        )
        for facet in facets:
            nodes.append(
                _NodeSpec(
                    node_id=f"qlp-st-f5-{stress_deep_field_index:04d}",
                    label=f"QP_STRESS_LEVEL5_FIELD_{stress_deep_field_index:04d}",
                    name=facet.name,
                    parent_node_id=parent.node_id,
                    kind="PROPERTY",
                    family="stress_only_filler",
                    value_type=facet.value_type,
                    multiple=facet.multiple,
                    semantic_role="SCALAR_FIELD",
                    represents=(
                        f"{parent.represents}的“{facet.name}”字段值"
                    ),
                    parent_relation="作为该组成记录的标量字段",
                )
            )
            stress_deep_field_index += 1
    if stress_deep_field_index - 1 != 137:
        raise AssertionError("production blueprint requires 137 stress level-5 fields")

    background_level_six_field_index = 1
    for index, parent in enumerate(background_level_five_classes, start=1):
        child_count = 4 if index <= 41 else 3
        facets = _choose_facets(
            _DEEP_FIELD_POOL,
            count=child_count,
            choice_index=index + 360,
        )
        for facet in facets:
            nodes.append(
                _NodeSpec(
                    node_id=f"qlp-bg-f6-{background_level_six_field_index:04d}",
                    label=f"QP_BG_LEVEL6_FIELD_{background_level_six_field_index:04d}",
                    name=facet.name,
                    parent_node_id=parent.node_id,
                    kind="PROPERTY",
                    family="approved_blueprint_background",
                    value_type=facet.value_type,
                    multiple=facet.multiple,
                    semantic_role="SCALAR_FIELD",
                    represents=(
                        f"{parent.represents}的“{facet.name}”字段值"
                    ),
                    parent_relation="作为该组成记录的标量字段",
                )
            )
            background_level_six_field_index += 1
    if background_level_six_field_index - 1 != 167:
        raise AssertionError("production blueprint requires 167 background level-6 fields")

    stress_level_six_field_index = 1
    for index, parent in enumerate(stress_level_five_classes, start=1):
        child_count = 5 if index == 1 else 4
        facets = _choose_facets(
            _STRESS_FIELD_POOL,
            count=child_count,
            choice_index=index + 90,
        )
        for facet in facets:
            nodes.append(
                _NodeSpec(
                    node_id=f"qlp-st-f6-{stress_level_six_field_index:04d}",
                    label=f"QP_STRESS_LEVEL6_FIELD_{stress_level_six_field_index:04d}",
                    name=facet.name,
                    parent_node_id=parent.node_id,
                    kind="PROPERTY",
                    family="stress_only_filler",
                    value_type=facet.value_type,
                    multiple=facet.multiple,
                    semantic_role="SCALAR_FIELD",
                    represents=(
                        f"{parent.represents}的“{facet.name}”字段值"
                    ),
                    parent_relation="作为该组成记录的标量字段",
                )
            )
            stress_level_six_field_index += 1
    if stress_level_six_field_index - 1 != 53:
        raise AssertionError("production blueprint requires 53 stress level-6 fields")

    if len(nodes) != TARGET_NODE_COUNT:
        raise AssertionError(
            f"production blueprint built {len(nodes)} nodes"
        )
    if len({node.node_id for node in nodes}) != len(nodes):
        raise AssertionError("production blueprint node ids must be unique")
    return tuple(nodes)


_BLUEPRINT_NODE_SPECS = _build_node_specs()


def _freeze_allowed_facets_from_blueprint(
    specs: tuple[_NodeSpec, ...],
) -> dict[str, tuple[_NodeSpec, ...]]:
    facets: dict[str, list[_NodeSpec]] = defaultdict(list)
    for spec in specs:
        if (
            spec.kind == "PROPERTY"
            and spec.value_type != "class"
            and spec.parent_node_id is not None
        ):
            facets[spec.parent_node_id].append(spec)
    return {
        subject: tuple(items)
        for subject, items in sorted(facets.items())
    }


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


ALLOWED_FACETS_BY_SUBJECT = _freeze_allowed_facets_from_blueprint(
    _BLUEPRINT_NODE_SPECS
)
RECORD_BLUEPRINT_BY_ID = {
    spec.node_id: spec
    for spec in _BLUEPRINT_NODE_SPECS
    if spec.kind == "PROPERTY" and spec.value_type == "class"
}
RECORD_BLUEPRINT_DIGEST = _canonical_digest(
    [
        {
            "node_id": spec.node_id,
            "parent_node_id": spec.parent_node_id,
            "name": spec.name,
            "represents": spec.represents,
            "parent_relation": spec.parent_relation,
            "entity_scope": spec.entity_scope,
            "cardinality": "MULTIPLE" if spec.multiple else "SINGLE",
            "record_profile": spec.record_profile,
        }
        for spec in RECORD_BLUEPRINT_BY_ID.values()
    ]
)
ALLOWED_FACETS_DIGEST = _canonical_digest(
    {
        subject_id: [
            {
                "node_id": facet.node_id,
                "name": facet.name,
                "value_type": facet.value_type,
                "cardinality": (
                    "MULTIPLE" if facet.multiple else "SINGLE"
                ),
            }
            for facet in facets
        ]
        for subject_id, facets in ALLOWED_FACETS_BY_SUBJECT.items()
    }
)


def _materialize_blueprint_nodes() -> tuple[_NodeSpec, ...]:
    allowed_ids = {
        facet.node_id
        for facets in ALLOWED_FACETS_BY_SUBJECT.values()
        for facet in facets
    }
    blueprint_scalar_ids = {
        spec.node_id
        for spec in _BLUEPRINT_NODE_SPECS
        if spec.kind == "PROPERTY" and spec.value_type != "class"
    }
    if allowed_ids != blueprint_scalar_ids:
        raise AssertionError("frozen allowed table does not cover blueprint")
    return tuple(_BLUEPRINT_NODE_SPECS)


_NODES = _materialize_blueprint_nodes()
_NODE_BY_ID = {node.node_id: node for node in _NODES}


def _children_by_parent() -> dict[str | None, tuple[_NodeSpec, ...]]:
    children: dict[str | None, list[_NodeSpec]] = defaultdict(list)
    for spec in _NODES:
        children[spec.parent_node_id].append(spec)
    return {parent: tuple(items) for parent, items in children.items()}


def _value_owner_scope(spec: _NodeSpec) -> str:
    if spec.kind == "CONCEPT":
        return (
            "RESOURCE_SINGLETON"
            if spec.semantic_role == "SINGLETON_SECTION"
            else "NOT_APPLICABLE"
        )
    if spec.value_type == "class":
        return "REPEATED_RECORD" if spec.multiple else "SINGLETON_RECORD"
    parent = _NODE_BY_ID.get(spec.parent_node_id)
    if parent is not None and parent.kind == "CONCEPT":
        return "PARENT_SINGLETON_SECTION"
    return "PARENT_CLASS_RECORD"


def _blueprint_attribute_scope(spec: _NodeSpec) -> str:
    if spec.kind == "CONCEPT":
        return (
            "ROOT_ENTITY"
            if spec.semantic_role == "SINGLETON_SECTION"
            else "NOT_APPLICABLE"
        )
    current: _NodeSpec | None = spec
    while current is not None:
        if (
            current.kind == "PROPERTY"
            and current.value_type == "class"
            and current.multiple
        ):
            return "COLLECTION_ITEM"
        current = _NODE_BY_ID.get(current.parent_node_id)
    return "ROOT_ENTITY"


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
        "node_type": spec.kind.lower(),
        "extension": {
            "dataset_family": spec.family,
            "lineage_role": spec.lineage_role,
            "semantic_target_eligible": spec.semantic_target_eligible,
            "semantic_role": spec.semantic_role,
            "value_owner_scope": _value_owner_scope(spec),
            "attribute_scope": _blueprint_attribute_scope(spec),
            "represents": spec.represents,
            "parent_relation": spec.parent_relation,
            "entity_scope": _blueprint_attribute_scope(spec),
            "declared_entity_scope": spec.entity_scope,
            "declared_cardinality": (
                (
                    "MULTIPLE"
                    if spec.multiple
                    else "SINGLE"
                )
                if spec.kind == "PROPERTY"
                else None
            ),
            "record_profile": spec.record_profile,
        },
    }
    if spec.kind == "PROPERTY":
        metadata.update(
            {
                "value_type": spec.value_type,
                "is_list": spec.multiple,
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
        for child_order, child in enumerate(
            children.get(spec.node_id, ()),
            start=1,
        )
    }
    return {"metadata": metadata, "subnodes": subnodes}


def build_qinglan_library_production_shape_tree() -> dict[str, Any]:
    """Build the 2,001-node clean-room production-shape tree."""

    children = _children_by_parent()
    roots = children.get(None, ())
    if len(roots) != 1:
        raise AssertionError("production blueprint requires one root")
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
            "record_blueprint_digest": RECORD_BLUEPRINT_DIGEST,
            "allowed_facets_digest": ALLOWED_FACETS_DIGEST,
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


def _scenario(
    scenario_ref: str,
    primary_risk: str,
    challenge_tags: tuple[str, ...],
    requirement_text: str,
    parent_node_id: str | None,
    node_kind: str,
    value_type: str | None,
    cardinality: str,
    observable_category: str,
) -> dict[str, Any]:
    return {
        "scenario_ref": scenario_ref,
        "primary_risk": primary_risk,
        "challenge_tags": list(challenge_tags),
        "request": {
            "requirement_text": requirement_text,
            "proposed_parent_node_id": parent_node_id,
            "node_kind_hint": node_kind,
            "value_type_hint": value_type,
            "cardinality_hint": cardinality,
        },
        "proposed_observable_state": {
            "authority": "PROVISIONAL_HUMAN_REVIEW_REQUIRED",
            "category": observable_category,
        },
        "source_class": SOURCE_CLASS,
        "candidate_source": "AI_SYNTHETIC",
        "fictional": True,
        "gold_eligible": False,
        "patch_eligible": False,
    }


def _replay_scenarios() -> list[dict[str, Any]]:
    medium = {
        item["scenario_ref"]: item
        for item in build_qinglan_library_semantic_scenarios()
    }
    items = []
    for replay_ref, source_ref in REPLAY_SCENARIO_MAP.items():
        item = json.loads(
            json.dumps(medium[source_ref], ensure_ascii=False)
        )
        item["scenario_ref"] = replay_ref
        item["challenge_tags"] = [
            *item["challenge_tags"],
            "replay_anchor",
            "large_tree",
        ]
        items.append(item)
    return items


_NEW_SCENARIOS = (
    _scenario(
        "QP-C05",
        "NEAR_NAME_HARD_NEGATIVE",
        ("near_name_negative", "candidate_limit", "large_tree"),
        "在馆藏版本下面记录版本说明。",
        "qp-s001",
        "PROPERTY",
        "string",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QP-C06",
        "INSTANCE_SCOPE_CONFLICT",
        ("value_owner", "collection_item", "large_tree"),
        "在读者服务下面记录每位到馆协助对象的等候时长。",
        "ql-004",
        "PROPERTY",
        "integer",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QP-C07",
        "REORDER_STABILITY",
        ("deterministic_replay", "node_reordering", "large_tree"),
        "在开放安排下面记录开放时段。",
        "qp-s002",
        "PROPERTY",
        "time_code",
        "MULTIPLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QP-C08",
        "LARGE_TREE_NO_SIGNAL",
        ("stress_only", "oracle_boundary", "insufficient_evidence"),
        "请判断借阅高峰应采用哪一种最优分流方式并记录结论；当前树没有效果证据。",
        None,
        "PROPERTY",
        "string",
        "SINGLE",
        "NEED_EVIDENCE",
    ),
)


def build_qinglan_library_production_shape_scenarios() -> list[dict[str, Any]]:
    """Return detached scenarios in stable order."""

    return json.loads(
        json.dumps(
            [*_replay_scenarios(), *_NEW_SCENARIOS],
            ensure_ascii=False,
        )
    )


def _anchor_projection(node: Any) -> dict[str, Any]:
    contract = node.value_contract
    return {
        "node_id": node.node_id,
        "parent_node_id": node.parent_node_id,
        "path_labels": list(node.path_labels),
        "kind": node.kind,
        "name": node.name,
        "value_type": None if contract is None else contract.value_type,
        "cardinality": None if contract is None else contract.cardinality,
        "constraints": (
            None if contract is None else dict(contract.constraints)
        ),
    }


def _depth_by_node_id(nodes: Iterable[Any]) -> dict[str, int]:
    by_id = {node.node_id: node for node in nodes}
    depths: dict[str, int] = {}

    def depth(node_id: str) -> int:
        if node_id in depths:
            return depths[node_id]
        parent_id = by_id[node_id].parent_node_id
        value = 0 if parent_id is None else depth(parent_id) + 1
        depths[node_id] = value
        return value

    for node_id in by_id:
        depth(node_id)
    return depths


def _child_vector(
    node: Any,
    *,
    nodes_by_id: dict[str, Any],
) -> tuple[tuple[Any, ...], ...]:
    vector = []
    for child_id in node.child_node_ids:
        child = nodes_by_id[child_id]
        contract = child.value_contract
        vector.append(
            (
                child.name,
                child.kind,
                None if contract is None else contract.value_type,
                None if contract is None else contract.cardinality,
            )
        )
    return tuple(vector)


def run_qinglan_library_production_shape_preflight(
    *,
    tree: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run aggregate-only deterministic gates."""

    candidate_tree = (
        build_qinglan_library_production_shape_tree()
        if tree is None
        else tree
    )
    candidate_scenarios = (
        build_qinglan_library_production_shape_scenarios()
        if scenarios is None
        else scenarios
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
    if metadata.get("record_blueprint_digest") != RECORD_BLUEPRINT_DIGEST:
        findings["DATASET_RECORD_BLUEPRINT_DIGEST_MISMATCH"] += 1
    if metadata.get("allowed_facets_digest") != ALLOWED_FACETS_DIGEST:
        findings["DATASET_ALLOWLIST_DERIVED_FROM_OUTPUT"] += 1

    try:
        result = adapt_tree_document(candidate_tree)
    except (TypeError, ValueError):
        result = None
    if result is None or not result.is_valid or result.tree is None:
        findings["DATASET_ADAPTER_INVALID"] += 1
        canonical_nodes = ()
    else:
        canonical_nodes = result.tree.nodes
    observed_node_count = 0 if result is None else result.observed_node_count
    observed_value_count = 0 if result is None else result.observed_value_count
    if (
        observed_node_count != TARGET_NODE_COUNT
        or observed_value_count != 0
        or len(candidate_scenarios) != TARGET_SCENARIO_COUNT
    ):
        findings["DATASET_COUNT_MISMATCH"] += 1

    nodes_by_id = {node.node_id: node for node in canonical_nodes}
    node_ids = set(nodes_by_id)
    medium_id_overlap = node_ids & set(_MEDIUM_NODES_BY_ID)
    if medium_id_overlap != set(ANCHOR_NODE_IDS):
        findings["DATASET_UNDECLARED_ANCHOR_COPY"] += 1
    for node_id in ANCHOR_NODE_IDS:
        candidate = nodes_by_id.get(node_id)
        source = _MEDIUM_NODES_BY_ID.get(node_id)
        if (
            candidate is None
            or source is None
            or _anchor_projection(candidate) != _anchor_projection(source)
        ):
            findings["DATASET_ANCHOR_CONTRACT_CHANGED"] += 1

    family_counts = Counter(
        node.extension.get("dataset_family") for node in canonical_nodes
    )
    if dict(family_counts) != TARGET_FAMILY_COUNTS:
        findings["DATASET_ROLE_MISMATCH"] += 1
    anchor_ids = {
        node.node_id
        for node in canonical_nodes
        if node.extension.get("lineage_role") == "replay_anchor"
    }
    if anchor_ids != set(ANCHOR_NODE_IDS):
        findings["DATASET_LINEAGE_INVALID"] += 1

    class_owner_ids = {
        node.node_id
        for node in canonical_nodes
        if (
            node.kind == "PROPERTY"
            and node.value_contract is not None
            and node.value_contract.value_type == "class"
        )
    }
    scalar_property_ids = {
        node.node_id
        for node in canonical_nodes
        if (
            node.kind == "PROPERTY"
            and node.value_contract is not None
            and node.value_contract.value_type != "class"
        )
    }
    allowed_property_ids = {
        facet.node_id
        for facets in ALLOWED_FACETS_BY_SUBJECT.values()
        for facet in facets
    }
    if scalar_property_ids != allowed_property_ids:
        findings["DATASET_COMBINATION_UNAPPROVED"] += 1
    expected_allowed_contracts = {
        facet.node_id: (
            subject_id,
            facet.name,
            facet.value_type,
            "MULTIPLE" if facet.multiple else "SINGLE",
        )
        for subject_id, facets in ALLOWED_FACETS_BY_SUBJECT.items()
        for facet in facets
    }
    observed_allowed_contracts = {
        node.node_id: (
            node.parent_node_id,
            node.name,
            node.value_contract.value_type,
            node.value_contract.cardinality,
        )
        for node in canonical_nodes
        if node.node_id in allowed_property_ids
        and node.value_contract is not None
    }
    if observed_allowed_contracts != expected_allowed_contracts:
        findings["DATASET_COMBINATION_UNAPPROVED"] += 1

    invalid_owner_count = 0
    missing_referent_count = 0
    missing_parent_relation_count = 0
    scope_ancestry_conflict_count = 0
    singleton_section_count = 0

    def expected_scope_from_ancestry(node: Any) -> str:
        if node.kind == "CONCEPT":
            return (
                "ROOT_ENTITY"
                if node.extension.get("semantic_role")
                == "SINGLETON_SECTION"
                else "NOT_APPLICABLE"
            )
        current = node
        visited: set[str] = set()
        while current is not None and current.node_id not in visited:
            visited.add(current.node_id)
            contract = current.value_contract
            if (
                current.kind == "PROPERTY"
                and contract is not None
                and contract.value_type == "class"
                and contract.cardinality == "MULTIPLE"
            ):
                return "COLLECTION_ITEM"
            current = nodes_by_id.get(current.parent_node_id)
        return "ROOT_ENTITY"

    for node in canonical_nodes:
        role = node.extension.get("semantic_role")
        owner_scope = node.extension.get("value_owner_scope")
        attribute_scope = node.extension.get("attribute_scope")
        entity_scope = node.extension.get("entity_scope")
        if node.kind == "CONCEPT":
            if role == "SINGLETON_SECTION":
                singleton_section_count += 1
                if (
                    owner_scope != "RESOURCE_SINGLETON"
                    or attribute_scope != "ROOT_ENTITY"
                ):
                    invalid_owner_count += 1
                allow_scalar = True
            elif role == "ORGANIZATIONAL_CONCEPT":
                if (
                    owner_scope != "NOT_APPLICABLE"
                    or attribute_scope != "NOT_APPLICABLE"
                ):
                    invalid_owner_count += 1
                allow_scalar = False
            else:
                invalid_owner_count += 1
                allow_scalar = False
            for child_id in node.child_node_ids:
                child = nodes_by_id.get(child_id)
                if (
                    not allow_scalar
                    and child is not None
                    and child.kind == "PROPERTY"
                    and child.value_contract is not None
                    and child.value_contract.value_type != "class"
                ):
                    invalid_owner_count += 1
        elif node.value_contract is not None:
            expected_attribute = expected_scope_from_ancestry(node)
            if node.value_contract.value_type == "class":
                expected_owner = (
                    "REPEATED_RECORD"
                    if node.value_contract.cardinality == "MULTIPLE"
                    else "SINGLETON_RECORD"
                )
                if (
                    role != "COMPOSITE_RECORD"
                    or owner_scope != expected_owner
                    or attribute_scope != expected_attribute
                    or entity_scope != expected_attribute
                ):
                    invalid_owner_count += 1
                if not isinstance(
                    node.extension.get("represents"),
                    str,
                ) or not node.extension.get("represents", "").strip():
                    missing_referent_count += 1
                if not isinstance(
                    node.extension.get("parent_relation"),
                    str,
                ) or not node.extension.get(
                    "parent_relation",
                    "",
                ).strip():
                    missing_parent_relation_count += 1
                if (
                    node.extension.get("declared_entity_scope")
                    != expected_attribute
                    or node.extension.get("declared_cardinality")
                    != node.value_contract.cardinality
                ):
                    scope_ancestry_conflict_count += 1
            else:
                parent = nodes_by_id.get(node.parent_node_id)
                parent_is_class = (
                    parent is not None
                    and parent.kind == "PROPERTY"
                    and parent.value_contract is not None
                    and parent.value_contract.value_type == "class"
                )
                parent_is_singleton = (
                    parent is not None
                    and parent.kind == "CONCEPT"
                    and parent.extension.get("semantic_role")
                    == "SINGLETON_SECTION"
                )
                expected_owner = (
                    "PARENT_CLASS_RECORD"
                    if parent_is_class
                    else (
                        "PARENT_SINGLETON_SECTION"
                        if parent_is_singleton
                        else None
                    )
                )
                if (
                    role != "SCALAR_FIELD"
                    or expected_owner is None
                    or owner_scope != expected_owner
                    or attribute_scope != expected_attribute
                    or entity_scope != expected_attribute
                ):
                    invalid_owner_count += 1
    if singleton_section_count != 1 or invalid_owner_count:
        findings["DATASET_VALUE_OWNER_INVALID"] += max(
            1,
            invalid_owner_count,
        )
    if missing_referent_count:
        findings["DATASET_RECORD_REFERENT_MISSING"] += (
            missing_referent_count
        )
    if missing_parent_relation_count:
        findings["DATASET_PARENT_RELATION_UNDECLARED"] += (
            missing_parent_relation_count
        )
    if scope_ancestry_conflict_count:
        findings["DATASET_SCOPE_ANCESTRY_CONFLICT"] += (
            scope_ancestry_conflict_count
        )

    filler_ids = {
        node.node_id
        for node in canonical_nodes
        if node.extension.get("dataset_family") == "stress_only_filler"
    }
    scenario_refs = [item.get("scenario_ref") for item in candidate_scenarios]
    primary_risks = [item.get("primary_risk") for item in candidate_scenarios]
    if (
        len(scenario_refs) != len(set(scenario_refs))
        or len(primary_risks) != len(set(primary_risks))
        or any(not isinstance(ref, str) or not ref for ref in scenario_refs)
    ):
        findings["DATASET_SCENARIO_COVERAGE_DUPLICATE"] += 1

    medium_scenarios = {
        item["scenario_ref"]: item
        for item in build_qinglan_library_semantic_scenarios()
    }
    replay_count = 0
    for item in candidate_scenarios:
        request = item.get("request", {})
        proposed = item.get("proposed_observable_state", {})
        parent_id = (
            request.get("proposed_parent_node_id")
            if isinstance(request, dict)
            else None
        )
        if parent_id is not None and parent_id not in node_ids:
            findings["DATASET_REFERENCE_INVALID"] += 1
        if parent_id in filler_ids:
            findings["DATASET_FILLER_TARGETED"] += 1
        if (
            item.get("source_class") != SOURCE_CLASS
            or item.get("fictional") is not True
            or item.get("gold_eligible") is not False
            or item.get("patch_eligible") is not False
        ):
            findings["DATASET_SOURCE_CLASS_INVALID"] += 1
        if "oracle" in item:
            findings["DATASET_ORACLE_OVERCLAIM"] += 1
        if (
            not isinstance(proposed, dict)
            or proposed.get("authority")
            != "PROVISIONAL_HUMAN_REVIEW_REQUIRED"
            or proposed.get("category")
            not in _ALLOWED_OBSERVABLE_CATEGORIES
        ):
            findings["DATASET_ORACLE_OVERCLAIM"] += 1
        tags = item.get("challenge_tags")
        if not isinstance(tags, list) or not tags:
            findings["DATASET_SCENARIO_COVERAGE_INVALID"] += 1
            tags = []
        if "replay_anchor" in tags:
            replay_count += 1
            source_ref = REPLAY_SCENARIO_MAP.get(item.get("scenario_ref"))
            source = medium_scenarios.get(source_ref)
            if (
                source is None
                or item.get("request") != source.get("request")
                or proposed != source.get("proposed_observable_state")
            ):
                findings["DATASET_REPLAY_CONTRACT_CHANGED"] += 1
    if replay_count != TARGET_REPLAY_SCENARIO_COUNT:
        findings["DATASET_LINEAGE_INVALID"] += 1

    depths = _depth_by_node_id(canonical_nodes) if canonical_nodes else {}
    depth_counts = Counter(depths.values())
    if dict(sorted(depth_counts.items())) != TARGET_DEPTH_COUNTS:
        findings["DATASET_DEPTH_PLAN_INVALID"] += 1

    child_vector_parents: dict[
        tuple[tuple[Any, ...], ...],
        set[str],
    ] = defaultdict(set)
    for node in canonical_nodes:
        if node.child_node_ids:
            child_vector_parents[
                _child_vector(node, nodes_by_id=nodes_by_id)
            ].add(node.node_id)
    repeated_parent_sets = {
        frozenset(parent_ids)
        for parent_ids in child_vector_parents.values()
        if len(parent_ids) > 1
    }
    allowed_repeated_sets = set(ALLOWED_REPEATED_VECTOR_PARENT_SETS)
    unapproved_repeated_sets = repeated_parent_sets - allowed_repeated_sets
    missing_declared_sets = allowed_repeated_sets - repeated_parent_sets
    if unapproved_repeated_sets:
        findings["DATASET_REPEATED_VECTOR"] += sum(
            len(parent_ids) - 1
            for parent_ids in unapproved_repeated_sets
        )
    if missing_declared_sets:
        findings["DATASET_DECLARED_VECTOR_MISSING"] += len(
            missing_declared_sets
        )

    if any(_NUMBERED_NAME.search(node.name) for node in canonical_nodes):
        findings["DATASET_NUMBERED_SIBLING_NAME"] += 1
    serialized = json.dumps(
        {"tree": candidate_tree, "scenarios": candidate_scenarios},
        ensure_ascii=False,
    ).casefold()
    if any(marker in serialized for marker in _BOUNDARY_MARKERS):
        findings["DATASET_BOUNDARY_CANARY_FOUND"] += 1

    unique_facet_names = {
        facet.name
        for facets in ALLOWED_FACETS_BY_SUBJECT.values()
        for facet in facets
    }
    combination_density = (
        len(allowed_property_ids)
        / (len(ALLOWED_FACETS_BY_SUBJECT) * len(unique_facet_names))
        if ALLOWED_FACETS_BY_SUBJECT and unique_facet_names
        else 0.0
    )
    if combination_density >= 0.10:
        findings["DATASET_CARTESIAN_DENSITY_HIGH"] += 1

    return {
        "report_version": "fictional-dataset-l1-report.v1",
        "dataset_ref": DATASET_REF,
        "run_ref": RUN_REF,
        "status": "PASS" if not findings else "FAIL",
        "counts": {
            "nodes": observed_node_count,
            "scenarios": len(candidate_scenarios),
            "value_envelopes": observed_value_count,
            "concepts": sum(
                node.kind == "CONCEPT" for node in canonical_nodes
            ),
            "class_properties": len(class_owner_ids),
            "scalar_properties": len(scalar_property_ids),
            "replay_anchor_nodes": len(anchor_ids),
            "replay_scenarios": replay_count,
            "stress_only_nodes": len(filler_ids),
            "families": dict(sorted(family_counts.items())),
            "depths": {
                str(key): value
                for key, value in sorted(depth_counts.items())
            },
            "unapproved_repeated_child_vectors": sum(
                len(parent_ids) - 1
                for parent_ids in unapproved_repeated_sets
            ),
            "declared_repeated_vector_groups": len(
                repeated_parent_sets & allowed_repeated_sets
            ),
        },
        "combination_density": round(combination_density, 6),
        "finding_code_counts": dict(sorted(findings.items())),
        "blocking_count": sum(findings.values()),
    }


def build_qinglan_library_production_shape_manifest() -> dict[str, Any]:
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
            "variant_ref": "large",
            "category_id": "fictional-qinglan-library",
            "resource_id": TREE_ID,
            "version": TREE_VERSION,
            "benchmark_role": "production_shape",
            "node_count": TARGET_NODE_COUNT,
            "scenario_count": TARGET_SCENARIO_COUNT,
        },
        "synthetic_lineage": {
            "source_dataset": (
                "fictional-qinglan-library-semantic-v1"
            ),
            "anchor_contract_nodes": TARGET_ANCHOR_COUNT,
            "replay_scenarios": TARGET_REPLAY_SCENARIO_COUNT,
            "non_anchor_copy_allowed": False,
            "anchor_projection_excludes": [
                "child_node_ids",
                "order",
            ],
        },
        "frozen_semantic_inputs": {
            "record_blueprint_digest": RECORD_BLUEPRINT_DIGEST,
            "allowed_facets_digest": ALLOWED_FACETS_DIGEST,
            "allowlist_source": "PRE_GENERATION_BLUEPRINT",
        },
        "limitations": [
            "只验证完全虚构数据上的生产形状合同。",
            "不是图书馆领域 Gold，不能外推生产准确率。",
            "跨规模结论只适用于 24 个声明锚点和 4 条配对场景。",
            "stress-only filler 不参与语义准确率判断。",
        ],
    }


def build_dataset_charter_view() -> dict[str, Any]:
    return {
        "charter_version": "fictional-dataset-charter.v1",
        "dataset_ref": DATASET_REF,
        "primary_role": PRIMARY_ROLE,
        "purpose": [
            "验证 2,001 节点下的确定性构建、适配和有界候选。",
            "验证节点重排不改变声明锚点的可观察结果。",
            "检查大规模生成没有模板换词或笛卡尔积扩张。",
        ],
        "non_goals": [
            "不复现真实生产树语义、结构比例或字段。",
            "不创建 Gold、Patch 或生产准确率指标。",
            "不让 stress-only 节点承担语义结论。",
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
            "family_counts": dict(TARGET_FAMILY_COUNTS),
            "depth_counts": {
                str(key): value
                for key, value in TARGET_DEPTH_COUNTS.items()
            },
        },
        "synthetic_lineage": {
            "anchor_contract_nodes": TARGET_ANCHOR_COUNT,
            "replay_scenarios": TARGET_REPLAY_SCENARIO_COUNT,
            "non_anchor_copy_allowed": False,
        },
        "review_budget": {
            "candidate_limit": TARGET_SCENARIO_COUNT,
            "codex_pre_review_all": True,
            "human_screen_all_scenarios": True,
            "human_review_curated_nodes": 40,
            "structural_cluster_representatives": 12,
            "random_node_sample": 24,
            "random_self_recheck_scenarios": 3,
            "high_risk_self_recheck_scenarios": 4,
            "dual_review_limit": 0,
            "time_limit_minutes": 180,
        },
        "independence": {
            "generation_blind_to_legacy_fire_semantics": True,
            "legacy_similarity_audit_stage": "POST_FREEZE_ONLY",
            "audit_may_reject_but_must_not_guide_generation": True,
        },
    }


def build_semantic_blueprint_view() -> dict[str, Any]:
    return {
        "blueprint_version": (
            "qinglan-library-production-shape-blueprint.v2"
        ),
        "dataset_ref": DATASET_REF,
        "source_class": SOURCE_CLASS,
        "tree_subject_scope": "RESOURCE_SINGLETON",
        "first_level_branch_ids": [
            "ql-002",
            "ql-003",
            "ql-004",
            "ql-005",
            "ql-009",
            "qs-ops",
        ],
        "anchor_contract": {
            "source_dataset": (
                "fictional-qinglan-library-semantic-v1"
            ),
            "node_ids": list(ANCHOR_NODE_IDS),
            "projection_fields": [
                "node_id",
                "parent_node_id",
                "path_labels",
                "kind",
                "name",
                "value_type",
                "cardinality",
                "constraints",
            ],
            "excluded_fields": [
                "child_node_ids",
                "order",
            ],
        },
        "family_counts": dict(TARGET_FAMILY_COUNTS),
        "depth_counts": {
            str(key): value
            for key, value in TARGET_DEPTH_COUNTS.items()
        },
        "value_owner_contract": {
            "singleton_section_count": 1,
            "organizational_concept_direct_scalar_fields": False,
            "repeated_entity_contract": {
                "node_kind": "PROPERTY",
                "value_type": "class",
                "cardinality": "MULTIPLE",
            },
            "scalar_field_requires_declared_owner": True,
            "record_requires_declared_referent": True,
            "parent_relation_required": True,
            "scope_inherits_repeated_ancestor": True,
            "allowed_attribute_scopes": [
                "ROOT_ENTITY",
                "COLLECTION_ITEM",
                "COLLECTION_AGGREGATE",
            ],
        },
        "frozen_semantic_inputs": {
            "record_blueprint_digest": RECORD_BLUEPRINT_DIGEST,
            "allowed_facets_digest": ALLOWED_FACETS_DIGEST,
            "allowlist_source": "PRE_GENERATION_BLUEPRINT",
        },
        "record_blueprints": [
            {
                "node_id": spec.node_id,
                "parent_node_id": spec.parent_node_id,
                "name": spec.name,
                "represents": spec.represents,
                "parent_relation": spec.parent_relation,
                "entity_scope": spec.entity_scope,
                "cardinality": (
                    "MULTIPLE" if spec.multiple else "SINGLE"
                ),
                "record_profile": spec.record_profile,
                "dataset_family": spec.family,
            }
            for spec in RECORD_BLUEPRINT_BY_ID.values()
        ],
        "allowed_facets_by_subject": {
            subject_id: [
                {
                    "node_id": facet.node_id,
                    "name": facet.name,
                    "value_type": facet.value_type,
                    "cardinality": (
                        "MULTIPLE" if facet.multiple else "SINGLE"
                    ),
                    "dataset_family": facet.family,
                    "semantic_target_eligible": (
                        facet.semantic_target_eligible
                    ),
                }
                for facet in facets
            ]
            for subject_id, facets in ALLOWED_FACETS_BY_SUBJECT.items()
        },
        "construction_policy": {
            "global_cartesian_product": False,
            "numbered_sibling_names": False,
            "template_word_substitution": False,
            "undeclared_medium_tree_copy": False,
            "stress_filler_targetable": False,
            "exact_allowed_table_materialized": True,
            "allowlist_derived_from_output": False,
            "record_names_bound_to_group_before_generation": True,
            "declared_repeated_vector_parent_sets": [
                sorted(parent_ids)
                for parent_ids in ALLOWED_REPEATED_VECTOR_PARENT_SETS
            ],
            "declared_repeated_vector_purpose": (
                "保持 QP-C02 的同名异义对照"
            ),
        },
    }


def build_coverage_matrix_view() -> dict[str, Any]:
    return {
        "coverage_version": "fictional-coverage-matrix.v1",
        "dataset_ref": DATASET_REF,
        "tree_size_bucket": "LARGE_1800_2300",
        "cells": [
            {
                "scenario_ref": item["scenario_ref"],
                "primary_role": PRIMARY_ROLE,
                "primary_risk": item["primary_risk"],
                "challenge_tags": item["challenge_tags"],
                "coverage_class": (
                    "CROSS_SCALE_REPLAY"
                    if "replay_anchor" in item["challenge_tags"]
                    else "LARGE_SHAPE_COVERAGE"
                ),
                "expected_observable_category": item[
                    "proposed_observable_state"
                ]["category"],
                "replay_of": REPLAY_SCENARIO_MAP.get(
                    item["scenario_ref"]
                ),
            }
            for item in build_qinglan_library_production_shape_scenarios()
        ],
    }


def run_read_only_critic(
    *,
    preflight: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return deterministic, non-authoritative aggregate critic findings."""

    report = (
        run_qinglan_library_production_shape_preflight()
        if preflight is None
        else preflight
    )
    candidate_scenarios = (
        build_qinglan_library_production_shape_scenarios()
        if scenarios is None
        else scenarios
    )
    findings = []
    if report.get("status") != "PASS":
        findings.append(
            {
                "code": "L1_NOT_PASS",
                "severity": "blocking",
                "fictional_ref": DATASET_REF,
                "summary": "确定性门禁未通过，不能进入人工审核。",
            }
        )
    for item in candidate_scenarios:
        request = item.get("request", {})
        requirement_text = (
            request.get("requirement_text")
            if isinstance(request, dict)
            else None
        )
        if (
            isinstance(requirement_text, str)
            and any(
                name in requirement_text
                for name in _STRESS_SUBJECT_NAMES
            )
        ):
            findings.append(
                {
                    "code": "SEMANTIC_FILLER_DIRECT_REFERENCE",
                    "severity": "blocking",
                    "fictional_ref": item.get("scenario_ref"),
                    "summary": (
                        "场景直接点名 stress-only 节点，无法公平检验 filler 隔离。"
                    ),
                }
            )
    return {
        "critic_version": "fictional-dataset-critic.v1",
        "critic_authority": "NON_AUTHORITATIVE",
        "source_class": SOURCE_CLASS,
        "dataset_ref": DATASET_REF,
        "findings": findings,
        "blocking_count": sum(
            item["severity"] == "blocking" for item in findings
        ),
    }


def build_human_review_checklist() -> dict[str, Any]:
    scenario_refs = [
        item["scenario_ref"]
        for item in build_qinglan_library_production_shape_scenarios()
    ]
    curated_ids = [
        node.node_id for node in _NODES if node.family == "curated_core"
    ]
    non_curated_ids = [
        node.node_id for node in _NODES if node.family != "curated_core"
    ]
    rng = random.Random(SEED)
    record_referent_representatives = [
        next(
            spec.node_id
            for spec in _BLUEPRINT_NODE_SPECS
            if spec.parent_node_id == group.node_id
            and spec.value_type == "class"
        )
        for group in _GROUPS
    ]
    return {
        "review_contract_version": "fictional-human-review.v1",
        "dataset_ref": DATASET_REF,
        "run_ref": RUN_REF,
        "status": "PENDING",
        "time_limit_minutes": 180,
        "codex_pre_review_all": scenario_refs,
        "screen_all_scenarios": scenario_refs,
        "human_review_curated_nodes": curated_ids,
        "random_node_sample": sorted(rng.sample(non_curated_ids, 24)),
        "structural_cluster_representatives": [
            "qlp-bg-s001",
            "qlp-bg-c4-001",
            "qlp-bg-c5-001",
            "qlp-bg-f6-0001",
            "qlp-st-s001",
            "qlp-st-c4-001",
            "qlp-st-c5-001",
            "qlp-st-f6-0001",
            "qp-s001",
            "qp-s002",
            "qp-s003",
            "ql-009",
        ],
        "random_self_recheck": sorted(
            random.Random(SEED + 1).sample(scenario_refs, 3)
        ),
        "high_risk_self_recheck": [
            "QP-C02",
            "QP-C03",
            "QP-C06",
            "QP-C08",
        ],
        "codex_record_referent_review": record_referent_representatives,
        "record_referent_review_fields": [
            "represents",
            "parent_relation",
            "entity_scope",
            "declared_cardinality",
        ],
        "dual_review": [],
        "tree_scope_review_required": True,
        "tree_scope_review_contract": {
            "tree_subject_scope": "RESOURCE_SINGLETON",
            "singleton_section_node_ids": ["ql-009"],
            "allowed_decisions": [
                "CONFIRM_SCOPE",
                "REVISE_TREE",
            ],
        },
        "anchor_contract_review_required": True,
        "anchor_contract_node_ids": list(ANCHOR_NODE_IDS),
        "stop_rules": [
            "DATASET_BOUNDARY_CANARY_FOUND",
            "DATASET_ATTRIBUTE_OWNER_AMBIGUOUS",
            "DATASET_ITEM_ATTRIBUTE_ON_COLLECTION",
            "DATASET_RECORD_REFERENT_MISSING",
            "DATASET_PARENT_RELATION_UNDECLARED",
            "DATASET_SCOPE_ANCESTRY_CONFLICT",
            "DATASET_ALLOWLIST_DERIVED_FROM_OUTPUT",
            "DATASET_UNDECLARED_ANCHOR_COPY",
            "DATASET_REPEATED_VECTOR",
            "DATASET_CARTESIAN_DENSITY_HIGH",
            "TWO_MATERIAL_RANDOM_SAMPLE_ERRORS",
            "REPEATED_ERROR_ACROSS_TWO_CLUSTERS",
            "DATASET_REVIEW_BUDGET_EXCEEDED",
            "POST_FREEZE_SIMILARITY_REJECTED",
        ],
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def candidate_files() -> dict[str, Any]:
    preflight = run_qinglan_library_production_shape_preflight()
    if preflight["status"] != "PASS":
        raise RuntimeError(
            "Qinglan production-shape candidate failed deterministic preflight"
        )
    return {
        "dataset-charter.json": build_dataset_charter_view(),
        "manifest.json": build_qinglan_library_production_shape_manifest(),
        "coverage-matrix.json": build_coverage_matrix_view(),
        "semantic-blueprint.json": build_semantic_blueprint_view(),
        "tree.json": build_qinglan_library_production_shape_tree(),
        "scenarios.json": (
            build_qinglan_library_production_shape_scenarios()
        ),
        "l1-report.json": preflight,
        "l2-critic-findings.json": run_read_only_critic(
            preflight=preflight
        ),
        "human-review-checklist.json": build_human_review_checklist(),
        "promotion-checklist.json": {
            "dataset_ref": DATASET_REF,
            "run_ref": RUN_REF,
            "candidate_state": "MACHINE_VALIDATED",
            "gold_eligible": False,
            "patch_eligible": False,
            "codex_pre_reviewed": False,
            "human_screened": False,
            "human_tree_scope_reviewed": False,
            "human_anchor_contract_reviewed": False,
            "self_rechecked": False,
            "frozen": False,
            "legacy_similarity_audited": False,
            "formal_fixture_promoted": False,
            "runtime_registered": False,
        },
    }


def write_qinglan_library_production_shape_candidate(
    output_dir: str | Path,
) -> tuple[Path, ...]:
    """Write one new, non-overwriting staging candidate."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    written = []
    for filename, payload in candidate_files().items():
        path = target / filename
        path.write_bytes(_canonical_json_bytes(payload))
        written.append(path)
    return tuple(written)


__all__ = [
    "ALLOWED_FACETS_DIGEST",
    "ALLOWED_FACETS_BY_SUBJECT",
    "ALLOWED_REPEATED_VECTOR_PARENT_SETS",
    "ANCHOR_NODE_IDS",
    "DATASET_REF",
    "PRIMARY_ROLE",
    "REPLAY_SCENARIO_MAP",
    "RECORD_BLUEPRINT_BY_ID",
    "RECORD_BLUEPRINT_DIGEST",
    "RUN_REF",
    "SEED",
    "SOURCE_CLASS",
    "TARGET_ANCHOR_COUNT",
    "TARGET_DEPTH_COUNTS",
    "TARGET_FAMILY_COUNTS",
    "TARGET_NODE_COUNT",
    "TARGET_REPLAY_SCENARIO_COUNT",
    "TARGET_SCENARIO_COUNT",
    "build_coverage_matrix_view",
    "build_dataset_charter_view",
    "build_human_review_checklist",
    "build_qinglan_library_production_shape_manifest",
    "build_qinglan_library_production_shape_scenarios",
    "build_qinglan_library_production_shape_tree",
    "build_semantic_blueprint_view",
    "candidate_files",
    "run_qinglan_library_production_shape_preflight",
    "run_read_only_critic",
    "write_qinglan_library_production_shape_candidate",
]
