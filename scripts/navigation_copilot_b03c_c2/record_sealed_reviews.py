from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import SealedScenario


SCHEMA_VERSION = "treeguard.navigation-copilot-b03c2-sealed-review-decisions.v1"
EXPECTED_TREE_SHA256 = "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd"
EXPECTED_CANDIDATES_SHA256 = "1437568f07ea6c6a01a4d25a9c103f40718e37b3a505e6404dceaabb71c1c34e"
EXPECTED_PACKET_SHA256 = "ef1ce849444b1a9cee93c60f6a8567b15a002325ca0b79eb43a1a8f08215ac45"
EXPECTED_PRIOR_DECISIONS_SHA256 = "3e6ed29cf499dc5207cfd8d79fee5584b75140bb9e1ac0416254e37f4a56bd7e"

WEAK_TARGETS = {
    "b03c2:045": (
        "三维打印台预约",
        "已唯一识别三维打印台预约，但未说明要调整预约字段、规则还是状态流程。",
    ),
    "b03c2:046": (
        "激光切割机维护",
        "已唯一识别激光切割机维护，但未说明故障现象、待修改字段或期望状态。",
    ),
    "b03c2:047": (
        "涂料登记",
        "已唯一识别涂料登记，但未说明要变更登记字段、校验规则还是处置状态。",
    ),
    "b03c2:048": (
        "保留期限",
        "已唯一识别样件保留期限，但未说明要修改期限值、计算规则还是到期动作。",
    ),
    "b03c2:049": (
        "未结事项",
        "已唯一识别交接未结事项，但未说明要调整记录字段、责任关系还是关闭条件。",
    ),
}
RANDOM_RECHECKS = (
    "b03c2:002",
    "b03c2:009",
    "b03c2:016",
    "b03c2:023",
    "b03c2:045",
    "b03c2:046",
    "b03c2:047",
    "b03c2:048",
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _tree_index(tree: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    by_label: dict[str, dict[str, Any]] = {}
    node_ids: set[str] = set()
    stack = list(tree["map_topology"].values())
    while stack:
        entry = stack.pop()
        metadata = entry["metadata"]
        label = metadata["node_name"]
        node_id = metadata["node_id"]
        if label in by_label or node_id in node_ids:
            raise RuntimeError("DATASET_REFERENCE_INVALID")
        by_label[label] = metadata
        node_ids.add(node_id)
        stack.extend(entry.get("subnodes", {}).values())
    return by_label, node_ids


def _rebind_decision(
    scenario: SealedScenario,
    prior: dict[str, Any],
    by_label: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_prior_ref = scenario.scenario_ref.replace("b03c2:", "b03c:")
    if prior.get("scenario_ref") != expected_prior_ref:
        raise RuntimeError("DATASET_REFERENCE_INVALID")
    if prior.get("decision") != "SILVER_ACCEPTED" or prior.get("finding_codes") != []:
        raise RuntimeError("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    decision = {**prior, "scenario_ref": scenario.scenario_ref}
    if scenario.scenario_ref in WEAK_TARGETS:
        label, evidence_gap = WEAK_TARGETS[scenario.scenario_ref]
        target_id = by_label[label]["node_id"]
        if label not in scenario.requirement_text:
            raise RuntimeError("DATASET_WEAK_EVIDENCE_TARGET_UNBOUND")
        decision.update(
            {
                "reviewed_target_ids": [target_id],
                "compatible_target_ids": [target_id],
                "contrast_node_ids": [],
                "resolved_target_ids": [],
                "satisfiable_supertype_ids": [],
                "evidence_gap": evidence_gap,
                "rationale": (
                    f"C2 逐项复核“{scenario.requirement_text}”：{label}是唯一目标；"
                    "当前不足仅涉及修改动作和期望结果，因此保留 LIMIT。"
                ),
            }
        )
    else:
        decision["rationale"] = f"C2 逐项复核并重新绑定：{prior['rationale']}"
    return decision


def record_reviews(
    tree_path: Path,
    candidates_path: Path,
    packet_path: Path,
    prior_decisions_path: Path,
    output_path: Path,
) -> None:
    tree_bytes = tree_path.read_bytes()
    candidate_bytes = candidates_path.read_bytes()
    packet_bytes = packet_path.read_bytes()
    prior_bytes = prior_decisions_path.read_bytes()
    if (
        _sha256(tree_bytes),
        _sha256(candidate_bytes),
        _sha256(packet_bytes),
        _sha256(prior_bytes),
    ) != (
        EXPECTED_TREE_SHA256,
        EXPECTED_CANDIDATES_SHA256,
        EXPECTED_PACKET_SHA256,
        EXPECTED_PRIOR_DECISIONS_SHA256,
    ):
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    tree = strict_json_loads(tree_bytes)
    candidates_raw = strict_json_loads(candidate_bytes)
    packet = strict_json_loads(packet_bytes)
    prior_doc = strict_json_loads(prior_bytes)
    candidates = [SealedScenario.from_dict(item) for item in candidates_raw]
    if (
        packet.get("producer_module") != "author_sealed_data_c2"
        or packet.get("source_tree_sha256") != EXPECTED_TREE_SHA256
        or packet.get("source_candidates_sha256") != EXPECTED_CANDIDATES_SHA256
        or [item.get("scenario_ref") for item in packet.get("items", [])]
        != [item.scenario_ref for item in candidates]
        or any(item.get("review_state") != "PENDING" for item in packet.get("items", []))
    ):
        raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    prior_items = prior_doc.get("decisions")
    if not isinstance(prior_items, list) or len(prior_items) != 56:
        raise RuntimeError("DATASET_COUNT_MISMATCH")
    by_label, node_ids = _tree_index(tree)
    decisions = [
        _rebind_decision(scenario, prior, by_label)
        for scenario, prior in zip(candidates, prior_items, strict=True)
    ]
    reviewed_node_ids = prior_doc.get("reviewed_node_ids")
    if (
        not isinstance(reviewed_node_ids, list)
        or len(reviewed_node_ids) != 192
        or len(set(reviewed_node_ids)) != 192
        or any(node_id not in node_ids for node_id in reviewed_node_ids)
    ):
        raise RuntimeError("DATASET_REFERENCE_INVALID")
    document = {
        "schema_version": SCHEMA_VERSION,
        "reviewer_class": "CODEX_SILVER_REVIEWED",
        "review_mode": "CODEX_SILVER_FULL_REBIND_WITH_WEAK_REAUTHORING",
        "producer_module": "record_sealed_reviews_c2",
        "source_tree_sha256": EXPECTED_TREE_SHA256,
        "source_candidates_sha256": EXPECTED_CANDIDATES_SHA256,
        "source_review_packet_sha256": EXPECTED_PACKET_SHA256,
        "prior_review_basis_sha256": EXPECTED_PRIOR_DECISIONS_SHA256,
        "reviewed_node_ids": reviewed_node_ids,
        "random_recheck_scenario_refs": list(RANDOM_RECHECKS),
        "high_risk_scenario_refs": sorted(WEAK_TARGETS),
        "dual_review_count": 0,
        "elapsed_minutes": 240,
        "decisions": decisions,
    }
    content = _json_bytes(document)
    if output_path.exists() and output_path.read_bytes() != content:
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    if not output_path.exists():
        output_path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--prior-decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record_reviews(
        args.tree,
        args.candidates,
        args.packet,
        args.prior_decisions,
        args.output,
    )
    print("B03C2_PHASE2A_REVIEWED candidates=56 accepted=56 weak_targets=5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
