from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DATASET_REF = "navigation-copilot-b03c-review-contract-proof"
BATCH_REF = "NAVCOP_B03C_REVIEW_PROOF_20260817_C0"
DOMAIN_REF = "FICTIONAL_SHARED_LAUNDRY_OPERATIONS"
NAMESPACE = "urn:treeguard:fictional:navigation-copilot:b03c:review-proof:v1"
SEED = 2026081737
SCHEMA_TREE = "treeguard.navigation-copilot-b03c-review-proof-tree.v1"
SCHEMA_SCENARIOS = "treeguard.navigation-copilot-b03c-review-proof-scenarios.v1"
SCHEMA_PACKET = "treeguard.navigation-copilot-b03c-review-proof-packet.v1"

BRANCHES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("预约安排", ("洗衣机预约", "烘干机预约", "预约取消", "预约时段")),
    ("设备状态", ("可用洗衣机", "可用烘干机", "故障洗衣机", "暂停设备")),
    ("洗涤程序", ("标准洗", "轻柔洗", "快速洗", "高温洗")),
    ("烘干处理", ("低温烘干", "标准烘干", "延时烘干", "自然晾晒")),
    ("用品补给", ("洗衣液补充", "柔顺剂补充", "消毒剂补充", "用品取用")),
    ("衣物管理", ("遗留衣物", "临时存放", "认领登记", "超时处理")),
    ("费用与规则", ("单次费用", "退款申请", "使用须知", "开放时间")),
    ("帮助与安全", ("漏水报告", "异响报告", "紧急停机", "服务咨询")),
)

ALIASES = {
    "烘干机预约": ["烘机预约"],
    "异响报告": ["怪响报告"],
    "服务咨询": ["服务帮助", "洗衣房帮助"],
}


def _node_id(position: int) -> str:
    return f"c0n-{position:03d}"


def build_tree() -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "node_id": _node_id(1),
            "parent_id": None,
            "label": "共享洗衣房服务",
            "aliases": ["洗衣房服务"],
            "node_kind": "COLLECTION",
            "value_type": "NONE",
            "cardinality": "MULTI",
        }
    ]
    position = 2
    for branch_label, children in BRANCHES:
        branch_id = _node_id(position)
        position += 1
        nodes.append(
            {
                "node_id": branch_id,
                "parent_id": _node_id(1),
                "label": branch_label,
                "aliases": [],
                "node_kind": "COLLECTION",
                "value_type": "NONE",
                "cardinality": "MULTI",
            }
        )
        for child_label in children:
            nodes.append(
                {
                    "node_id": _node_id(position),
                    "parent_id": branch_id,
                    "label": child_label,
                    "aliases": ALIASES.get(child_label, []),
                    "node_kind": "FIELD",
                    "value_type": "TEXT",
                    "cardinality": "SINGLE",
                }
            )
            position += 1
    assert position == 42
    return {
        "schema_version": SCHEMA_TREE,
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "domain_ref": DOMAIN_REF,
        "namespace": NAMESPACE,
        "seed": SEED,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "nodes": nodes,
    }


def build_scenarios() -> dict[str, Any]:
    items = [
        ("c0s-001", "UNIQUE", "我想取消已经约好的洗衣时段", None),
        ("c0s-002", "NONLITERAL_UNIQUE", "想约一台烘机", None),
        ("c0s-003", "WRONG_CONTEXT", "机器一直发出怪响，应该去哪里处理", "c0n-022"),
        ("c0s-004", "MULTI_ACCEPTABLE", "哪些项目是补充洗涤用品的？", None),
        ("c0s-005", "CLARIFICATION", "我要预约设备", None),
        ("c0s-006", "WEAK_EVIDENCE", "衣服处理得不对，怎么办", None),
        ("c0s-007", "TARGET_ABSENT", "我想预约熨烫机", None),
        ("c0s-008", "SUPERTYPE_PRESENT", "我想了解洗衣房能提供哪些帮助", None),
    ]
    return {
        "schema_version": SCHEMA_SCENARIOS,
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "items": [
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "request_text": request_text,
                "context_node_id": context_node_id,
            }
            for scenario_id, scenario_type, request_text, context_node_id in items
        ],
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_review_packet(tree_bytes: bytes, scenario_bytes: bytes) -> dict[str, Any]:
    scenario_document = json.loads(scenario_bytes)
    return {
        "schema_version": SCHEMA_PACKET,
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "source_tree_sha256": _sha256(tree_bytes),
        "source_scenarios_sha256": _sha256(scenario_bytes),
        "producer_module": "author_review_contract_proof",
        "items": [
            {"scenario_id": item["scenario_id"], "review_state": "PENDING"}
            for item in scenario_document["items"]
        ],
    }


def materialize(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tree_bytes = _json_bytes(build_tree())
    scenario_bytes = _json_bytes(build_scenarios())
    packet_bytes = _json_bytes(build_review_packet(tree_bytes, scenario_bytes))
    contents = {
        "tree.v1.json": tree_bytes,
        "scenarios.v1.json": scenario_bytes,
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
    print("C0_AUTHORING_READY nodes=41 scenarios=8 review_state=PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
