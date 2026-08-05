#!/usr/bin/env python3
"""Evaluate a deterministic action policy on frozen M4.9 relations."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
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
    M49SemanticPlanError,
    RECORDED_AT,
    REVIEWER_REF,
    read_intent_results,
)
from scripts.run_fire_m49_intent_phase import (  # noqa: E402
    M49IntentRunError,
    read_approved_plan,
)
from scripts.run_fire_m49_semantic_phase import (  # noqa: E402
    M49SemanticRunError,
    read_approved_semantic_plan,
    validate_result,
)
from treeguard.change_intent import (  # noqa: E402
    ChangeIntentDraft,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.private_io import read_private_json  # noqa: E402
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.retrieval import build_candidate_set  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    CapabilityOracle,
    RecommendationOracleOutcome,
)
from treeguard.semantic_recommendation import (  # noqa: E402
    SemanticRecommendationDraft,
    build_semantic_candidate_projection,
)


RESULT_SCHEMA_VERSION = "m49-relation-only-policy-result.v1"
EXPECTED_ELIGIBLE_COUNT = 51
EXPECTED_BASELINE_PREFERRED = 19
EXPECTED_BASELINE_SAFE = 32
PREREGISTERED_SHA256 = {
    "semantic_results": (
        "799883f8d4d27d33591a876ee16ed4108b306cfd20b15b7e1aecfac9724363fe"
    ),
    "intent_results": (
        "919fd1f873967b755c4d1ce3c5b481e75ce9c2edbe5c668e88bbce635ad4777f"
    ),
    "semantic_plan": (
        "07904d7537c958dd15668810a8af0d4553e8d2d0091eca10d27b7e735ba0a299"
    ),
    "intent_plan": (
        "6244d4632563934e2ed31cb37329156d3275155e81bb864a61700d8023ed9165"
    ),
}
SAFE_NON_TARGETING_ACTIONS = {
    "NEED_CLARIFICATION",
    "NEED_EVIDENCE",
    "ABSTAIN",
}


class RelationOnlyPolicyError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _compatible(projection: Any, candidate_ref: str) -> bool:
    candidate = next(
        item
        for item in projection.candidates
        if item.candidate_ref == candidate_ref
    )
    intent = projection.intent
    return not (
        (intent.node_kind != "UNKNOWN" and candidate.kind != intent.node_kind)
        or (
            intent.value_type is not None
            and candidate.value_type != intent.value_type
        )
        or (
            intent.cardinality != "UNKNOWN"
            and candidate.cardinality != intent.cardinality
        )
    )


def derive_relation_only_outcome(
    draft: SemanticRecommendationDraft,
    candidate_set: Any,
    projection: Any,
) -> RecommendationOracleOutcome:
    """Map validated per-candidate relations to one deterministic outcome."""

    candidate_by_ref = {
        f"C{candidate.rank:03d}": candidate
        for candidate in candidate_set.candidates[:8]
    }
    equivalent_refs = tuple(
        item.candidate_ref
        for item in draft.candidate_assessments
        if item.relation == "SEMANTICALLY_EQUIVALENT"
        and _compatible(projection, item.candidate_ref)
    )
    if len(equivalent_refs) == 1:
        selected_ref = equivalent_refs[0]
        return RecommendationOracleOutcome(
            action="USE_EXISTING_NODE",
            target_node_id=candidate_by_ref[selected_ref].node_id,
            relation="SEMANTICALLY_EQUIVALENT",
        )
    if len(equivalent_refs) > 1:
        return RecommendationOracleOutcome(
            action="NEED_CLARIFICATION",
            target_node_id=None,
            relation=None,
        )
    if any(
        item.relation == "NEED_EVIDENCE"
        for item in draft.candidate_assessments
    ):
        return RecommendationOracleOutcome(
            action="NEED_EVIDENCE",
            target_node_id=None,
            relation=None,
        )
    return RecommendationOracleOutcome(
        action="ABSTAIN",
        target_node_id=None,
        relation=None,
    )


def _classify(outcome: RecommendationOracleOutcome, oracle: Any) -> str:
    if outcome in oracle.recommendation.acceptable_outcomes:
        return "PREFERRED_MATCH"
    if outcome.action in SAFE_NON_TARGETING_ACTIONS:
        return "SAFE_ALTERNATIVE"
    return "UNSAFE_MISMATCH"


def _baseline_class(item: dict[str, Any]) -> str:
    if item["recommendation_status"] == "MATCH":
        return "PREFERRED_MATCH"
    draft = item["draft"]
    if isinstance(draft, dict) and (
        draft["recommended_action"] in SAFE_NON_TARGETING_ACTIONS
    ):
        return "SAFE_ALTERNATIVE"
    return "UNSAFE_MISMATCH"


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
        raise RelationOnlyPolicyError("RELATION_POLICY_SOURCE_INVALID") from None


def evaluate(
    *,
    semantic_result_file: Path,
    semantic_plan_file: Path,
    intent_plan_file: Path,
    intent_results_file: Path,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
    try:
        semantic_plan = read_approved_semantic_plan(
            semantic_plan_file,
            PREREGISTERED_SHA256["semantic_plan"],
            intent_plan_file=intent_plan_file,
            intent_plan_sha256=PREREGISTERED_SHA256["intent_plan"],
            intent_results_file=intent_results_file,
            intent_results_sha256=PREREGISTERED_SHA256["intent_results"],
            fixture_dir=fixture_dir,
        )
        semantic_results = read_private_json(
            semantic_result_file,
            max_bytes=10_000_000,
        )
        validate_result(
            semantic_results,
            semantic_plan,
            PREREGISTERED_SHA256["semantic_plan"],
        )
        intent_plan = read_approved_plan(
            intent_plan_file,
            PREREGISTERED_SHA256["intent_plan"],
            fixture_dir,
        )
        intent_results = read_intent_results(
            intent_results_file,
            PREREGISTERED_SHA256["intent_results"],
            intent_plan,
            PREREGISTERED_SHA256["intent_plan"],
        )
        contexts = {
            item.scenario_ref: item
            for item in load_formal_intent_contexts(fixture_dir)
        }
        oracles = _read_oracles(fixture_dir)
        intent_by_ref = {
            item["observation_ref"]: item
            for item in intent_results["results"]
        }
    except (
        KeyError,
        M49IntentRunError,
        M49SemanticPlanError,
        M49SemanticRunError,
        OSError,
        TypeError,
        ValueError,
    ):
        raise RelationOnlyPolicyError("RELATION_POLICY_SOURCE_INVALID") from None

    baseline_counts: Counter[str] = Counter()
    policy_counts: Counter[str] = Counter()
    migrations: Counter[str] = Counter()
    outcomes_by_scenario: dict[str, list[tuple[int, tuple[Any, ...]]]] = (
        defaultdict(list)
    )
    replay_match_count = 0
    eligible_count = 0
    try:
        for item in semantic_results["results"]:
            if item["retrieval_status"] != "MATCH" or item["draft"] is None:
                continue
            context = contexts[item["scenario_ref"]]
            oracle = oracles[item["scenario_ref"]]
            source_intent = intent_by_ref[item["observation_ref"]]
            intent_draft = ChangeIntentDraft.from_dict(
                source_intent["draft"],
                context.request,
                context.tree,
            )
            confirmation = apply_intent_review(
                context.request,
                intent_draft,
                IntentReviewAction(
                    expected_draft_hash=intent_draft.draft_hash,
                    decision="CONFIRM_FOR_RETRIEVAL",
                    reviewer_ref=REVIEWER_REF,
                    recorded_at=RECORDED_AT,
                    confirmed_intent=intent_draft.intent,
                ),
                context.tree,
            )
            candidate_set = build_candidate_set(confirmation, context.tree)
            draft = SemanticRecommendationDraft.from_dict(
                item["draft"],
                confirmation,
                candidate_set,
                context.tree,
            )
            projection = build_semantic_candidate_projection(
                confirmation,
                candidate_set,
                context.tree,
            )
            first = derive_relation_only_outcome(
                draft,
                candidate_set,
                projection,
            )
            second = derive_relation_only_outcome(
                draft,
                candidate_set,
                projection,
            )
            replay_match_count += first == second
            baseline = _baseline_class(item)
            policy = _classify(first, oracle)
            baseline_counts[baseline] += 1
            policy_counts[policy] += 1
            migrations[f"{baseline}->{policy}"] += 1
            outcomes_by_scenario[item["scenario_ref"]].append(
                (
                    item["round_index"],
                    (first.action, first.target_node_id, first.relation),
                )
            )
            eligible_count += 1
    except (KeyError, StopIteration, TypeError, ValueError):
        raise RelationOnlyPolicyError("RELATION_POLICY_EVALUATION_INVALID") from None

    if (
        eligible_count != EXPECTED_ELIGIBLE_COUNT
        or baseline_counts["PREFERRED_MATCH"]
        != EXPECTED_BASELINE_PREFERRED
        or baseline_counts["SAFE_ALTERNATIVE"] != EXPECTED_BASELINE_SAFE
        or baseline_counts["UNSAFE_MISMATCH"] != 0
    ):
        raise RelationOnlyPolicyError("RELATION_POLICY_DENOMINATOR_INVALID")

    complete_scenarios = 0
    stable_complete_scenarios = 0
    for observations in outcomes_by_scenario.values():
        if sorted(round_index for round_index, _ in observations) != [1, 2, 3]:
            continue
        complete_scenarios += 1
        stable_complete_scenarios += len(
            {outcome for _, outcome in observations}
        ) == 1

    gates = {
        "unsafe_zero": policy_counts["UNSAFE_MISMATCH"] == 0,
        "preferred_not_lower": (
            policy_counts["PREFERRED_MATCH"]
            >= EXPECTED_BASELINE_PREFERRED
        ),
        "accepted_all": (
            policy_counts["PREFERRED_MATCH"]
            + policy_counts["SAFE_ALTERNATIVE"]
            == eligible_count
        ),
        "replay_all": replay_match_count == eligible_count,
    }
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "PASS",
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "model_call_count": 0,
        "eligible_observation_count": eligible_count,
        "baseline_counts": dict(sorted(baseline_counts.items())),
        "relation_only_counts": dict(sorted(policy_counts.items())),
        "migration_counts": dict(sorted(migrations.items())),
        "deterministic_replay_match_count": replay_match_count,
        "complete_three_round_scenario_count": complete_scenarios,
        "stable_complete_three_round_scenario_count": (
            stable_complete_scenarios
        ),
        "gates": gates,
        "decision": (
            "RELATION_ONLY_POLICY_VIABLE"
            if all(gates.values())
            else "MODEL_ACTION_SIGNAL_REQUIRED"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-results", type=Path, required=True)
    parser.add_argument("--semantic-plan", type=Path, required=True)
    parser.add_argument("--intent-plan", type=Path, required=True)
    parser.add_argument("--intent-results", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = evaluate(
            semantic_result_file=args.semantic_results,
            semantic_plan_file=args.semantic_plan,
            intent_plan_file=args.intent_plan,
            intent_results_file=args.intent_results,
            fixture_dir=args.fixture_dir,
        )
    except RelationOnlyPolicyError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
