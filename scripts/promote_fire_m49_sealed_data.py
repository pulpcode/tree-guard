#!/usr/bin/env python3
"""Promote the frozen M4.9 Silver batch into a tracked fictional fixture."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.generate_fire_m49_sealed_data import (
    DATASET_REF,
    OUTPUT_DIR,
    build_payloads,
)
from scripts.preflight_fire_m49_sealed_data import run_preflight
from scripts.review_fire_m49_sealed_data import build_review
from treeguard.adapter import adapt_tree_document
from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads
from treeguard.private_io import read_private_json, write_private_json
from treeguard.scenario_capability_validation import CapabilityOracle

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "fictional" / "fire_m49_sealed"
FIXTURE_FILES = (
    "manifest.json",
    "tree.json",
    "scenario-candidates.json",
    "oracle-sidecar.json",
    "silver-review.json",
    "promotion.json",
)
MANIFEST_KEYS = {
    "schema_version",
    "dataset_ref",
    "fixture_state",
    "primary_role",
    "source_class",
    "fictional",
    "derived_from_real",
    "quality_tier",
    "assessment_authority",
    "execution_scope",
    "gold_eligible",
    "gate_eligible",
    "patch_eligible",
    "execution_eligible",
    "runtime_registered",
    "functional_baseline_commit",
    "tree_file",
    "scenario_file",
    "oracle_sidecar_file",
    "silver_review_file",
    "promotion_file",
    "tree_snapshot_hash",
    "tree_digest",
    "candidate_batch_digest",
    "oracle_sidecar_digest",
    "silver_review_digest",
    "node_count",
    "curated_core_count",
    "approved_background_count",
    "stress_filler_count",
    "top_level_branch_count",
    "maximum_depth",
    "value_envelope_count",
    "formal_scenario_count",
    "formal_proceed_count",
    "formal_clarify_count",
    "reserve_scenario_count",
    "limitations",
}
PROMOTION_KEYS = {
    "schema_version",
    "dataset_ref",
    "fixture_state",
    "candidate_state",
    "explicit_promotion_approved",
    "source_class",
    "fictional",
    "derived_from_real",
    "quality_tier",
    "gold_eligible",
    "gate_eligible",
    "patch_eligible",
    "execution_eligible",
    "formal_fixture_promoted",
    "runtime_registered",
    "experiment_executed",
    "source_tree_snapshot_hash",
    "source_candidate_batch_digest",
    "source_oracle_sidecar_digest",
    "source_silver_review_digest",
    "next_gate",
    "promotion_digest",
}


class PromotionError(RuntimeError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _strict_fixture_json(path: Path, *, max_bytes: int = 20_000_000) -> Any:
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise PromotionError("FIXTURE_FILE_TOO_LARGE")
    payload = strict_json_loads(raw.decode("utf-8"))
    if raw != canonical_json_bytes(payload):
        raise PromotionError("FIXTURE_JSON_NOT_CANONICAL")
    return payload


def build_fixture_payloads(staging_dir: Path) -> dict[str, dict[str, Any]]:
    preflight = run_preflight(staging_dir)
    expected_silver, critic = build_review(staging_dir)
    stored_silver = read_private_json(
        staging_dir / "silver-review.json", max_bytes=5_000_000
    )
    if stored_silver != expected_silver or critic["status"] != "PASS":
        raise PromotionError("SILVER_REVIEW_SOURCE_MISMATCH")
    readiness = read_private_json(
        staging_dir / "promotion-readiness.json", max_bytes=1_000_000
    )
    if (
        readiness.get("status") != "READY_FOR_EXPLICIT_PROMOTION_REVIEW"
        or readiness.get("explicit_promotion_approval") is not False
        or readiness.get("source_silver_review_digest")
        != stored_silver["review_digest"]
    ):
        raise PromotionError("PROMOTION_READINESS_INVALID")

    tree = read_private_json(staging_dir / "tree.json", max_bytes=20_000_000)
    scenarios = read_private_json(
        staging_dir / "scenario-candidates.json", max_bytes=2_000_000
    )
    oracle = read_private_json(
        staging_dir / "oracle-sidecar.json", max_bytes=5_000_000
    )
    candidate_manifest = read_private_json(
        staging_dir / "manifest.json", max_bytes=1_000_000
    )
    manifest = {
        "schema_version": "fire-m49-sealed-fixture-manifest.v1",
        "dataset_ref": DATASET_REF,
        "fixture_state": "PROMOTED",
        "primary_role": "SEMANTIC_CHALLENGE",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "assessment_authority": "CODEX_ASSISTED",
        "execution_scope": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "execution_eligible": False,
        "runtime_registered": False,
        "functional_baseline_commit": "d52e92341b1d081c45c9e4594b98323327379da5",
        "tree_file": "tree.json",
        "scenario_file": "scenario-candidates.json",
        "oracle_sidecar_file": "oracle-sidecar.json",
        "silver_review_file": "silver-review.json",
        "promotion_file": "promotion.json",
        "tree_snapshot_hash": preflight["tree_snapshot_hash"],
        "tree_digest": candidate_manifest["tree_digest"],
        "candidate_batch_digest": preflight["candidate_batch_digest"],
        "oracle_sidecar_digest": preflight["oracle_sidecar_digest"],
        "silver_review_digest": stored_silver["review_digest"],
        "node_count": preflight["node_count"],
        "curated_core_count": preflight["curated_core_count"],
        "approved_background_count": preflight["approved_background_count"],
        "stress_filler_count": preflight["stress_filler_count"],
        "top_level_branch_count": preflight["top_level_branch_count"],
        "maximum_depth": preflight["maximum_depth"],
        "value_envelope_count": 0,
        "formal_scenario_count": 24,
        "formal_proceed_count": 18,
        "formal_clarify_count": 6,
        "reserve_scenario_count": 6,
        "limitations": [
            "CODEX_ASSISTED_SILVER_IS_NOT_GOLD",
            "FIXTURE_PROMOTION_DOES_NOT_AUTHORIZE_EXECUTION",
            "RUNTIME_PLAN_AND_MODEL_CALLS_REMAIN_SEPARATE_GATES",
        ],
    }
    promotion = {
        "schema_version": "fire-m49-sealed-promotion.v1",
        "dataset_ref": DATASET_REF,
        "fixture_state": "PROMOTED",
        "candidate_state": "FROZEN",
        "explicit_promotion_approved": True,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "execution_eligible": False,
        "formal_fixture_promoted": True,
        "runtime_registered": False,
        "experiment_executed": False,
        "source_tree_snapshot_hash": preflight["tree_snapshot_hash"],
        "source_candidate_batch_digest": preflight["candidate_batch_digest"],
        "source_oracle_sidecar_digest": preflight["oracle_sidecar_digest"],
        "source_silver_review_digest": stored_silver["review_digest"],
        "next_gate": "FREEZE_EXACT_RUNTIME_REQUEST_PLAN",
    }
    promotion["promotion_digest"] = canonical_digest(promotion)
    return {
        "manifest.json": manifest,
        "tree.json": tree,
        "scenario-candidates.json": scenarios,
        "oracle-sidecar.json": oracle,
        "silver-review.json": stored_silver,
        "promotion.json": promotion,
    }


def validate_fixture(fixture_dir: Path) -> dict[str, Any]:
    if not fixture_dir.is_dir() or {
        path.name for path in fixture_dir.iterdir()
    } != set(FIXTURE_FILES):
        raise PromotionError("FIXTURE_FILE_SET_INVALID")
    payloads = {
        filename: _strict_fixture_json(fixture_dir / filename)
        for filename in FIXTURE_FILES
    }
    manifest = payloads["manifest.json"]
    promotion = payloads["promotion.json"]
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise PromotionError("FIXTURE_MANIFEST_FIELDS_INVALID")
    if not isinstance(promotion, dict) or set(promotion) != PROMOTION_KEYS:
        raise PromotionError("FIXTURE_PROMOTION_FIELDS_INVALID")
    for payload in (manifest, promotion):
        if (
            payload["source_class"] != "CLEANROOM_SYNTHETIC"
            or payload["fictional"] is not True
            or payload["derived_from_real"] is not False
            or payload["gold_eligible"] is not False
            or payload["gate_eligible"] is not False
            or payload["patch_eligible"] is not False
            or payload["execution_eligible"] is not False
        ):
            raise PromotionError("FIXTURE_BOUNDARY_INVALID")
    if (
        manifest["fixture_state"] != "PROMOTED"
        or manifest["quality_tier"] != "CODEX_ASSISTED_SILVER"
        or manifest["assessment_authority"] != "CODEX_ASSISTED"
        or manifest["execution_scope"] != "CALIBRATION_ONLY"
        or manifest["runtime_registered"] is not False
        or manifest["limitations"]
        != [
            "CODEX_ASSISTED_SILVER_IS_NOT_GOLD",
            "FIXTURE_PROMOTION_DOES_NOT_AUTHORIZE_EXECUTION",
            "RUNTIME_PLAN_AND_MODEL_CALLS_REMAIN_SEPARATE_GATES",
        ]
    ):
        raise PromotionError("FIXTURE_MANIFEST_POLICY_INVALID")
    count_fields = {
        "node_count": 1_453,
        "curated_core_count": 216,
        "approved_background_count": 1_237,
        "stress_filler_count": 0,
        "top_level_branch_count": 12,
        "maximum_depth": 5,
        "value_envelope_count": 0,
        "formal_scenario_count": 24,
        "formal_proceed_count": 18,
        "formal_clarify_count": 6,
        "reserve_scenario_count": 6,
    }
    if any(
        not isinstance(manifest[field], int)
        or isinstance(manifest[field], bool)
        or manifest[field] != expected
        for field, expected in count_fields.items()
    ):
        raise PromotionError("FIXTURE_MANIFEST_COUNT_INVALID")
    if (
        promotion["promotion_digest"]
        != canonical_digest(
            {key: value for key, value in promotion.items() if key != "promotion_digest"}
        )
        or promotion["explicit_promotion_approved"] is not True
        or promotion["formal_fixture_promoted"] is not True
        or promotion["runtime_registered"] is not False
        or promotion["experiment_executed"] is not False
    ):
        raise PromotionError("FIXTURE_PROMOTION_INVALID")

    tree_result = adapt_tree_document(payloads["tree.json"])
    if not tree_result.is_valid or tree_result.tree is None:
        raise PromotionError("FIXTURE_TREE_INVALID")
    tree = tree_result.tree
    scenarios = payloads["scenario-candidates.json"]
    oracle = payloads["oracle-sidecar.json"]
    silver = payloads["silver-review.json"]
    expected = build_payloads()
    if (
        payloads["tree.json"] != expected["tree.json"]
        or scenarios != expected["scenario-candidates.json"]
        or oracle != expected["oracle-sidecar.json"]
    ):
        raise PromotionError("FIXTURE_GENERATOR_REPLAY_MISMATCH")
    if (
        manifest["tree_snapshot_hash"] != tree.snapshot_hash
        or manifest["tree_digest"] != canonical_digest(payloads["tree.json"])
        or manifest["candidate_batch_digest"] != canonical_digest(scenarios)
        or manifest["oracle_sidecar_digest"] != canonical_digest(oracle)
        or manifest["silver_review_digest"] != silver.get("review_digest")
    ):
        raise PromotionError("FIXTURE_SOURCE_BINDING_INVALID")
    if (
        len(tree.nodes) != manifest["node_count"]
        or tree_result.observed_value_count != manifest["value_envelope_count"]
        or max(len(node.path_labels) for node in tree.nodes)
        != manifest["maximum_depth"]
    ):
        raise PromotionError("FIXTURE_TREE_ACCOUNTING_INVALID")
    if (
        oracle.get("source_candidate_batch_digest") != canonical_digest(scenarios)
        or oracle.get("source_tree_snapshot_hash") != tree.snapshot_hash
        or silver.get("source_candidate_batch_digest") != canonical_digest(scenarios)
        or silver.get("source_oracle_sidecar_digest") != canonical_digest(oracle)
        or silver.get("source_tree_snapshot_hash") != tree.snapshot_hash
    ):
        raise PromotionError("FIXTURE_REVIEW_BINDING_INVALID")
    if (
        silver.get("status") != "SILVER_ACCEPTED"
        or silver.get("quality_tier") != "CODEX_ASSISTED_SILVER"
        or silver.get("reviewer_independence") is not False
        or silver.get("gold_eligible") is not False
        or silver.get("gate_eligible") is not False
        or silver.get("execution_eligible") is not False
    ):
        raise PromotionError("FIXTURE_SILVER_POLICY_INVALID")
    silver_payload = {
        key: value for key, value in silver.items() if key != "review_digest"
    }
    if (
        silver.get("review_digest") != canonical_digest(silver_payload)
        or silver.get("reviewer_ref") != "codex-m49-silver-review"
        or silver.get("review_round") != 4
        or silver.get("reviewed_count") != 30
        or silver.get("accepted_count") != 30
        or silver.get("rejected_count") != 0
        or not isinstance(silver.get("items"), list)
        or len(silver["items"]) != 30
    ):
        raise PromotionError("FIXTURE_SILVER_REVIEW_INVALID")
    for review_item in silver["items"]:
        if (
            review_item.get("decision") != "ACCEPTED"
            or review_item.get("execution_eligible") is not False
            or review_item.get("review_item_digest")
            != canonical_digest(
                {
                    key: value
                    for key, value in review_item.items()
                    if key != "review_item_digest"
                }
            )
        ):
            raise PromotionError("FIXTURE_SILVER_ITEM_INVALID")

    candidate_items = scenarios.get("items")
    oracle_items = oracle.get("items")
    if (
        not isinstance(candidate_items, list)
        or not isinstance(oracle_items, list)
        or len(candidate_items) != 30
        or len(oracle_items) != 30
        or any(item.get("execution_eligible") is not False for item in candidate_items)
    ):
        raise PromotionError("FIXTURE_SCENARIO_ACCOUNTING_INVALID")
    formal_items = [item for item in candidate_items if item.get("batch") == "FORMAL"]
    reserve_items = [item for item in candidate_items if item.get("batch") == "RESERVE"]
    if (
        len(formal_items) != manifest["formal_scenario_count"]
        or len(reserve_items) != manifest["reserve_scenario_count"]
        or sum(item["scenario_ref"].startswith("P") for item in formal_items)
        != manifest["formal_proceed_count"]
        or sum(item["scenario_ref"].startswith("C") for item in formal_items)
        != manifest["formal_clarify_count"]
    ):
        raise PromotionError("FIXTURE_SCENARIO_COMPOSITION_INVALID")
    node_ids = {node.node_id for node in tree.nodes}
    for item in oracle_items:
        typed_oracle = CapabilityOracle.from_dict(item["oracle"])
        if not set(typed_oracle.retrieval.acceptable_node_ids) <= node_ids:
            raise PromotionError("FIXTURE_ORACLE_TARGET_UNKNOWN")
        for outcome in typed_oracle.recommendation.acceptable_outcomes:
            if outcome.target_node_id is not None and outcome.target_node_id not in node_ids:
                raise PromotionError("FIXTURE_ORACLE_TARGET_UNKNOWN")
    public_text = json.dumps(scenarios, ensure_ascii=False, sort_keys=True)
    if "acceptable_node_ids" in public_text or '"oracle"' in public_text:
        raise PromotionError("FIXTURE_ORACLE_LEAKED_TO_PUBLIC_SCENARIOS")
    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    for forbidden in ("requirement_text", "target_node_id", "acceptable_node_ids", "reviewer_ref"):
        if forbidden in manifest_text:
            raise PromotionError("FIXTURE_MANIFEST_NOT_AGGREGATE_ONLY")
    return {
        "status": "PASS",
        "dataset_ref": DATASET_REF,
        "node_count": len(tree.nodes),
        "formal_scenario_count": manifest["formal_scenario_count"],
        "reserve_scenario_count": manifest["reserve_scenario_count"],
        "quality_tier": manifest["quality_tier"],
        "runtime_registered": manifest["runtime_registered"],
    }


def promote(staging_dir: Path, fixture_dir: Path) -> dict[str, Any]:
    if fixture_dir.exists():
        raise PromotionError("FIXTURE_TARGET_ALREADY_EXISTS")
    payloads = build_fixture_payloads(staging_dir)
    fixture_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{fixture_dir.name}-", dir=fixture_dir.parent)
    )
    try:
        for filename in FIXTURE_FILES:
            if not write_private_json(temporary / filename, payloads[filename]):
                raise PromotionError("FIXTURE_WRITE_FAILED")
            os.chmod(temporary / filename, 0o644)
        os.chmod(temporary, 0o755)
        validate_fixture(temporary)
        os.rename(temporary, fixture_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return validate_fixture(fixture_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    report = (
        validate_fixture(args.fixture_dir.resolve())
        if args.validate_only
        else promote(args.staging_dir.resolve(), args.fixture_dir.resolve())
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
