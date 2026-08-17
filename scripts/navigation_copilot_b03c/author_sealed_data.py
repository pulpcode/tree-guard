from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from treeguard.adapter import adapt_tree_document
from treeguard.navigation_copilot_sealed_validation import SealedScenario


DATASET_REF = "navigation-copilot-sealed-v3c-b03-maker-lab-c"
BATCH_REF = "NAVCOP_SEALED_V3C_B03_20260817_C"
DOMAIN_REF = "FICTIONAL_MAKER_LAB_OPERATIONS"
NAMESPACE = "urn:treeguard:fictional:navigation-copilot:b03:maker-lab:v1"
TREE_SEED = 2026081743
SELECTION_SEED = 2026081789
FUNCTION_COMMIT = "40098afe985dfc81183c928a473a2e8a3c2176dc"
BLUEPRINT_SCHEMA = "treeguard.navigation-copilot-b03c-blueprint.v1"
PACKET_SCHEMA = "treeguard.navigation-copilot-b03c-sealed-review-packet.v1"

CATEGORY_ORDER = (
    "LITERAL_UNIQUE",
    "NONLITERAL_UNIQUE",
    "STRUCTURAL_INTERFERENCE",
    "MULTI_ACCEPTABLE",
    "CLARIFICATION",
    "WEAK_EVIDENCE",
    "TARGET_ABSENT",
)
CANDIDATE_QUOTAS = {
    "LITERAL_UNIQUE": 11,
    "NONLITERAL_UNIQUE": 12,
    "STRUCTURAL_INTERFERENCE": 10,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 7,
    "WEAK_EVIDENCE": 5,
    "TARGET_ABSENT": 7,
}
FINAL_QUOTAS = {
    "LITERAL_UNIQUE": 10,
    "NONLITERAL_UNIQUE": 10,
    "STRUCTURAL_INTERFERENCE": 8,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 6,
    "WEAK_EVIDENCE": 4,
    "TARGET_ABSENT": 6,
}

BRANCHES: tuple[dict[str, Any], ...] = (
    {
        "key": "project",
        "label": "项目登记",
        "quota": (81, 18, 50, 13),
        "groups": (
            ("项目基本资料", ("项目名称", "项目摘要", "发起目的", "预计周期")),
            ("项目成员安排", ("发起人", "协作成员", "联络方式")),
            ("项目资源说明", ("计划工位", "计划工具", "材料范围")),
            ("项目审核进度", ("提交状态", "审核意见", "完成条件")),
        ),
        "subjects": (
            "概念草案", "协作名单", "资源估算", "阶段目标", "成果边界", "时间计划",
            "风险备注", "审核记录", "联络安排", "工作说明", "资料附件", "参与邀请",
            "变更请求", "优先顺序", "依赖事项", "完成条件", "准备清单", "归档条目",
        ),
    },
    {
        "key": "workstation",
        "label": "工位预约",
        "quota": (87, 19, 54, 14),
        "groups": (
            ("工位预约对象", ("激光切割台预约", "三维打印台预约", "木工台预约", "电子焊接台预约")),
            ("工位预约时段", ("开始时段", "结束时段", "预计占用时长")),
            ("工位使用资格", ("准入状态", "培训确认", "陪同要求")),
            ("工位预约变更", ("预约取消", "预约改期", "超时释放", "冲突处理")),
        ),
        "subjects": (
            "激光台时段", "打印台时段", "木工台时段", "焊接台时段", "临时工位",
            "共享工位", "培训工位", "演示工位", "静音工位", "组装工位", "调试工位",
            "清洁工位", "摄影工位", "测量工位", "包装工位", "备用工位", "排队席位", "候补时段",
        ),
    },
    {
        "key": "tools",
        "label": "工具借还",
        "quota": (92, 20, 57, 15),
        "groups": (
            ("工具借用对象", ("手持钻借用", "热风枪借用", "万用表借用", "雕刻刀借用")),
            ("工具借出登记", ("借出时间", "预计归还", "领用确认", "配件清单")),
            ("工具归还登记", ("实际归还", "完好状态", "缺件说明", "清洁确认")),
            ("工具异常处理", ("逾期处理", "损坏报告", "遗失报告")),
        ),
        "subjects": (
            "手钻箱", "热风枪盒", "万用表包", "雕刻刀套", "扳手组", "夹具架", "测量尺盒",
            "螺丝刀组", "钳具盒", "锉刀架", "焊台附件", "切割垫", "压板套件", "清洁刷组",
            "备用电池", "防护罩件", "借用凭条", "归还清单",
        ),
    },
    {
        "key": "materials",
        "label": "材料管理",
        "quota": (86, 19, 53, 14),
        "groups": (
            ("材料分类登记", ("板材登记", "线材登记", "涂料登记", "紧固件登记")),
            ("材料库存管理", ("当前余量", "安全余量", "补充申请")),
            ("材料领用登记", ("领用数量", "用途说明", "领用人")),
            ("剩余材料处理", ("剩余材料", "回收分类", "存放位置", "处置状态")),
        ),
        "subjects": (
            "薄木板", "透明板", "软木片", "铜线卷", "彩色线束", "水性涂料", "固定螺钉",
            "连接螺母", "泡棉片", "纸板张", "布料卷", "胶条盒", "砂纸包", "扎带袋",
            "磁片组", "模型泥", "清洁布", "包装膜",
        ),
    },
    {
        "key": "maintenance",
        "label": "设备维护",
        "quota": (96, 21, 59, 16),
        "groups": (
            ("设备维护对象", ("激光切割机维护", "三维打印机维护", "排风设备维护", "焊接设备维护")),
            ("设备维护计划", ("维护周期", "下次维护", "责任人员", "停机窗口")),
            ("设备维护执行", ("检查清单", "更换部件", "校准记录", "完成时间")),
            ("设备故障处置", ("故障现象", "影响范围", "临时措施", "恢复状态")),
        ),
        "subjects": (
            "激光镜片", "打印喷头", "排风滤网", "焊台烙铁", "运动导轨", "平台底板",
            "急停按钮", "电源模块", "温控探头", "冷却回路", "照明组件", "控制面板",
            "门锁开关", "接地线路", "传动皮带", "除尘管路", "校准治具", "维修工单",
        ),
    },
    {
        "key": "sample",
        "label": "样件处理",
        "quota": (88, 19, 55, 14),
        "groups": (
            ("样件身份登记", ("样件名称", "关联项目", "制作批次")),
            ("样件加工状态", ("待加工", "加工中", "待检验", "已完成")),
            ("样件存放管理", ("临时存放位", "保留期限", "认领方式")),
            ("样件后续处置", ("返工要求", "报废申请", "移交准备", "照片记录")),
        ),
        "subjects": (
            "结构样件", "外观样件", "装配样件", "测试样件", "展示样件", "尺寸样件",
            "材料试片", "连接试件", "功能模型", "纸面模型", "打印模型", "切割模型",
            "焊接试件", "涂装试片", "包装样稿", "返工样件", "待领样件", "留存样件",
        ),
    },
    {
        "key": "safety",
        "label": "安全检查",
        "quota": (101, 22, 62, 17),
        "groups": (
            ("安全检查范围", ("消防通道检查", "护罩检查", "电源检查", "通风检查", "急停检查")),
            ("个人防护确认", ("护目镜确认", "手套确认", "耳罩确认", "口罩确认")),
            ("作业风险识别", ("高温风险", "粉尘风险", "锐器风险", "用电风险")),
            ("安全事件报告", ("漏液报告", "异响报告", "冒烟报告", "紧急停机")),
        ),
        "subjects": (
            "入口通道", "疏散出口", "设备护罩", "主电源箱", "局部排风", "急停回路",
            "护目镜架", "防护手套", "听力护具", "防尘口罩", "高温区域", "粉尘区域",
            "锐器存放", "用电区域", "漏液点位", "异响点位", "冒烟点位", "停机记录",
        ),
    },
    {
        "key": "handoff",
        "label": "成果交接",
        "quota": (104, 21, 66, 17),
        "groups": (
            ("成果基本资料", ("成果名称", "关联成果项目", "版本说明", "完成摘要")),
            ("成果接收安排", ("接收人员", "接收方式", "约定时间", "确认状态")),
            ("成果附件说明", ("图纸清单", "参数说明", "检验记录", "使用说明")),
            ("成果收尾事项", ("工位归还", "工具归还", "余料交接", "未结事项")),
        ),
        "subjects": (
            "结构成果", "电子成果", "打印成果", "切割成果", "装配成果", "展示成果",
            "测试成果", "图纸附件", "参数附件", "检验附件", "使用附件", "包装附件",
            "接收清单", "交接凭条", "版本记录", "完成记录", "收尾清单", "遗留说明",
        ),
    },
)

FACETS = (
    "填写状态", "更新时间", "确认方式", "责任角色", "说明文本", "有效期限", "来源备注",
    "版本标记", "检查结果", "补充要求", "关联说明", "排序依据", "可见范围", "处理进度",
    "异常备注", "归档方式",
)
FILLER_TOKENS = (
    "晨星", "暮云", "青杉", "白桦", "赤陶", "蓝砂", "银线", "金叶", "墨石",
    "晴岚", "远帆", "静湖", "流萤", "新月", "微雨", "长风", "浅湾", "松影",
)

ALIASES_BY_LABEL = {
    "三维打印台预约": ("3D打印台预约",),
    "激光切割机维护": ("激切机维护",),
    "万用表借用": ("万表借用",),
    "维护周期": ("保养周期", "修护周期"),
    "下次维护": ("下次保养",),
    "材料范围": ("要用的材料",),
    "接收人员": ("接收人",),
    "护目镜确认": ("护目镜检查",),
    "存放位置": ("剩料位置",),
    "结束时段": ("腾出工位时间",),
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _slug(prefix: str, position: int) -> str:
    return f"{prefix.upper()}_{position:03d}"


def _node(
    *, node_id: str, parent_id: str | None, label: str, token: str, route: str,
    order: int, node_type: str, role: str, branch_key: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "node_id": node_id,
        "node_type": node_type,
        "node_name": label,
        "node_label": token,
        "node_label_route": route,
        "node_order": order,
        "extension": {
            "dataset_role": role,
            "branch_key": branch_key,
            "aliases": list(ALIASES_BY_LABEL.get(label, ())),
        },
        "remark": "完全虚构的创作工坊验证节点",
    }
    if parent_id is not None:
        metadata["parent_node_id"] = parent_id
    if node_type == "property":
        metadata.update({"value_type": "string", "is_list": False, "value_constraints": {"raw_constraints": {}}})
    return {"metadata": metadata}


def _background_pairs(subjects: tuple[str, ...], count: int) -> list[tuple[str, str]]:
    allowed: list[tuple[str, str]] = []
    offsets = (0, 3, 7, 11)
    for index, subject in enumerate(subjects):
        for offset in offsets:
            allowed.append((subject, FACETS[(index + offset) % len(FACETS)]))
    if len(allowed) < count:
        raise AssertionError("background compatibility plan is too small")
    return allowed[:count]


def build_tree_and_blueprint() -> tuple[dict[str, Any], dict[str, Any]]:
    next_id = 500001
    root_id = f"N{next_id:06d}"
    next_id += 1
    root = _node(
        node_id=root_id, parent_id=None, label="虚构创作工坊运营", token="MAKER_LAB_ROOT",
        route="MAKER_LAB_ROOT", order=1, node_type="concept", role="curated", branch_key="root",
    )
    root["subnodes"] = {}
    blueprint_branches = []
    for branch_index, branch in enumerate(BRANCHES, 1):
        total, curated_quota, background_quota, filler_quota = branch["quota"]
        branch_id = f"N{next_id:06d}"
        next_id += 1
        branch_token = f"BRANCH_{branch['key'].upper()}"
        branch_entry = _node(
            node_id=branch_id, parent_id=root_id, label=branch["label"], token=branch_token,
            route=f"MAKER_LAB_ROOT/-/{branch_token}", order=branch_index,
            node_type="concept", role="curated", branch_key=branch["key"],
        )
        branch_entry["subnodes"] = {}
        group_entries: list[dict[str, Any]] = []
        curated_labels: list[str] = []
        for group_index, (group_label, leaves) in enumerate(branch["groups"], 1):
            group_id = f"N{next_id:06d}"
            next_id += 1
            group_token = f"{branch['key'].upper()}_GROUP_{group_index:02d}"
            group_entry = _node(
                node_id=group_id, parent_id=branch_id, label=group_label, token=group_token,
                route=f"MAKER_LAB_ROOT/-/{branch_token}/-/{group_token}", order=group_index,
                node_type="concept", role="curated", branch_key=branch["key"],
            )
            group_entry["subnodes"] = {}
            for leaf_index, leaf_label in enumerate(leaves, 1):
                leaf_id = f"N{next_id:06d}"
                next_id += 1
                leaf_token = f"{branch['key'].upper()}_CURATED_{len(curated_labels) + 1:03d}"
                group_entry["subnodes"][leaf_token] = _node(
                    node_id=leaf_id, parent_id=group_id, label=leaf_label, token=leaf_token,
                    route=f"MAKER_LAB_ROOT/-/{branch_token}/-/{group_token}/-/{leaf_token}",
                    order=leaf_index, node_type="property", role="curated", branch_key=branch["key"],
                )
                curated_labels.append(leaf_label)
            branch_entry["subnodes"][group_token] = group_entry
            group_entries.append(group_entry)
        if 1 + len(group_entries) + len(curated_labels) != curated_quota:
            raise AssertionError(f"curated quota mismatch for {branch['key']}")

        allowed_pairs = _background_pairs(branch["subjects"], background_quota)
        for background_index, (subject, facet) in enumerate(allowed_pairs, 1):
            group_entry = group_entries[(background_index - 1) % len(group_entries)]
            group_token = group_entry["metadata"]["node_label"]
            label = f"{subject}{facet}"
            token = f"{branch['key'].upper()}_BACKGROUND_{background_index:03d}"
            node_id = f"N{next_id:06d}"
            next_id += 1
            group_entry["subnodes"][token] = _node(
                node_id=node_id, parent_id=group_entry["metadata"]["node_id"], label=label,
                token=token, route=f"MAKER_LAB_ROOT/-/{branch_token}/-/{group_token}/-/{token}",
                order=100 + background_index, node_type="property", role="background",
                branch_key=branch["key"],
            )
        for filler_index in range(filler_quota):
            label = f"{branch['label']}压力检索锚点·{FILLER_TOKENS[filler_index]}"
            token = f"{branch['key'].upper()}_FILLER_{filler_index + 1:03d}"
            node_id = f"N{next_id:06d}"
            next_id += 1
            branch_entry["subnodes"][token] = _node(
                node_id=node_id, parent_id=branch_id, label=label, token=token,
                route=f"MAKER_LAB_ROOT/-/{branch_token}/-/{token}", order=500 + filler_index,
                node_type="property", role="filler", branch_key=branch["key"],
            )
        built_total = curated_quota + background_quota + filler_quota
        if built_total != total:
            raise AssertionError(f"branch quota mismatch for {branch['key']}")
        root["subnodes"][branch_token] = branch_entry
        blueprint_branches.append(
            {
                "branch_key": branch["key"],
                "label": branch["label"],
                "total": total,
                "curated": curated_quota,
                "background": background_quota,
                "filler": filler_quota,
                "curated_groups": [group[0] for group in branch["groups"]],
                "curated_group_items": [
                    {"group": group_label, "leaves": list(leaves)}
                    for group_label, leaves in branch["groups"]
                ],
                "background_subjects": list(branch["subjects"]),
                "allowed_pair_count": len(branch["subjects"]) * 4,
                "background_pair_count": background_quota,
            }
        )
    if next_id != 500737:
        raise AssertionError("tree must contain exactly 736 nodes")
    tree = {
        "metadata": {
            "id": "fictional-maker-lab-c-record",
            "map_id": DATASET_REF,
            "map_type": "resource",
            "map_name": "虚构创作工坊运营信息树",
            "version": "B03C-C1-PHASE2A-V1",
            "category_id": "fictional-maker-lab-category",
            "concurrent_version": 1,
        },
        "map_topology": {"MAKER_LAB_ROOT": root},
    }
    blueprint = {
        "schema_version": BLUEPRINT_SCHEMA,
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "domain_ref": DOMAIN_REF,
        "namespace": NAMESPACE,
        "tree_seed": TREE_SEED,
        "selection_seed": SELECTION_SEED,
        "function_commit": FUNCTION_COMMIT,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "target": {"nodes": 736, "curated": 160, "background": 456, "filler": 120, "value_envelope_count": 0},
        "branches": blueprint_branches,
        "background_pairing": {"facet_count": len(FACETS), "offsets": [0, 3, 7, 11]},
        "filler_policy": "STRESS_ONLY_NOT_TARGETABLE",
    }
    return tree, blueprint


SCENARIO_GROUPS: dict[str, tuple[tuple[Any, ...], ...]] = {
    "LITERAL_UNIQUE": (
        ("新增项目名称字段", "安全事件报告"), ("记录工位预约取消", None),
        ("登记工具实际归还时间", "项目基本资料"), ("补充材料当前余量", None),
        ("记录设备维护完成时间", None), ("登记样件保留期限", None),
        ("增加消防通道检查项", None), ("填写成果版本说明", None),
        ("登记万用表借用", None), ("记录项目审核意见", None),
        ("填写余料存放位置", None),
    ),
    "NONLITERAL_UNIQUE": (
        ("给3D打印台加预约入口", "材料分类登记"), ("登记激切机的维护安排", None),
        ("记录工位预悦取消", None), ("工具实际归坏时间要记录", "成果附件说明"),
        ("登记设备修护周期", None), ("激光切割机什么时候再保养", None),
        ("项目要用哪些材料", None), ("成品交给谁", None),
        ("增加万表借用入口", None), ("检查护目境是否佩戴", None),
        ("剩料放哪儿", None), ("什么时候把台子腾出来", None),
    ),
    "STRUCTURAL_INTERFERENCE": (
        ("记录项目完成条件", "个人防护确认"), ("记录设备恢复状态", None),
        ("登记样件关联项目", "工位预约时段"), ("填写材料用途说明", None),
        ("记录维护责任人员", None), ("登记成果确认状态", None),
        ("报告设备异响", None), ("登记工具完好状态", None),
        ("记录项目预计周期", None), ("填写交接未结事项", None),
    ),
    "MULTI_ACCEPTABLE": (
        ("列出所有工位预约入口", None), ("列出所有设备维护对象", None),
        ("列出全部安全检查范围", None), ("列出成果交接的附件项目", None),
    ),
    "CLARIFICATION": (
        ("我要预约工位", "安全事件报告", "我要预约三维打印台。"),
        ("我要借工具", None, "我要借万用表。"),
        ("我要登记材料", None, "我要登记涂料。"),
        ("我要报告安全问题", None, "设备正在冒烟。"),
        ("我要处理样件", None, "这个样件需要报废。"),
        ("我要归还东西", None, "借来的工具已经归还。"),
        ("我要登记完成情况", None, "填写成果交接的完成摘要。"),
    ),
    "WEAK_EVIDENCE": (
        ("这个安排不合适，帮我加个字段", "工具借用对象"),
        ("设备好像有问题", None), ("材料需要处理一下", None),
        ("样件状态不对", None), ("交接还没弄完", None),
    ),
    "TARGET_ABSENT": (
        ("新增陶艺窑炉预约", None), ("登记玻璃吹制炉温度", None),
        ("增加织布机经线密度", None), ("记录暗房显影液浓度", None),
        ("增加水刀切割压力", None), ("登记喷漆房湿度", None),
        ("新增金工车床转速", None),
    ),
}


def _raw_label_index(tree: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    stack = list(tree["map_topology"].values())
    while stack:
        entry = stack.pop()
        metadata = entry["metadata"]
        result[metadata["node_name"]] = metadata["node_id"]
        stack.extend(entry.get("subnodes", {}).values())
    return result


def build_candidates(tree: dict[str, Any]) -> list[dict[str, Any]]:
    imported = adapt_tree_document(tree)
    if not imported.is_valid or imported.tree is None:
        raise RuntimeError("DATASET_REFERENCE_INVALID")
    label_index = _raw_label_index(tree)
    candidates: list[dict[str, Any]] = []
    sequence = 1
    for category in CATEGORY_ORDER:
        rows = SCENARIO_GROUPS[category]
        if len(rows) != CANDIDATE_QUOTAS[category]:
            raise AssertionError(f"candidate quota mismatch: {category}")
        for category_index, row in enumerate(rows):
            requirement_text = row[0]
            wrong_parent_label = row[1]
            clarification_answer = row[2] if category == "CLARIFICATION" else None
            repeat = category in {"NONLITERAL_UNIQUE", "STRUCTURAL_INTERFERENCE", "CLARIFICATION", "WEAK_EVIDENCE"} and category_index < 4
            proposed_parent_ref = label_index[wrong_parent_label] if wrong_parent_label else None
            scenario = SealedScenario.create(
                scenario_ref=f"b03c:{sequence:03d}",
                tree_digest=imported.tree.snapshot_hash,
                category=category,
                requirement_text=requirement_text,
                proposed_parent_ref=proposed_parent_ref,
                node_kind_hint="UNKNOWN" if category in {"CLARIFICATION", "WEAK_EVIDENCE"} else "PROPERTY",
                value_type_hint=None if category in {"CLARIFICATION", "WEAK_EVIDENCE"} else "string",
                cardinality_hint="MULTIPLE" if category == "MULTI_ACCEPTABLE" else ("UNKNOWN" if category in {"CLARIFICATION", "WEAK_EVIDENCE"} else "SINGLE"),
                frozen_clarification_answer=clarification_answer,
                wrong_context_challenge=wrong_parent_label is not None,
                repeat_challenge=repeat,
            )
            candidates.append(scenario.to_dict())
            sequence += 1
    if sequence != 57:
        raise AssertionError("candidate count must be 56")
    return candidates


def build_review_packet(tree_bytes: bytes, candidate_bytes: bytes, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": PACKET_SCHEMA,
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "source_tree_sha256": _sha256(tree_bytes),
        "source_candidates_sha256": _sha256(candidate_bytes),
        "producer_module": "author_sealed_data",
        "items": [{"scenario_ref": item["scenario_ref"], "review_state": "PENDING"} for item in candidates],
    }


def materialize(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tree, blueprint = build_tree_and_blueprint()
    candidates = build_candidates(tree)
    blueprint_bytes = _json_bytes(blueprint)
    tree_bytes = _json_bytes(tree)
    candidate_bytes = _json_bytes(candidates)
    packet_bytes = _json_bytes(build_review_packet(tree_bytes, candidate_bytes, candidates))
    contents = {
        "blueprint.v1.json": blueprint_bytes,
        "tree.json": tree_bytes,
        "candidate-scenarios.v2.json": candidate_bytes,
        "review-packet.v1.json": packet_bytes,
    }
    for name, content in contents.items():
        path = output_dir / name
        if path.exists() and path.read_bytes() != content:
            raise RuntimeError("DATASET_NONDETERMINISTIC")
        if not path.exists():
            path.write_bytes(content)
    return {name: _sha256(content) for name, content in contents.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.output_dir)
    print("B03C_PHASE2A_AUTHORED nodes=736 candidates=56 oracle=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
