#!/usr/bin/env python3
"""Offline, aggregate-only preflight for the frozen M4 blind data fixture."""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from treeguard.adapter import load_tree_export  # noqa: E402
from treeguard.change_intent import (  # noqa: E402
    DRAFT_SCHEMA_VERSION as INTENT_DRAFT_SCHEMA_VERSION,
    REQUEST_SCHEMA_VERSION as INTENT_REQUEST_SCHEMA_VERSION,
)
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.retrieval import SCHEMA_VERSION as RETRIEVAL_SCHEMA_VERSION  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    CAPABILITY_OVERLAY_SCHEMA_VERSION,
    CAPABILITY_REPORT_SCHEMA_VERSION,
    CAPABILITY_RUN_SCHEMA_VERSION,
    ScenarioCapabilityOverlay,
    verify_capability_overlay_for_execution,
)
from treeguard.scenario_validation import (  # noqa: E402
    ACTION_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    ReviewedValidationScenario,
    ScenarioReviewAction,
)
from treeguard.semantic_recommendation import (  # noqa: E402
    DRAFT_SCHEMA_VERSION as RECOMMENDATION_DRAFT_SCHEMA_VERSION,
)
from treeguard.tree_understanding import (  # noqa: E402
    SCENARIO_BATCH_SCHEMA_VERSION,
    SCENARIO_PLAN_SCHEMA_VERSION,
    ScenarioPreparationBatch,
    build_scenario_preparation_plan,
    build_scenario_preparation_projection,
    build_tree_diagnostic_profile,
)


DEFAULT_FIXTURE_DIR = (
    PROJECT_ROOT / "tests/fixtures/fictional/fire_validation_m4_blind"
)
BASE_FIXTURE_DIR = PROJECT_ROOT / "tests/fixtures/fictional/fire_validation"
TREE_PATH = BASE_FIXTURE_DIR / "tree-medium.json"
BASE_MANIFEST_PATH = BASE_FIXTURE_DIR / "manifest.json"

DATASET_REF = "fictional-fire-m4-blind-v1"
FEATURE_CONTRACT_COMMIT = (
    "d7dff7994167d606aa2e3269c7606860bf22fc41"
)
TREE_DIGEST = (
    "50e6ed21679e105651136d05262434ea56c3beefdf03a2c4941136430e003352"
)
TREE_FILE_SHA256 = (
    "d4ffbc91c462d94cc2daa5246859e8ea0f3d02fd20f1761e8f910a1fcb1d5b0b"
)
PLAN_HASH = (
    "b5364de36637719ab75215b20c6b55cefd4ae1a5c11d38aa8bc985a7400dba5b"
)
SOURCE_CANDIDATE_BATCH_SHA256 = (
    "02a95c2af49f82ae3577d6dff6d4974304ea7312a4f327cd0a116f9c26c9391f"
)
SOURCE_REVIEW_PACKET_SHA256 = (
    "4342da50a910b4a41ebe7c93428b9264a631e5c77ecec8b3ae6ac571164f0547"
)
FROZEN_ORACLE_SIDECAR_SHA256 = (
    "7f467c0e1c0c2fc1a1666aeb95d50975be41f3812c7e77920e005fa88569cce0"
)
SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
SIDECAR_SCHEMA_VERSION = "fire-m4-blind-oracle-sidecar.v1"
MANIFEST_SCHEMA_VERSION = "fire-m4-blind-dataset-manifest.v1"
REPORT_SCHEMA_VERSION = "fire-m4-blind-data-preflight-report.v1"
RUBRIC_VERSION = "fire-m4-blind-human-review.v1"

EXPECTED_UNITS = tuple(f"U{index:03d}" for index in range(1, 12))
EXECUTION_UNITS = (
    "U001",
    "U002",
    "U003",
    "U004",
    "U005",
    "U007",
    "U008",
    "U009",
)
EXECUTION_REFS = tuple(f"M4-{unit_ref}" for unit_ref in EXECUTION_UNITS)
SOURCE_CELLS = {
    "U001": "B01",
    "U002": "B03",
    "U003": "B04",
    "U004": "B05",
    "U005": "B08-CANDIDATE-A",
    "U006": "B08-CANDIDATE-B",
    "U007": "B02",
    "U008": "B06",
    "U009": "B07",
    "U010": "B08F-SPARE-A",
    "U011": "B08F-SPARE-B",
}
EXECUTION_CELLS = {
    "U001": "B01",
    "U002": "B03",
    "U003": "B04",
    "U004": "B05",
    "U005": "B08",
    "U007": "B02",
    "U008": "B06",
    "U009": "B07",
}
RUBRIC_CHECKS = (
    "DATA_BOUNDARY",
    "SOURCE_BINDING",
    "INDEPENDENCE",
    "ANSWERABILITY",
    "COVERAGE_VALUE",
    "INTENT_CORRECTNESS",
    "RETRIEVAL_CORRECTNESS",
    "RECOMMENDATION_CORRECTNESS",
    "ORACLE_HIDING",
    "DETERMINISM",
)
CONTRACT_VERSIONS = {
    "scenario_preparation_batch": SCENARIO_BATCH_SCHEMA_VERSION,
    "scenario_preparation_plan": SCENARIO_PLAN_SCHEMA_VERSION,
    "scenario_review_action": ACTION_SCHEMA_VERSION,
    "scenario_review_record": RECORD_SCHEMA_VERSION,
    "capability_overlay": CAPABILITY_OVERLAY_SCHEMA_VERSION,
    "capability_run": CAPABILITY_RUN_SCHEMA_VERSION,
    "capability_report": CAPABILITY_REPORT_SCHEMA_VERSION,
    "intent_request": INTENT_REQUEST_SCHEMA_VERSION,
    "intent_draft": INTENT_DRAFT_SCHEMA_VERSION,
    "retrieval": RETRIEVAL_SCHEMA_VERSION,
    "recommendation": RECOMMENDATION_DRAFT_SCHEMA_VERSION,
}

_MANIFEST_KEYS = {
    "schema_version",
    "dataset_ref",
    "run_ref",
    "primary_role",
    "source_class",
    "fictional",
    "derived_from_real",
    "gold_eligible",
    "patch_eligible",
    "feature_contract_commit",
    "contract_versions",
    "base_dataset_ref",
    "category_id",
    "variant_ref",
    "resource_id",
    "tree_version",
    "tree_snapshot_hash",
    "tree_fixture_sha256",
    "scenario_plan_hash",
    "source_candidate_batch_sha256",
    "source_review_packet_sha256",
    "planned_unit_count",
    "candidate_review_limit",
    "reviewed_candidate_count",
    "accepted_candidate_count",
    "revised_accepted_candidate_count",
    "rejected_candidate_count",
    "execution_limit",
    "execution_count",
    "full_chain_count",
    "clarification_count",
    "clarification_coverage_status",
    "coverage_cells",
    "human_review_elapsed_minutes",
    "review_time_limit_minutes",
    "review_round",
    "dual_review_limit",
    "blocking_finding_count",
    "lifecycle_status",
    "oracle_sidecar_file",
    "oracle_sidecar_sha256",
    "limitations",
}
_SIDECAR_KEYS = {
    "schema_version",
    "dataset_ref",
    "base_dataset_ref",
    "variant_ref",
    "resource_id",
    "tree_version",
    "source_class",
    "fictional",
    "derived_from_real",
    "gold_eligible",
    "patch_eligible",
    "feature_contract_commit",
    "contract_versions",
    "tree_snapshot_hash",
    "tree_fixture_sha256",
    "scenario_plan_hash",
    "source_candidate_batch_sha256",
    "source_review_packet_sha256",
    "reviewer_ref",
    "recorded_at",
    "review_round",
    "rubric_version",
    "human_review_elapsed_minutes",
    "time_limit_minutes",
    "dual_review_limit",
    "review_status",
    "lifecycle_status",
    "clarification_coverage_status",
    "execution_scenario_refs",
    "scenario_preparation_batch",
    "items",
}
_ITEM_KEYS = {
    "scenario_ref",
    "source_coverage_cell",
    "execution_coverage_cell",
    "plan_unit_ref",
    "candidate_ref",
    "candidate_digest",
    "review_status",
    "review_round",
    "execution_eligible",
    "finding_codes",
    "rubric_passed",
    "action",
    "reviewed",
    "overlay",
}
_FORBIDDEN_SIDECAR_KEYS = {
    "acceptable_candidate_refs",
    "prompt",
    "response",
    "selected_candidate_ref",
    "trace",
}


class M4BlindDataError(RuntimeError):
    """One fixed data-only validation failure safe for aggregate reporting."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def _is_exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _read_canonical_json(
    path: Path, *, max_bytes: int, failure_code: str
) -> tuple[Any, bytes]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > max_bytes:
            raise ValueError
        payload = strict_json_loads(raw.decode("utf-8"))
        if raw != canonical_json_bytes(payload):
            raise ValueError
    except (OSError, UnicodeError, ValueError):
        raise M4BlindDataError(failure_code) from None
    return payload, raw


def _require_exact_dict(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise M4BlindDataError(code)
    return value


def _contains_forbidden_sidecar_key(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(set(value) & _FORBIDDEN_SIDECAR_KEYS) or any(
            _contains_forbidden_sidecar_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_sidecar_key(item) for item in value)
    return False


def _validate_boundary(payload: dict[str, Any]) -> None:
    if (
        payload.get("source_class") != SOURCE_CLASS
        or payload.get("fictional") is not True
        or payload.get("derived_from_real") is not False
        or payload.get("gold_eligible") is not False
        or payload.get("patch_eligible") is not False
    ):
        raise M4BlindDataError("DATASET_BOUNDARY_INVALID")


def _validate_manifest_and_sidecar_bindings(
    manifest: dict[str, Any],
    sidecar: dict[str, Any],
) -> None:
    _validate_boundary(manifest)
    _validate_boundary(sidecar)
    common_expected = {
        "dataset_ref": DATASET_REF,
        "base_dataset_ref": "fictional-fire-governance-validation",
        "variant_ref": "medium",
        "resource_id": "fictional-fire-02-medium",
        "tree_version": "FFV-MEDIUM-V2",
        "feature_contract_commit": FEATURE_CONTRACT_COMMIT,
        "tree_snapshot_hash": TREE_DIGEST,
        "tree_fixture_sha256": TREE_FILE_SHA256,
        "scenario_plan_hash": PLAN_HASH,
    }
    if any(
        manifest.get(key) != expected or sidecar.get(key) != expected
        for key, expected in common_expected.items()
    ):
        raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")
    if (
        manifest["contract_versions"] != CONTRACT_VERSIONS
        or sidecar["contract_versions"] != CONTRACT_VERSIONS
    ):
        raise M4BlindDataError("DATASET_CONTRACT_BINDING_INVALID")
    review_packet_sha256 = sidecar["source_review_packet_sha256"]
    if (
        manifest["source_candidate_batch_sha256"]
        != SOURCE_CANDIDATE_BATCH_SHA256
        or sidecar["source_candidate_batch_sha256"]
        != SOURCE_CANDIDATE_BATCH_SHA256
        or manifest["source_review_packet_sha256"]
        != SOURCE_REVIEW_PACKET_SHA256
        or review_packet_sha256 != SOURCE_REVIEW_PACKET_SHA256
    ):
        raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")


def _validate_review_budget(
    manifest: dict[str, Any], sidecar: dict[str, Any]
) -> None:
    elapsed = manifest["human_review_elapsed_minutes"]
    if (
        not _is_exact_int(elapsed, 20)
        or not _is_exact_int(sidecar["human_review_elapsed_minutes"], 20)
        or not _is_exact_int(manifest["review_time_limit_minutes"], 150)
        or not _is_exact_int(sidecar["time_limit_minutes"], 150)
        or not _is_exact_int(manifest["dual_review_limit"], 0)
        or not _is_exact_int(sidecar["dual_review_limit"], 0)
        or not _is_exact_int(manifest["review_round"], 1)
        or not _is_exact_int(sidecar["review_round"], 1)
    ):
        raise M4BlindDataError("DATASET_REVIEW_BUDGET_EXCEEDED")


def load_bound_tree_profile_and_plan():
    try:
        base_manifest, _ = _read_canonical_json(
            BASE_MANIFEST_PATH,
            max_bytes=200_000,
            failure_code="DATASET_SOURCE_BINDING_INVALID",
        )
        medium = [
            item
            for item in base_manifest.get("tiers", [])
            if isinstance(item, dict) and item.get("tier") == "medium"
        ]
        if (
            base_manifest.get("dataset_id")
            != "fictional-fire-governance-validation"
            or base_manifest.get("source_policy") != "PUBLIC_CATEGORY_CLEAN_ROOM"
            or len(medium) != 1
            or medium[0].get("tree_file") != "tree-medium.json"
            or medium[0].get("node_count") != 401
            or medium[0].get("benchmark_role") != "semantic_interference"
        ):
            raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")
        tree_bytes = TREE_PATH.read_bytes()
        if _digest(tree_bytes) != TREE_FILE_SHA256:
            raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")
        tree_payload = strict_json_loads(tree_bytes.decode("utf-8"))
        if tree_payload.get("metadata", {}).get("version") != "FFV-MEDIUM-V2":
            raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")
        result = load_tree_export(TREE_PATH)
        if (
            result.tree is None
            or result.observed_node_count != 401
            or result.observed_value_count != 0
            or result.tree.snapshot_hash != TREE_DIGEST
        ):
            raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")
        tree = result.tree
        profile = build_tree_diagnostic_profile(tree)
        plan = build_scenario_preparation_plan(tree, profile)
        if (
            plan.plan_hash != PLAN_HASH
            or tuple(unit.plan_unit_ref for unit in plan.units) != EXPECTED_UNITS
        ):
            raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")
        return tree, profile, plan
    except M4BlindDataError:
        raise
    except (OSError, TypeError, ValueError):
        raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID") from None


def _validate_items(
    sidecar: dict[str, Any],
    batch: ScenarioPreparationBatch,
    tree: Any,
    profile: Any,
    plan: Any,
) -> tuple[int, int, tuple[tuple[Any, ReviewedValidationScenario], ...]]:
    items = sidecar["items"]
    if not isinstance(items, list) or len(items) != 11:
        raise M4BlindDataError("DATASET_EXECUTION_ACCOUNTING_INVALID")
    candidate_by_unit = {
        candidate.plan_unit_ref: candidate for candidate in batch.candidates
    }
    if tuple(candidate_by_unit) != EXPECTED_UNITS:
        raise M4BlindDataError("DATASET_PLAN_ACCOUNTING_INVALID")

    execution_refs: list[str] = []
    execution_cells: set[str] = set()
    temporary_candidate_refs = {
        candidate.candidate_ref for candidate in batch.candidates
    }
    proceed_count = 0
    clarify_count = 0
    execution_overlays: list[tuple[Any, ReviewedValidationScenario]] = []
    for expected_unit, raw_item in zip(EXPECTED_UNITS, items, strict=True):
        item = _require_exact_dict(
            raw_item, _ITEM_KEYS, "DATASET_SIDECAR_FIELDS_INVALID"
        )
        candidate = candidate_by_unit[expected_unit]
        expected_execution = expected_unit in EXECUTION_UNITS
        if (
            item["scenario_ref"] != f"M4-{expected_unit}"
            or item["plan_unit_ref"] != expected_unit
            or item["candidate_ref"] != candidate.candidate_ref
            or item["candidate_digest"] != candidate.draft.draft_hash
            or item["review_status"] != "ACCEPTED"
            or not _is_exact_int(item["review_round"], 1)
            or item["execution_eligible"] is not expected_execution
            or item["execution_coverage_cell"]
            != EXECUTION_CELLS.get(expected_unit)
            or item["source_coverage_cell"] != SOURCE_CELLS[expected_unit]
            or item["finding_codes"] != []
            or item["rubric_passed"] != list(RUBRIC_CHECKS)
        ):
            raise M4BlindDataError("DATASET_EXECUTION_ACCOUNTING_INVALID")
        try:
            projection = build_scenario_preparation_projection(
                tree, profile, plan, expected_unit
            )
            action = ScenarioReviewAction.from_dict(item["action"])
            reviewed = ReviewedValidationScenario.from_dict(
                item["reviewed"],
                action,
                batch,
                candidate,
                projection,
                plan,
                profile,
                tree,
            )
            if (
                action.reviewer_ref != sidecar["reviewer_ref"]
                or action.recorded_at != sidecar["recorded_at"]
                or reviewed.reviewer_ref != sidecar["reviewer_ref"]
                or reviewed.recorded_at != sidecar["recorded_at"]
            ):
                raise ValueError
            if expected_execution:
                if not isinstance(item["overlay"], dict):
                    raise M4BlindDataError(
                        "DATASET_EXECUTION_ACCOUNTING_INVALID"
                    )
                overlay = ScenarioCapabilityOverlay.from_dict(
                    item["overlay"], reviewed, plan, tree
                )
                if (
                    overlay.status != "ACCEPTED"
                    or overlay.reviewer_ref != sidecar["reviewer_ref"]
                    or overlay.recorded_at != sidecar["recorded_at"]
                    or overlay.review_round != 1
                ):
                    raise ValueError
                oracle = overlay.oracle
                targets = set(oracle.retrieval.acceptable_node_ids)
                targets.update(
                    outcome.target_node_id
                    for outcome in oracle.recommendation.acceptable_outcomes
                    if outcome.target_node_id is not None
                )
                if targets & temporary_candidate_refs:
                    raise M4BlindDataError("DATASET_TEMPORARY_TARGET_REF_FOUND")
                execution_refs.append(item["scenario_ref"])
                execution_cells.add(item["execution_coverage_cell"])
                if oracle.expected_route == "PROCEED":
                    proceed_count += 1
                    if (
                        not oracle.retrieval.applicable
                        or not oracle.recommendation.applicable
                        or oracle.retrieval.top_k != 8
                    ):
                        raise M4BlindDataError(
                            "DATASET_EXECUTION_ACCOUNTING_INVALID"
                        )
                elif oracle.expected_route == "CLARIFY":
                    clarify_count += 1
                    if (
                        item["execution_coverage_cell"] != "B08"
                        or oracle.retrieval.applicable
                        or oracle.recommendation.applicable
                    ):
                        raise M4BlindDataError(
                            "DATASET_EXECUTION_ACCOUNTING_INVALID"
                        )
                else:
                    raise M4BlindDataError(
                        "DATASET_EXECUTION_ACCOUNTING_INVALID"
                    )
                execution_overlays.append((overlay, reviewed))
            elif item["overlay"] is not None:
                raise M4BlindDataError("DATASET_EXECUTION_ACCOUNTING_INVALID")
        except M4BlindDataError:
            raise
        except (TypeError, ValueError, RuntimeError):
            raise M4BlindDataError("DATASET_CONTRACT_INTEGRITY_FAILURE") from None

    if (
        tuple(execution_refs) != EXECUTION_REFS
        or sidecar["execution_scenario_refs"] != list(EXECUTION_REFS)
        or execution_cells != {f"B{index:02d}" for index in range(1, 9)}
        or proceed_count != 7
        or clarify_count != 1
    ):
        raise M4BlindDataError("DATASET_EXECUTION_ACCOUNTING_INVALID")
    return proceed_count, clarify_count, tuple(execution_overlays)


def validate_fixture(
    fixture_dir: str | Path = DEFAULT_FIXTURE_DIR,
) -> dict[str, Any]:
    fixture_path = Path(fixture_dir)
    try:
        entries = tuple(fixture_path.iterdir())
    except OSError:
        raise M4BlindDataError("DATASET_FIXTURE_FILES_INVALID") from None
    names = {path.name for path in entries}
    if (
        names != {"manifest.json", "oracle-sidecar.json"}
        or any(path.is_symlink() or not path.is_file() for path in entries)
    ):
        raise M4BlindDataError("DATASET_FIXTURE_FILES_INVALID")

    manifest, _ = _read_canonical_json(
        fixture_path / "manifest.json",
        max_bytes=200_000,
        failure_code="DATASET_MANIFEST_INVALID",
    )
    manifest = _require_exact_dict(
        manifest, _MANIFEST_KEYS, "DATASET_MANIFEST_FIELDS_INVALID"
    )
    sidecar, sidecar_bytes = _read_canonical_json(
        fixture_path / "oracle-sidecar.json",
        max_bytes=2_000_000,
        failure_code="DATASET_SIDECAR_INVALID",
    )
    if (
        manifest["oracle_sidecar_file"] != "oracle-sidecar.json"
        or manifest["oracle_sidecar_sha256"] != _digest(sidecar_bytes)
    ):
        raise M4BlindDataError("DATASET_FIXTURE_SHA_MISMATCH")
    sidecar = _require_exact_dict(
        sidecar, _SIDECAR_KEYS, "DATASET_SIDECAR_FIELDS_INVALID"
    )
    if _contains_forbidden_sidecar_key(sidecar):
        raise M4BlindDataError("DATASET_BOUNDARY_INVALID")

    if (
        manifest["schema_version"] != MANIFEST_SCHEMA_VERSION
        or sidecar["schema_version"] != SIDECAR_SCHEMA_VERSION
        or manifest["run_ref"] != "fire-m4-blind-v1"
        or manifest["primary_role"] != "SEMANTIC_CHALLENGE"
        or manifest["category_id"] != "fictional-fire-validation-category"
        or manifest["lifecycle_status"] != "FROZEN"
        or sidecar["lifecycle_status"] != "FROZEN"
        or sidecar["review_status"] != "ACCEPTED"
        or sidecar["rubric_version"] != RUBRIC_VERSION
        or manifest["clarification_coverage_status"] != "COVERED"
        or sidecar["clarification_coverage_status"] != "COVERED"
    ):
        raise M4BlindDataError("DATASET_CONTRACT_BINDING_INVALID")
    _validate_manifest_and_sidecar_bindings(manifest, sidecar)
    _validate_review_budget(manifest, sidecar)
    tree, profile, plan = load_bound_tree_profile_and_plan()

    batch_payload = sidecar["scenario_preparation_batch"]
    if (
        _digest(canonical_json_bytes(batch_payload))
        != sidecar["source_candidate_batch_sha256"]
    ):
        raise M4BlindDataError("DATASET_SOURCE_BINDING_INVALID")
    try:
        batch = ScenarioPreparationBatch.from_dict(
            batch_payload, plan, profile, tree
        )
    except (TypeError, ValueError, RuntimeError):
        raise M4BlindDataError("DATASET_CONTRACT_INTEGRITY_FAILURE") from None
    if (
        batch.completed_unit_count != 11
        or batch.failed_unit_count != 0
        or batch.not_executed_unit_count != 0
    ):
        raise M4BlindDataError("DATASET_PLAN_ACCOUNTING_INVALID")
    proceed_count, clarify_count, execution_overlays = _validate_items(
        sidecar, batch, tree, profile, plan
    )

    expected_manifest_values = {
        "planned_unit_count": 11,
        "candidate_review_limit": 11,
        "reviewed_candidate_count": 11,
        "accepted_candidate_count": 11,
        "revised_accepted_candidate_count": 0,
        "rejected_candidate_count": 0,
        "execution_limit": 8,
        "execution_count": 8,
        "full_chain_count": proceed_count,
        "clarification_count": clarify_count,
        "blocking_finding_count": 0,
        "coverage_cells": [f"B{index:02d}" for index in range(1, 9)],
        "limitations": [
            "GO_SHADOW_ONLY_NOT_PRODUCTION_ACCURACY",
            "CLEANROOM_SYNTHETIC_NOT_GOLD",
            "NO_PATCH_OR_PRODUCTION_WRITE_AUTHORITY",
        ],
    }
    if any(
        (
            not _is_exact_int(manifest.get(key), expected)
            if isinstance(expected, int) and not isinstance(expected, bool)
            else manifest.get(key) != expected
        )
        for key, expected in expected_manifest_values.items()
    ):
        raise M4BlindDataError("DATASET_EXECUTION_ACCOUNTING_INVALID")
    if (
        manifest["oracle_sidecar_sha256"] != FROZEN_ORACLE_SIDECAR_SHA256
        or _digest(sidecar_bytes) != FROZEN_ORACLE_SIDECAR_SHA256
    ):
        raise M4BlindDataError("DATASET_FIXTURE_SHA_MISMATCH")
    try:
        for overlay, reviewed in execution_overlays:
            verify_capability_overlay_for_execution(
                overlay, reviewed, plan, tree
            )
    except (TypeError, ValueError, RuntimeError):
        raise M4BlindDataError("DATASET_CONTRACT_INTEGRITY_FAILURE") from None

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_ref": DATASET_REF,
        "source_class": "DETERMINISTIC_REPORT",
        "status": "PASS",
        "planned_unit_count": 11,
        "reviewed_candidate_count": 11,
        "accepted_candidate_count": 11,
        "execution_count": 8,
        "full_chain_count": proceed_count,
        "clarification_count": clarify_count,
        "blocking_finding_count": 0,
        "finding_counts": {},
        "checks": [
            "BOUNDARY_POLICY",
            "SOURCE_BINDING",
            "CONTRACT_BINDING",
            "TREE_AND_PLAN_REPLAY",
            "CANDIDATE_BATCH_REPLAY",
            "REVIEW_ACTION_REPLAY",
            "REVIEWED_RECORD_REPLAY",
            "CAPABILITY_OVERLAY_REPLAY",
            "EXECUTION_ACCOUNTING",
            "PUBLIC_OUTPUT_ALLOWLIST",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = validate_fixture(args.fixture_dir)
    except M4BlindDataError as error:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "dataset_ref": DATASET_REF,
            "source_class": "DETERMINISTIC_REPORT",
            "status": "FAIL",
            "finding_counts": {error.code: 1},
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1
    except Exception:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "dataset_ref": DATASET_REF,
            "source_class": "DETERMINISTIC_REPORT",
            "status": "FAIL",
            "finding_counts": {"DATASET_PREFLIGHT_INTERNAL_FAILURE": 1},
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
