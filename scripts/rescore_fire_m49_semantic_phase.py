#!/usr/bin/env python3
"""Produce a public-safe M4.9 Silver diagnostic from private run artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_fire_m49_runtime_plan import (  # noqa: E402
    FIXTURE_DIR,
    load_formal_intent_contexts,
)
from scripts.prepare_fire_m49_semantic_plan import (  # noqa: E402
    read_intent_results,
)
from scripts.run_fire_m49_intent_phase import read_approved_plan  # noqa: E402
from scripts.run_fire_m49_semantic_phase import (  # noqa: E402
    M49SemanticRunError,
    read_approved_semantic_plan,
    validate_result,
)
from treeguard.change_intent import ChangeIntentDraft  # noqa: E402
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.private_io import read_private_json  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    CapabilityOracle,
    intent_matches_oracle,
)


SAFE_ALTERNATIVE_ACTIONS = {
    "NEED_CLARIFICATION",
    "NEED_EVIDENCE",
    "ABSTAIN",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise M49SemanticRunError("M49_SEMANTIC_RESCORE_SOURCE_INVALID") from None
    return digest.hexdigest()


def score_semantic_item(item: dict[str, Any]) -> tuple[str, bool, bool]:
    """Return stage class, strict match and safe-but-nonpreferred acceptance."""

    if item["retrieval_status"] != "MATCH":
        return "UPSTREAM_SHORT_CIRCUIT", False, False
    if item["recommendation_status"] == "MATCH":
        return "PREFERRED_MATCH", True, True
    draft = item["draft"]
    if (
        item["recommendation_status"] == "MISMATCH"
        and isinstance(draft, dict)
        and draft.get("recommended_action") in SAFE_ALTERNATIVE_ACTIONS
    ):
        return "SAFE_ALTERNATIVE", False, True
    if item["recommendation_status"] == "RUN_FAILED":
        return "RUN_FAILED", False, False
    return "UNSAFE_MISMATCH", False, False


def _read_oracles(fixture_dir: Path) -> dict[str, CapabilityOracle]:
    try:
        payload = strict_json_loads(
            (fixture_dir / "oracle-sidecar.json").read_text(encoding="utf-8")
        )
        return {
            item["scenario_ref"]: CapabilityOracle.from_dict(item["oracle"])
            for item in payload["items"]
        }
    except (KeyError, OSError, TypeError, UnicodeError, ValueError):
        raise M49SemanticRunError("M49_SEMANTIC_RESCORE_SOURCE_INVALID") from None


def rescore(
    *,
    semantic_result_file: Path,
    semantic_result_sha256: str,
    semantic_plan_file: Path,
    semantic_plan_sha256: str,
    intent_plan_file: Path,
    intent_plan_sha256: str,
    intent_results_file: Path,
    intent_results_sha256: str,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
    plan = read_approved_semantic_plan(
        semantic_plan_file,
        semantic_plan_sha256,
        intent_plan_file=intent_plan_file,
        intent_plan_sha256=intent_plan_sha256,
        intent_results_file=intent_results_file,
        intent_results_sha256=intent_results_sha256,
        fixture_dir=fixture_dir,
    )
    try:
        semantic_results = read_private_json(
            semantic_result_file, max_bytes=10_000_000
        )
        if (
            _sha256_file(semantic_result_file) != semantic_result_sha256
            or stat.S_IMODE(semantic_result_file.stat().st_mode) != 0o600
        ):
            raise ValueError
        validate_result(semantic_results, plan, semantic_plan_sha256)
        intent_plan = read_approved_plan(
            intent_plan_file, intent_plan_sha256, fixture_dir
        )
        intent_results = read_intent_results(
            intent_results_file,
            intent_results_sha256,
            intent_plan,
            intent_plan_sha256,
        )
        contexts = {
            context.scenario_ref: context
            for context in load_formal_intent_contexts(fixture_dir)
        }
        oracles = _read_oracles(fixture_dir)
    except (M49SemanticRunError, OSError, TypeError, ValueError):
        raise M49SemanticRunError("M49_SEMANTIC_RESCORE_SOURCE_INVALID") from None

    strict_by_ref: dict[str, bool] = {}
    safe_by_ref: dict[str, bool] = {}
    semantic_classes: dict[str, int] = {}
    for item in semantic_results["results"]:
        stage_class, strict_match, safe_match = score_semantic_item(item)
        semantic_classes[stage_class] = semantic_classes.get(stage_class, 0) + 1
        strict_by_ref[item["observation_ref"]] = strict_match
        safe_by_ref[item["observation_ref"]] = safe_match

    for item in intent_results["results"]:
        observation_ref = item["observation_ref"]
        if observation_ref in strict_by_ref:
            continue
        context = contexts[item["scenario_ref"]]
        oracle = oracles[item["scenario_ref"]]
        draft = ChangeIntentDraft.from_dict(
            item["draft"], context.request, context.tree
        )
        clarification_match = (
            oracle.expected_route == "CLARIFY"
            and intent_matches_oracle(draft, oracle)
        )
        strict_by_ref[observation_ref] = clarification_match
        safe_by_ref[observation_ref] = clarification_match

    if len(strict_by_ref) != 72 or len(safe_by_ref) != 72:
        raise M49SemanticRunError("M49_SEMANTIC_RESCORE_ACCOUNTING_INVALID")
    strict_round_counts = [
        sum(
            matched
            for observation_ref, matched in strict_by_ref.items()
            if observation_ref.startswith(f"R{round_index:02d}:")
        )
        for round_index in range(1, 4)
    ]
    safe_round_counts = [
        sum(
            matched
            for observation_ref, matched in safe_by_ref.items()
            if observation_ref.startswith(f"R{round_index:02d}:")
        )
        for round_index in range(1, 4)
    ]
    strict_stable = sum(
        all(
            strict_by_ref[f"R{round_index:02d}:{scenario_ref}"]
            for round_index in range(1, 4)
        )
        for scenario_ref in contexts
    )
    safe_stable = sum(
        all(
            safe_by_ref[f"R{round_index:02d}:{scenario_ref}"]
            for round_index in range(1, 4)
        )
        for scenario_ref in contexts
    )
    scored_semantic_count = (
        semantic_results["retrieval_match_count"]
    )
    report = {
        "report_version": "treeguard.m49-semantic-silver-diagnostic.v1",
        "status": "PASS",
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "semantic_wire_observation_count": semantic_results[
            "semantic_observation_count"
        ],
        "semantic_scored_observation_count": scored_semantic_count,
        "semantic_upstream_short_circuit_count": semantic_classes.get(
            "UPSTREAM_SHORT_CIRCUIT", 0
        ),
        "semantic_wire_contract_legal_count": semantic_results[
            "draft_ready_count"
        ],
        "semantic_scored_contract_legal_count": sum(
            semantic_classes.get(code, 0)
            for code in (
                "PREFERRED_MATCH",
                "SAFE_ALTERNATIVE",
                "UNSAFE_MISMATCH",
            )
        ),
        "semantic_scored_contract_failed_count": semantic_classes.get(
            "RUN_FAILED", 0
        ),
        "recommendation_preferred_match_count": semantic_classes.get(
            "PREFERRED_MATCH", 0
        ),
        "recommendation_safe_alternative_count": semantic_classes.get(
            "SAFE_ALTERNATIVE", 0
        ),
        "recommendation_unsafe_mismatch_count": semantic_classes.get(
            "UNSAFE_MISMATCH", 0
        ),
        "retrieval_match_count": semantic_results["retrieval_match_count"],
        "retrieval_mismatch_count": semantic_results["retrieval_mismatch_count"],
        "strict_end_to_end_match_count": sum(strict_by_ref.values()),
        "strict_end_to_end_mismatch_count": 72 - sum(strict_by_ref.values()),
        "strict_round_match_counts": strict_round_counts,
        "strict_stable_scenario_count": strict_stable,
        "safe_end_to_end_match_count": sum(safe_by_ref.values()),
        "safe_end_to_end_mismatch_count": 72 - sum(safe_by_ref.values()),
        "safe_round_match_counts": safe_round_counts,
        "safe_stable_scenario_count": safe_stable,
        "next_gate": "HUMAN_REVIEW_SILVER_ORACLE_AND_ACTION_POLICY",
    }
    if (
        sum(semantic_classes.values())
        != semantic_results["semantic_observation_count"]
        or scored_semantic_count
        != sum(
            semantic_classes.get(code, 0)
            for code in (
                "PREFERRED_MATCH",
                "SAFE_ALTERNATIVE",
                "UNSAFE_MISMATCH",
                "RUN_FAILED",
            )
        )
    ):
        raise M49SemanticRunError("M49_SEMANTIC_RESCORE_ACCOUNTING_INVALID")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-result-file", type=Path, required=True)
    parser.add_argument("--semantic-result-sha256", required=True)
    parser.add_argument("--semantic-plan-file", type=Path, required=True)
    parser.add_argument("--semantic-plan-sha256", required=True)
    parser.add_argument("--intent-plan-file", type=Path, required=True)
    parser.add_argument("--intent-plan-sha256", required=True)
    parser.add_argument("--intent-results-file", type=Path, required=True)
    parser.add_argument("--intent-results-sha256", required=True)
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = rescore(
            semantic_result_file=args.semantic_result_file,
            semantic_result_sha256=args.semantic_result_sha256,
            semantic_plan_file=args.semantic_plan_file,
            semantic_plan_sha256=args.semantic_plan_sha256,
            intent_plan_file=args.intent_plan_file,
            intent_plan_sha256=args.intent_plan_sha256,
            intent_results_file=args.intent_results_file,
            intent_results_sha256=args.intent_results_sha256,
            fixture_dir=args.fixture_dir,
        )
    except M49SemanticRunError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
