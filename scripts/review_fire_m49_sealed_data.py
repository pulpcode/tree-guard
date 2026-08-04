#!/usr/bin/env python3
"""Record the bounded Codex-assisted Silver review of the M4.9 candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.generate_fire_m49_sealed_data import DATASET_REF, OUTPUT_DIR
from scripts.preflight_fire_m49_sealed_data import run_preflight
from treeguard.hashing import canonical_digest
from treeguard.private_io import read_private_json, write_private_json

REVIEWER_REF = "codex-m49-silver-review"
RECORDED_AT = "2026-08-04T00:00:00Z"


def build_review(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    preflight = run_preflight(directory)
    candidates = read_private_json(directory / "scenario-candidates.json", max_bytes=2_000_000)
    sidecar = read_private_json(directory / "oracle-sidecar.json", max_bytes=5_000_000)
    expected_refs = [f"P{i:02d}" for i in range(1, 19)] + [f"C{i:02d}" for i in range(1, 7)] + [f"R{i:02d}" for i in range(1, 7)]
    by_ref = {item["scenario_ref"]: item for item in candidates["items"]}
    oracle_by_ref = {item["scenario_ref"]: item for item in sidecar["items"]}
    if set(by_ref) != set(expected_refs) or set(oracle_by_ref) != set(expected_refs):
        raise RuntimeError("review source references do not match the frozen batch")

    review_items = []
    for ref in expected_refs:
        item = {
            "scenario_ref": ref,
            "source_candidate_digest": by_ref[ref]["candidate_digest"],
            "source_oracle_item_digest": oracle_by_ref[ref]["oracle_item_digest"],
            "decision": "ACCEPTED",
            "severity": "NONE",
            "finding_codes": [],
            "execution_eligible": False,
        }
        item["review_item_digest"] = canonical_digest(item)
        review_items.append(item)

    silver_review = {
        "schema_version": "fire-m49-sealed-silver-review.v1",
        "dataset_ref": DATASET_REF,
        "status": "SILVER_ACCEPTED",
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "assessment_authority": "CODEX_ASSISTED",
        "reviewer_ref": REVIEWER_REF,
        "reviewer_independence": False,
        "authoritative_gold_review": False,
        "semantic_approval": False,
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "execution_eligible": False,
        "recorded_at": RECORDED_AT,
        "review_round": 4,
        "source_tree_snapshot_hash": preflight["tree_snapshot_hash"],
        "source_candidate_batch_digest": preflight["candidate_batch_digest"],
        "source_oracle_sidecar_digest": preflight["oracle_sidecar_digest"],
        "reviewed_count": len(review_items),
        "accepted_count": len(review_items),
        "rejected_count": 0,
        "items": review_items,
    }
    silver_review["review_digest"] = canonical_digest(silver_review)

    critic_report = {
        "schema_version": "fire-m49-sealed-critic-report.v1",
        "dataset_ref": DATASET_REF,
        "status": "PASS",
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "authoritative_gold_review": False,
        "reviewer_independence": False,
        "final_review_round": 4,
        "reviewed_count": len(review_items),
        "accepted_count": len(review_items),
        "blocking_finding_count": 0,
        "repair_history": [
            {
                "round": 1,
                "outcome": "REJECTED_AND_REGENERATED",
                "finding_code_counts": {
                    "FIELD_TYPE_SEMANTICS_INVALID": 4,
                    "TOP_K_TARGET_SEMANTICS_INVALID": 1,
                },
            },
            {
                "round": 2,
                "outcome": "REJECTED_AND_REGENERATED",
                "finding_code_counts": {
                    "RESERVE_RISK_CONTRACT_MISMATCH": 4,
                    "TOP_K_REQUIREMENT_ALIGNMENT_WEAK": 1,
                },
            },
            {
                "round": 3,
                "outcome": "REJECTED_AND_REGENERATED",
                "finding_code_counts": {
                    "FORMAL_BRANCH_CAP_EXCEEDED": 1,
                },
            },
            {
                "round": 4,
                "outcome": "SILVER_ACCEPTED",
                "finding_code_counts": {},
            },
        ],
        "source_tree_snapshot_hash": preflight["tree_snapshot_hash"],
        "source_candidate_batch_digest": preflight["candidate_batch_digest"],
        "source_oracle_sidecar_digest": preflight["oracle_sidecar_digest"],
        "silver_review_digest": silver_review["review_digest"],
        "next_gate": "EXPLICIT_FIXTURE_PROMOTION_APPROVAL",
    }
    critic_report["report_digest"] = canonical_digest(critic_report)
    return silver_review, critic_report


def promotion_readiness(
    silver_review: dict[str, Any],
    critic_report: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": "fire-m49-sealed-promotion-readiness.v1",
        "dataset_ref": DATASET_REF,
        "status": "READY_FOR_EXPLICIT_PROMOTION_REVIEW",
        "l1_machine_validation": "PASS",
        "l2_semantic_review": "PASS",
        "silver_authorization": "CODEX_ASSISTED_SILVER",
        "gold_eligible": False,
        "gate_eligible": False,
        "execution_eligible": False,
        "explicit_promotion_approval": False,
        "fixture_promoted": False,
        "experiment_executed": False,
        "source_silver_review_digest": silver_review["review_digest"],
        "source_critic_report_digest": critic_report["report_digest"],
        "next_gate": "EXPLICIT_FIXTURE_PROMOTION_APPROVAL",
    }
    payload["readiness_digest"] = canonical_digest(payload)
    return payload


def publish_or_verify(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        if read_private_json(path, max_bytes=5_000_000) != payload:
            raise RuntimeError(f"existing {path.name} does not match the review")
        return
    if not write_private_json(path, payload):
        raise RuntimeError(f"failed to publish {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    silver_review, critic_report = build_review(directory)
    if args.write:
        publish_or_verify(directory / "silver-review.json", silver_review)
        publish_or_verify(directory / "critic-report.json", critic_report)
        publish_or_verify(
            directory / "promotion-readiness.json",
            promotion_readiness(silver_review, critic_report),
        )
    print(json.dumps({"status": critic_report["status"], "quality_tier": critic_report["quality_tier"], "reviewed_count": critic_report["reviewed_count"], "accepted_count": critic_report["accepted_count"], "blocking_finding_count": critic_report["blocking_finding_count"], "next_gate": critic_report["next_gate"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
