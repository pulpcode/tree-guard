#!/usr/bin/env python3
"""Score frozen M4.9 Intent results and freeze exact Semantic v4 bodies."""

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
    wire_bytes,
)
from scripts.run_fire_m49_intent_phase import (  # noqa: E402
    M49IntentRunError,
    read_approved_plan,
    validate_result,
)
from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianSemanticRecommendationV4Provider,
)
from treeguard.change_intent import (  # noqa: E402
    ChangeIntentDraft,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.hashing import canonical_digest  # noqa: E402
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.private_io import read_private_json, write_private_json  # noqa: E402
from treeguard.retrieval import build_candidate_set  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    CapabilityOracle,
    intent_matches_oracle,
)
from treeguard.semantic_recommendation import (  # noqa: E402
    build_semantic_candidate_projection,
)


PLAN_SCHEMA_VERSION = "fire-m49-sealed-semantic-plan.v1"
REVIEWER_REF = "m49-deterministic-intent-bridge"
RECORDED_AT = "2030-01-02T03:06:00Z"
SEMANTIC_RETRY_CODES = (
    "SEMANTIC_ACTION_INVALID",
    "SEMANTIC_ACTION_POLICY_INVALID",
    "SEMANTIC_ASSESSMENTS_INVALID",
    "SEMANTIC_CANDIDATE_COVERAGE_INVALID",
    "SEMANTIC_CANDIDATE_REF_INVALID",
    "SEMANTIC_CONTEXT_EVIDENCE_REQUIRED",
    "SEMANTIC_INTERNAL_ID_FORBIDDEN",
    "SEMANTIC_MODEL_FIELDS_INVALID",
    "SEMANTIC_MODEL_OUTPUT_INVALID",
    "SEMANTIC_MODEL_RESPONSE_INVALID",
    "SEMANTIC_MODEL_VERSION_INVALID",
    "SEMANTIC_RELATION_INVALID",
    "SEMANTIC_SELECTED_CANDIDATE_CONTRACT_CONFLICT",
    "SEMANTIC_SELECTED_CANDIDATE_INVALID",
    "SEMANTIC_TEXT_INVALID",
    "SEMANTIC_TEXT_LIST_INVALID",
)


class M49SemanticPlanError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise M49SemanticPlanError("M49_SEMANTIC_SOURCE_INVALID") from None
    return digest.hexdigest()


def read_intent_results(
    path: Path,
    expected_sha256: str,
    plan: dict[str, Any],
    approved_plan_sha256: str,
) -> dict[str, Any]:
    try:
        payload = read_private_json(path, max_bytes=10_000_000)
        if (
            _sha256_file(path) != expected_sha256
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise ValueError
        validate_result(payload, plan)
        if payload["plan_file_sha256"] != approved_plan_sha256:
            raise ValueError
    except (
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        M49IntentRunError,
    ):
        raise M49SemanticPlanError("M49_SEMANTIC_INTENT_RESULTS_INVALID") from None
    return payload


def _read_fixture_json(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeError, ValueError):
        raise M49SemanticPlanError("M49_SEMANTIC_FIXTURE_INVALID") from None


def build_plan(
    *,
    intent_plan_file: Path,
    intent_plan_sha256: str,
    intent_results_file: Path,
    intent_results_sha256: str,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
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
    oracle_sidecar = _read_fixture_json(fixture_dir / "oracle-sidecar.json")
    oracle_by_ref = {
        item["scenario_ref"]: CapabilityOracle.from_dict(item["oracle"])
        for item in oracle_sidecar["items"]
    }
    provider = BailianSemanticRecommendationV4Provider(
        BailianConfig(
            api_key="NOT_USED_FOR_LOCAL_PLAN",
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            timeout_seconds=90.0,
            max_attempts=2,
            max_transport_retries=1,
        )
    )

    units = []
    route_matches = 0
    intent_matches = 0
    for result in intent_results["results"]:
        context = contexts[result["scenario_ref"]]
        oracle = oracle_by_ref[result["scenario_ref"]]
        draft = ChangeIntentDraft.from_dict(
            result["draft"], context.request, context.tree
        )
        actual_route = (
            "CLARIFY"
            if draft.review_status == "NEEDS_CLARIFICATION"
            else "PROCEED"
        )
        if actual_route == oracle.expected_route:
            route_matches += 1
        if not intent_matches_oracle(draft, oracle):
            continue
        intent_matches += 1
        if oracle.expected_route != "PROCEED":
            continue
        confirmation = apply_intent_review(
            context.request,
            draft,
            IntentReviewAction(
                expected_draft_hash=draft.draft_hash,
                decision="CONFIRM_FOR_RETRIEVAL",
                reviewer_ref=REVIEWER_REF,
                recorded_at=RECORDED_AT,
                confirmed_intent=draft.intent,
            ),
            context.tree,
        )
        candidate_set = build_candidate_set(confirmation, context.tree)
        projection = build_semantic_candidate_projection(
            confirmation, candidate_set, context.tree
        )
        possible_requests = []
        for attempt, retry_code in ((1, None),) + tuple(
            (2, code) for code in SEMANTIC_RETRY_CODES
        ):
            body = provider._semantic_request_body(
                projection, retry_code=retry_code
            )
            encoded = wire_bytes(body)
            possible_requests.append(
                {
                    "attempt": attempt,
                    "retry_code": retry_code,
                    "stage": "SEMANTIC_RECOMMENDATION",
                    "wire_body_text": encoded.decode("utf-8"),
                    "wire_sha256": hashlib.sha256(encoded).hexdigest(),
                }
            )
        units.append(
            {
                "observation_ref": result["observation_ref"],
                "round_index": result["round_index"],
                "scenario_ref": result["scenario_ref"],
                "source_intent_draft_hash": draft.draft_hash,
                "source_confirmation_hash": confirmation.confirmation_hash,
                "source_candidate_set_hash": candidate_set.candidate_set_hash,
                "possible_requests": possible_requests,
            }
        )

    possible_count = len(units) * (1 + len(SEMANTIC_RETRY_CODES))
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "purpose": "M49_SEALED_SILVER_SEMANTIC_ONLY",
        "dataset_ref": intent_plan["dataset_ref"],
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "execution_authorized": False,
        "contains_oracle": False,
        "contains_credentials": False,
        "endpoint": DEFAULT_BASE_URL.rstrip("/") + "/chat/completions",
        "model": DEFAULT_MODEL,
        "prompt_version": provider.prompt_version,
        "timeout_seconds": 90.0,
        "max_contract_attempts": 2,
        "max_transport_retries": 1,
        "source_intent_plan_sha256": intent_plan_sha256,
        "source_intent_results_sha256": intent_results_sha256,
        "intent_observation_count": 72,
        "intent_route_match_count": route_matches,
        "intent_full_match_count": intent_matches,
        "semantic_observation_count": len(units),
        "initial_request_count": len(units),
        "maximum_actual_request_count": len(units) * 3,
        "possible_request_body_count": possible_count,
        "retry_policy": "TWO_CONTRACT_ATTEMPTS_AND_ONE_CONNECTION_RECOVERY",
        "units": units,
        "next_gate": "EXPLICIT_SEMANTIC_EXECUTION_APPROVAL",
    }
    plan["plan_digest"] = canonical_digest(plan)
    validate_plan(plan, fixture_dir)
    return plan


def validate_plan(plan: Any, fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("plan_digest") != canonical_digest(
        {key: value for key, value in plan.items() if key != "plan_digest"}
    ):
        raise M49SemanticPlanError("M49_SEMANTIC_PLAN_DIGEST_INVALID")
    units = plan.get("units")
    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or plan.get("source_class") != "CLEANROOM_SYNTHETIC"
        or plan.get("fictional") is not True
        or plan.get("derived_from_real") is not False
        or plan.get("execution_authorized") is not False
        or plan.get("contains_oracle") is not False
        or plan.get("contains_credentials") is not False
        or plan.get("endpoint")
        != DEFAULT_BASE_URL.rstrip("/") + "/chat/completions"
        or plan.get("model") != DEFAULT_MODEL
        or plan.get("prompt_version")
        != "treeguard.semantic-recommendation.zh.v4"
        or not isinstance(units, list)
        or plan.get("semantic_observation_count") != len(units)
        or plan.get("initial_request_count") != len(units)
        or plan.get("maximum_actual_request_count") != len(units) * 3
        or plan.get("possible_request_body_count")
        != len(units) * (1 + len(SEMANTIC_RETRY_CODES))
        or plan.get("next_gate") != "EXPLICIT_SEMANTIC_EXECUTION_APPROVAL"
    ):
        raise M49SemanticPlanError("M49_SEMANTIC_PLAN_POLICY_INVALID")
    text = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    forbidden = ('"acceptable_node_ids"', '"acceptable_outcomes"', '"target_node_id"')
    if any(marker in text for marker in forbidden):
        raise M49SemanticPlanError("M49_SEMANTIC_ORACLE_LEAK")
    oracle = _read_fixture_json(fixture_dir / "oracle-sidecar.json")
    target_ids = {
        node_id
        for item in oracle["items"]
        for node_id in (
            list(item["oracle"]["retrieval"]["acceptable_node_ids"])
            + [
                outcome["target_node_id"]
                for outcome in item["oracle"]["recommendation"]["acceptable_outcomes"]
                if outcome["target_node_id"] is not None
            ]
        )
    }
    if any(json.dumps(node_id, ensure_ascii=False) in text for node_id in target_ids):
        raise M49SemanticPlanError("M49_SEMANTIC_ORACLE_LEAK")
    return {
        "status": "PASS",
        "intent_observation_count": plan["intent_observation_count"],
        "intent_route_match_count": plan["intent_route_match_count"],
        "intent_full_match_count": plan["intent_full_match_count"],
        "semantic_observation_count": len(units),
        "possible_request_body_count": plan["possible_request_body_count"],
        "maximum_actual_request_count": plan["maximum_actual_request_count"],
        "execution_authorized": False,
    }


def write_plan(output: Path, **kwargs: Any) -> dict[str, Any]:
    if output.exists():
        raise M49SemanticPlanError("M49_SEMANTIC_OUTPUT_EXISTS")
    plan = build_plan(**kwargs)
    if not write_private_json(output, plan):
        raise M49SemanticPlanError("M49_SEMANTIC_OUTPUT_INVALID")
    if stat.S_IMODE(output.stat().st_mode) != 0o600:
        output.unlink(missing_ok=True)
        raise M49SemanticPlanError("M49_SEMANTIC_OUTPUT_INVALID")
    return validate_plan(plan, kwargs.get("fixture_dir", FIXTURE_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent-plan-file", type=Path, required=True)
    parser.add_argument("--intent-plan-sha256", required=True)
    parser.add_argument("--intent-results-file", type=Path, required=True)
    parser.add_argument("--intent-results-sha256", required=True)
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = write_plan(
            args.output,
            intent_plan_file=args.intent_plan_file,
            intent_plan_sha256=args.intent_plan_sha256,
            intent_results_file=args.intent_results_file,
            intent_results_sha256=args.intent_results_sha256,
            fixture_dir=args.fixture_dir,
        )
    except M49SemanticPlanError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
