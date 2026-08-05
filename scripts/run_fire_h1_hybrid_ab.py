#!/usr/bin/env python3
"""Run the frozen H1 lexical-versus-hybrid development calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from generate_fire_h1_hybrid_calibration import validate_materialized
from treeguard.adapter import load_tree_export
from treeguard.ai_review import BailianProviderError
from treeguard.change_intent import (
    CONFIRMATION_SCHEMA_VERSION,
    IntentConfirmation,
    IntentContent,
    IntentRequest,
)
from treeguard.embedding_provider import (
    BailianHybridEmbeddingProvider,
    EmbeddingProviderError,
    HybridEmbeddingProvider,
    build_hybrid_index_with_provider,
    build_hybrid_query_embedding_with_provider,
)
from treeguard.hashing import canonical_digest
from treeguard.hybrid_index_io import (
    read_private_hybrid_embedding_index,
    write_private_hybrid_embedding_index,
)
from treeguard.json_utils import strict_json_loads
from treeguard.private_io import preflight_private_output, write_private_json
from treeguard.retrieval_hybrid import (
    HybridEmbeddingIndex,
    build_hybrid_candidate_set,
    build_hybrid_node_documents,
    build_hybrid_query_document,
    vector_leg_enabled,
)
from treeguard.retrieval_role_tolerant import (
    build_boundary_tolerant_role_candidate_set,
)
from treeguard.retrieval_roles import (
    RetrievalRoleEvidence,
    build_retrieval_role_evidence,
)


REPORT_VERSION = "treeguard.fire-h1-hybrid-ab-report.v1"
PRIVATE_RESULT_VERSION = "treeguard.fire-h1-hybrid-ab-private-result.v1"
RUNNER_VERSION = "treeguard.fire-h1-hybrid-ab-runner.v1"
FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_h1_hybrid_calibration"
POSITIVE_CATEGORIES = {
    "BOUNDARY_VARIATION",
    "CROSS_BRANCH_INTERFERENCE",
    "LEXICAL_BASELINE",
    "NON_LITERAL",
}
SCENARIO_COUNT = 24
POSITIVE_COUNT = 16
NON_LITERAL_COUNT = 8
HARD_NEGATIVE_COUNT = 4
EMPTY_COUNT = 4
LEXICAL_BASELINE_COUNT = 4


class H1RunnerError(ValueError):
    def __init__(self, code: str, *, model_called: bool = False) -> None:
        self.code = code
        self.model_called = model_called
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class H1Sources:
    scenarios: tuple[dict[str, Any], ...]
    oracle_by_ref: dict[str, dict[str, Any]]
    tree: Any


def load_h1_sources(fixture_dir: Path = FIXTURE_DIR) -> H1Sources:
    """Load only the exact materialized clean-room calibration bundle."""

    try:
        report = validate_materialized(fixture_dir)
        if report.get("status") != "PASS":
            raise ValueError
        scenario_payload = strict_json_loads(
            (fixture_dir / "scenarios.json").read_bytes().decode("utf-8")
        )
        oracle_payload = strict_json_loads(
            (fixture_dir / "oracle-sidecar.json").read_bytes().decode("utf-8")
        )
        manifest = strict_json_loads(
            (fixture_dir / "manifest.json").read_bytes().decode("utf-8")
        )
        source_path = fixture_dir / manifest["source_tree_file"]
        if not source_path.is_file() or source_path.is_symlink():
            raise ValueError
        source_bytes = source_path.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != manifest["source_tree_file_sha256"]:
            raise ValueError
        imported = load_tree_export(source_path)
    except (KeyError, OSError, TypeError, UnicodeError, ValueError):
        raise H1RunnerError("H1_SOURCE_PREFLIGHT_FAILED") from None
    if (
        imported.tree is None
        or not imported.is_valid
        or imported.tree.snapshot_hash != manifest["source_tree_canonical_digest"]
        or len(imported.tree.nodes) != manifest["node_count"]
    ):
        raise H1RunnerError("H1_SOURCE_PREFLIGHT_FAILED")
    scenarios = tuple(scenario_payload["scenarios"])
    oracle_by_ref = {
        item["scenario_ref"]: item for item in oracle_payload["entries"]
    }
    if (
        len(scenarios) != SCENARIO_COUNT
        or len(oracle_by_ref) != SCENARIO_COUNT
        or tuple(item["scenario_ref"] for item in scenarios)
        != tuple(f"H1S{index:03d}" for index in range(1, SCENARIO_COUNT + 1))
        or set(oracle_by_ref) != {item["scenario_ref"] for item in scenarios}
    ):
        raise H1RunnerError("H1_SOURCE_DENOMINATOR_INVALID")
    return H1Sources(scenarios, oracle_by_ref, imported.tree)


def build_h1_case_sources(
    scenario: dict[str, Any],
    tree: Any,
) -> tuple[RetrievalRoleEvidence, IntentRequest, IntentConfirmation]:
    request = IntentRequest.from_dict(
        {"schema_version": "intent-request.v1", **scenario["request"]},
        tree,
    )
    intent = IntentContent(
        subject=None,
        role=None,
        scenario=None,
        lifecycle=None,
        ownership="UNKNOWN",
        node_kind=scenario["request"]["node_kind_hint"],
        value_type=scenario["request"]["value_type_hint"],
        cardinality=scenario["request"]["cardinality_hint"],
        confirmed_facts=(),
        assumptions=(),
        evidence_gaps=(),
        clarification_question=None,
    )
    scenario_ref = scenario["scenario_ref"]
    draft_hash = canonical_digest([RUNNER_VERSION, scenario_ref, "draft"])
    action_hash = canonical_digest([RUNNER_VERSION, scenario_ref, "action"])
    payload = {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "status": "CONFIRMED_FOR_RETRIEVAL",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "semantic_approval": False,
        "patch_eligible": False,
        "source_request_hash": request.request_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": draft_hash,
        "source_action_hash": action_hash,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "reviewer_ref": "h1-development-calibration",
        "recorded_at": "2026-08-05T00:00:00Z",
        "intent": intent.to_dict(),
    }
    confirmation = IntentConfirmation(
        status="CONFIRMED_FOR_RETRIEVAL",
        source_request_hash=request.request_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=draft_hash,
        source_action_hash=action_hash,
        proposed_parent_node_id=request.proposed_parent_node_id,
        reviewer_ref="h1-development-calibration",
        recorded_at="2026-08-05T00:00:00Z",
        intent=intent,
        confirmation_hash=canonical_digest(payload),
    )
    annotations = tuple(
        (item["role"], item["text"]) for item in scenario["silver_roles"]
    )
    return (
        build_retrieval_role_evidence(request, annotations),
        request,
        confirmation,
    )


def preflight_h1_ab(sources: H1Sources) -> dict[str, Any]:
    documents = build_hybrid_node_documents(sources.tree)
    rows = []
    vector_query_count = 0
    for scenario in sources.scenarios:
        evidence, request, confirmation = build_h1_case_sources(
            scenario, sources.tree
        )
        first = build_boundary_tolerant_role_candidate_set(
            evidence,
            request,
            confirmation,
            sources.tree,
            include_model_expansion=False,
            max_candidates=20,
        )
        second = build_boundary_tolerant_role_candidate_set(
            evidence,
            request,
            confirmation,
            sources.tree,
            include_model_expansion=False,
            max_candidates=20,
        )
        query_document = build_hybrid_query_document(
            evidence, request, confirmation, sources.tree
        )
        vector_query_count += int(vector_leg_enabled(query_document, documents))
        rows.append(
            _evaluation_row(
                scenario,
                sources.oracle_by_ref[scenario["scenario_ref"]],
                first,
                first.to_dict() == second.to_dict(),
            )
        )
    baseline = _metrics(rows)
    if (
        baseline["recall_at_8"] != 14
        or baseline["recall_at_20"] != 14
        or baseline["non_literal_recall_at_20"] != 6
        or baseline["hard_negative_safe_at_8"] != HARD_NEGATIVE_COUNT
        or baseline["empty_status_match_count"] != EMPTY_COUNT
        or baseline["replay_match_count"] != SCENARIO_COUNT
    ):
        raise H1RunnerError("H1_BASELINE_REPLAY_MISMATCH")
    return {
        "report_version": REPORT_VERSION,
        "status": "PREFLIGHT_READY",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "model_called": False,
        "scenario_count": SCENARIO_COUNT,
        "positive_count": POSITIVE_COUNT,
        "node_count": len(documents),
        "planned_index_call_count": (len(documents) + 9) // 10,
        "planned_query_call_count": vector_query_count,
        "baseline": baseline,
    }


def run_h1_ab(
    sources: H1Sources,
    index: HybridEmbeddingIndex,
    provider: HybridEmbeddingProvider,
) -> tuple[dict[str, Any], dict[str, Any]]:
    documents = build_hybrid_node_documents(sources.tree)
    lexical_rows = []
    hybrid_rows = []
    private_cases = []
    for scenario in sources.scenarios:
        evidence, request, confirmation = build_h1_case_sources(
            scenario, sources.tree
        )
        lexical_first = build_boundary_tolerant_role_candidate_set(
            evidence,
            request,
            confirmation,
            sources.tree,
            include_model_expansion=False,
            max_candidates=20,
        )
        lexical_second = build_boundary_tolerant_role_candidate_set(
            evidence,
            request,
            confirmation,
            sources.tree,
            include_model_expansion=False,
            max_candidates=20,
        )
        query_document = build_hybrid_query_document(
            evidence, request, confirmation, sources.tree
        )
        if vector_leg_enabled(query_document, documents):
            query_embedding = build_hybrid_query_embedding_with_provider(
                provider,
                query_document,
                external_data_approved=True,
            )
            hybrid_first = build_hybrid_candidate_set(
                evidence,
                request,
                confirmation,
                sources.tree,
                index=index,
                query_embedding=query_embedding,
            )
            hybrid_second = build_hybrid_candidate_set(
                evidence,
                request,
                confirmation,
                sources.tree,
                index=index,
                query_embedding=query_embedding,
            )
        else:
            hybrid_first = build_hybrid_candidate_set(
                evidence, request, confirmation, sources.tree
            )
            hybrid_second = build_hybrid_candidate_set(
                evidence, request, confirmation, sources.tree
            )
        oracle = sources.oracle_by_ref[scenario["scenario_ref"]]
        lexical_rows.append(
            _evaluation_row(
                scenario,
                oracle,
                lexical_first,
                lexical_first.to_dict() == lexical_second.to_dict(),
            )
        )
        hybrid_rows.append(
            _evaluation_row(
                scenario,
                oracle,
                hybrid_first,
                hybrid_first.to_dict() == hybrid_second.to_dict(),
            )
        )
        private_cases.append(
            {
                "scenario_ref": scenario["scenario_ref"],
                "primary_category": scenario["primary_category"],
                "oracle": oracle,
                "lexical": lexical_first.to_dict(),
                "hybrid": hybrid_first.to_dict(),
            }
        )
    lexical = _metrics(lexical_rows)
    hybrid = _metrics(hybrid_rows)
    failure_codes = _gate_failures(lexical, hybrid)
    public = {
        "report_version": REPORT_VERSION,
        "status": "PASS" if not failure_codes else "FAIL",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "production_qualification": False,
        "model_called": True,
        "scenario_count": SCENARIO_COUNT,
        "positive_count": POSITIVE_COUNT,
        "lexical": lexical,
        "hybrid": hybrid,
        "failure_codes": failure_codes,
        "decision": "H1_DEVELOPMENT_CANDIDATE" if not failure_codes else "H1_REJECTED",
    }
    private = {
        "schema_version": PRIVATE_RESULT_VERSION,
        "runner_version": RUNNER_VERSION,
        "aggregate": public,
        "cases": private_cases,
    }
    return public, private


def _evaluation_row(
    scenario: dict[str, Any],
    oracle: dict[str, Any],
    result: Any,
    replay_match: bool,
) -> dict[str, Any]:
    acceptable = set(oracle["acceptable_node_ids"])
    ranks = [item.rank for item in result.candidates if item.node_id in acceptable]
    excluded = set(oracle["excluded_node_ids"])
    return {
        "category": scenario["primary_category"],
        "rank": min(ranks) if ranks else None,
        "hard_negative_safe": not any(
            item.node_id in excluded for item in result.candidates[:8]
        ),
        "empty_status_match": (
            result.status in oracle["allowed_statuses"] and not result.candidates
        ),
        "replay_match": replay_match,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, int]:
    positives = [row for row in rows if row["category"] in POSITIVE_CATEGORIES]
    non_literal = [row for row in rows if row["category"] == "NON_LITERAL"]
    lexical_baseline = [
        row for row in rows if row["category"] == "LEXICAL_BASELINE"
    ]
    hard_negatives = [
        row for row in rows if row["category"] == "EXCLUSION_HARD_NEGATIVE"
    ]
    empty = [row for row in rows if row["category"] == "EXPLICIT_EMPTY"]
    if tuple(map(len, (positives, non_literal, lexical_baseline, hard_negatives, empty))) != (
        POSITIVE_COUNT,
        NON_LITERAL_COUNT,
        LEXICAL_BASELINE_COUNT,
        HARD_NEGATIVE_COUNT,
        EMPTY_COUNT,
    ):
        raise H1RunnerError("H1_METRIC_DENOMINATOR_INVALID")
    ranks = [row["rank"] for row in positives]
    return {
        "recall_at_8": sum(rank is not None and rank <= 8 for rank in ranks),
        "recall_at_20": sum(rank is not None and rank <= 20 for rank in ranks),
        "mrr_scaled_1e6": sum(
            1_000_000 // rank for rank in ranks if rank is not None
        )
        // POSITIVE_COUNT,
        "non_literal_recall_at_20": sum(
            row["rank"] is not None and row["rank"] <= 20 for row in non_literal
        ),
        "lexical_baseline_recall_at_8": sum(
            row["rank"] is not None and row["rank"] <= 8
            for row in lexical_baseline
        ),
        "hard_negative_safe_at_8": sum(
            row["hard_negative_safe"] for row in hard_negatives
        ),
        "empty_status_match_count": sum(
            row["empty_status_match"] for row in empty
        ),
        "replay_match_count": sum(row["replay_match"] for row in rows),
    }


def _gate_failures(
    lexical: dict[str, int],
    hybrid: dict[str, int],
) -> list[str]:
    failures = []
    if hybrid["recall_at_20"] < 15 or hybrid["recall_at_20"] < lexical["recall_at_20"] + 2:
        failures.append("H1_RECALL_AT_20_GATE_FAILED")
    if (
        hybrid["non_literal_recall_at_20"] < 6
        or hybrid["non_literal_recall_at_20"]
        < lexical["non_literal_recall_at_20"] + 2
    ):
        failures.append("H1_NON_LITERAL_GATE_FAILED")
    if hybrid["recall_at_8"] < lexical["recall_at_8"]:
        failures.append("H1_RECALL_AT_8_REGRESSION")
    if hybrid["hard_negative_safe_at_8"] != HARD_NEGATIVE_COUNT:
        failures.append("H1_HARD_NEGATIVE_REGRESSION")
    if hybrid["empty_status_match_count"] != EMPTY_COUNT:
        failures.append("H1_EMPTY_STATUS_REGRESSION")
    if (
        hybrid["lexical_baseline_recall_at_8"]
        < lexical["lexical_baseline_recall_at_8"] - 1
    ):
        failures.append("H1_LEXICAL_BASELINE_REGRESSION")
    if hybrid["replay_match_count"] != SCENARIO_COUNT:
        failures.append("H1_REPLAY_MISMATCH")
    return failures


def _error_report(code: str, *, model_called: bool) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "status": "ERROR",
        "error_code": code,
        "model_called": model_called,
    }


def _same_resolved_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except (OSError, RuntimeError):
        raise H1RunnerError("H1_LIVE_PATHS_INVALID") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--live", action="store_true")
    index = parser.add_mutually_exclusive_group()
    index.add_argument("--index-input", type=Path)
    index.add_argument("--index-output", type=Path)
    parser.add_argument("--internal-output", type=Path)
    args = parser.parse_args(argv)
    provider: BailianHybridEmbeddingProvider | None = None
    try:
        sources = load_h1_sources(args.fixture_dir)
        preflight = preflight_h1_ab(sources)
        if args.preflight_only:
            if args.index_input or args.index_output or args.internal_output:
                raise H1RunnerError("H1_PREFLIGHT_OUTPUT_FORBIDDEN")
            print(json.dumps(preflight, ensure_ascii=False, sort_keys=True))
            return 0
        if (
            args.internal_output is None
            or (args.index_input is None) == (args.index_output is None)
        ):
            raise H1RunnerError("H1_LIVE_PATHS_INVALID")
        if (
            args.index_output is not None
            and _same_resolved_path(args.index_output, args.internal_output)
        ):
            raise H1RunnerError("H1_LIVE_PATHS_INVALID")
        preflight_private_output(args.internal_output)
        if args.index_output is not None:
            preflight_private_output(args.index_output)
        if args.index_input is not None:
            embedding_index = read_private_hybrid_embedding_index(
                args.index_input, sources.tree
            )
        provider = BailianHybridEmbeddingProvider.from_env()
        if args.index_output is not None:
            assert args.index_output is not None
            embedding_index = build_hybrid_index_with_provider(
                provider, sources.tree, external_data_approved=True
            )
            if not write_private_hybrid_embedding_index(
                args.index_output, embedding_index
            ):
                raise H1RunnerError("H1_INDEX_WRITE_FAILED", model_called=True)
        public, private = run_h1_ab(sources, embedding_index, provider)
        if not write_private_json(args.internal_output, private):
            raise H1RunnerError("H1_RESULT_WRITE_FAILED", model_called=True)
        print(json.dumps(public, ensure_ascii=False, sort_keys=True))
        return 0 if public["status"] == "PASS" else 1
    except BailianProviderError as error:
        print(json.dumps(_error_report(error.code, model_called=False), sort_keys=True))
        return 2
    except EmbeddingProviderError as error:
        called = bool(getattr(provider, "wire_attempt_count", 0))
        print(json.dumps(_error_report(error.code, model_called=called), sort_keys=True))
        return 3 if called else 2
    except (H1RunnerError, OSError, TypeError, ValueError) as error:
        code = getattr(error, "code", "H1_RUNNER_FAILED")
        called = bool(getattr(error, "model_called", False))
        print(json.dumps(_error_report(code, model_called=called), sort_keys=True))
        return 3 if called else 2


if __name__ == "__main__":
    raise SystemExit(main())
