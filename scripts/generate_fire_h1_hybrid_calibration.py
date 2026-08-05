#!/usr/bin/env python3
"""Build the transparent fictional H1 hybrid-retrieval calibration dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from treeguard.adapter import adapt_tree_document
from treeguard.hashing import canonical_digest


DATASET_REF = "fictional-fire-h1-hybrid-calibration"
MANIFEST_VERSION = "treeguard.fire-h1-hybrid-calibration-manifest.v1"
SCENARIO_VERSION = "treeguard.fire-h1-hybrid-calibration-scenarios.v1"
ORACLE_VERSION = "treeguard.fire-h1-hybrid-calibration-oracle.v1"
GENERATOR_VERSION = "treeguard.fire-h1-hybrid-calibration-generator.v1"
SOURCE_TREE = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow/tree.json"
FIXTURE_DIRECTORY = ROOT / "tests/fixtures/fictional/fire_h1_hybrid_calibration"

CATEGORY_COUNTS = {
    "BOUNDARY_VARIATION": 2,
    "CROSS_BRANCH_INTERFERENCE": 2,
    "EXCLUSION_HARD_NEGATIVE": 4,
    "EXPLICIT_EMPTY": 4,
    "LEXICAL_BASELINE": 4,
    "NON_LITERAL": 8,
}
POSITIVE_CATEGORIES = {
    "BOUNDARY_VARIATION",
    "CROSS_BRANCH_INTERFERENCE",
    "LEXICAL_BASELINE",
    "NON_LITERAL",
}


def _scenario(
    scenario_ref: str,
    category: str,
    text: str,
    *,
    target_role: str,
    scope_role: str | None = None,
    exclusion_role: str | None = None,
    parent: str | None = None,
    value_type: str | None = None,
    cardinality: str = "UNKNOWN",
    acceptable: tuple[str, ...] = (),
    excluded: tuple[str, ...] = (),
) -> dict[str, Any]:
    role_specs = [("TARGET", target_role)]
    if scope_role is not None:
        role_specs.append(("SCOPE", scope_role))
    if exclusion_role is not None:
        role_specs.append(("EXCLUSION", exclusion_role))
    roles = []
    for role, value in role_specs:
        if text.count(value) != 1:
            raise ValueError(f"{scenario_ref} role text must occur exactly once")
        start = text.index(value)
        roles.append({"end": start + len(value), "role": role, "start": start, "text": value})
    roles.sort(key=lambda item: (item["start"], item["end"], item["role"]))
    if category == "EXPLICIT_EMPTY":
        allowed_statuses = ["INSUFFICIENT_SIGNAL", "NO_CANDIDATES"]
    elif category == "EXCLUSION_HARD_NEGATIVE":
        allowed_statuses = ["CANDIDATES_READY", "NO_CANDIDATES"]
    else:
        allowed_statuses = ["CANDIDATES_READY"]
    return {
        "oracle": {
            "acceptable_node_ids": list(acceptable),
            "allowed_statuses": allowed_statuses,
            "excluded_node_ids": list(excluded),
        },
        "scenario": {
            "primary_category": category,
            "request": {
                "cardinality_hint": cardinality,
                "node_kind_hint": "PROPERTY",
                "proposed_parent_node_id": parent,
                "requirement_text": text,
                "value_type_hint": value_type,
            },
            "scenario_ref": scenario_ref,
            "silver_roles": roles,
        },
    }


def _definitions() -> tuple[dict[str, Any], ...]:
    return (
        _scenario(
            "H1S001", "NON_LITERAL", "请在先遣侦查范围复用材料需要保存多久的属性定义。",
            target_role="材料需要保存多久", scope_role="先遣侦查", parent="M5N0015",
            value_type="class", cardinality="SINGLE", acceptable=("M5N0016",),
        ),
        _scenario(
            "H1S002", "NON_LITERAL", "为水源保障记录可关联的外部资源标识，复用现有属性。",
            target_role="可关联的外部资源标识", scope_role="水源保障", parent="M5N0415",
            value_type="time_code", cardinality="SINGLE", acceptable=("M5N0416",),
        ),
        _scenario(
            "H1S003", "NON_LITERAL", "承包方接受演练通知应记录在哪个时间段，复用已有属性。",
            target_role="接受演练通知应记录在哪个时间段", scope_role="承包方",
            parent="M5N0791", value_type="float", cardinality="SINGLE",
            acceptable=("M5N0792",),
        ),
        _scenario(
            "H1S004", "NON_LITERAL", "社区联络未成功时如何处置，复用已有多值属性。",
            target_role="联络未成功时如何处置", scope_role="社区", parent="M5N1333",
            value_type="string", cardinality="MULTIPLE", acceptable=("M5N1337",),
        ),
        _scenario(
            "H1S005", "NON_LITERAL", "对外报送完成后采用什么确认办法，复用已有属性。",
            target_role="完成后采用什么确认办法", scope_role="对外报送", parent="M5N1347",
            value_type="entity_code", cardinality="SINGLE", acceptable=("M5N1351",),
        ),
        _scenario(
            "H1S006", "NON_LITERAL", "个人防护用品需要采用哪种提醒规则，复用已有属性。",
            target_role="需要采用哪种提醒规则", scope_role="个人防护用品", parent="M5N0950",
            value_type="string", cardinality="SINGLE", acceptable=("M5N0953",),
        ),
        _scenario(
            "H1S007", "NON_LITERAL", "整改复查抽样由哪个维护责任方负责，复用已有属性。",
            target_role="由哪个维护责任方负责", scope_role="整改复查抽样", parent="M5N1161",
            value_type="string", cardinality="SINGLE", acceptable=("M5N1163",),
        ),
        _scenario(
            "H1S008", "NON_LITERAL", "事件升级条件对哪些范围有效，复用已有属性。",
            target_role="对哪些范围有效", scope_role="事件升级条件", parent="M5N0833",
            value_type="time_code", cardinality="SINGLE", acceptable=("M5N0834",),
        ),
        _scenario(
            "H1S009", "LEXICAL_BASELINE", "复用警戒组织依赖条件，不新增同义属性。",
            target_role="警戒组织依赖条件", parent="M5N0028", value_type="entity_code",
            cardinality="SINGLE", acceptable=("M5N0029",),
        ),
        _scenario(
            "H1S010", "LEXICAL_BASELINE", "复用作业区域空间范围，不新增同义属性。",
            target_role="作业区域空间范围", parent="M5N0203", value_type="space_code",
            cardinality="MULTIPLE", acceptable=("M5N0205",),
        ),
        _scenario(
            "H1S011", "LEXICAL_BASELINE", "复用季节影响时间窗口，不新增同义属性。",
            target_role="季节影响时间窗口", parent="M5N0377", value_type="boolean",
            cardinality="SINGLE", acceptable=("M5N0382",),
        ),
        _scenario(
            "H1S012", "LEXICAL_BASELINE", "复用复测确认触发条件，不新增同义属性。",
            target_role="复测确认触发条件", parent="M5N0617", value_type="float",
            cardinality="MULTIPLE", acceptable=("M5N0618",),
        ),
        _scenario(
            "H1S013", "BOUNDARY_VARIATION", "复用警戒组织任务交接所使用的节点标识。",
            target_role="任务交接所使用的节点标识", scope_role="警戒组织", parent="M5N0028",
            value_type="string", cardinality="SINGLE", acceptable=("M5N0030",),
        ),
        _scenario(
            "H1S014", "BOUNDARY_VARIATION", "复用信息报送流程结束前的交接节点记录。",
            target_role="流程结束前的交接节点记录", scope_role="信息报送", parent="M5N1347",
            value_type="time_code", cardinality="SINGLE", acceptable=("M5N1354",),
        ),
        _scenario(
            "H1S015", "CROSS_BRANCH_INTERFERENCE",
            "在外部衔接域的交通资源下复用启停规则，不要使用先遣侦察启停规则。",
            target_role="交通资源下复用启停规则", scope_role="外部衔接域",
            exclusion_role="先遣侦察启停规则", parent="M5N1307", value_type="float",
            cardinality="SINGLE", acceptable=("M5N1308",), excluded=("M5N0026",),
        ),
        _scenario(
            "H1S016", "CROSS_BRANCH_INTERFERENCE",
            "在终止确认流程复用反馈渠道，不要使用个人防护反馈渠道。",
            target_role="复用反馈渠道", scope_role="终止确认流程",
            exclusion_role="个人防护反馈渠道", parent="M5N0117", value_type="boolean",
            cardinality="SINGLE", acceptable=("M5N0124",), excluded=("M5N0956",),
        ),
        _scenario(
            "H1S017", "EXCLUSION_HARD_NEGATIVE",
            "需要建立接驳路线停用审批口径，不要将交通资源启停规则作为已有目标。",
            target_role="接驳路线停用审批口径", exclusion_role="交通资源启停规则",
            value_type="string", cardinality="SINGLE", excluded=("M5N1308",),
        ),
        _scenario(
            "H1S018", "EXCLUSION_HARD_NEGATIVE",
            "需要建立居民通知失败补偿口径，不要将社区沟通失败处置作为已有目标。",
            target_role="居民通知失败补偿口径", exclusion_role="社区沟通失败处置",
            value_type="string", cardinality="SINGLE", excluded=("M5N1337",),
        ),
        _scenario(
            "H1S019", "EXCLUSION_HARD_NEGATIVE",
            "需要建立演练供应商回执编号，不要将承包商告知时间窗口作为已有目标。",
            target_role="演练供应商回执编号", exclusion_role="承包商告知时间窗口",
            value_type="entity_code", cardinality="SINGLE", excluded=("M5N0792",),
        ),
        _scenario(
            "H1S020", "EXCLUSION_HARD_NEGATIVE",
            "需要建立水池补给来源编号，不要将水源保障关联资源作为已有目标。",
            target_role="水池补给来源编号", exclusion_role="水源保障关联资源",
            value_type="entity_code", cardinality="SINGLE", excluded=("M5N0416",),
        ),
        _scenario(
            "H1S021", "EXPLICIT_EMPTY", "需要定义h1voidalpha占位合同。",
            target_role="h1voidalpha", value_type="string", cardinality="SINGLE",
        ),
        _scenario(
            "H1S022", "EXPLICIT_EMPTY", "需要定义h1voidbeta占位合同。",
            target_role="h1voidbeta", value_type="string", cardinality="SINGLE",
        ),
        _scenario(
            "H1S023", "EXPLICIT_EMPTY", "需要定义h1voidgamma占位合同。",
            target_role="h1voidgamma", value_type="string", cardinality="SINGLE",
        ),
        _scenario(
            "H1S024", "EXPLICIT_EMPTY", "需要定义h1voiddelta占位合同。",
            target_role="h1voiddelta", value_type="string", cardinality="SINGLE",
        ),
    )


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _value_envelope_count(value: Any) -> int:
    if isinstance(value, dict):
        return int("VALUE" in value) + sum(_value_envelope_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_value_envelope_count(item) for item in value)
    return 0


def build_bundle() -> dict[str, bytes]:
    source_bytes = SOURCE_TREE.read_bytes()
    source_document = json.loads(source_bytes)
    imported = adapt_tree_document(source_document, source_hint="h1-hybrid-calibration")
    if not imported.is_valid or imported.tree is None:
        raise ValueError("source tree is not adaptable")
    tree = imported.tree
    nodes = {node.node_id: node for node in tree.nodes}
    definitions = _definitions()
    scenarios = [item["scenario"] for item in definitions]
    oracles = [
        {
            **item["oracle"],
            "primary_category": item["scenario"]["primary_category"],
            "scenario_ref": item["scenario"]["scenario_ref"],
        }
        for item in definitions
    ]
    if [item["scenario_ref"] for item in scenarios] != [f"H1S{i:03d}" for i in range(1, 25)]:
        raise ValueError("scenario order is invalid")
    if Counter(item["primary_category"] for item in scenarios) != Counter(CATEGORY_COUNTS):
        raise ValueError("category quota is invalid")
    if len({item["request"]["requirement_text"] for item in scenarios}) != 24:
        raise ValueError("requests must be unique")
    oracle_by_ref = {item["scenario_ref"]: item for item in oracles}
    for scenario in scenarios:
        ref = scenario["scenario_ref"]
        request = scenario["request"]
        roles = scenario["silver_roles"]
        text = request["requirement_text"]
        if roles != sorted(roles, key=lambda item: (item["start"], item["end"], item["role"])):
            raise ValueError(f"{ref} roles are not ordered")
        if sum(item["role"] == "TARGET" for item in roles) != 1:
            raise ValueError(f"{ref} target role is invalid")
        for role in roles:
            if text[role["start"]:role["end"]] != role["text"]:
                raise ValueError(f"{ref} role binding is invalid")
        oracle = oracle_by_ref[ref]
        accepted = set(oracle["acceptable_node_ids"])
        excluded = set(oracle["excluded_node_ids"])
        if not (accepted | excluded) <= nodes.keys() or accepted & excluded:
            raise ValueError(f"{ref} oracle node binding is invalid")
        category = scenario["primary_category"]
        if (category in POSITIVE_CATEGORIES) != bool(accepted):
            raise ValueError(f"{ref} positive category binding is invalid")
        if (category == "EXCLUSION_HARD_NEGATIVE") != (bool(excluded) and not accepted):
            raise ValueError(f"{ref} hard-negative binding is invalid")
        if category == "EXPLICIT_EMPTY" and (accepted or excluded):
            raise ValueError(f"{ref} empty binding is invalid")
        if accepted:
            target = nodes[next(iter(accepted))]
            contract = target.value_contract
            expected_cardinality = contract.cardinality if contract is not None else "UNKNOWN"
            expected_value_type = contract.value_type if contract is not None else None
            if (
                request["node_kind_hint"] != target.kind
                or request["value_type_hint"] != expected_value_type
                or request["cardinality_hint"] != expected_cardinality
            ):
                raise ValueError(f"{ref} request contract does not match target")
    scenario_payload = {
        "dataset_ref": DATASET_REF,
        "schema_version": SCENARIO_VERSION,
        "scenarios": scenarios,
        "source_tree_digest": tree.snapshot_hash,
    }
    scenario_payload["scenario_digest"] = canonical_digest(scenario_payload)
    oracle_payload = {
        "dataset_ref": DATASET_REF,
        "entries": oracles,
        "gold_eligible": False,
        "model_input_forbidden": True,
        "patch_eligible": False,
        "quality_tier": "CODEX_SILVER_DEVELOPMENT",
        "schema_version": ORACLE_VERSION,
        "source_scenario_digest": scenario_payload["scenario_digest"],
        "source_tree_digest": tree.snapshot_hash,
    }
    oracle_payload["oracle_digest"] = canonical_digest(oracle_payload)
    scenario_bytes = _json_bytes(scenario_payload)
    oracle_bytes = _json_bytes(oracle_payload)
    manifest_payload = {
        "benchmark_role": "HYBRID_RETRIEVAL_DEVELOPMENT_CALIBRATION",
        "category_counts": CATEGORY_COUNTS,
        "dataset_ref": DATASET_REF,
        "derived_from_real": False,
        "explicit_empty_count": 4,
        "fictional": True,
        "generator_version": GENERATOR_VERSION,
        "gold_eligible": False,
        "hard_negative_count": 4,
        "node_count": len(tree.nodes),
        "oracle_file": "oracle-sidecar.json",
        "oracle_file_sha256": _sha256(oracle_bytes),
        "patch_eligible": False,
        "positive_count": 16,
        "scenario_count": 24,
        "scenario_file": "scenarios.json",
        "scenario_file_sha256": _sha256(scenario_bytes),
        "schema_version": MANIFEST_VERSION,
        "source_class": "CLEANROOM_SYNTHETIC",
        "source_tree_canonical_digest": tree.snapshot_hash,
        "source_tree_file": "../fire_m5_assisted_shadow/tree.json",
        "source_tree_file_sha256": _sha256(source_bytes),
        "value_envelope_count": _value_envelope_count(source_document),
    }
    return {
        "manifest.json": _json_bytes(manifest_payload),
        "oracle-sidecar.json": oracle_bytes,
        "scenarios.json": scenario_bytes,
    }


def write_bundle(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    for name, payload in build_bundle().items():
        (output_directory / name).write_bytes(payload)


def validate_materialized(output_directory: Path) -> dict[str, Any]:
    expected = build_bundle()
    if not output_directory.is_dir() or output_directory.is_symlink():
        raise ValueError("materialized directory is invalid")
    if {path.name for path in output_directory.iterdir()} != set(expected):
        raise ValueError("materialized file set is invalid")
    for name, payload in expected.items():
        path = output_directory / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise ValueError("materialized bytes are invalid")
    return {
        "dataset_ref": DATASET_REF,
        "explicit_empty_count": 4,
        "hard_negative_count": 4,
        "model_called": False,
        "positive_count": 16,
        "scenario_count": 24,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=FIXTURE_DIRECTORY)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        try:
            report = validate_materialized(args.output_dir)
        except (OSError, ValueError):
            print(json.dumps({"error_code": "H1_CALIBRATION_MATERIALIZED_INVALID", "status": "FAIL"}, sort_keys=True))
            return 2
        print(json.dumps(report, sort_keys=True))
        return 0
    write_bundle(args.output_dir)
    print(json.dumps({"dataset_ref": DATASET_REF, "model_called": False, "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
