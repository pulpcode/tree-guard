#!/usr/bin/env python3
"""Run the frozen aggregate-only R2 lexical A calibration."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

from treeguard.adapter import adapt_tree_document
from treeguard.change_intent import IntentConfirmation, IntentContent, IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads
from treeguard.retrieval_role_tolerant import (
    ALGORITHM_VERSION,
    build_boundary_tolerant_role_candidate_set,
)
from treeguard.retrieval_roles import build_retrieval_role_evidence


DATA_COMMIT = "3af7671ce4bd5e32179b94605e0f3b16f3275880"
MANIFEST_HASH = "61533ab2dcd7c5d982da9c994076484e689c1de56b726ddf2ff508f94dd3712f"
REPORT_VERSION = "treeguard.h2-local-lexical-a-aggregate.v1"
LEXICAL_TOP_K = 40
RESULT_TOP_K = 20
HARD_NEGATIVE_TOP_K = 8
_FIXED_DRAFT_HASH = "0" * 64
_FIXED_ACTION_HASH = "1" * 64
_FIXED_REVIEWER = "codex-silver-calibration"
_FIXED_RECORDED_AT = "2026-08-05T00:00:00Z"
_PUBLIC_FILES = ("manifest.v1.json", "tree.v1.json", "scenarios.v1.json")
MAX_ARTIFACT_BYTES = 32_000_000
_RESULT_KEYS = {
    "schema_version",
    "status",
    "data_commit",
    "source_manifest_hash",
    "lexical_algorithm_version",
    "lexical_top_k",
    "result_top_k",
    "hard_negative_top_k",
    "embedding_used",
    "provider_called",
    "index_used",
    "gold_eligible",
    "production_qualification",
    "patch_eligible",
    "targeted_count",
    "recall_at_20",
    "recall_at_8",
    "mrr_at_20",
    "non_literal_recall_at_20",
    "hard_negative_top_8",
    "explicit_empty",
}


class H2LexicalAError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def load_json_artifact(path: Path, error_code: str) -> Any:
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or path.is_symlink()
            or info.st_size > MAX_ARTIFACT_BYTES
        ):
            raise H2LexicalAError(error_code)
        return strict_json_loads(path.read_bytes().decode("utf-8"))
    except H2LexicalAError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise H2LexicalAError(error_code) from None


def verify_self_hash(artifact: Mapping[str, Any], field: str, code: str) -> None:
    value = artifact.get(field)
    payload = {key: item for key, item in artifact.items() if key != field}
    if not isinstance(value, str) or canonical_digest(payload) != value:
        raise H2LexicalAError(code)


def load_public_inputs(dataset_dir: Path) -> tuple[Any, list[Mapping[str, Any]]]:
    if not dataset_dir.is_dir() or dataset_dir.is_symlink():
        raise H2LexicalAError("H2_A_DATASET_INVALID")
    artifacts = {
        name: load_json_artifact(dataset_dir / name, "H2_A_DATASET_INVALID")
        for name in _PUBLIC_FILES
    }
    manifest = artifacts["manifest.v1.json"]
    scenarios = artifacts["scenarios.v1.json"]
    tree_document = artifacts["tree.v1.json"]
    if not isinstance(manifest, dict) or not isinstance(scenarios, dict):
        raise H2LexicalAError("H2_A_DATASET_INVALID")
    verify_self_hash(manifest, "manifest_hash", "H2_A_MANIFEST_INVALID")
    verify_self_hash(scenarios, "scenario_set_hash", "H2_A_DATASET_INVALID")
    if manifest.get("manifest_hash") != MANIFEST_HASH:
        raise H2LexicalAError("H2_A_MANIFEST_MISMATCH")
    if (
        manifest.get("dataset_status") != "FROZEN_CODEX_SILVER"
        or manifest.get("a_baseline_status") != "NOT_RUN"
        or manifest.get("embedding_used") is not False
        or manifest.get("execution_count") != 28
        or manifest.get("artifact_hashes", {}).get("tree")
        != canonical_digest(tree_document)
        or manifest.get("artifact_hashes", {}).get("scenarios")
        != scenarios.get("scenario_set_hash")
    ):
        raise H2LexicalAError("H2_A_DATASET_INVALID")
    rows = scenarios.get("scenarios")
    if not isinstance(rows, list) or len(rows) != 28:
        raise H2LexicalAError("H2_A_DATASET_INVALID")
    imported = adapt_tree_document(tree_document, source_hint="h2-local-cleanroom")
    if not imported.is_valid or imported.tree is None or not imported.tree.is_resource_map:
        raise H2LexicalAError("H2_A_DATASET_INVALID")
    return imported.tree, rows


def build_confirmation(request: IntentRequest, tree: Any) -> IntentConfirmation:
    intent = IntentContent(
        subject=None,
        role=None,
        scenario=None,
        lifecycle=None,
        ownership="UNKNOWN",
        node_kind=request.node_kind_hint,
        value_type=request.value_type_hint,
        cardinality=request.cardinality_hint,
        confirmed_facts=(),
        assumptions=(),
        evidence_gaps=(),
        clarification_question=None,
    )
    payload = {
        "schema_version": "intent-confirmation.v1",
        "status": "CONFIRMED_FOR_RETRIEVAL",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "semantic_approval": False,
        "patch_eligible": False,
        "source_request_hash": request.request_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": _FIXED_DRAFT_HASH,
        "source_action_hash": _FIXED_ACTION_HASH,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "reviewer_ref": _FIXED_REVIEWER,
        "recorded_at": _FIXED_RECORDED_AT,
        "intent": intent.to_dict(),
    }
    return IntentConfirmation(
        status="CONFIRMED_FOR_RETRIEVAL",
        source_request_hash=request.request_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=_FIXED_DRAFT_HASH,
        source_action_hash=_FIXED_ACTION_HASH,
        proposed_parent_node_id=request.proposed_parent_node_id,
        reviewer_ref=_FIXED_REVIEWER,
        recorded_at=_FIXED_RECORDED_AT,
        intent=intent,
        confirmation_hash=canonical_digest(payload),
    )


def retrieve_public_scenarios(
    tree: Any, scenarios: list[Mapping[str, Any]]
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Complete every retrieval before the Oracle sidecar is opened."""

    observations: dict[str, tuple[str, tuple[str, ...]]] = {}
    for scenario in scenarios:
        try:
            scenario_id = scenario["scenario_id"]
            request = IntentRequest.from_dict(scenario["request"], tree)
            annotations = tuple(
                (item["role"], item["text"])
                for item in scenario["role_annotations"]
            )
            evidence = build_retrieval_role_evidence(request, annotations)
            result = build_boundary_tolerant_role_candidate_set(
                evidence,
                request,
                build_confirmation(request, tree),
                tree,
                include_model_expansion=False,
                max_candidates=LEXICAL_TOP_K,
            )
        except (KeyError, TypeError, ValueError):
            raise H2LexicalAError("H2_A_SCENARIO_INVALID") from None
        if not isinstance(scenario_id, str) or scenario_id in observations:
            raise H2LexicalAError("H2_A_SCENARIO_INVALID")
        observations[scenario_id] = (
            result.status,
            tuple(item.node_id for item in result.candidates[:RESULT_TOP_K]),
        )
    return observations


def _ratio(hits: int, total: int) -> dict[str, Any]:
    return {"hits": hits, "total": total, "value": round(hits / total, 6)}


def build_aggregate_report(
    *,
    recall20_hits: int,
    recall8_hits: int,
    reciprocal_rank_sum: float,
    non_literal_recall20_hits: int,
    hard_negative_passes: int,
    explicit_empty_passes: int,
) -> dict[str, Any]:
    status = (
        "H2_DATASET_NOT_DISCRIMINATIVE"
        if recall20_hits > 18 or non_literal_recall20_hits > 8
        else "H2_DATASET_DISCRIMINATIVE"
    )
    report = {
        "schema_version": REPORT_VERSION,
        "status": status,
        "data_commit": DATA_COMMIT,
        "source_manifest_hash": MANIFEST_HASH,
        "lexical_algorithm_version": ALGORITHM_VERSION,
        "lexical_top_k": LEXICAL_TOP_K,
        "result_top_k": RESULT_TOP_K,
        "hard_negative_top_k": HARD_NEGATIVE_TOP_K,
        "embedding_used": False,
        "provider_called": False,
        "index_used": False,
        "gold_eligible": False,
        "production_qualification": False,
        "patch_eligible": False,
        "targeted_count": 20,
        "recall_at_20": _ratio(recall20_hits, 20),
        "recall_at_8": _ratio(recall8_hits, 20),
        "mrr_at_20": round(reciprocal_rank_sum / 20, 6),
        "non_literal_recall_at_20": _ratio(non_literal_recall20_hits, 10),
        "hard_negative_top_8": _ratio(hard_negative_passes, 4),
        "explicit_empty": _ratio(explicit_empty_passes, 4),
    }
    if set(report) != _RESULT_KEYS:
        raise H2LexicalAError("H2_A_REPORT_INVALID")
    return report


def score_after_retrieval(
    dataset_dir: Path,
    scenarios: list[Mapping[str, Any]],
    observations: Mapping[str, tuple[str, tuple[str, ...]]],
) -> dict[str, Any]:
    """Load the local Oracle only after retrieval, then discard item detail."""

    oracle = load_json_artifact(
        dataset_dir / "oracle-sidecar.v1.json", "H2_A_ORACLE_INVALID"
    )
    if not isinstance(oracle, dict):
        raise H2LexicalAError("H2_A_ORACLE_INVALID")
    verify_self_hash(oracle, "oracle_hash", "H2_A_ORACLE_INVALID")
    if oracle.get("oracle_hash") != "042ea1818541c17d8c2bd424da39e776d9a30b60dc0c117a62484b9c6881482c":
        raise H2LexicalAError("H2_A_ORACLE_INVALID")
    entries = oracle.get("entries")
    if not isinstance(entries, list) or len(entries) != 28:
        raise H2LexicalAError("H2_A_ORACLE_INVALID")
    categories = {item.get("scenario_id"): item.get("category") for item in scenarios}
    if set(observations) != {item.get("scenario_id") for item in entries}:
        raise H2LexicalAError("H2_A_ORACLE_INVALID")
    recall20_hits = recall8_hits = non_literal_hits = 0
    reciprocal_rank_sum = 0.0
    hard_negative_passes = explicit_empty_passes = 0
    target_count = hard_negative_count = explicit_empty_count = 0
    for entry in entries:
        scenario_id = entry.get("scenario_id")
        status, candidates = observations[scenario_id]
        oracle_type = entry.get("oracle_type")
        if oracle_type == "TARGET":
            target = entry.get("target_node_id")
            if not isinstance(target, str):
                raise H2LexicalAError("H2_A_ORACLE_INVALID")
            target_count += 1
            if target in candidates:
                rank = candidates.index(target) + 1
                recall20_hits += 1
                reciprocal_rank_sum += 1 / rank
                if rank <= 8:
                    recall8_hits += 1
                if categories.get(scenario_id) == "NON_LITERAL":
                    non_literal_hits += 1
        elif oracle_type == "HARD_NEGATIVE":
            excluded = entry.get("excluded_node_ids")
            if not isinstance(excluded, list) or len(excluded) != 1:
                raise H2LexicalAError("H2_A_ORACLE_INVALID")
            hard_negative_count += 1
            hard_negative_passes += int(excluded[0] not in candidates[:HARD_NEGATIVE_TOP_K])
        elif oracle_type == "EXPLICIT_EMPTY":
            explicit_empty_count += 1
            explicit_empty_passes += int(status == entry.get("expected_empty_status"))
        else:
            raise H2LexicalAError("H2_A_ORACLE_INVALID")
    if (target_count, hard_negative_count, explicit_empty_count) != (20, 4, 4):
        raise H2LexicalAError("H2_A_ORACLE_INVALID")
    return build_aggregate_report(
        recall20_hits=recall20_hits,
        recall8_hits=recall8_hits,
        reciprocal_rank_sum=reciprocal_rank_sum,
        non_literal_recall20_hits=non_literal_hits,
        hard_negative_passes=hard_negative_passes,
        explicit_empty_passes=explicit_empty_passes,
    )


def run(dataset_dir: Path) -> dict[str, Any]:
    tree, scenarios = load_public_inputs(dataset_dir)
    observations = retrieve_public_scenarios(tree, scenarios)
    return score_after_retrieval(dataset_dir, scenarios, observations)


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
    except FileExistsError:
        raise H2LexicalAError("H2_A_RESULT_EXISTS") from None
    except OSError:
        raise H2LexicalAError("H2_A_RESULT_WRITE_FAILED") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.dataset_dir)
        write_report(args.output, report)
    except H2LexicalAError as exc:
        print(json.dumps({"valid": False, "error_code": exc.code}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
