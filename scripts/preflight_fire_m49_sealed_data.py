#!/usr/bin/env python3
"""Deterministic L1 validation for the M4.9 sealed candidate batch."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.generate_fire_m49_sealed_data import DATASET_REF, OUTPUT_DIR, build_payloads
from treeguard.adapter import adapt_tree_document
from treeguard.change_intent import IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.private_io import read_private_json, write_private_json
from treeguard.scenario_capability_validation import CapabilityOracle
from treeguard.tree_understanding import build_tree_diagnostic_profile

FILES = (
    "manifest.json",
    "tree.json",
    "semantic-blueprint.json",
    "scenario-candidates.json",
    "oracle-sidecar.json",
    "review-packet.json",
    "promotion-checklist.json",
)


class PreflightFailure(RuntimeError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PreflightFailure(code)


def load_payloads(directory: Path) -> dict[str, dict[str, Any]]:
    payloads = {}
    for filename in FILES:
        payload = read_private_json(directory / filename, max_bytes=20_000_000)
        require(isinstance(payload, dict), "M49_FILE_NOT_OBJECT")
        payloads[filename] = payload
    return payloads


def validate_payloads(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    expected = build_payloads()
    require(payloads == expected, "M49_DETERMINISTIC_REPLAY_MISMATCH")
    manifest = payloads["manifest.json"]
    tree_doc = payloads["tree.json"]
    blueprint = payloads["semantic-blueprint.json"]
    candidates = payloads["scenario-candidates.json"]
    sidecar = payloads["oracle-sidecar.json"]

    require(manifest["dataset_ref"] == DATASET_REF, "M49_DATASET_REF_MISMATCH")
    for payload in (manifest, candidates):
        require(payload["source_class"] == "CLEANROOM_SYNTHETIC", "M49_SOURCE_CLASS_INVALID")
        require(payload["fictional"] is True, "M49_FICTIONAL_FLAG_INVALID")
        require(payload["derived_from_real"] is False, "M49_REAL_DERIVATION_INVALID")
        require(payload["gold_eligible"] is False, "M49_GOLD_POLICY_INVALID")
        require(payload["gate_eligible"] is False, "M49_GATE_POLICY_INVALID")
        require(payload["patch_eligible"] is False, "M49_PATCH_POLICY_INVALID")

    adapted = adapt_tree_document(tree_doc)
    require(adapted.is_valid and adapted.tree is not None, "M49_TREE_ADAPTER_INVALID")
    tree = adapted.tree
    require(1_200 <= len(tree.nodes) <= 1_600, "M49_NODE_COUNT_OUT_OF_RANGE")
    require(len(tree.nodes) == 1_453 == manifest["node_count"], "M49_NODE_COUNT_MISMATCH")
    require(adapted.observed_value_count == 0, "M49_VALUE_ENVELOPE_PRESENT")
    require(len(tree.root_node_ids) == 1, "M49_ROOT_COUNT_INVALID")
    require(len(tree.nodes[0].path_labels) >= 1, "M49_PATH_INVALID")
    require(max(len(node.path_labels) for node in tree.nodes) == 5, "M49_DEPTH_INVALID")
    root = next(node for node in tree.nodes if node.node_id == tree.root_node_ids[0])
    require(len(root.child_node_ids) == 12, "M49_BRANCH_COUNT_INVALID")
    require(manifest["tree_snapshot_hash"] == tree.snapshot_hash, "M49_SNAPSHOT_BINDING_INVALID")
    require(manifest["tree_digest"] == canonical_digest(tree_doc), "M49_TREE_DIGEST_INVALID")
    require(manifest["blueprint_digest"] == canonical_digest(blueprint), "M49_BLUEPRINT_DIGEST_INVALID")

    node_ids = {node.node_id for node in tree.nodes}
    classes = blueprint["node_classes"]
    require(set(classes) == node_ids, "M49_NODE_CLASS_COVERAGE_INVALID")
    class_counts = Counter(classes.values())
    require(160 <= class_counts["CURATED_CORE"] <= 240, "M49_CURATED_COUNT_INVALID")
    require(class_counts["STRESS_FILLER"] == 0, "M49_STRESS_FILLER_FORBIDDEN")
    require(sum(class_counts.values()) == len(tree.nodes), "M49_CLASS_COUNT_INVALID")
    require(blueprint["construction_policy"] == "EXPLICIT_SUBJECT_BLUEPRINT_NO_CARTESIAN_PRODUCT", "M49_CONSTRUCTION_POLICY_INVALID")
    require(blueprint["filler_targetable"] is False, "M49_FILLER_TARGET_POLICY_INVALID")
    subjects = blueprint["subjects"]
    require(len(subjects) == 120, "M49_SUBJECT_BLUEPRINT_COUNT_INVALID")
    require(len({item["subject_id"] for item in subjects}) == 120, "M49_SUBJECT_BLUEPRINT_DUPLICATE")
    require(all(item["owner_scope_status"] == "EXPLICIT" for item in subjects), "M49_OWNER_SCOPE_AMBIGUOUS")

    profile = build_tree_diagnostic_profile(tree)
    finding_counts = Counter(item.code for item in profile.findings)
    require(finding_counts["CHILD_CONTRACT_VECTOR_REUSED"] == 0, "M49_REPEATED_CHILD_VECTOR")

    items = candidates["items"]
    require(len(items) == 30, "M49_SCENARIO_COUNT_INVALID")
    refs = [item["scenario_ref"] for item in items]
    require(len(refs) == len(set(refs)), "M49_SCENARIO_REF_DUPLICATE")
    formal = [item for item in items if item["batch"] == "FORMAL"]
    reserve = [item for item in items if item["batch"] == "RESERVE"]
    require(len(formal) == 24 and len(reserve) == 6, "M49_BATCH_SPLIT_INVALID")
    expected_formal = {f"P{i:02d}" for i in range(1, 19)} | {f"C{i:02d}" for i in range(1, 7)}
    require({item["scenario_ref"] for item in formal} == expected_formal, "M49_FORMAL_COVERAGE_INVALID")
    require({item["scenario_ref"] for item in reserve} == {f"R{i:02d}" for i in range(1, 7)}, "M49_RESERVE_COVERAGE_INVALID")
    require(sum(item["scenario_ref"].startswith("P") for item in formal) == 18, "M49_PROCEED_COUNT_INVALID")
    require(sum(item["scenario_ref"].startswith("C") for item in formal) == 6, "M49_CLARIFY_COUNT_INVALID")
    require(all(len(item["secondary_tags"]) <= 2 for item in items), "M49_TAG_LIMIT_INVALID")
    require(all(item["review_status"] == "PENDING_SILVER_REVIEW" and item["execution_eligible"] is False for item in items), "M49_REVIEW_GATE_INVALID")
    require(len({item["top_level_branch_ref"] for item in formal}) == 12, "M49_BRANCH_COVERAGE_INVALID")
    require(max(Counter(item["top_level_branch_ref"] for item in formal).values()) <= 3, "M49_BRANCH_CAP_INVALID")

    oracle_by_ref = {item["scenario_ref"]: item for item in sidecar["items"]}
    require(set(oracle_by_ref) == set(refs), "M49_ORACLE_REF_COVERAGE_INVALID")
    for item in items:
        ref = item["scenario_ref"]
        require(item["candidate_digest"] == canonical_digest({key: value for key, value in item.items() if key != "candidate_digest"}), "M49_CANDIDATE_DIGEST_INVALID")
        oracle_item = oracle_by_ref[ref]
        require(oracle_item["source_candidate_digest"] == item["candidate_digest"], "M49_ORACLE_SOURCE_BINDING_INVALID")
        require(oracle_item["oracle_item_digest"] == canonical_digest({key: value for key, value in oracle_item.items() if key != "oracle_item_digest"}), "M49_ORACLE_ITEM_DIGEST_INVALID")
        oracle = CapabilityOracle.from_dict(oracle_item["oracle"])
        request = IntentRequest.from_dict(item["request"], tree)
        model_view = request.to_model_dict(tree)
        serialized_model_view = json.dumps(model_view, ensure_ascii=False, sort_keys=True)
        require("M49-" not in serialized_model_view, "M49_STABLE_ID_LEAKED_TO_INTENT_MODEL")
        if oracle.expected_route == "PROCEED":
            preview = oracle_item["deterministic_preview"]
            require(preview is not None and preview["status"] == "CANDIDATES_READY", "M49_PREVIEW_STATUS_INVALID")
            require(oracle.retrieval.top_k == max(preview["oracle_target_ranks"].values()), "M49_TOP_K_BINDING_INVALID")
            require(set(oracle.retrieval.acceptable_node_ids) <= set(preview["candidate_node_ids"][: oracle.retrieval.top_k]), "M49_TARGET_OUTSIDE_TOP_K")
        else:
            require(oracle_item["deterministic_preview"] is None, "M49_CLARIFY_PREVIEW_FORBIDDEN")
    for ref, expected_rank in (("P09", 2), ("P10", 2)):
        oracle_item = oracle_by_ref[ref]
        require(max(oracle_item["deterministic_preview"]["oracle_target_ranks"].values()) == expected_rank, "M49_TOP_K_BOUNDARY_NOT_EXACT")

    public_by_ref = {item["scenario_ref"]: item for item in items}
    require(max(oracle_by_ref["R03"]["deterministic_preview"]["oracle_target_ranks"].values()) > 1, "M49_RESERVE_TOP_K_NOT_CHALLENGING")
    require(not public_by_ref["R04"]["request"]["proposed_parent_node_id"].startswith("M49-B06-"), "M49_RESERVE_CROSS_BRANCH_MISSING")
    require(public_by_ref["R05"]["request"]["node_kind_hint"] == "CONCEPT", "M49_RESERVE_KIND_CONFLICT_MISSING")
    r05_target_id = oracle_by_ref["R05"]["oracle"]["retrieval"]["acceptable_node_ids"][0]
    require(next(node for node in tree.nodes if node.node_id == r05_target_id).kind == "PROPERTY", "M49_RESERVE_KIND_EVIDENCE_INVALID")
    r06_target_id = oracle_by_ref["R06"]["oracle"]["retrieval"]["acceptable_node_ids"][0]
    r06_target = next(node for node in tree.nodes if node.node_id == r06_target_id)
    require(public_by_ref["R06"]["request"]["cardinality_hint"] != r06_target.value_contract.cardinality, "M49_RESERVE_CARDINALITY_CONFLICT_MISSING")

    public_text = json.dumps(candidates, ensure_ascii=False, sort_keys=True)
    require("acceptable_node_ids" not in public_text and '"oracle"' not in public_text, "M49_ORACLE_LEAKED_TO_PUBLIC_BATCH")
    require(sidecar["source_candidate_batch_digest"] == canonical_digest(candidates), "M49_BATCH_ORACLE_BINDING_INVALID")
    require(manifest["candidate_batch_digest"] == canonical_digest(candidates), "M49_MANIFEST_BATCH_DIGEST_INVALID")
    require(manifest["oracle_sidecar_digest"] == canonical_digest(sidecar), "M49_MANIFEST_ORACLE_DIGEST_INVALID")

    return {
        "schema_version": "fire-m49-sealed-preflight-report.v1",
        "status": "PASS",
        "dataset_ref": DATASET_REF,
        "node_count": len(tree.nodes),
        "curated_core_count": class_counts["CURATED_CORE"],
        "approved_background_count": class_counts["APPROVED_BACKGROUND"],
        "stress_filler_count": class_counts["STRESS_FILLER"],
        "formal_scenario_count": len(formal),
        "reserve_scenario_count": len(reserve),
        "top_level_branch_count": len(root.child_node_ids),
        "maximum_depth": profile.max_depth + 1,
        "finding_code_counts": dict(sorted(finding_counts.items())),
        "tree_snapshot_hash": tree.snapshot_hash,
        "candidate_batch_digest": canonical_digest(candidates),
        "oracle_sidecar_digest": canonical_digest(sidecar),
    }


def run_preflight(directory: Path, *, write_report: bool = False) -> dict[str, Any]:
    report = validate_payloads(load_payloads(directory))
    if write_report:
        require(write_private_json(directory / "preflight-report.json", report), "M49_PREFLIGHT_REPORT_WRITE_FAILED")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    try:
        report = run_preflight(args.directory.resolve(), write_report=args.write_report)
    except (OSError, ValueError, PreflightFailure) as exc:
        print(json.dumps({"status": "FAIL", "code": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({key: report[key] for key in ("status", "dataset_ref", "node_count", "formal_scenario_count", "reserve_scenario_count")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
