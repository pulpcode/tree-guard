#!/usr/bin/env python3
"""Create the second independent public R2 clean-room tree and manifest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


BASELINE = "03faee0a7a33e0ee413a4d91b70e8f577085751f"
DATASET = "fire-r2-sealed-confirmation-cleanroom-2-v1"
TREE_FILE = Path(
    "tests/fixtures/fictional/fire_r2_sealed_confirmation_cleanroom_2/tree.v1.json"
)
MANIFEST_FILE = Path(
    "tests/fixtures/fictional/fire_r2_sealed_confirmation_cleanroom_2/manifest.v1.json"
)

DISTRICTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("绯湾船坞区", ("潮砾装配厅", "岬灯检修棚", "珊桥物料库", "浪纹调度屋")),
    ("苍苔算力区", ("苔芯机房", "雾栈运维厅", "竹环换热屋", "云脉配线室")),
    ("琥珀展贸区", ("蜜珀会展馆", "橙弦路演厅", "砂糖备展库", "霞幕接待屋")),
    ("靛羽研修区", ("蓝羽讲习馆", "墨帆实训厅", "靛星器材库", "青穹演练屋")),
    ("银杏仓配区", ("金叶分拨厅", "霜籽冷藏库", "麦纹装卸棚", "榆轮调度站")),
    ("紫萝文创区", ("藤影排练馆", "紫砂制作坊", "花信展藏库", "萝月观众厅")),
    ("金穗康养区", ("穗光照护馆", "杏雨康复厅", "禾风膳食屋", "麦舟后勤站")),
    ("玄石制造区", ("黑曜铸造厅", "岩芯动力房", "砾环备件库", "玄梭调试屋")),
)

CAPABILITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "征兆研判链",
        ("感烟判定阈阶", "热迹复核间隔", "警情升级路径", "误报抑制策略"),
    ),
    (
        "人群转移链",
        ("引导光带续航", "转移路线版本", "集合区容量档", "辅助播报方式"),
    ),
    (
        "保障介质链",
        ("供水接驳级别", "储液保障档位", "阀组轮检间隔", "替代介质方案"),
    ),
)


def _json_bytes(value: Any) -> bytes:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{text}\n".encode("utf-8")


def _property_type(label: str) -> str:
    if any(word in label for word in ("间隔", "续航", "容量")):
        return "integer"
    return "string"


def build_tree() -> dict[str, Any]:
    serial = 0

    def new_id() -> str:
        nonlocal serial
        serial += 1
        return f"c2-fire-{serial:06d}"

    def concept(label: str, parent: str | None, route: tuple[str, ...], order: int):
        node_id = new_id()
        labels = route + (label,)
        return node_id, {
            "metadata": {
                "extension": {"cleanroom_source": DATASET},
                "node_id": node_id,
                "node_label": label,
                "node_label_route": "/-/".join(labels),
                "node_name": label,
                "node_order": order,
                "node_type": "concept",
                "parent_node_id": parent,
            },
            "subnodes": {},
        }

    def scalar(label: str, parent: str, route: tuple[str, ...], order: int):
        node_id = new_id()
        labels = route + (label,)
        return {
            "metadata": {
                "extension": {"cleanroom_source": DATASET},
                "is_list": False,
                "node_id": node_id,
                "node_label": label,
                "node_label_route": "/-/".join(labels),
                "node_name": label,
                "node_order": order,
                "node_type": "property",
                "parent_node_id": parent,
                "value_constraints": {},
                "value_placeholder": None,
                "value_type": _property_type(label),
            },
            "subnodes": {},
        }

    root_label = "澜烬群岛应急治理图"
    root_id, root = concept(root_label, None, (), 1)
    for district_order, (district_label, facilities) in enumerate(DISTRICTS, 1):
        district_id, district = concept(
            district_label,
            root_id,
            (root_label,),
            district_order,
        )
        for facility_order, facility_label in enumerate(facilities, 1):
            facility_id, facility = concept(
                facility_label,
                district_id,
                (root_label, district_label),
                facility_order,
            )
            for capability_order, (capability_label, fields) in enumerate(
                CAPABILITIES,
                1,
            ):
                capability_id, capability = concept(
                    capability_label,
                    facility_id,
                    (root_label, district_label, facility_label),
                    capability_order,
                )
                for field_order, field_label in enumerate(fields, 1):
                    capability["subnodes"][field_label] = scalar(
                        field_label,
                        capability_id,
                        (
                            root_label,
                            district_label,
                            facility_label,
                            capability_label,
                        ),
                        field_order,
                    )
                facility["subnodes"][capability_label] = capability
            district["subnodes"][facility_label] = facility
        root["subnodes"][district_label] = district

    if serial != 521:
        raise AssertionError("second clean-room tree size drifted")
    return {
        "map_topology": {root_label: root},
        "metadata": {
            "concurrent_version": 1,
            "id": "cleanroom-two-fire-r2-v1",
            "map_id": "cleanroom-two-fire-r2",
            "map_type": "resource",
            "version": "V1.0.0",
        },
    }


def build_manifest() -> dict[str, Any]:
    return {
        "candidate_limit": 36,
        "data_commit_binding": "PRIVATE_FREEZE_LEDGER",
        "dataset_id": DATASET,
        "derived_from_real": False,
        "fictional": True,
        "frozen_count": 28,
        "function_baseline_commit": BASELINE,
        "gold_eligible": False,
        "model_execution_allowed": False,
        "network_execution_allowed": False,
        "patch_eligible": False,
        "positive_count": 24,
        "quota": {
            "BOUNDARY_VARIATION": 6,
            "CROSS_BRANCH_INTERFERENCE": 4,
            "EXCLUSION_HARD_NEGATIVE": 4,
            "LEXICAL_BASELINE": 6,
            "NON_LITERAL": 4,
            "EXPLICIT_EMPTY": 4,
        },
        "schema_version": "treeguard.fire-r2-sealed-cleanroom-2-manifest.v1",
        "source_class": "CLEANROOM_SYNTHETIC",
        "tree_file": TREE_FILE.as_posix(),
        "tree_node_count": 521,
        "tree_profile": "resource",
    }


def _create(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                raise OSError("public write stalled")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()

    tree_path = options.repo_root / TREE_FILE
    manifest_path = options.repo_root / MANIFEST_FILE
    tree_content = _json_bytes(build_tree())
    manifest_content = _json_bytes(build_manifest())
    if options.check:
        if tree_path.read_bytes() != tree_content or manifest_path.read_bytes() != manifest_content:
            raise SystemExit("FIRE_R2_C2_PUBLIC_BYTES_MISMATCH")
        print('{"status":"PUBLIC_BYTES_MATCH","tree_node_count":521}')
        return 0
    if tree_path.exists() or manifest_path.exists():
        raise SystemExit("FIRE_R2_C2_PUBLIC_OUTPUT_EXISTS")
    _create(tree_path, tree_content)
    try:
        _create(manifest_path, manifest_content)
    except BaseException:
        tree_path.unlink(missing_ok=True)
        raise
    print('{"status":"PUBLIC_DATA_CREATED","tree_node_count":521}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
