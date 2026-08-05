#!/usr/bin/env python3
"""Run the frozen H2 local-embedding B comparison under an explicit gate."""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_fire_h2_local_embedding_lexical_a import (
    DATA_COMMIT,
    MANIFEST_HASH,
    build_confirmation,
    load_json_artifact,
    load_public_inputs,
    retrieve_public_scenarios,
    score_after_retrieval,
    verify_self_hash,
)
from treeguard.change_intent import IntentRequest
from treeguard.h2_index_io import (
    read_private_h2_embedding_index,
    write_private_h2_embedding_index,
)
from treeguard.local_embedding_provider import (
    LocalBgeH2EmbeddingProvider,
    LocalEmbeddingProviderError,
    build_h2_index_with_provider,
    build_h2_query_embedding_with_provider,
)
from treeguard.private_io import preflight_private_output, write_private_json
from treeguard.retrieval_hybrid import (
    build_hybrid_node_documents,
    build_hybrid_query_document,
    vector_leg_enabled,
)
from treeguard.retrieval_hybrid_h2 import (
    ALGORITHM_VERSION,
    FROZEN_BATCH_SIZE,
    H2EmbeddingIndex,
    RETRIEVAL_SEMANTICS,
    build_h2_candidate_set,
)
from treeguard.retrieval_roles import build_retrieval_role_evidence


FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_h2_local_embedding_calibration"
A_REPORT_NAME = "lexical-a-aggregate.v1.json"
REPORT_VERSION = "treeguard.h2-local-embedding-b-aggregate.v1"
PRIVATE_RESULT_VERSION = "treeguard.h2-local-embedding-b-private-result.v1"
RUNNER_VERSION = "treeguard.h2-local-embedding-b-runner.v1"
SCENARIO_COUNT = 28
POSITIVE_COUNT = 20
NON_LITERAL_COUNT = 10
HARD_NEGATIVE_COUNT = 4
EMPTY_COUNT = 4


class H2BRunnerError(ValueError):
    def __init__(self, code: str, *, inference_called: bool = False) -> None:
        self.code = code
        self.inference_called = inference_called
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class H2BSources:
    dataset_dir: Path
    tree: Any
    scenarios: list[Mapping[str, Any]]
    lexical_a: Mapping[str, Any]


def load_h2_b_sources(dataset_dir: Path = FIXTURE_DIR) -> H2BSources:
    tree, scenarios = load_public_inputs(dataset_dir)
    a_report = load_json_artifact(
        dataset_dir / A_REPORT_NAME, "H2_B_A_REPORT_INVALID"
    )
    if not isinstance(a_report, dict) or not _valid_a_report(a_report):
        raise H2BRunnerError("H2_B_A_REPORT_INVALID")
    return H2BSources(dataset_dir, tree, scenarios, a_report)


def _valid_a_report(report: Mapping[str, Any]) -> bool:
    try:
        return (
            report["schema_version"]
            == "treeguard.h2-local-lexical-a-aggregate.v1"
            and report["status"] == "H2_DATASET_DISCRIMINATIVE"
            and report["data_commit"] == DATA_COMMIT
            and report["source_manifest_hash"] == MANIFEST_HASH
            and report["embedding_used"] is False
            and report["provider_called"] is False
            and report["index_used"] is False
            and report["targeted_count"] == POSITIVE_COUNT
            and report["recall_at_20"] == {"hits": 16, "total": 20, "value": 0.8}
            and report["recall_at_8"] == {"hits": 16, "total": 20, "value": 0.8}
            and report["mrr_at_20"] == 0.775
            and report["non_literal_recall_at_20"]
            == {"hits": 6, "total": 10, "value": 0.6}
            and report["hard_negative_top_8"]
            == {"hits": 4, "total": 4, "value": 1.0}
            and report["explicit_empty"]
            == {"hits": 4, "total": 4, "value": 1.0}
        )
    except (KeyError, TypeError):
        return False


def _public_a_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "recall_at_20": report["recall_at_20"],
        "recall_at_8": report["recall_at_8"],
        "mrr_at_20": report["mrr_at_20"],
        "non_literal_recall_at_20": report["non_literal_recall_at_20"],
        "hard_negative_top_8": report["hard_negative_top_8"],
        "explicit_empty": report["explicit_empty"],
    }


def preflight_h2_b(sources: H2BSources) -> dict[str, Any]:
    documents = build_hybrid_node_documents(sources.tree)
    if len(sources.scenarios) != SCENARIO_COUNT or len(documents) != 733:
        raise H2BRunnerError("H2_B_DENOMINATOR_INVALID")
    lexical_observations = retrieve_public_scenarios(
        sources.tree, sources.scenarios
    )
    replayed_a = score_after_retrieval(
        sources.dataset_dir, sources.scenarios, lexical_observations
    )
    if replayed_a != sources.lexical_a:
        raise H2BRunnerError("H2_B_A_REPLAY_MISMATCH")
    lexical_baseline_recall_at_8 = _lexical_baseline_recall_at_8(
        sources.dataset_dir,
        sources.scenarios,
        lexical_observations,
    )
    return {
        "report_version": REPORT_VERSION,
        "status": "PREFLIGHT_READY",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "model_called": False,
        "formal_b_executed": False,
        "scenario_count": SCENARIO_COUNT,
        "positive_count": POSITIVE_COUNT,
        "node_count": len(documents),
        "batch_size": FROZEN_BATCH_SIZE,
        "planned_index_call_count": (len(documents) + FROZEN_BATCH_SIZE - 1)
        // FROZEN_BATCH_SIZE,
        "planned_query_call_count_max": SCENARIO_COUNT,
        "lexical_baseline_recall_at_8": {
            "hits": lexical_baseline_recall_at_8,
            "total": 4,
            "value": round(lexical_baseline_recall_at_8 / 4, 6),
        },
        "lexical_a": _public_a_metrics(sources.lexical_a),
    }


def _lexical_baseline_recall_at_8(
    dataset_dir: Path,
    scenarios: list[Mapping[str, Any]],
    observations: Mapping[str, tuple[str, tuple[str, ...]]],
) -> int:
    oracle = load_json_artifact(
        dataset_dir / "oracle-sidecar.v1.json", "H2_B_ORACLE_INVALID"
    )
    if not isinstance(oracle, dict):
        raise H2BRunnerError("H2_B_ORACLE_INVALID")
    verify_self_hash(oracle, "oracle_hash", "H2_B_ORACLE_INVALID")
    entries = oracle.get("entries")
    if not isinstance(entries, list):
        raise H2BRunnerError("H2_B_ORACLE_INVALID")
    targets = {
        item.get("scenario_id"): item.get("target_node_id")
        for item in entries
        if item.get("oracle_type") == "TARGET"
    }
    lexical_ids = [
        item.get("scenario_id")
        for item in scenarios
        if item.get("category") == "LEXICAL_BASELINE"
    ]
    if (
        len(lexical_ids) != 4
        or any(not isinstance(item, str) for item in lexical_ids)
        or any(not isinstance(targets.get(item), str) for item in lexical_ids)
    ):
        raise H2BRunnerError("H2_B_ORACLE_INVALID")
    return sum(
        targets[scenario_id] in observations[scenario_id][1][:8]
        for scenario_id in lexical_ids
    )


def retrieve_h2_scenarios(
    sources: H2BSources,
    index: H2EmbeddingIndex,
    provider: LocalBgeH2EmbeddingProvider,
) -> tuple[
    dict[str, tuple[str, tuple[str, ...]]],
    list[dict[str, Any]],
    list[float],
]:
    documents = build_hybrid_node_documents(sources.tree)
    observations: dict[str, tuple[str, tuple[str, ...]]] = {}
    private_cases: list[dict[str, Any]] = []
    query_seconds: list[float] = []
    query_replay_checked = False
    for scenario in sources.scenarios:
        try:
            scenario_id = scenario["scenario_id"]
            request = IntentRequest.from_dict(scenario["request"], sources.tree)
            annotations = tuple(
                (item["role"], item["text"])
                for item in scenario["role_annotations"]
            )
            evidence = build_retrieval_role_evidence(request, annotations)
            confirmation = build_confirmation(request, sources.tree)
            query_document = build_hybrid_query_document(
                evidence, request, confirmation, sources.tree
            )
            if vector_leg_enabled(query_document, documents):
                query_started = time.perf_counter()
                query_embedding = build_h2_query_embedding_with_provider(
                    provider, query_document
                )
                query_seconds.append(time.perf_counter() - query_started)
                if not query_replay_checked:
                    replay_started = time.perf_counter()
                    replay_embedding = build_h2_query_embedding_with_provider(
                        provider, query_document
                    )
                    query_seconds.append(time.perf_counter() - replay_started)
                    if replay_embedding != query_embedding:
                        raise H2BRunnerError(
                            "H2_B_EMBEDDING_REPLAY_MISMATCH",
                            inference_called=True,
                        )
                    query_replay_checked = True
                first = build_h2_candidate_set(
                    evidence,
                    request,
                    confirmation,
                    sources.tree,
                    profile=provider.profile,
                    index=index,
                    query_embedding=query_embedding,
                    max_candidates=20,
                )
                second = build_h2_candidate_set(
                    evidence,
                    request,
                    confirmation,
                    sources.tree,
                    profile=provider.profile,
                    index=index,
                    query_embedding=query_embedding,
                    max_candidates=20,
                )
            else:
                first = build_h2_candidate_set(
                    evidence,
                    request,
                    confirmation,
                    sources.tree,
                    profile=provider.profile,
                    max_candidates=20,
                )
                second = build_h2_candidate_set(
                    evidence,
                    request,
                    confirmation,
                    sources.tree,
                    profile=provider.profile,
                    max_candidates=20,
                )
        except (KeyError, TypeError, ValueError):
            raise H2BRunnerError(
                "H2_B_SCENARIO_INVALID",
                inference_called=provider.inference_call_count > 0,
            ) from None
        if (
            not isinstance(scenario_id, str)
            or scenario_id in observations
            or first.to_dict() != second.to_dict()
        ):
            raise H2BRunnerError(
                "H2_B_REPLAY_MISMATCH",
                inference_called=provider.inference_call_count > 0,
            )
        observations[scenario_id] = (
            first.status,
            tuple(item.node_id for item in first.candidates),
        )
        private_cases.append(
            {"scenario_id": scenario_id, "hybrid": first.to_dict()}
        )
    if not query_replay_checked:
        raise H2BRunnerError(
            "H2_B_EMBEDDING_NOT_EXERCISED",
            inference_called=provider.inference_call_count > 0,
        )
    return observations, private_cases, query_seconds


def build_b_report(
    lexical_a: Mapping[str, Any],
    scored_b: Mapping[str, Any],
    *,
    inference_call_count: int,
    lexical_baseline_a_at_8: int,
    lexical_baseline_b_at_8: int,
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    recall20 = scored_b["recall_at_20"]["hits"]
    recall8 = scored_b["recall_at_8"]["hits"]
    non_literal = scored_b["non_literal_recall_at_20"]["hits"]
    if recall20 < 18 or recall20 < lexical_a["recall_at_20"]["hits"] + 2:
        failures.append("H2_RECALL_AT_20_GATE_FAILED")
    if (
        non_literal < 8
        or non_literal
        < lexical_a["non_literal_recall_at_20"]["hits"] + 2
    ):
        failures.append("H2_NON_LITERAL_GATE_FAILED")
    if recall8 < lexical_a["recall_at_8"]["hits"]:
        failures.append("H2_RECALL_AT_8_REGRESSION")
    if scored_b["mrr_at_20"] < lexical_a["mrr_at_20"]:
        failures.append("H2_MRR_REGRESSION")
    if scored_b["hard_negative_top_8"]["hits"] != HARD_NEGATIVE_COUNT:
        failures.append("H2_HARD_NEGATIVE_REGRESSION")
    if scored_b["explicit_empty"]["hits"] != EMPTY_COUNT:
        failures.append("H2_EMPTY_STATUS_REGRESSION")
    if lexical_baseline_b_at_8 < lexical_baseline_a_at_8 - 1:
        failures.append("H2_LEXICAL_BASELINE_REGRESSION")
    return {
        "report_version": REPORT_VERSION,
        "status": "PASS" if not failures else "FAIL",
        "decision": "H2_CANDIDATE" if not failures else "H2_REJECTED",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "production_qualification": False,
        "patch_eligible": False,
        "formal_b_executed": True,
        "embedding_used": True,
        "provider_called": inference_call_count > 0,
        "index_used": True,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "inference_call_count": inference_call_count,
        "embedding_replay_match": True,
        "runtime": dict(runtime),
        "lexical_a": _public_a_metrics(lexical_a),
        "hybrid_b": {
            "recall_at_20": scored_b["recall_at_20"],
            "recall_at_8": scored_b["recall_at_8"],
            "mrr_at_20": scored_b["mrr_at_20"],
            "non_literal_recall_at_20": scored_b[
                "non_literal_recall_at_20"
            ],
            "hard_negative_top_8": scored_b["hard_negative_top_8"],
            "explicit_empty": scored_b["explicit_empty"],
            "lexical_baseline_recall_at_8": {
                "hits": lexical_baseline_b_at_8,
                "total": 4,
                "value": round(lexical_baseline_b_at_8 / 4, 6),
            },
        },
        "failure_codes": failures,
    }


def run_h2_b(
    sources: H2BSources,
    index: H2EmbeddingIndex,
    provider: LocalBgeH2EmbeddingProvider,
) -> tuple[dict[str, Any], dict[str, Any]]:
    observations, private_cases, query_seconds = retrieve_h2_scenarios(
        sources, index, provider
    )
    scored = score_after_retrieval(
        sources.dataset_dir,
        sources.scenarios,
        observations,
    )
    lexical_observations = retrieve_public_scenarios(
        sources.tree, sources.scenarios
    )
    lexical_baseline_a_at_8 = _lexical_baseline_recall_at_8(
        sources.dataset_dir,
        sources.scenarios,
        lexical_observations,
    )
    lexical_baseline_b_at_8 = _lexical_baseline_recall_at_8(
        sources.dataset_dir,
        sources.scenarios,
        observations,
    )
    sorted_query_seconds = sorted(query_seconds)
    runtime = {
        "query_count": len(query_seconds),
        "query_p50_milliseconds": _percentile_milliseconds(
            sorted_query_seconds, 50
        ),
        "query_p95_milliseconds": _percentile_milliseconds(
            sorted_query_seconds, 95
        ),
    }
    public = build_b_report(
        sources.lexical_a,
        scored,
        inference_call_count=provider.inference_call_count,
        lexical_baseline_a_at_8=lexical_baseline_a_at_8,
        lexical_baseline_b_at_8=lexical_baseline_b_at_8,
        runtime=runtime,
    )
    private = {
        "schema_version": PRIVATE_RESULT_VERSION,
        "runner_version": RUNNER_VERSION,
        "bindings": {
            "data_commit": DATA_COMMIT,
            "source_manifest_hash": MANIFEST_HASH,
            "source_profile_hash": provider.profile.profile_hash,
            "source_index_hash": index.index_hash,
        },
        "aggregate": public,
        "cases": private_cases,
    }
    return public, private


def _percentile_milliseconds(values: list[float], percentile: int) -> int:
    if not values or percentile not in {50, 95}:
        raise H2BRunnerError("H2_B_RUNTIME_METRICS_INVALID")
    index = ((len(values) * percentile + 99) // 100) - 1
    return int(values[max(0, min(index, len(values) - 1))] * 1_000)


def _same_resolved_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except (OSError, RuntimeError):
        raise H2BRunnerError("H2_B_LIVE_PATHS_INVALID") from None


def _error_report(code: str, *, inference_called: bool) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "status": "ERROR",
        "error_code": code,
        "model_called": inference_called,
        "formal_b_executed": inference_called,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, default=FIXTURE_DIR)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--execution-approved", action="store_true")
    parser.add_argument("--snapshot-dir", type=Path)
    index_group = parser.add_mutually_exclusive_group()
    index_group.add_argument("--index-input", type=Path)
    index_group.add_argument("--index-output", type=Path)
    parser.add_argument("--internal-output", type=Path)
    args = parser.parse_args(argv)
    provider: LocalBgeH2EmbeddingProvider | None = None
    live_started: float | None = None
    try:
        sources = load_h2_b_sources(args.dataset_dir)
        preflight = preflight_h2_b(sources)
        if args.preflight_only:
            if any(
                (
                    args.execution_approved,
                    args.snapshot_dir,
                    args.index_input,
                    args.index_output,
                    args.internal_output,
                )
            ):
                raise H2BRunnerError("H2_B_PREFLIGHT_OUTPUT_FORBIDDEN")
            print(json.dumps(preflight, ensure_ascii=False, sort_keys=True))
            return 0
        if (
            not args.execution_approved
            or args.snapshot_dir is None
            or args.internal_output is None
            or (args.index_input is None) == (args.index_output is None)
        ):
            raise H2BRunnerError("H2_B_EXECUTION_NOT_APPROVED")
        if args.index_output is not None and _same_resolved_path(
            args.index_output, args.internal_output
        ):
            raise H2BRunnerError("H2_B_LIVE_PATHS_INVALID")
        preflight_private_output(args.internal_output)
        if args.index_output is not None:
            preflight_private_output(args.index_output)
        live_started = time.perf_counter()
        provider_started = live_started
        provider = LocalBgeH2EmbeddingProvider.from_local_snapshot(
            args.snapshot_dir, batch_size=FROZEN_BATCH_SIZE
        )
        provider_loaded = time.perf_counter()
        index_started = provider_loaded
        if args.index_input is not None:
            embedding_index = read_private_h2_embedding_index(
                args.index_input, sources.tree, provider.profile
            )
        else:
            embedding_index = build_h2_index_with_provider(provider, sources.tree)
            if not write_private_h2_embedding_index(
                args.index_output, embedding_index
            ):
                raise H2BRunnerError(
                    "H2_B_INDEX_WRITE_FAILED", inference_called=True
                )
        index_ready = time.perf_counter()
        public, private = run_h2_b(sources, embedding_index, provider)
        finished = time.perf_counter()
        elapsed_seconds = finished - live_started
        if elapsed_seconds > 1_800:
            raise H2BRunnerError(
                "H2_B_ENGINEERING_TIMEOUT", inference_called=True
            )
        peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform != "darwin":
            peak_rss *= 1_024
        public["runtime"].update(
            {
                "model_load_milliseconds": int(
                    (provider_loaded - provider_started) * 1_000
                ),
                "index_milliseconds": int(
                    (index_ready - index_started) * 1_000
                ),
                "total_milliseconds": int(elapsed_seconds * 1_000),
                "peak_rss_bytes": peak_rss,
            }
        )
        private["aggregate"] = public
        if not write_private_json(args.internal_output, private):
            raise H2BRunnerError(
                "H2_B_RESULT_WRITE_FAILED", inference_called=True
            )
        print(json.dumps(public, ensure_ascii=False, sort_keys=True))
        return 0 if public["status"] == "PASS" else 1
    except LocalEmbeddingProviderError as error:
        called = bool(getattr(provider, "inference_call_count", 0))
        print(json.dumps(_error_report(error.code, inference_called=called)))
        return 3 if called else 2
    except (H2BRunnerError, OSError, TypeError, ValueError) as error:
        code = getattr(error, "code", "H2_B_RUNNER_FAILED")
        called = bool(getattr(error, "inference_called", False)) or bool(
            getattr(provider, "inference_call_count", 0)
        )
        print(json.dumps(_error_report(code, inference_called=called)))
        return 3 if called else 2


if __name__ == "__main__":
    raise SystemExit(main())
