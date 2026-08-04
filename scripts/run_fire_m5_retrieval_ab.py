#!/usr/bin/env python3
"""Run the pre-registered deterministic M5 retrieval A/B calibration."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from fire_m5_data_common import preflight_dataset
from fire_m5_retrieval_calibration import (
    RetrievalCalibrationError,
    RetrievalCalibrationItem,
    build_retrieval_calibration_oracle_v2,
)
from fire_m5_retrieval_roles import (
    aggregate_annotation_report,
    build_silver_role_evidence,
)
from treeguard.adapter import load_tree_export
from treeguard.change_intent import (
    CONFIRMATION_SCHEMA_VERSION,
    IntentConfirmation,
    IntentContent,
    IntentRequest,
)
from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads
from treeguard.retrieval import CandidateRetrievalError, build_candidate_set
from treeguard.retrieval_anchor import (
    build_anchored_candidate_set,
    build_anchored_retrieval_query,
)
from treeguard.retrieval_query import (
    build_decoupled_candidate_set,
    build_retrieval_query,
)
from treeguard.retrieval_phrase import (
    build_phrase_candidate_set,
    build_phrase_retrieval_query,
)
from treeguard.retrieval_roles import (
    RetrievalRoleEvidence,
    build_model_retrieval_role_evidence,
    build_role_candidate_set,
)
from treeguard.retrieval_role_tolerant import (
    build_boundary_tolerant_role_candidate_set,
)


REPORT_VERSION = "fire-m5-retrieval-ab-report.v1"
HARNESS_VERSION = "treeguard.fire-m5-retrieval-ab.v1"
VIEW_ORDER = (
    "V_CANONICAL",
    "V_FREE_TEXT_DROPPED",
    "V_PARENT_ABSENT",
    "V_PARENT_WRONG_BRANCH",
    "V_REQUIREMENT_ONLY",
)
TARGET_COUNT = 16
EMPTY_COUNT = 2
PROCEED_COUNT = 18


class RetrievalABError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _read_json(path: Path, *, maximum_bytes: int) -> Any:
    data = path.read_bytes()
    if not data or len(data) > maximum_bytes:
        raise RetrievalABError("RETRIEVAL_AB_SOURCE_SIZE_INVALID")
    try:
        return strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise RetrievalABError("RETRIEVAL_AB_SOURCE_JSON_INVALID") from None


def _request(payload: dict[str, Any], tree: Any) -> IntentRequest:
    return IntentRequest.from_dict(
        {"schema_version": "intent-request.v1", **payload},
        tree,
    )


def _confirmation(
    request: IntentRequest,
    seed: dict[str, Any],
    tree: Any,
    *,
    view: str,
) -> IntentConfirmation:
    intent = IntentContent(
        subject=seed["subject"],
        role=seed["role"],
        scenario=seed["scenario"],
        lifecycle=seed["lifecycle"],
        ownership=seed["ownership"],
        node_kind=seed["node_kind"],
        value_type=seed["value_type"],
        cardinality=seed["cardinality"],
        confirmed_facts=tuple(seed["confirmed_facts"]),
        assumptions=tuple(seed["assumptions"]),
        evidence_gaps=tuple(seed["evidence_gaps"]),
        clarification_question=seed["clarification_question"],
    )
    source_draft_hash = canonical_digest([HARNESS_VERSION, view, "draft"])
    source_action_hash = canonical_digest([HARNESS_VERSION, view, "action"])
    payload = {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "status": "CONFIRMED_FOR_RETRIEVAL",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "semantic_approval": False,
        "patch_eligible": False,
        "source_request_hash": request.request_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": source_draft_hash,
        "source_action_hash": source_action_hash,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "reviewer_ref": "m5-retrieval-ab",
        "recorded_at": "2026-08-04T00:00:00Z",
        "intent": intent.to_dict(),
    }
    return IntentConfirmation(
        status="CONFIRMED_FOR_RETRIEVAL",
        source_request_hash=request.request_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=source_draft_hash,
        source_action_hash=source_action_hash,
        proposed_parent_node_id=request.proposed_parent_node_id,
        reviewer_ref="m5-retrieval-ab",
        recorded_at="2026-08-04T00:00:00Z",
        intent=intent,
        confirmation_hash=canonical_digest(payload),
    )


def _drop_free_text(seed: dict[str, Any]) -> dict[str, Any]:
    return {
        **seed,
        "subject": None,
        "role": None,
        "scenario": None,
        "lifecycle": None,
        "confirmed_facts": [],
        "assumptions": [],
        "evidence_gaps": [],
        "clarification_question": None,
    }


def build_view_sources(
    scenario: dict[str, Any],
    oracle: dict[str, Any],
    tree: Any,
    branch_refs: tuple[str, ...],
    view: str,
) -> tuple[IntentRequest, IntentConfirmation, bool]:
    request_payload = dict(scenario["request"])
    seed = dict(oracle["retrieval_seed"])
    include_expansion = True
    if view == "V_FREE_TEXT_DROPPED":
        seed = _drop_free_text(seed)
    elif view == "V_PARENT_ABSENT":
        request_payload["proposed_parent_node_id"] = None
    elif view == "V_PARENT_WRONG_BRANCH":
        other_branches = tuple(
            branch for branch in branch_refs if branch != scenario["primary_branch_ref"]
        )
        if not other_branches:
            raise RetrievalABError("RETRIEVAL_AB_WRONG_PARENT_UNAVAILABLE")
        request_payload["proposed_parent_node_id"] = other_branches[0]
    elif view == "V_REQUIREMENT_ONLY":
        seed = _drop_free_text(seed)
        include_expansion = False
    elif view != "V_CANONICAL":
        raise RetrievalABError("RETRIEVAL_AB_VIEW_INVALID")
    request = _request(request_payload, tree)
    return request, _confirmation(request, seed, tree, view=view), include_expansion


def _candidate_rank(candidate_set: Any, acceptable_ids: set[str]) -> int | None:
    ranks = [
        candidate.rank
        for candidate in candidate_set.candidates
        if candidate.node_id in acceptable_ids
    ]
    return min(ranks) if ranks else None


def _evaluate_algorithm(
    formal: tuple[dict[str, Any], ...],
    oracle_by_ref: dict[str, dict[str, Any]],
    tree: Any,
    branch_refs: tuple[str, ...],
    view: str,
    algorithm: str,
    calibration_by_ref: dict[str, RetrievalCalibrationItem] | None = None,
    role_evidence_by_ref: dict[str, RetrievalRoleEvidence] | None = None,
) -> dict[str, Any]:
    ranks: list[int | None] = []
    empty_match_count = 0
    status_counts: Counter[str] = Counter()
    replay_match_count = 0
    for scenario in formal:
        oracle = oracle_by_ref[scenario["scenario_ref"]]
        request, confirmation, include_expansion = build_view_sources(
            scenario, oracle, tree, branch_refs, view
        )
        if algorithm == "A":
            build: Callable[[], Any] = lambda: build_candidate_set(confirmation, tree)
        elif algorithm in {"B", "B1"}:
            query = build_retrieval_query(
                request,
                confirmation,
                tree,
                include_model_expansion=include_expansion,
            )
            build = lambda: build_decoupled_candidate_set(query, tree)
        elif algorithm == "B2":
            query = build_anchored_retrieval_query(
                request,
                confirmation,
                tree,
                include_model_expansion=include_expansion,
            )
            build = lambda: build_anchored_candidate_set(query, tree)
        elif algorithm == "B3":
            query = build_phrase_retrieval_query(
                request,
                confirmation,
                tree,
                include_model_expansion=include_expansion,
            )
            build = lambda: build_phrase_candidate_set(query, tree)
        elif algorithm in {"R1", "R2"}:
            if role_evidence_by_ref is None:
                evidence = build_silver_role_evidence(scenario, request)
            else:
                source_evidence = role_evidence_by_ref.get(
                    scenario["scenario_ref"]
                )
                if source_evidence is None:
                    raise RetrievalABError("RETRIEVAL_AB_ROLE_EVIDENCE_MISSING")
                evidence = build_model_retrieval_role_evidence(
                    source_evidence.to_model_dict(),
                    request,
                )
            if algorithm == "R1":
                build = lambda: build_role_candidate_set(
                    evidence,
                    request,
                    confirmation,
                    tree,
                    include_model_expansion=include_expansion,
                )
            else:
                build = lambda: build_boundary_tolerant_role_candidate_set(
                    evidence,
                    request,
                    confirmation,
                    tree,
                    include_model_expansion=include_expansion,
                )
        else:
            raise RetrievalABError("RETRIEVAL_AB_ALGORITHM_INVALID")
        results = tuple(build() for _ in range(3))
        if results[0].to_dict() == results[1].to_dict() == results[2].to_dict():
            replay_match_count += 1
        candidate_set = results[0]
        status_counts[candidate_set.status] += 1
        calibration = None
        if calibration_by_ref is not None:
            calibration = calibration_by_ref.get(scenario["scenario_ref"])
            if calibration is None:
                raise RetrievalABError("RETRIEVAL_AB_CALIBRATION_ITEM_MISSING")
        retrieval_oracle = oracle["capability_oracle"]["retrieval"]
        acceptable_ids = set(
            calibration.acceptable_node_ids
            if calibration is not None
            else retrieval_oracle["acceptable_node_ids"]
        )
        if acceptable_ids:
            ranks.append(_candidate_rank(candidate_set, acceptable_ids))
        elif candidate_set.status in set(
            calibration.allowed_statuses
            if calibration is not None
            else retrieval_oracle["allowed_statuses"]
        ):
            empty_match_count += 1
    if len(ranks) != TARGET_COUNT:
        raise RetrievalABError("RETRIEVAL_AB_TARGET_DENOMINATOR_INVALID")
    reciprocal_scaled_sum = sum(
        1_000_000 // rank for rank in ranks if rank is not None
    )
    return {
        "target_count": TARGET_COUNT,
        "recall_at_8": sum(rank is not None and rank <= 8 for rank in ranks),
        "recall_at_20": sum(rank is not None and rank <= 20 for rank in ranks),
        "mrr_scaled_1e6": reciprocal_scaled_sum // TARGET_COUNT,
        "empty_count": EMPTY_COUNT,
        "empty_status_match_count": empty_match_count,
        "replay_count": PROCEED_COUNT,
        "replay_match_count": replay_match_count,
        "status_counts": dict(sorted(status_counts.items())),
    }


def load_experiment_sources(
    fixture_dir: Path,
) -> tuple[
    tuple[dict[str, Any], ...],
    dict[str, dict[str, Any]],
    Any,
    tuple[str, ...],
]:
    preflight = preflight_dataset(fixture_dir)
    if preflight.get("status") != "PASS":
        raise RetrievalABError("RETRIEVAL_AB_PREFLIGHT_FAILED")
    manifest = _read_json(fixture_dir / "manifest.json", maximum_bytes=1_000_000)
    scenarios = _read_json(
        fixture_dir / "scenario-candidates.json", maximum_bytes=2_000_000
    )
    oracle = _read_json(
        fixture_dir / "oracle-sidecar.json", maximum_bytes=3_000_000
    )
    if (
        manifest.get("source_class") != "CLEANROOM_SYNTHETIC"
        or manifest.get("fictional") is not True
        or manifest.get("derived_from_real") is not False
    ):
        raise RetrievalABError("RETRIEVAL_AB_SOURCE_POLICY_INVALID")
    imported = load_tree_export(fixture_dir / manifest["tree_file"])
    if imported.tree is None or not imported.is_valid:
        raise RetrievalABError("RETRIEVAL_AB_TREE_INVALID")
    formal = tuple(
        item
        for item in scenarios["candidates"]
        if item["selection_status"] == "EXECUTION"
        and item["expected_route"] == "PROCEED"
    )
    if len(formal) != PROCEED_COUNT:
        raise RetrievalABError("RETRIEVAL_AB_PROCEED_DENOMINATOR_INVALID")
    oracle_by_ref = {item["scenario_ref"]: item for item in oracle["items"]}
    branch_refs = tuple(sorted({item["primary_branch_ref"] for item in formal}))
    return formal, oracle_by_ref, imported.tree, branch_refs


def run_ab(fixture_dir: Path) -> dict[str, Any]:
    formal, oracle_by_ref, tree, branch_refs = load_experiment_sources(fixture_dir)
    views: dict[str, Any] = {}
    for view in VIEW_ORDER:
        views[view] = {
            algorithm: _evaluate_algorithm(
                formal,
                oracle_by_ref,
                tree,
                branch_refs,
                view,
                algorithm,
            )
            for algorithm in ("A", "B")
        }
    b = {view: views[view]["B"] for view in VIEW_ORDER}
    failure_codes = []
    for view in ("V_REQUIREMENT_ONLY", "V_FREE_TEXT_DROPPED"):
        if b[view]["recall_at_8"] != TARGET_COUNT:
            failure_codes.append("RETRIEVAL_AB_PRIMARY_RECALL_BELOW_MINIMUM")
        if b[view]["mrr_scaled_1e6"] < 900_000:
            failure_codes.append("RETRIEVAL_AB_PRIMARY_MRR_BELOW_MINIMUM")
    if b["V_CANONICAL"]["recall_at_8"] != TARGET_COUNT:
        failure_codes.append("RETRIEVAL_AB_CANONICAL_REGRESSION")
    if b["V_PARENT_ABSENT"]["recall_at_8"] < 15:
        failure_codes.append("RETRIEVAL_AB_PARENT_ABSENT_BELOW_MINIMUM")
    if b["V_PARENT_WRONG_BRANCH"]["recall_at_20"] < 15:
        failure_codes.append("RETRIEVAL_AB_CONTEXT_POISONING")
    if any(b[view]["empty_status_match_count"] != EMPTY_COUNT for view in VIEW_ORDER):
        failure_codes.append("RETRIEVAL_AB_EMPTY_STATUS_REGRESSION")
    if any(b[view]["replay_match_count"] != PROCEED_COUNT for view in VIEW_ORDER):
        failure_codes.append("RETRIEVAL_AB_REPLAY_MISMATCH")
    return {
        "report_version": REPORT_VERSION,
        "harness_version": HARNESS_VERSION,
        "status": "PASS" if not failure_codes else "FAIL",
        "calibration_only": True,
        "production_qualification": False,
        "llm_called": False,
        "execution_proceed_count": PROCEED_COUNT,
        "target_count": TARGET_COUNT,
        "empty_count": EMPTY_COUNT,
        "views": views,
        "failure_codes": sorted(set(failure_codes)),
    }


def run_b2(fixture_dir: Path) -> dict[str, Any]:
    formal, oracle_by_ref, tree, branch_refs = load_experiment_sources(fixture_dir)
    calibration = build_retrieval_calibration_oracle_v2(
        formal, oracle_by_ref, tree
    )
    calibration_by_ref = {item.scenario_ref: item for item in calibration.items}
    views: dict[str, Any] = {}
    for view in VIEW_ORDER:
        views[view] = {
            algorithm: _evaluate_algorithm(
                formal,
                oracle_by_ref,
                tree,
                branch_refs,
                view,
                algorithm,
                calibration_by_ref,
            )
            for algorithm in ("A", "B1", "B2")
        }
    b2 = {view: views[view]["B2"] for view in VIEW_ORDER}
    failure_codes = []
    for view in ("V_REQUIREMENT_ONLY", "V_FREE_TEXT_DROPPED"):
        if b2[view]["recall_at_8"] != TARGET_COUNT:
            failure_codes.append("RETRIEVAL_B2_PRIMARY_RECALL_BELOW_MINIMUM")
        if b2[view]["mrr_scaled_1e6"] < 900_000:
            failure_codes.append("RETRIEVAL_B2_PRIMARY_MRR_BELOW_MINIMUM")
    if b2["V_CANONICAL"]["recall_at_8"] != TARGET_COUNT:
        failure_codes.append("RETRIEVAL_B2_CANONICAL_REGRESSION")
    if b2["V_PARENT_ABSENT"]["recall_at_8"] < 15:
        failure_codes.append("RETRIEVAL_B2_PARENT_ABSENT_BELOW_MINIMUM")
    if b2["V_PARENT_WRONG_BRANCH"]["recall_at_20"] < 15:
        failure_codes.append("RETRIEVAL_B2_CONTEXT_POISONING")
    if any(
        b2[view]["empty_status_match_count"] != EMPTY_COUNT
        for view in VIEW_ORDER
    ):
        failure_codes.append("RETRIEVAL_B2_EMPTY_STATUS_REGRESSION")
    if any(
        b2[view]["replay_match_count"] != PROCEED_COUNT for view in VIEW_ORDER
    ):
        failure_codes.append("RETRIEVAL_B2_REPLAY_MISMATCH")
    return {
        "report_version": "fire-m5-retrieval-b2-report.v1",
        "harness_version": HARNESS_VERSION,
        "status": "PASS" if not failure_codes else "FAIL",
        "calibration_only": True,
        "production_qualification": False,
        "llm_called": False,
        "execution_proceed_count": PROCEED_COUNT,
        "target_count": TARGET_COUNT,
        "empty_count": EMPTY_COUNT,
        "oracle_v2": calibration.aggregate_report(),
        "views": views,
        "failure_codes": sorted(set(failure_codes)),
    }


def run_b3(fixture_dir: Path) -> dict[str, Any]:
    formal, oracle_by_ref, tree, branch_refs = load_experiment_sources(fixture_dir)
    calibration = build_retrieval_calibration_oracle_v2(
        formal, oracle_by_ref, tree
    )
    calibration_by_ref = {item.scenario_ref: item for item in calibration.items}
    views: dict[str, Any] = {}
    for view in VIEW_ORDER:
        views[view] = {
            algorithm: _evaluate_algorithm(
                formal,
                oracle_by_ref,
                tree,
                branch_refs,
                view,
                algorithm,
                calibration_by_ref,
            )
            for algorithm in ("A", "B1", "B2", "B3")
        }
    b3 = {view: views[view]["B3"] for view in VIEW_ORDER}
    failure_codes = []
    for view in ("V_REQUIREMENT_ONLY", "V_FREE_TEXT_DROPPED"):
        if b3[view]["recall_at_8"] != TARGET_COUNT:
            failure_codes.append("RETRIEVAL_B3_PRIMARY_RECALL_BELOW_MINIMUM")
        if b3[view]["mrr_scaled_1e6"] < 900_000:
            failure_codes.append("RETRIEVAL_B3_PRIMARY_MRR_BELOW_MINIMUM")
    if b3["V_CANONICAL"]["recall_at_8"] != TARGET_COUNT:
        failure_codes.append("RETRIEVAL_B3_CANONICAL_REGRESSION")
    if b3["V_PARENT_ABSENT"]["recall_at_8"] < 15:
        failure_codes.append("RETRIEVAL_B3_PARENT_ABSENT_BELOW_MINIMUM")
    if b3["V_PARENT_WRONG_BRANCH"]["recall_at_20"] < 15:
        failure_codes.append("RETRIEVAL_B3_CONTEXT_POISONING")
    if any(
        b3[view]["empty_status_match_count"] != EMPTY_COUNT
        for view in VIEW_ORDER
    ):
        failure_codes.append("RETRIEVAL_B3_EMPTY_STATUS_REGRESSION")
    if any(
        b3[view]["replay_match_count"] != PROCEED_COUNT for view in VIEW_ORDER
    ):
        failure_codes.append("RETRIEVAL_B3_REPLAY_MISMATCH")
    return {
        "report_version": "fire-m5-retrieval-b3-report.v1",
        "harness_version": HARNESS_VERSION,
        "status": "PASS" if not failure_codes else "FAIL",
        "calibration_only": True,
        "production_qualification": False,
        "llm_called": False,
        "execution_proceed_count": PROCEED_COUNT,
        "target_count": TARGET_COUNT,
        "empty_count": EMPTY_COUNT,
        "oracle_v2": calibration.aggregate_report(),
        "views": views,
        "failure_codes": sorted(set(failure_codes)),
    }


def run_role_upper_bound(fixture_dir: Path) -> dict[str, Any]:
    formal, oracle_by_ref, tree, branch_refs = load_experiment_sources(fixture_dir)
    calibration = build_retrieval_calibration_oracle_v2(
        formal, oracle_by_ref, tree
    )
    calibration_by_ref = {item.scenario_ref: item for item in calibration.items}
    views: dict[str, Any] = {}
    for view in VIEW_ORDER:
        views[view] = {
            algorithm: _evaluate_algorithm(
                formal,
                oracle_by_ref,
                tree,
                branch_refs,
                view,
                algorithm,
                calibration_by_ref,
            )
            for algorithm in ("B3", "R1")
        }
    r1 = {view: views[view]["R1"] for view in VIEW_ORDER}
    failure_codes = role_gate_failure_codes(r1, prefix="RETRIEVAL_R1")
    return {
        "report_version": "fire-m5-retrieval-role-upper-bound-report.v1",
        "harness_version": HARNESS_VERSION,
        "status": "PASS" if not failure_codes else "FAIL",
        "calibration_only": True,
        "production_qualification": False,
        "llm_called": False,
        "execution_proceed_count": PROCEED_COUNT,
        "target_count": TARGET_COUNT,
        "empty_count": EMPTY_COUNT,
        "role_annotations": aggregate_annotation_report(formal),
        "oracle_v2": calibration.aggregate_report(),
        "views": views,
        "failure_codes": failure_codes,
    }


def run_role_boundary_upper_bound(fixture_dir: Path) -> dict[str, Any]:
    formal, oracle_by_ref, tree, branch_refs = load_experiment_sources(fixture_dir)
    calibration = build_retrieval_calibration_oracle_v2(
        formal, oracle_by_ref, tree
    )
    calibration_by_ref = {item.scenario_ref: item for item in calibration.items}
    views: dict[str, Any] = {}
    for view in VIEW_ORDER:
        views[view] = {
            algorithm: _evaluate_algorithm(
                formal,
                oracle_by_ref,
                tree,
                branch_refs,
                view,
                algorithm,
                calibration_by_ref,
            )
            for algorithm in ("R1", "R2")
        }
    r2 = {view: views[view]["R2"] for view in VIEW_ORDER}
    failure_codes = role_gate_failure_codes(r2, prefix="RETRIEVAL_R2_SILVER")
    return {
        "report_version": "fire-m5-retrieval-role-r2-upper-bound-report.v1",
        "harness_version": HARNESS_VERSION,
        "status": "PASS" if not failure_codes else "FAIL",
        "calibration_only": True,
        "production_qualification": False,
        "llm_called": False,
        "execution_proceed_count": PROCEED_COUNT,
        "target_count": TARGET_COUNT,
        "empty_count": EMPTY_COUNT,
        "role_annotations": aggregate_annotation_report(formal),
        "oracle_v2": calibration.aggregate_report(),
        "views": views,
        "failure_codes": failure_codes,
    }


def role_gate_failure_codes(
    results_by_view: dict[str, dict[str, Any]],
    *,
    prefix: str,
) -> list[str]:
    if set(results_by_view) != set(VIEW_ORDER):
        raise RetrievalABError("RETRIEVAL_AB_ROLE_VIEW_DENOMINATOR_INVALID")
    failure_codes = []
    for view in ("V_REQUIREMENT_ONLY", "V_FREE_TEXT_DROPPED"):
        if results_by_view[view]["recall_at_8"] != TARGET_COUNT:
            failure_codes.append(f"{prefix}_PRIMARY_RECALL_BELOW_MINIMUM")
        if results_by_view[view]["mrr_scaled_1e6"] < 900_000:
            failure_codes.append(f"{prefix}_PRIMARY_MRR_BELOW_MINIMUM")
    if results_by_view["V_CANONICAL"]["recall_at_8"] != TARGET_COUNT:
        failure_codes.append(f"{prefix}_CANONICAL_REGRESSION")
    if results_by_view["V_PARENT_ABSENT"]["recall_at_8"] < 15:
        failure_codes.append(f"{prefix}_PARENT_ABSENT_BELOW_MINIMUM")
    if results_by_view["V_PARENT_WRONG_BRANCH"]["recall_at_20"] < 15:
        failure_codes.append(f"{prefix}_CONTEXT_POISONING")
    if any(
        results_by_view[view]["empty_status_match_count"] != EMPTY_COUNT
        for view in VIEW_ORDER
    ):
        failure_codes.append(f"{prefix}_EMPTY_STATUS_REGRESSION")
    if any(
        results_by_view[view]["replay_match_count"] != PROCEED_COUNT
        for view in VIEW_ORDER
    ):
        failure_codes.append(f"{prefix}_REPLAY_MISMATCH")
    return sorted(set(failure_codes))


def evaluate_model_role_views(
    fixture_dir: Path,
    evidence_by_ref: dict[str, RetrievalRoleEvidence],
    *,
    algorithm: str = "R1",
) -> dict[str, dict[str, Any]]:
    if algorithm not in {"R1", "R2"}:
        raise RetrievalABError("RETRIEVAL_AB_ROLE_ALGORITHM_INVALID")
    formal, oracle_by_ref, tree, branch_refs = load_experiment_sources(fixture_dir)
    calibration = build_retrieval_calibration_oracle_v2(
        formal, oracle_by_ref, tree
    )
    calibration_by_ref = {item.scenario_ref: item for item in calibration.items}
    return {
        view: _evaluate_algorithm(
            formal,
            oracle_by_ref,
            tree,
            branch_refs,
            view,
            algorithm,
            calibration_by_ref,
            evidence_by_ref,
        )
        for view in VIEW_ORDER
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow",
    )
    parser.add_argument(
        "--mode",
        choices=("b1", "b2", "b3", "r1", "r2"),
        default="b1",
    )
    args = parser.parse_args(argv)
    try:
        runners = {
            "b1": run_ab,
            "b2": run_b2,
            "b3": run_b3,
            "r1": run_role_upper_bound,
            "r2": run_role_boundary_upper_bound,
        }
        report = runners[args.mode](args.fixture_dir)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        code = (
            exc.code
            if isinstance(
                exc,
                (
                    RetrievalABError,
                    RetrievalCalibrationError,
                    CandidateRetrievalError,
                ),
            )
            else "RETRIEVAL_AB_FAILED"
        )
        report = {
            "report_version": REPORT_VERSION,
            "status": "ERROR",
            "error_code": code,
            "llm_called": False,
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
