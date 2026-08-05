#!/usr/bin/env python3
"""Fail-closed preflight for the frozen H2 local-embedding clean-room data."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from treeguard.adapter import adapt_tree_document
from treeguard.hashing import canonical_digest

from generate_fire_h2_local_embedding_calibration import (
    CANDIDATE_COUNTS,
    EXECUTION_COUNTS,
    GENERATOR_SEED,
    GENERATOR_VERSION,
    NON_LITERAL_EXECUTION_COUNTS,
    SILVER_PASS_CODES,
    SOURCE_CLASS,
    TREE_NODE_COUNT,
    H2DataError,
    select_execution_ids,
)


PREFLIGHT_SCHEMA_VERSION = "treeguard.h2-local-data-preflight.v1"
REQUIRED_FILES = (
    "tree.v1.json",
    "scenario-candidates.v1.json",
    "candidate-oracle-sidecar.v1.json",
    "silver-review.v1.json",
    "scenarios.v1.json",
    "oracle-sidecar.v1.json",
    "manifest.v1.json",
)


class H2PreflightError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _load(path: Path) -> Any:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise H2PreflightError("H2_PREFLIGHT_FILE_INVALID")
        return json.loads(path.read_text(encoding="utf-8"))
    except H2PreflightError:
        raise
    except (OSError, json.JSONDecodeError):
        raise H2PreflightError("H2_PREFLIGHT_FILE_INVALID") from None


def _verify_hash(artifact: Mapping[str, Any], field: str) -> None:
    if not isinstance(artifact, dict) or not isinstance(artifact.get(field), str):
        raise H2PreflightError("H2_PREFLIGHT_HASH_INVALID")
    payload = {key: value for key, value in artifact.items() if key != field}
    if canonical_digest(payload) != artifact[field]:
        raise H2PreflightError("H2_PREFLIGHT_HASH_INVALID")


def _classification(artifact: Mapping[str, Any]) -> None:
    if (
        artifact.get("source_class") != SOURCE_CLASS
        or artifact.get("fictional") is not True
        or artifact.get("derived_from_real") is not False
        or artifact.get("gold_eligible") is not False
        or artifact.get("patch_eligible") is not False
    ):
        raise H2PreflightError("H2_PREFLIGHT_CLASSIFICATION_INVALID")


def _contains_value_envelope(value: Any) -> bool:
    if isinstance(value, dict):
        if "value" in value:
            return True
        return any(_contains_value_envelope(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value_envelope(item) for item in value)
    return False


def _counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    return dict(Counter(item.get("category") for item in rows))


def _oracle_entry_valid(entry: Mapping[str, Any], node_ids: set[str]) -> bool:
    oracle_type = entry.get("oracle_type")
    if oracle_type == "TARGET":
        return (
            set(entry) == {"scenario_id", "oracle_type", "target_node_id"}
            and entry.get("target_node_id") in node_ids
        )
    if oracle_type == "HARD_NEGATIVE":
        excluded = entry.get("excluded_node_ids")
        return (
            set(entry) == {"scenario_id", "oracle_type", "excluded_node_ids"}
            and isinstance(excluded, list)
            and len(excluded) == 1
            and excluded[0] in node_ids
        )
    return (
        oracle_type == "EXPLICIT_EMPTY"
        and set(entry) == {"scenario_id", "oracle_type", "expected_empty_status"}
        and entry.get("expected_empty_status") == "NO_CANDIDATES"
    )


def validate_dataset(dataset_dir: Path) -> dict[str, Any]:
    if not dataset_dir.is_dir() or dataset_dir.is_symlink():
        raise H2PreflightError("H2_PREFLIGHT_DIRECTORY_INVALID")
    artifacts = {name: _load(dataset_dir / name) for name in REQUIRED_FILES}
    tree = artifacts["tree.v1.json"]
    candidates = artifacts["scenario-candidates.v1.json"]
    candidate_oracle = artifacts["candidate-oracle-sidecar.v1.json"]
    review = artifacts["silver-review.v1.json"]
    scenarios = artifacts["scenarios.v1.json"]
    oracle = artifacts["oracle-sidecar.v1.json"]
    manifest = artifacts["manifest.v1.json"]

    for artifact, field in (
        (candidates, "candidate_set_hash"),
        (candidate_oracle, "oracle_hash"),
        (review, "review_hash"),
        (scenarios, "scenario_set_hash"),
        (oracle, "oracle_hash"),
        (manifest, "manifest_hash"),
    ):
        _verify_hash(artifact, field)

    if _contains_value_envelope(tree):
        raise H2PreflightError("H2_PREFLIGHT_VALUE_ENVELOPE_PRESENT")
    tree_metadata = tree.get("metadata") if isinstance(tree, dict) else None
    if not isinstance(tree_metadata, dict):
        raise H2PreflightError("H2_PREFLIGHT_TREE_INVALID")
    _classification(tree_metadata)
    if (
        tree_metadata.get("map_type") != "resource"
        or tree_metadata.get("generator_version") != GENERATOR_VERSION
        or tree_metadata.get("generator_seed") != GENERATOR_SEED
    ):
        raise H2PreflightError("H2_PREFLIGHT_TREE_INVALID")
    imported = adapt_tree_document(tree, source_hint="h2-local-cleanroom")
    if (
        not imported.is_valid
        or imported.tree is None
        or not imported.tree.is_resource_map
        or imported.observed_node_count != TREE_NODE_COUNT
        or imported.observed_value_count != 0
        or len(imported.tree.root_node_ids) != 1
    ):
        raise H2PreflightError("H2_PREFLIGHT_TREE_INVALID")
    node_ids = {node.node_id for node in imported.tree.nodes}
    if len(node_ids) != TREE_NODE_COUNT:
        raise H2PreflightError("H2_PREFLIGHT_TREE_INVALID")

    _classification(candidates)
    candidate_rows = candidates.get("candidates")
    if (
        not isinstance(candidate_rows, list)
        or candidates.get("candidate_count") != 36
        or len(candidate_rows) != 36
        or candidates.get("category_counts") != CANDIDATE_COUNTS
        or _counts(candidate_rows) != CANDIDATE_COUNTS
    ):
        raise H2PreflightError("H2_CANDIDATE_QUOTA_INVALID")
    candidate_ids = [item.get("scenario_id") for item in candidate_rows]
    if len(candidate_ids) != len(set(candidate_ids)) or any(not isinstance(item, str) for item in candidate_ids):
        raise H2PreflightError("H2_CANDIDATE_ID_INVALID")
    for item in candidate_rows:
        _classification(item)
        request = item.get("request")
        annotations = item.get("role_annotations")
        if not isinstance(request, dict) or not isinstance(annotations, list) or not annotations:
            raise H2PreflightError("H2_CANDIDATE_CONTRACT_INVALID")
        requirement = request.get("requirement_text")
        if not isinstance(requirement, str) or any(
            not isinstance(annotation, dict)
            or set(annotation) != {"role", "text"}
            or annotation.get("role") not in {"TARGET", "SCOPE", "EXCLUSION"}
            or not isinstance(annotation.get("text"), str)
            or requirement.count(annotation["text"]) != 1
            for annotation in annotations
        ):
            raise H2PreflightError("H2_CANDIDATE_CONTRACT_INVALID")
        if sum(annotation["role"] == "TARGET" for annotation in annotations) != 1:
            raise H2PreflightError("H2_CANDIDATE_CONTRACT_INVALID")
    for category, required in CANDIDATE_COUNTS.items():
        orders = sorted(
            item.get("selection_order")
            for item in candidate_rows
            if item.get("category") == category
        )
        if orders != list(range(1, required + 1)):
            raise H2PreflightError("H2_CANDIDATE_QUOTA_INVALID")

    candidate_oracle_entries = candidate_oracle.get("entries")
    if (
        candidate_oracle.get("source_candidate_set_hash") != candidates["candidate_set_hash"]
        or candidate_oracle.get("entry_count") != 36
        or not isinstance(candidate_oracle_entries, list)
        or len(candidate_oracle_entries) != 36
        or {item.get("scenario_id") for item in candidate_oracle_entries} != set(candidate_ids)
        or any(not _oracle_entry_valid(item, node_ids) for item in candidate_oracle_entries)
    ):
        raise H2PreflightError("H2_CANDIDATE_ORACLE_INVALID")

    review_entries = review.get("entries")
    if (
        review.get("review_status") != "CODEX_SILVER_REVIEWED"
        or review.get("reviewer_role") != "CODEX_SILVER_REVIEWER"
        or review.get("gold_eligible") is not False
        or review.get("production_qualification") is not False
        or review.get("patch_eligible") is not False
        or review.get("source_candidate_set_hash") != candidates["candidate_set_hash"]
        or not isinstance(review_entries, list)
        or len(review_entries) != 36
        or {item.get("scenario_id") for item in review_entries} != set(candidate_ids)
        or any(item.get("decision") not in {"PASS", "REJECT"} for item in review_entries)
        or review.get("decision_counts")
        != dict(sorted(Counter(item.get("decision") for item in review_entries).items()))
    ):
        raise H2PreflightError("H2_SILVER_REVIEW_INVALID")
    for item in review_entries:
        expected_codes = list(SILVER_PASS_CODES) if item["decision"] == "PASS" else ["SILVER_REJECTED"]
        if set(item) != {"scenario_id", "decision", "reason_codes"} or item.get("reason_codes") != expected_codes:
            raise H2PreflightError("H2_SILVER_REVIEW_INVALID")

    scenario_rows = scenarios.get("scenarios")
    if (
        not isinstance(scenario_rows, list)
        or scenarios.get("execution_count") != 28
        or len(scenario_rows) != 28
        or scenarios.get("category_counts") != EXECUTION_COUNTS
        or _counts(scenario_rows) != EXECUTION_COUNTS
        or scenarios.get("non_literal_subtype_counts") != NON_LITERAL_EXECUTION_COUNTS
    ):
        raise H2PreflightError("H2_EXECUTION_QUOTA_INVALID")
    subtype_counts = Counter(
        item.get("subtype") for item in scenario_rows if item.get("category") == "NON_LITERAL"
    )
    if dict(subtype_counts) != NON_LITERAL_EXECUTION_COUNTS:
        raise H2PreflightError("H2_EXECUTION_QUOTA_INVALID")
    scenario_ids = [item.get("scenario_id") for item in scenario_rows]
    passed_ids = {
        item.get("scenario_id") for item in review_entries if item.get("decision") == "PASS"
    }
    try:
        expected_scenario_ids = select_execution_ids(review)
    except H2DataError:
        raise H2PreflightError("H2_SILVER_QUOTA_INSUFFICIENT") from None
    if (
        len(scenario_ids) != len(set(scenario_ids))
        or not set(scenario_ids) <= passed_ids
        or tuple(sorted(scenario_ids)) != expected_scenario_ids
    ):
        raise H2PreflightError("H2_SILVER_QUOTA_INSUFFICIENT")

    oracle_entries = oracle.get("entries")
    if (
        oracle.get("source_scenario_set_hash") != scenarios["scenario_set_hash"]
        or oracle.get("entry_count") != 28
        or not isinstance(oracle_entries, list)
        or len(oracle_entries) != 28
        or {item.get("scenario_id") for item in oracle_entries} != set(scenario_ids)
        or any(not _oracle_entry_valid(item, node_ids) for item in oracle_entries)
    ):
        raise H2PreflightError("H2_ORACLE_INVALID")

    public_text = json.dumps({"candidates": candidates, "scenarios": scenarios}, ensure_ascii=False)
    if any(key in public_text for key in ("target_node_id", "excluded_node_ids", "expected_empty_status")):
        raise H2PreflightError("H2_ORACLE_LEAKED")
    oracle_values = {
        value
        for entry in candidate_oracle_entries
        for value in (
            [entry["target_node_id"]]
            if "target_node_id" in entry
            else entry.get("excluded_node_ids", [entry.get("expected_empty_status")])
        )
        if isinstance(value, str)
    }
    if any(value in public_text for value in oracle_values):
        raise H2PreflightError("H2_ORACLE_LEAKED")

    _classification(manifest)
    expected_hashes = {
        "tree": canonical_digest(tree),
        "scenario_candidates": candidates["candidate_set_hash"],
        "candidate_oracle": candidate_oracle["oracle_hash"],
        "silver_review": review["review_hash"],
        "scenarios": scenarios["scenario_set_hash"],
        "oracle": oracle["oracle_hash"],
    }
    if (
        manifest.get("dataset_status") != "FROZEN_CODEX_SILVER"
        or manifest.get("embedding_used") is not False
        or manifest.get("a_baseline_status") != "NOT_RUN"
        or manifest.get("tree_node_count") != TREE_NODE_COUNT
        or manifest.get("candidate_count") != 36
        or manifest.get("candidate_category_counts") != CANDIDATE_COUNTS
        or manifest.get("execution_count") != 28
        or manifest.get("execution_category_counts") != EXECUTION_COUNTS
        or manifest.get("non_literal_subtype_counts") != NON_LITERAL_EXECUTION_COUNTS
        or manifest.get("artifact_hashes") != expected_hashes
    ):
        raise H2PreflightError("H2_MANIFEST_INVALID")

    report_payload = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "valid": True,
        "status": "FROZEN_CODEX_SILVER",
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "production_qualification": False,
        "patch_eligible": False,
        "embedding_used": False,
        "a_baseline_status": "NOT_RUN",
        "tree_node_count": TREE_NODE_COUNT,
        "value_envelope_count": 0,
        "candidate_count": 36,
        "execution_count": 28,
        "candidate_category_counts": dict(CANDIDATE_COUNTS),
        "execution_category_counts": dict(EXECUTION_COUNTS),
        "non_literal_subtype_counts": dict(NON_LITERAL_EXECUTION_COUNTS),
        "source_manifest_hash": manifest["manifest_hash"],
    }
    return {**report_payload, "preflight_hash": canonical_digest(report_payload)}


def write_report(dataset_dir: Path, report: Mapping[str, Any]) -> None:
    path = dataset_dir / "preflight-report.v1.json"
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
    except FileExistsError:
        raise H2PreflightError("H2_PREFLIGHT_REPORT_EXISTS") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = validate_dataset(args.dataset_dir)
        write_report(args.dataset_dir, report)
    except H2PreflightError as exc:
        print(json.dumps({"valid": False, "error_code": exc.code}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "valid": True,
                "status": report["status"],
                "candidate_count": report["candidate_count"],
                "execution_count": report["execution_count"],
                "embedding_used": False,
                "a_baseline_status": "NOT_RUN",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
