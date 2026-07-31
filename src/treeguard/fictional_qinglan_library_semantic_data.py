"""Deterministic clean-room Qinglan medium semantic-challenge dataset."""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from treeguard.adapter import adapt_tree_document


DATASET_REF = "fictional-qinglan-library-semantic-v1"
RUN_REF = "qinglan-library-semantic-v1-run-007"
SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
PRIMARY_ROLE = "SEMANTIC_CHALLENGE"
SEED = 20260731
TARGET_NODE_COUNT = 312
TARGET_SCENARIO_COUNT = 20
TARGET_FAMILY_COUNTS = {
    "curated_core": 72,
    "blueprint_background": 180,
    "stress_only_filler": 60,
}
TARGET_CLASS_OWNER_COUNT = 52
TARGET_SINGLETON_SECTION_COUNT = 1
TARGET_REPEATED_CLASS_OWNER_COUNT = 51
TARGET_SINGLETON_CLASS_OWNER_COUNT = 1
TARGET_LINEAGE_REFERENCE_COUNT = 24
TARGET_REPLAY_ANCHOR_COUNT = 0
TREE_ID = "qinglan-library-semantic-tree"
TREE_VERSION = "QS-1.0"
VERSION_RECORD_ID = "qinglan-library-semantic-record-v1"

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
    "REFUSE_UNBOUNDED_COMBINATION",
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
class _ConceptSpec:
    node_id: str
    label: str
    name: str
    parent_node_id: str | None
    family: str
    lineage_reference: bool = False
    semantic_role: str = "ORGANIZATIONAL_CONCEPT"


@dataclass(frozen=True, slots=True)
class _FacetTemplate:
    name: str
    value_type: str
    multiple: bool = False


@dataclass(frozen=True, slots=True)
class _SubjectSpec:
    node_id: str
    label: str
    name: str
    parent_node_id: str
    background_facets: tuple[_FacetTemplate, ...]
    lineage_reference: bool = False
    multiple: bool = True


@dataclass(frozen=True, slots=True)
class _NodeSpec:
    node_id: str
    label: str
    name: str
    parent_node_id: str | None
    kind: str
    family: str
    lineage_reference: bool = False
    semantic_target_eligible: bool = True
    value_type: str | None = None
    multiple: bool | None = None
    semantic_role: str | None = None


def _f(
    name: str,
    value_type: str = "string",
    multiple: bool = False,
) -> _FacetTemplate:
    return _FacetTemplate(name, value_type, multiple)


_ROOT_BRANCHES_GROUPS = (
    _ConceptSpec(
        "ql-001",
        "QINGLAN_COMMUNITY_LIBRARY",
        "青岚社区图书馆",
        None,
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-002",
        "COLLECTION_RESOURCES",
        "馆藏资源",
        "ql-001",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-003",
        "SERVICE_SPACES",
        "服务空间",
        "ql-001",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-004",
        "READER_SERVICES",
        "读者服务",
        "ql-001",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-005",
        "PUBLIC_PROGRAMS",
        "公共活动",
        "ql-001",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "qs-ops",
        "OPERATIONS_ACCESS_SUPPORT",
        "运营与可达保障",
        "ql-001",
        "blueprint_background",
    ),
    _ConceptSpec(
        "ql-006",
        "PRINT_MATERIALS",
        "纸本文献",
        "ql-002",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-007",
        "SERIAL_PUBLICATIONS",
        "连载刊物",
        "ql-002",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-008",
        "DIGITAL_MATERIALS",
        "数字资料",
        "ql-002",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "qs-g004",
        "THEMATIC_CATALOGS",
        "主题编目",
        "ql-002",
        "blueprint_background",
    ),
    _ConceptSpec(
        "ql-009",
        "LIBRARY_BASIC_INFORMATION",
        "本馆基本信息",
        "ql-001",
        "curated_core",
        True,
        "SINGLETON_SECTION",
    ),
    _ConceptSpec(
        "ql-012",
        "LENDING_SERVICE",
        "借阅办理",
        "ql-004",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-013",
        "SPACE_RESERVATION",
        "空间预约",
        "ql-004",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "qs-g010",
        "MEMBER_COLLABORATION",
        "成员协作",
        "ql-004",
        "blueprint_background",
    ),
    _ConceptSpec(
        "ql-015",
        "READING_CIRCLE",
        "阅读分享会",
        "ql-005",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-016",
        "CRAFT_WORKSHOP",
        "手作工作坊",
        "ql-005",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "ql-017",
        "COMMUNITY_EXHIBITION",
        "社区展览",
        "ql-005",
        "curated_core",
        True,
    ),
    _ConceptSpec(
        "qs-g014",
        "CONTINUITY_SUPPORT",
        "连续服务保障",
        "qs-ops",
        "blueprint_background",
    ),
    _ConceptSpec(
        "qs-g015",
        "ROSTER_HANDOVER",
        "排班与交接",
        "qs-ops",
        "blueprint_background",
    ),
    _ConceptSpec(
        "qs-g016",
        "ENVIRONMENT_OBSERVATION",
        "环境观察",
        "qs-ops",
        "blueprint_background",
    ),
)


_SUBJECTS = (
    _SubjectSpec(
        "ql-018",
        "PRINT_CIRCULATION_POLICY",
        "纸本文献流通政策",
        "ql-006",
        (
            _f("适用读者范围", multiple=True),
            _f("借出前置条件", multiple=True),
            _f("馆内使用例外", multiple=True),
            _f("规则复核周期", "time_code"),
        ),
        True,
        False,
    ),
    _SubjectSpec(
        "qs-s001",
        "IN_LIBRARY_REFERENCE",
        "馆内参考文献",
        "ql-006",
        (
            _f("查阅地点", multiple=True),
            _f("取用协助需求", "boolean"),
            _f("索引入口", multiple=True),
            _f("当日查阅上限", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s002",
        "LOCAL_MEMORY_BOOKS",
        "地方记忆册",
        "ql-006",
        (
            _f("收录主题", multiple=True),
            _f("年代跨度说明"),
            _f("口述资料关联", "boolean"),
            _f("整理完成度", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s003",
        "LARGE_PRINT_READING",
        "大字版读物",
        "ql-006",
        (
            _f("字号级别", multiple=True),
            _f("辅助阅读说明"),
            _f("可借阅册数", "integer"),
            _f("配套音频标记", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s004",
        "COMMUNITY_WEEKLY",
        "社区周报",
        "ql-007",
        (
            _f("出刊频率", "time_code", True),
            _f("版面数量", "integer"),
            _f("社区栏目", multiple=True),
            _f("归档保留期", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s005",
        "THEMATIC_QUARTERLY",
        "主题季刊",
        "ql-007",
        (
            _f("主题周期", "time_code"),
            _f("专栏范围", multiple=True),
            _f("合订册状态", "boolean"),
            _f("往期可查数量", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s006",
        "SERIAL_PICTURE_PAPER",
        "连续画报",
        "ql-007",
        (
            _f("连载周期", "time_code", True),
            _f("图像页数", "integer"),
            _f("适读年龄段", multiple=True),
            _f("缺期说明"),
        ),
    ),
    _SubjectSpec(
        "qs-s007",
        "ELECTRONIC_ATLAS",
        "电子图册",
        "ql-008",
        (
            _f("图像格式", multiple=True),
            _f("页面总数", "integer"),
            _f("下载许可", "boolean"),
            _f("更新日期码", "time_code"),
        ),
    ),
    _SubjectSpec(
        "qs-s008",
        "AUDIO_READING",
        "音频读物",
        "ql-008",
        (
            _f("音频时长", "integer"),
            _f("朗读语言", multiple=True),
            _f("分段数量", "integer"),
            _f("文稿同步", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s009",
        "INTERACTIVE_LEARNING_PACK",
        "交互学习包",
        "ql-008",
        (
            _f("互动模块", multiple=True),
            _f("完成预计时长", "integer"),
            _f("离线使用许可", "boolean"),
            _f("适用设备", multiple=True),
        ),
    ),
    _SubjectSpec(
        "qs-s010",
        "NATURE_OBSERVATION_THEME",
        "自然观察专题",
        "qs-g004",
        (
            _f("观察主题", multiple=True),
            _f("推荐季节", multiple=True),
            _f("图鉴关联", "boolean"),
            _f("任务卡数量", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s011",
        "URBAN_CRAFT_THEME",
        "城市手作专题",
        "qs-g004",
        (
            _f("手作方向", multiple=True),
            _f("工具难度"),
            _f("参考作品数量", "integer"),
            _f("材料替代说明", multiple=True),
        ),
    ),
    _SubjectSpec(
        "qs-s012",
        "FAMILY_READING_THEME",
        "亲子共读专题",
        "qs-g004",
        (
            _f("共读年龄段", multiple=True),
            _f("推荐时长", "integer"),
            _f("讨论问题数量", "integer"),
            _f("家庭参与提示"),
        ),
    ),
    _SubjectSpec(
        "qs-s013",
        "QUIET_READING_AREA",
        "静音阅览区",
        "ql-003",
        (
            _f("座位朝向"),
            _f("自然光时段", "time_code", True),
            _f("电源可用", "boolean"),
            _f("桌面宽度等级"),
        ),
    ),
    _SubjectSpec(
        "qs-s014",
        "LOW_LIGHT_READING_CORNER",
        "低照度阅读角",
        "qs-s013",
        (
            _f("照明级别", multiple=True),
            _f("辅助灯可用", "boolean"),
            _f("推荐停留时长", "integer"),
            _f("座位数量", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s015",
        "QUIET_LONG_TABLE",
        "安静长桌",
        "qs-s013",
        (
            _f("可用席位", "integer"),
            _f("桌面分区", multiple=True),
            _f("安静提示方式"),
            _f("插座数量", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s016",
        "COLLABORATIVE_WHITEBOARD",
        "协作白板区",
        "ql-010",
        (
            _f("白板面数", "integer"),
            _f("书写工具清单", multiple=True),
            _f("最多协作人数", "integer"),
            _f("远程投屏许可", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s017",
        "SMALL_DISCUSSION_ROOM",
        "小型讨论间",
        "ql-010",
        (
            _f("讨论席位", "integer"),
            _f("隔音等级"),
            _f("预约提前量", "integer"),
            _f("饮水许可", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s018",
        "REMOTE_COHORT_ROOM",
        "远程共学间",
        "ql-010",
        (
            _f("远程连接方式", multiple=True),
            _f("摄像设备可用", "boolean"),
            _f("同时在线人数", "integer"),
            _f("支持平台", multiple=True),
        ),
    ),
    _SubjectSpec(
        "qs-s019",
        "MOBILE_PODIUM_AREA",
        "移动讲台区",
        "ql-011",
        (
            _f("讲台移动范围"),
            _f("扩音设备可用", "boolean"),
            _f("演示接口", multiple=True),
            _f("讲者席位", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s020",
        "FLEXIBLE_SEATING_AREA",
        "可变座席区",
        "ql-011",
        (
            _f("座席布局", multiple=True),
            _f("活动容量", "integer"),
            _f("无障碍席位", "integer"),
            _f("重排准备时长", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s021",
        "WORK_DISPLAY_AREA",
        "作品展示区",
        "ql-011",
        (
            _f("展示墙长度等级"),
            _f("悬挂方式", multiple=True),
            _f("作品容量", "integer"),
            _f("照明模式", multiple=True),
        ),
    ),
    _SubjectSpec(
        "qs-s022",
        "RESERVED_PICKUP",
        "预约取书",
        "ql-012",
        (
            _f("保留时长", "integer"),
            _f("取书窗口", "time_code", True),
            _f("到馆提醒渠道", multiple=True),
            _f("超时释放", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s023",
        "RETURN_ROUTING",
        "归还分流",
        "ql-012",
        (
            _f("分流去向", multiple=True),
            _f("处理批次数", "integer"),
            _f("异常登记要求", "boolean"),
            _f("当日结清时刻", "time_code"),
        ),
    ),
    _SubjectSpec(
        "qs-s024",
        "LOAN_REMINDER",
        "借阅提醒",
        "ql-012",
        (
            _f("提醒提前量", "integer"),
            _f("提醒渠道", multiple=True),
            _f("暂停提醒", "boolean"),
        ),
    ),
    _SubjectSpec(
        "ql-020",
        "SPACE_RESERVATION_REQUEST",
        "空间预约申请",
        "ql-013",
        (
            _f("使用目的"),
            _f("申请时刻", "time_code"),
            _f("候补接受", "boolean"),
        ),
        True,
    ),
    _SubjectSpec(
        "qs-s025",
        "TEMPORARY_HOLD",
        "临时保留",
        "ql-013",
        (
            _f("保留原因", multiple=True),
            _f("释放时刻", "time_code"),
            _f("续留许可", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s026",
        "WAITLIST_ARRANGEMENT",
        "候补安排",
        "ql-013",
        (
            _f("候补顺序说明"),
            _f("通知渠道", multiple=True),
            _f("响应时限", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s027",
        "NEW_READER_GUIDANCE",
        "新读者引导",
        "qs-g010",
        (
            _f("引导步骤", multiple=True),
            _f("首次到馆提示"),
            _f("完成确认", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s028",
        "FAMILY_ACCOUNT_COLLABORATION",
        "家庭账户协作",
        "qs-g010",
        (
            _f("协作成员数", "integer"),
            _f("可见借阅记录范围"),
            _f("代办许可", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s029",
        "ACCESSIBILITY_ASSISTANCE",
        "无障碍协助",
        "qs-g010",
        (
            _f("协助方式", multiple=True),
            _f("预约需求", "boolean"),
            _f("陪同人数", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s030",
        "NEW_BOOK_DIALOGUE",
        "新书对谈",
        "ql-015",
        (
            _f("对谈主题", multiple=True),
            _f("嘉宾人数", "integer"),
            _f("报名要求", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s031",
        "THEMATIC_SHARED_READING",
        "主题共读",
        "ql-015",
        (
            _f("阅读章节", multiple=True),
            _f("讨论场次", "integer"),
            _f("主持方式"),
        ),
    ),
    _SubjectSpec(
        "qs-s032",
        "FAMILY_READ_ALOUD",
        "亲子朗读",
        "ql-015",
        (
            _f("朗读篇目", multiple=True),
            _f("陪同人数", "integer"),
            _f("录音许可", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s033",
        "PAPER_ART_PRACTICE",
        "纸艺练习",
        "ql-016",
        (
            _f("折叠技法", multiple=True),
            _f("参与材料", multiple=True),
            _f("完成时长", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s034",
        "BINDING_EXPERIENCE",
        "装帧体验",
        "ql-016",
        (
            _f("装帧方式", multiple=True),
            _f("工具套数", "integer"),
            _f("安全说明"),
        ),
    ),
    _SubjectSpec(
        "qs-s035",
        "MATERIAL_REUSE",
        "材料再造",
        "ql-016",
        (
            _f("可再用材料", multiple=True),
            _f("分类筐数", "integer"),
            _f("清洁要求", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s036",
        "RESIDENT_WORKS_EXHIBITION",
        "居民作品展",
        "ql-017",
        (
            _f("参展居民数", "integer"),
            _f("作品类别", multiple=True),
            _f("展示周期", "time_code"),
        ),
    ),
    _SubjectSpec(
        "qs-s037",
        "THEMATIC_RESOURCE_EXHIBITION",
        "主题资料展",
        "ql-017",
        (
            _f("资料主题", multiple=True),
            _f("展签数量", "integer"),
            _f("更新频率", "time_code", True),
        ),
    ),
    _SubjectSpec(
        "qs-s038",
        "MOBILE_WINDOW_EXHIBITION",
        "流动橱窗展",
        "ql-017",
        (
            _f("橱窗位置", multiple=True),
            _f("轮换周期", "time_code", True),
            _f("可见作品数", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s039",
        "ENTRANCE_ROUTE",
        "入口通行安排",
        "qs-g014",
        (
            _f("通行方向", multiple=True),
            _f("开放时段", "time_code", True),
            _f("临时绕行", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s040",
        "ASSISTED_ROUTE",
        "辅助通行方案",
        "qs-s039",
        (
            _f("辅助方式", multiple=True),
            _f("申请提前量", "integer"),
            _f("陪同许可", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s041",
        "TEMPORARY_ROUTE",
        "临时通道启用",
        "qs-s040",
        (
            _f("启用条件", multiple=True),
            _f("通道宽度等级"),
            _f("值守需求", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s042",
        "ROUTE_TIME_EXCEPTION",
        "通道时段例外",
        "qs-s041",
        (
            _f("例外日期", "time_code", True),
            _f("适用人群", multiple=True),
            _f("确认状态", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s043",
        "STAFF_ROSTER",
        "人员轮值",
        "qs-g015",
        (
            _f("轮值角色", multiple=True),
            _f("每班人数", "integer"),
            _f("换班时刻", "time_code", True),
        ),
    ),
    _SubjectSpec(
        "qs-s044",
        "SPACE_TRANSITION",
        "场地切换",
        "qs-g015",
        (
            _f("切换步骤", multiple=True),
            _f("准备时长", "integer"),
            _f("并行使用许可", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s045",
        "MATERIAL_HANDOVER",
        "物资交接",
        "qs-g015",
        (
            _f("交接物资", multiple=True),
            _f("清点数量", "integer"),
            _f("异常备注要求", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s046",
        "LIGHTING_INSPECTION",
        "照明巡查",
        "qs-g016",
        (
            _f("巡查区域", multiple=True),
            _f("巡查时段", "time_code", True),
            _f("异常灯位数", "integer"),
        ),
    ),
    _SubjectSpec(
        "qs-s047",
        "LOCAL_ILLUMINANCE_REVIEW",
        "局部照度复核",
        "qs-s046",
        (
            _f("复核位置", multiple=True),
            _f("照度等级"),
            _f("补光需求", "boolean"),
        ),
    ),
    _SubjectSpec(
        "qs-s048",
        "READING_SURFACE_OBSERVATION",
        "读写面观察",
        "qs-s047",
        (
            _f("观察桌面数量", "integer"),
            _f("反光情况", multiple=True),
            _f("调整建议状态", "boolean"),
        ),
    ),
)


_SPACE_CLASS_SUBJECTS = (
    _SubjectSpec(
        "ql-010",
        "GROUP_STUDY_ROOM",
        "小组研讨室",
        "ql-003",
        (),
        True,
    ),
    _SubjectSpec(
        "ql-011",
        "MULTIPURPOSE_HALL",
        "多用途活动厅",
        "ql-003",
        (),
        True,
    ),
)


_ALL_CLASS_SUBJECTS = _SUBJECTS + _SPACE_CLASS_SUBJECTS


_LINEAGE_PROPERTIES = (
    _NodeSpec(
        "ql-024",
        "DEFAULT_LOAN_PERMISSION",
        "默认外借许可",
        "ql-018",
        "PROPERTY",
        "curated_core",
        True,
        True,
        "boolean",
        False,
    ),
    _NodeSpec(
        "ql-029",
        "LIBRARY_NAME",
        "馆舍名称",
        "ql-009",
        "PROPERTY",
        "curated_core",
        True,
        True,
        "string",
        False,
    ),
    _NodeSpec(
        "ql-032",
        "OPEN_HOURS",
        "开放时间",
        "ql-010",
        "PROPERTY",
        "curated_core",
        True,
        True,
        "time_code",
        True,
    ),
    _NodeSpec(
        "ql-034",
        "EVENT_CAPACITY",
        "活动容量",
        "ql-011",
        "PROPERTY",
        "curated_core",
        True,
        True,
        "integer",
        False,
    ),
    _NodeSpec(
        "ql-038",
        "RESERVATION_SLOT",
        "预约时段",
        "ql-020",
        "PROPERTY",
        "curated_core",
        True,
        True,
        "time_code",
        False,
    ),
    _NodeSpec(
        "ql-039",
        "PARTICIPANT_COUNT",
        "参与人数",
        "ql-020",
        "PROPERTY",
        "curated_core",
        True,
        True,
        "integer",
        False,
    ),
)


_FILLER_NAMES = (
    "整理批次标记",
    "校对节律",
    "交接提示",
    "复核窗口",
    "维护分组",
    "观察备注",
    "轮转状态",
    "更新来源说明",
    "暂存标识",
    "归档提示",
    "清点方式",
    "核对日期码",
    "处理队列",
    "维护优先级",
    "巡查标签",
    "资料状态说明",
    "操作提示",
    "变更缘由",
    "检查节拍",
    "交接渠道",
    "准备状态",
    "使用提醒",
    "整备方式",
    "记录周期",
    "关注标记",
    "流转备注",
    "核验角色",
    "复查条件",
    "维护窗口",
    "同步提示",
    "整理策略",
    "观察频率",
    "备用说明",
    "协作备注",
    "状态来源",
    "调整时点",
    "核对范围",
    "处理节奏",
    "检查来源",
    "维护责任",
    "记录口径",
    "更新提示",
    "复核范围",
    "交接状态",
    "观察时点",
    "整理说明",
    "处理标记",
    "核验提示",
    "维护备注",
    "轮换条件",
    "同步状态",
    "准备说明",
    "复查时点",
    "关注范围",
    "调整备注",
    "巡查周期",
    "归档状态",
    "协作提示",
    "整备备注",
    "使用状态来源",
)


def _build_node_specs() -> tuple[_NodeSpec, ...]:
    nodes = [
        _NodeSpec(
            item.node_id,
            item.label,
            item.name,
            item.parent_node_id,
            "CONCEPT",
            item.family,
            item.lineage_reference,
            True,
            None,
            None,
            item.semantic_role,
        )
        for item in _ROOT_BRANCHES_GROUPS
    ]
    nodes.extend(
        _NodeSpec(
            item.node_id,
            item.label,
            item.name,
            item.parent_node_id,
            "PROPERTY",
            "curated_core",
            item.lineage_reference,
            True,
            "class",
            item.multiple,
            "COMPOSITE_RECORD",
        )
        for item in _ALL_CLASS_SUBJECTS
    )
    nodes.extend(_LINEAGE_PROPERTIES)

    background_index = 1
    filler_index = 1
    for subject_index, subject in enumerate(_SUBJECTS):
        for facet in subject.background_facets:
            nodes.append(
                _NodeSpec(
                    f"qs-b{background_index:03d}",
                    f"QS_BACKGROUND_{background_index:03d}",
                    facet.name,
                    subject.node_id,
                    "PROPERTY",
                    "blueprint_background",
                    False,
                    True,
                    facet.value_type,
                    facet.multiple,
                )
            )
            background_index += 1
        filler_names = [_FILLER_NAMES[subject_index]]
        if subject_index < 10:
            filler_names.append(_FILLER_NAMES[50 + subject_index])
        for filler_name in filler_names:
            nodes.append(
                _NodeSpec(
                    f"qs-f{filler_index:03d}",
                    f"QS_FILLER_{filler_index:03d}",
                    filler_name,
                    subject.node_id,
                    "PROPERTY",
                    "stress_only_filler",
                    False,
                    False,
                    "string",
                    False,
                )
            )
            filler_index += 1
    if background_index != 175 or filler_index != 61:
        raise AssertionError("Qinglan semantic facet plan count drifted")
    return tuple(nodes)


_NODES = _build_node_specs()
_NODE_BY_ID = {spec.node_id: spec for spec in _NODES}


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
        "QS-C01",
        "CLEAR_INTENT",
        ("clear_intent", "existing_property"),
        "在社区周报下面记录每期包含的版面数量。",
        "qs-s004",
        "PROPERTY",
        "integer",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QS-C02",
        "HOMONYM",
        ("homonym", "cross_branch"),
        "需要记录陪同人数。",
        None,
        "PROPERTY",
        "integer",
        "SINGLE",
        "NEED_CLARIFICATION",
    ),
    _scenario(
        "QS-C03",
        "CROSS_BRANCH",
        ("cross_branch", "wrong_branch"),
        "在公共活动下面记录预约取书的保留截止时刻。",
        "ql-005",
        "PROPERTY",
        "time_code",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QS-C04",
        "KIND_CONFLICT",
        ("kind_conflict",),
        "把远程共学间作为一个概念节点记录。",
        None,
        "CONCEPT",
        None,
        "UNKNOWN",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QS-C05",
        "CARDINALITY_CONFLICT",
        ("cardinality_conflict",),
        "将“纸艺练习”下的“参与材料”从可填写多个名称，改为只能填写一个名称。",
        "qs-s033",
        "PROPERTY",
        "string",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QS-C06",
        "WRONG_PARENT_HINT",
        ("wrong_parent_hint", "cross_branch"),
        "在馆藏资源下面记录低照度阅读角的照明级别。",
        "ql-002",
        "PROPERTY",
        "string",
        "MULTIPLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QS-C07",
        "NEAR_NAME_HARD_NEGATIVE",
        ("near_name_negative", "existing_property"),
        "记录预约取书允许保留的时长。",
        "qs-s022",
        "PROPERTY",
        "integer",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QS-C08",
        "INSUFFICIENT_EVIDENCE",
        ("insufficient_evidence", "judgment_requires_evidence"),
        "请判断哪类社区周报最值得长期保存并记录等级；当前没有读者反馈或保存政策。",
        "qs-s004",
        "PROPERTY",
        "string",
        "SINGLE",
        "NEED_EVIDENCE",
    ),
    _scenario(
        "QS-C09",
        "CLARIFICATION_REQUIRED",
        ("clarification_required", "multiple_targets"),
        "记录社区展览内容的更新周期。",
        "ql-005",
        "PROPERTY",
        "time_code",
        "MULTIPLE",
        "NEED_CLARIFICATION",
    ),
    _scenario(
        "QS-C10",
        "REFUSAL",
        ("refusal", "unbounded_request", "bounded_alternative_guidance"),
        "为每个馆藏、空间、服务、活动和保障节点统一添加所有已经出现的属性。",
        "ql-001",
        "UNKNOWN",
        None,
        "UNKNOWN",
        "REFUSE_UNBOUNDED_COMBINATION",
    ),
    _scenario(
        "QS-C11",
        "DUPLICATE_SUBSTRUCTURE",
        ("duplicate_substructure", "deletion_requires_evidence"),
        "低照度阅读角和安静长桌的部分属性相近，请直接删除其中一个分支。",
        "qs-s013",
        "UNKNOWN",
        None,
        "UNKNOWN",
        "NEED_EVIDENCE",
    ),
    _scenario(
        "QS-C12",
        "UNUSUAL_DEPTH",
        ("unusual_depth", "move_requires_evidence"),
        "通道时段例外位于较深层级，请直接把它移动到信息树根节点。",
        "ql-001",
        "UNKNOWN",
        None,
        "UNKNOWN",
        "NEED_EVIDENCE",
    ),
    _scenario(
        "QS-C13",
        "CARTESIAN_DENSITY",
        ("cartesian_request", "refusal"),
        "把树中所有时间属性复制到全部读者服务节点。",
        "ql-004",
        "UNKNOWN",
        None,
        "UNKNOWN",
        "REFUSE_UNBOUNDED_COMBINATION",
    ),
    _scenario(
        "QS-C14",
        "INSTANCE_FIELD_SCOPE_CLEAR",
        ("instance_boundary", "clear_intent"),
        "为每条音频读物记录其自身的音频时长。",
        "qs-s008",
        "PROPERTY",
        "integer",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QS-C15",
        "COLLECTION_AGGREGATE_SCOPE",
        ("collection_aggregate", "instance_boundary"),
        "记录全部音频读物的总时长。",
        "ql-008",
        "PROPERTY",
        "integer",
        "SINGLE",
        "NEED_CLARIFICATION",
    ),
    _scenario(
        "QS-C16",
        "POLICY_INSTANCE_SEPARATION",
        ("policy_scope", "instance_boundary"),
        "把纸本文献默认外借许可记录到每一条纸本文献记录中。",
        "ql-006",
        "PROPERTY",
        "boolean",
        "SINGLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QS-C17",
        "SINGLETON_POLICY_SCOPE",
        ("singleton_policy", "existing_property"),
        "在纸本文献流通政策中记录该类文献的默认外借许可。",
        "ql-018",
        "PROPERTY",
        "boolean",
        "SINGLE",
        "STABLE_CANDIDATE",
    ),
    _scenario(
        "QS-C18",
        "ANCESTOR_SCOPE",
        ("ancestor_scope", "category_or_instance"),
        "记录纸本文献是否允许外借。",
        "ql-006",
        "PROPERTY",
        "boolean",
        "SINGLE",
        "NEED_CLARIFICATION",
    ),
    _scenario(
        "QS-C19",
        "CONFLICTING_HINTS",
        ("conflicting_hints", "kind_conflict"),
        "把小型讨论间作为可重复记录的文本字段。",
        "ql-003",
        "CONCEPT",
        "string",
        "MULTIPLE",
        "CONFLICT_VISIBLE",
    ),
    _scenario(
        "QS-C20",
        "GRANULARITY_AMBIGUITY",
        ("granularity_ambiguity", "multiple_parents"),
        "在读者服务下面增加预约提醒。",
        "ql-004",
        "UNKNOWN",
        None,
        "UNKNOWN",
        "NEED_CLARIFICATION",
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
    parent_spec = _NODE_BY_ID.get(spec.parent_node_id)
    semantic_role = spec.semantic_role or (
        "COMPOSITE_RECORD"
        if spec.value_type == "class"
        else "SCALAR_FIELD"
    )
    if spec.kind == "CONCEPT":
        value_owner_scope = (
            "RESOURCE_SINGLETON"
            if semantic_role == "SINGLETON_SECTION"
            else "NOT_APPLICABLE"
        )
    elif spec.value_type == "class":
        value_owner_scope = (
            "REPEATED_RECORD"
            if spec.multiple
            else "SINGLETON_RECORD"
        )
    elif parent_spec is not None and parent_spec.kind == "CONCEPT":
        value_owner_scope = "PARENT_SINGLETON_SECTION"
    else:
        value_owner_scope = "PARENT_CLASS_RECORD"
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
            "lineage_role": (
                "lineage_reference"
                if spec.lineage_reference
                else "new"
            ),
            "semantic_target_eligible": spec.semantic_target_eligible,
            "semantic_role": semantic_role,
            "value_owner_scope": value_owner_scope,
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


def build_qinglan_library_semantic_tree() -> dict[str, Any]:
    """Build the 312-node clean-room medium semantic-challenge tree."""

    children = _children_by_parent()
    roots = children.get(None, ())
    if len(roots) != 1:
        raise AssertionError("Qinglan semantic blueprint requires one root")
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


def build_qinglan_library_semantic_scenarios() -> list[dict[str, Any]]:
    """Return detached scenarios in stable order."""

    return json.loads(json.dumps(_SCENARIOS, ensure_ascii=False))


def _facets_by_subject() -> dict[str, tuple[_NodeSpec, ...]]:
    facets: dict[str, list[_NodeSpec]] = defaultdict(list)
    for spec in _NODES:
        if (
            spec.kind == "PROPERTY"
            and spec.value_type != "class"
            and spec.parent_node_id is not None
        ):
            facets[spec.parent_node_id].append(spec)
    return {subject: tuple(items) for subject, items in facets.items()}


ALLOWED_FACETS_BY_SUBJECT = _facets_by_subject()


def build_qinglan_library_semantic_manifest() -> dict[str, Any]:
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
            "variant_ref": "medium",
            "category_id": "fictional-qinglan-library",
            "resource_id": TREE_ID,
            "version": TREE_VERSION,
            "benchmark_role": "semantic_challenge",
            "node_count": TARGET_NODE_COUNT,
            "scenario_count": TARGET_SCENARIO_COUNT,
        },
        "synthetic_lineage": {
            "lineage_reference_dataset": (
                "fictional-qinglan-library-control-v1"
            ),
            "lineage_reference_nodes": TARGET_LINEAGE_REFERENCE_COUNT,
            "exact_replay_anchor_nodes": TARGET_REPLAY_ANCHOR_COUNT,
            "replay_scenarios": 0,
            "lineage_references_count_as_new_coverage": False,
        },
        "limitations": [
            "只验证完全虚构数据上的中型语义挑战合同。",
            "不是图书馆领域 Gold，不能外推生产准确率。",
            "本批不声明跨规模语义重放结论。",
            "24 个 lineage references 已按新实例边界重建。",
            "stress-only filler 不参与语义准确率判断。",
        ],
    }


def build_dataset_charter_view() -> dict[str, Any]:
    return {
        "charter_version": "fictional-dataset-charter.v1",
        "dataset_ref": DATASET_REF,
        "primary_role": PRIMARY_ROLE,
        "purpose": [
            "验证中型树中的歧义、冲突、证据不足、追问和拒答。",
            "验证实例字段、集合汇总和单例政策作用域。",
            "发现生成器的模板换词、重复结构和隐式笛卡尔积。",
        ],
        "non_goals": [
            "不验证真实图书馆行业正确性。",
            "不创建 Gold、Patch 或生产准确率指标。",
            "不逼近真实生产树的字段、比例或结构。",
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
        },
        "synthetic_lineage": {
            "lineage_reference_nodes": TARGET_LINEAGE_REFERENCE_COUNT,
            "exact_replay_anchor_nodes": TARGET_REPLAY_ANCHOR_COUNT,
            "replay_scenarios": 0,
        },
        "review_budget": {
            "candidate_limit": TARGET_SCENARIO_COUNT,
            "codex_pre_review_all": True,
            "human_screen_all": True,
            "random_self_recheck": 5,
            "high_risk_self_recheck": 5,
            "dual_review_limit": 0,
            "time_limit_minutes": 150,
        },
        "independence": {
            "generation_blind_to_legacy_fire_semantics": True,
            "legacy_similarity_audit_stage": "POST_FREEZE_ONLY",
            "audit_may_reject_but_must_not_guide_generation": True,
        },
    }


def build_semantic_blueprint_view() -> dict[str, Any]:
    family_counts = Counter(spec.family for spec in _NODES)
    return {
        "blueprint_version": "qinglan-library-semantic-blueprint.v1",
        "dataset_ref": DATASET_REF,
        "source_class": SOURCE_CLASS,
        "node_families": {
            family: [
                spec.node_id for spec in _NODES if spec.family == family
            ]
            for family in TARGET_FAMILY_COUNTS
        },
        "family_counts": dict(family_counts),
        "lineage_reference_node_ids": [
            spec.node_id
            for spec in _NODES
            if spec.lineage_reference
        ],
        "first_level_branches": [
            spec.node_id
            for spec in _NODES
            if spec.parent_node_id == "ql-001"
        ],
        "structural_group_ids": [
            spec.node_id
            for spec in _ROOT_BRANCHES_GROUPS
            if spec.parent_node_id not in {None, "ql-001"}
        ],
        "subject_ids": [
            item.node_id for item in _ALL_CLASS_SUBJECTS
        ],
        "value_owner_contract": {
            "class_owner_count": TARGET_CLASS_OWNER_COUNT,
            "singleton_section_count": (
                TARGET_SINGLETON_SECTION_COUNT
            ),
            "repeated_class_owner_count": (
                TARGET_REPEATED_CLASS_OWNER_COUNT
            ),
            "singleton_class_owner_count": (
                TARGET_SINGLETON_CLASS_OWNER_COUNT
            ),
            "concept_roles": [
                "ORGANIZATIONAL_CONCEPT",
                "SINGLETON_SECTION",
            ],
            "singleton_concept_scope": "RESOURCE_SINGLETON",
            "repeated_owner_scope": "REPEATED_RECORD",
            "singleton_owner_scope": "SINGLETON_RECORD",
            "scalar_field_scope": "PARENT_CLASS_RECORD",
            "singleton_scalar_field_scope": (
                "PARENT_SINGLETON_SECTION"
            ),
            "scalar_field_requires_declared_owner": True,
        },
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
            "stress_filler_targetable": False,
            "unusual_depth_paths": 2,
            "organizational_concept_direct_scalar_fields": False,
            "singleton_section_direct_scalar_fields": True,
            "exact_replay_anchors": 0,
        },
    }


def build_coverage_matrix_view() -> dict[str, Any]:
    return {
        "coverage_version": "fictional-coverage-matrix.v1",
        "dataset_ref": DATASET_REF,
        "tree_size_bucket": "MEDIUM_300_500",
        "cells": [
            {
                "scenario_ref": item["scenario_ref"],
                "primary_role": PRIMARY_ROLE,
                "primary_risk": item["primary_risk"],
                "challenge_tags": item["challenge_tags"],
                "coverage_class": (
                    "NEW_SEMANTIC_COVERAGE"
                ),
                "expected_observable_category": item[
                    "proposed_observable_state"
                ]["category"],
            }
            for item in build_qinglan_library_semantic_scenarios()
        ],
    }


def _iter_wrappers(document: dict[str, Any]) -> Iterable[dict[str, Any]]:
    pending = list(document["map_topology"].values())
    while pending:
        wrapper = pending.pop()
        yield wrapper
        pending.extend(wrapper.get("subnodes", {}).values())


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


def run_qinglan_library_semantic_preflight(
    *,
    tree: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run aggregate-only deterministic gates."""

    candidate_tree = (
        build_qinglan_library_semantic_tree() if tree is None else tree
    )
    candidate_scenarios = (
        build_qinglan_library_semantic_scenarios()
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

    try:
        result = adapt_tree_document(candidate_tree)
    except (TypeError, ValueError):
        result = None
    if result is None or not result.is_valid or result.tree is None:
        findings["DATASET_ADAPTER_INVALID"] += 1
        canonical_nodes = ()
    else:
        canonical_nodes = result.tree.nodes
    observed_node_count = (
        0 if result is None else result.observed_node_count
    )
    observed_value_count = (
        0 if result is None else result.observed_value_count
    )
    if (
        observed_node_count != TARGET_NODE_COUNT
        or observed_value_count != 0
        or len(candidate_scenarios) != TARGET_SCENARIO_COUNT
    ):
        findings["DATASET_COUNT_MISMATCH"] += 1

    node_ids = {node.node_id for node in canonical_nodes}
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
    if len(class_owner_ids) != TARGET_CLASS_OWNER_COUNT:
        findings["DATASET_VALUE_OWNER_INVALID"] += 1

    nodes_by_id = {node.node_id: node for node in canonical_nodes}
    singleton_section_ids = {
        node.node_id
        for node in canonical_nodes
        if (
            node.kind == "CONCEPT"
            and node.extension.get("semantic_role")
            == "SINGLETON_SECTION"
        )
    }
    repeated_class_owner_ids = {
        node.node_id
        for node in canonical_nodes
        if (
            node.node_id in class_owner_ids
            and node.value_contract is not None
            and node.value_contract.cardinality == "MULTIPLE"
        )
    }
    singleton_class_owner_ids = class_owner_ids - repeated_class_owner_ids
    if (
        len(singleton_section_ids) != TARGET_SINGLETON_SECTION_COUNT
        or len(repeated_class_owner_ids)
        != TARGET_REPEATED_CLASS_OWNER_COUNT
        or len(singleton_class_owner_ids)
        != TARGET_SINGLETON_CLASS_OWNER_COUNT
    ):
        findings["DATASET_VALUE_OWNER_INVALID"] += 1

    invalid_value_owners = 0
    for node in canonical_nodes:
        semantic_role = node.extension.get("semantic_role")
        owner_scope = node.extension.get("value_owner_scope")
        if node.kind == "CONCEPT":
            if semantic_role == "ORGANIZATIONAL_CONCEPT":
                if owner_scope != "NOT_APPLICABLE":
                    invalid_value_owners += 1
                allow_direct_scalar = False
            elif semantic_role == "SINGLETON_SECTION":
                if owner_scope != "RESOURCE_SINGLETON":
                    invalid_value_owners += 1
                allow_direct_scalar = True
            else:
                invalid_value_owners += 1
                allow_direct_scalar = False
            for child_id in node.child_node_ids:
                child = nodes_by_id.get(child_id)
                if (
                    not allow_direct_scalar
                    and child is not None
                    and child.kind == "PROPERTY"
                    and child.value_contract is not None
                    and child.value_contract.value_type != "class"
                ):
                    invalid_value_owners += 1
        elif node.value_contract is not None:
            if node.value_contract.value_type == "class":
                expected_scope = (
                    "REPEATED_RECORD"
                    if node.value_contract.cardinality == "MULTIPLE"
                    else "SINGLETON_RECORD"
                )
                if (
                    semantic_role != "COMPOSITE_RECORD"
                    or owner_scope != expected_scope
                ):
                    invalid_value_owners += 1
            else:
                parent = nodes_by_id.get(node.parent_node_id)
                parent_is_class_record = (
                    parent is not None
                    and parent.kind == "PROPERTY"
                    and parent.value_contract is not None
                    and parent.value_contract.value_type == "class"
                )
                parent_is_singleton_section = (
                    parent is not None
                    and parent.kind == "CONCEPT"
                    and parent.extension.get("semantic_role")
                    == "SINGLETON_SECTION"
                )
                expected_scope = (
                    "PARENT_CLASS_RECORD"
                    if parent_is_class_record
                    else (
                        "PARENT_SINGLETON_SECTION"
                        if parent_is_singleton_section
                        else None
                    )
                )
                if (
                    semantic_role != "SCALAR_FIELD"
                    or expected_scope is None
                    or owner_scope != expected_scope
                ):
                    invalid_value_owners += 1
    if invalid_value_owners:
        findings["DATASET_VALUE_OWNER_INVALID"] += invalid_value_owners

    family_counts = Counter(
        node.extension.get("dataset_family") for node in canonical_nodes
    )
    if dict(family_counts) != TARGET_FAMILY_COUNTS:
        findings["DATASET_ROLE_MISMATCH"] += 1
    lineage_reference_count = sum(
        node.extension.get("lineage_role") == "lineage_reference"
        for node in canonical_nodes
    )
    replay_anchor_count = sum(
        node.extension.get("lineage_role") == "replay_anchor"
        for node in canonical_nodes
    )
    if (
        lineage_reference_count != TARGET_LINEAGE_REFERENCE_COUNT
        or replay_anchor_count != TARGET_REPLAY_ANCHOR_COUNT
    ):
        findings["DATASET_LINEAGE_INVALID"] += 1

    filler_ids = {
        node.node_id
        for node in canonical_nodes
        if node.extension.get("dataset_family")
        == "stress_only_filler"
    }
    scenario_refs = [item.get("scenario_ref") for item in candidate_scenarios]
    risks = [item.get("primary_risk") for item in candidate_scenarios]
    if (
        len(scenario_refs) != len(set(scenario_refs))
        or len(risks) != len(set(risks))
        or any(not isinstance(ref, str) or not ref for ref in scenario_refs)
    ):
        findings["DATASET_SCENARIO_COVERAGE_DUPLICATE"] += 1

    replay_scenario_count = 0
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
        elif "replay_anchor" in tags:
            replay_scenario_count += 1
    if replay_scenario_count != 0:
        findings["DATASET_LINEAGE_INVALID"] += 1

    if any(_NUMBERED_NAME.search(node.name) for node in canonical_nodes):
        findings["DATASET_NUMBERED_SIBLING_NAME"] += 1
    serialized = json.dumps(
        {"tree": candidate_tree, "scenarios": candidate_scenarios},
        ensure_ascii=False,
    ).casefold()
    if any(marker in serialized for marker in _BOUNDARY_MARKERS):
        findings["DATASET_BOUNDARY_CANARY_FOUND"] += 1

    depths = _depth_by_node_id(canonical_nodes) if canonical_nodes else {}
    depth_counts = Counter(depths.values())
    if not depths or max(depths.values()) != 7:
        findings["DATASET_DEPTH_PLAN_INVALID"] += 1
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
            "singleton_section_concepts": len(singleton_section_ids),
            "repeated_class_records": len(repeated_class_owner_ids),
            "singleton_class_records": len(singleton_class_owner_ids),
            "lineage_reference_nodes": lineage_reference_count,
            "replay_anchor_nodes": replay_anchor_count,
            "replay_scenarios": replay_scenario_count,
            "families": dict(sorted(family_counts.items())),
            "depths": {
                str(key): value
                for key, value in sorted(depth_counts.items())
            },
        },
        "combination_density": round(combination_density, 6),
        "finding_code_counts": dict(sorted(findings.items())),
        "blocking_count": sum(findings.values()),
    }


def run_read_only_critic(
    *,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic, non-authoritative aggregate critic findings."""

    report = (
        run_qinglan_library_semantic_preflight()
        if preflight is None
        else preflight
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
    refs = [item["scenario_ref"] for item in _SCENARIOS]
    random_sample = sorted(random.Random(SEED).sample(refs, 5))
    return {
        "review_contract_version": "fictional-human-review.v1",
        "dataset_ref": DATASET_REF,
        "run_ref": RUN_REF,
        "status": "PENDING",
        "time_limit_minutes": 150,
        "codex_pre_review_all": refs,
        "screen_all": refs,
        "random_self_recheck": random_sample,
        "high_risk_self_recheck": [
            "QS-C08",
            "QS-C10",
            "QS-C12",
            "QS-C13",
            "QS-C16",
        ],
        "dual_review": [],
        "tree_scope_review_required": True,
        "tree_scope_review_contract": {
            "singleton_section_node_ids": ["ql-009"],
            "repeated_space_record_node_ids": [
                "qs-s013",
                "ql-010",
                "ql-011",
            ],
            "allowed_decisions": [
                "CONFIRM_SCOPE",
                "REVISE_TREE",
            ],
        },
        "stop_rules": [
            "DATASET_BOUNDARY_CANARY_FOUND",
            "DATASET_ORACLE_OVERCLAIM",
            "TWO_MATERIAL_RANDOM_SAMPLE_ERRORS",
            "REPEATED_ERROR_ACROSS_TWO_CLUSTERS",
            "DATASET_REVIEW_BUDGET_EXCEEDED",
            "DATASET_CARTESIAN_DENSITY_HIGH",
            "DATASET_FILLER_TARGETED",
            "POST_FREEZE_SIMILARITY_REJECTED",
        ],
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def candidate_files() -> dict[str, Any]:
    preflight = run_qinglan_library_semantic_preflight()
    if preflight["status"] != "PASS":
        raise RuntimeError(
            "Qinglan semantic candidate failed deterministic preflight"
        )
    return {
        "dataset-charter.json": build_dataset_charter_view(),
        "manifest.json": build_qinglan_library_semantic_manifest(),
        "coverage-matrix.json": build_coverage_matrix_view(),
        "semantic-blueprint.json": build_semantic_blueprint_view(),
        "tree.json": build_qinglan_library_semantic_tree(),
        "scenarios.json": build_qinglan_library_semantic_scenarios(),
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
            "self_rechecked": False,
            "frozen": False,
            "legacy_similarity_audited": False,
            "formal_fixture_promoted": False,
            "runtime_registered": False,
        },
    }


def write_qinglan_library_semantic_candidate(
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
    "ALLOWED_FACETS_BY_SUBJECT",
    "DATASET_REF",
    "PRIMARY_ROLE",
    "RUN_REF",
    "SEED",
    "SOURCE_CLASS",
    "TARGET_CLASS_OWNER_COUNT",
    "TARGET_FAMILY_COUNTS",
    "TARGET_LINEAGE_REFERENCE_COUNT",
    "TARGET_NODE_COUNT",
    "TARGET_REPLAY_ANCHOR_COUNT",
    "TARGET_SCENARIO_COUNT",
    "build_coverage_matrix_view",
    "build_dataset_charter_view",
    "build_human_review_checklist",
    "build_qinglan_library_semantic_manifest",
    "build_qinglan_library_semantic_scenarios",
    "build_qinglan_library_semantic_tree",
    "build_semantic_blueprint_view",
    "candidate_files",
    "run_qinglan_library_semantic_preflight",
    "run_read_only_critic",
    "write_qinglan_library_semantic_candidate",
]
