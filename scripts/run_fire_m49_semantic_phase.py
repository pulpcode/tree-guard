#!/usr/bin/env python3
"""Run the explicitly approved M4.9 Semantic observations and score locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
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
from scripts.prepare_fire_m49_semantic_plan import (  # noqa: E402
    M49SemanticPlanError,
    build_plan,
    read_intent_results,
    validate_plan,
)
from scripts.run_fire_m49_intent_phase import (  # noqa: E402
    M49IntentRunError,
    read_approved_plan,
)
from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianProviderError,
    BailianSemanticRecommendationV4Provider,
)
from treeguard.change_intent import (  # noqa: E402
    ChangeIntentDraft,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.private_io import (  # noqa: E402
    preflight_private_output,
    read_private_json,
    write_private_json,
)
from treeguard.retrieval import build_candidate_set  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    CapabilityOracle,
    intent_matches_oracle,
    recommendation_matches_oracle,
    retrieval_matches_oracle,
)


RESULT_SCHEMA_VERSION = "fire-m49-sealed-semantic-results.v1"
REVIEWER_REF = "m49-deterministic-intent-bridge"
RECORDED_AT = "2030-01-02T03:06:00Z"
RESULT_KEYS = {
    "schema_version",
    "purpose",
    "dataset_ref",
    "source_class",
    "fictional",
    "derived_from_real",
    "quality_tier",
    "evaluation_role",
    "gold_eligible",
    "gate_eligible",
    "patch_eligible",
    "contains_oracle",
    "contains_credentials",
    "semantic_plan_file_sha256",
    "source_intent_plan_sha256",
    "source_intent_results_sha256",
    "model",
    "prompt_version",
    "intent_observation_count",
    "intent_full_match_count",
    "semantic_observation_count",
    "actual_request_count",
    "single_wire_call_count",
    "multi_wire_call_observation_count",
    "contract_retry_observation_count",
    "transport_retry_call_count",
    "draft_ready_count",
    "run_failed_count",
    "failure_code_counts",
    "validation_error_code_counts",
    "retrieval_match_count",
    "retrieval_mismatch_count",
    "recommendation_match_count",
    "recommendation_mismatch_count",
    "clarification_end_to_end_match_count",
    "end_to_end_match_count",
    "end_to_end_mismatch_count",
    "stable_scenario_count",
    "unstable_scenario_count",
    "results",
    "next_gate",
}
RESULT_ITEM_KEYS = {
    "observation_ref",
    "round_index",
    "scenario_ref",
    "source_intent_draft_hash",
    "source_confirmation_hash",
    "source_candidate_set_hash",
    "status",
    "failure_code",
    "calls",
    "validation_error_codes",
    "retrieval_status",
    "recommendation_status",
    "end_to_end_status",
    "draft",
}


class M49SemanticRunError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PlannedSemanticProvider(BailianSemanticRecommendationV4Provider):
    """Enforce frozen body membership and a three-wire-call unit cap."""

    def __init__(
        self,
        config: BailianConfig,
        allowed_hashes: set[str],
        audit: list[dict[str, Any]],
    ) -> None:
        self.validation_error_codes: list[str] = []
        super().__init__(config, trace_sink=self._capture_trace)
        self.allowed_hashes = frozenset(allowed_hashes)
        self.audit = audit

    def _capture_trace(self, trace: Any) -> None:
        if (
            trace.validation_status == "FAILED"
            and isinstance(trace.validation_error_code, str)
        ):
            self.validation_error_codes.append(trace.validation_error_code)

    def _post_json(self, body: dict[str, Any]) -> Any:
        digest = hashlib.sha256(wire_bytes(body)).hexdigest()
        if digest not in self.allowed_hashes:
            raise M49SemanticRunError("M49_SEMANTIC_BODY_NOT_PLANNED")
        if len(self.audit) >= 3:
            raise M49SemanticRunError("M49_SEMANTIC_UNIT_CALL_LIMIT_EXCEEDED")
        self.audit.append(
            {"attempt": len(self.audit) + 1, "wire_sha256": digest}
        )
        return super()._post_json(body)


def validate_tls_trust() -> None:
    try:
        trusted_roots = ssl.create_default_context().get_ca_certs()
    except (OSError, ssl.SSLError):
        raise M49SemanticRunError("M49_SEMANTIC_TLS_TRUST_UNAVAILABLE") from None
    if not trusted_roots:
        raise M49SemanticRunError("M49_SEMANTIC_TLS_TRUST_UNAVAILABLE")


def _sha256_file(path: Path, *, error_code: str) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise M49SemanticRunError(error_code) from None
    return digest.hexdigest()


def read_approved_semantic_plan(
    path: Path,
    expected_sha256: str,
    *,
    intent_plan_file: Path,
    intent_plan_sha256: str,
    intent_results_file: Path,
    intent_results_sha256: str,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
    try:
        plan = read_private_json(path, max_bytes=30_000_000)
        if (
            _sha256_file(path, error_code="M49_SEMANTIC_PLAN_INVALID")
            != expected_sha256
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise ValueError
        validate_plan(plan, fixture_dir)
        expected = build_plan(
            intent_plan_file=intent_plan_file,
            intent_plan_sha256=intent_plan_sha256,
            intent_results_file=intent_results_file,
            intent_results_sha256=intent_results_sha256,
            fixture_dir=fixture_dir,
        )
        if plan != expected:
            raise ValueError
    except (
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        M49IntentRunError,
        M49SemanticPlanError,
    ):
        raise M49SemanticRunError("M49_SEMANTIC_PLAN_INVALID") from None
    return plan


def _count_codes(results: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        values = item[field]
        if values is None:
            continue
        if isinstance(values, str):
            values = [values]
        for code in values:
            if code is not None:
                counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _transport_retry_count(calls: list[dict[str, Any]]) -> int:
    return sum(
        calls[index]["wire_sha256"] == calls[index - 1]["wire_sha256"]
        for index in range(1, len(calls))
    )


def _has_contract_retry(calls: list[dict[str, Any]]) -> bool:
    return len({call["wire_sha256"] for call in calls}) > 1


def validate_result(
    payload: Any,
    plan: dict[str, Any],
    expected_plan_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != RESULT_KEYS:
        raise M49SemanticRunError("M49_SEMANTIC_RESULT_FIELDS_INVALID")
    results = payload["results"]
    if (
        payload["schema_version"] != RESULT_SCHEMA_VERSION
        or payload["purpose"] != "M49_SEALED_SILVER_SEMANTIC_ONLY"
        or payload["dataset_ref"] != plan["dataset_ref"]
        or payload["source_class"] != "CLEANROOM_SYNTHETIC"
        or payload["fictional"] is not True
        or payload["derived_from_real"] is not False
        or payload["quality_tier"] != "CODEX_ASSISTED_SILVER"
        or payload["evaluation_role"] != "CALIBRATION_ONLY"
        or payload["gold_eligible"] is not False
        or payload["gate_eligible"] is not False
        or payload["patch_eligible"] is not False
        or payload["contains_oracle"] is not False
        or payload["contains_credentials"] is not False
        or not isinstance(payload["semantic_plan_file_sha256"], str)
        or len(payload["semantic_plan_file_sha256"]) != 64
        or (
            expected_plan_sha256 is not None
            and payload["semantic_plan_file_sha256"] != expected_plan_sha256
        )
        or payload["source_intent_plan_sha256"]
        != plan["source_intent_plan_sha256"]
        or payload["source_intent_results_sha256"]
        != plan["source_intent_results_sha256"]
        or payload["model"] != DEFAULT_MODEL
        or payload["prompt_version"]
        != BailianSemanticRecommendationV4Provider.prompt_version
        or not isinstance(results, list)
        or len(results) != plan["semantic_observation_count"]
        or any(
            not isinstance(item, dict) or set(item) != RESULT_ITEM_KEYS
            for item in results
        )
        or payload["next_gate"] != "LOCAL_SILVER_DIAGNOSTIC_REVIEW"
    ):
        raise M49SemanticRunError("M49_SEMANTIC_RESULT_POLICY_INVALID")

    planned_by_ref = {
        unit["observation_ref"]: unit for unit in plan["units"]
    }
    if [item["observation_ref"] for item in results] != list(planned_by_ref):
        raise M49SemanticRunError("M49_SEMANTIC_RESULT_ORDER_INVALID")
    for item in results:
        unit = planned_by_ref[item["observation_ref"]]
        allowed = {
            request["wire_sha256"] for request in unit["possible_requests"]
        }
        calls = item["calls"]
        if (
            len(calls) not in {1, 2, 3}
            or any(
                not isinstance(call, dict)
                or set(call) != {"attempt", "wire_sha256"}
                or call["attempt"] != index
                or call["wire_sha256"] not in allowed
                for index, call in enumerate(calls, 1)
            )
            or len({call["wire_sha256"] for call in calls}) > 2
            or item["round_index"] != unit["round_index"]
            or item["scenario_ref"] != unit["scenario_ref"]
            or item["source_intent_draft_hash"]
            != unit["source_intent_draft_hash"]
            or item["source_confirmation_hash"]
            != unit["source_confirmation_hash"]
            or item["source_candidate_set_hash"]
            != unit["source_candidate_set_hash"]
            or item["status"] not in {"DRAFT_READY", "RUN_FAILED"}
            or (item["status"] == "DRAFT_READY")
            != (item["draft"] is not None and item["failure_code"] is None)
            or (item["status"] == "RUN_FAILED")
            != (item["draft"] is None and isinstance(item["failure_code"], str))
            or item["retrieval_status"] not in {"MATCH", "MISMATCH"}
            or item["recommendation_status"]
            not in {"MATCH", "MISMATCH", "RUN_FAILED"}
            or item["end_to_end_status"] not in {"MATCH", "MISMATCH"}
            or not isinstance(item["validation_error_codes"], list)
            or any(not isinstance(code, str) for code in item["validation_error_codes"])
            or (
                item["status"] == "RUN_FAILED"
                and item["recommendation_status"] != "RUN_FAILED"
            )
            or (
                item["status"] == "DRAFT_READY"
                and item["recommendation_status"] == "RUN_FAILED"
            )
            or (
                item["recommendation_status"] == "MATCH"
                and item["end_to_end_status"] != "MATCH"
            )
        ):
            raise M49SemanticRunError("M49_SEMANTIC_RESULT_ITEM_INVALID")

    actual_request_count = sum(len(item["calls"]) for item in results)
    observation_match = {
        item["observation_ref"]: item["end_to_end_status"] == "MATCH"
        for item in results
    }
    clarification_match_count = payload["intent_full_match_count"] - len(results)
    stable_scenarios = 0
    scenario_refs = {
        unit["scenario_ref"]
        for unit in plan["units"]
    }
    # Proceed scenarios absent from one round cannot be stable. Clarification
    # stability is calculated during live scoring and checked by aggregate sum.
    semantic_stable = sum(
        all(observation_match.get(f"R{round_index:02d}:{scenario_ref}", False)
            for round_index in range(1, 4))
        for scenario_ref in scenario_refs
    )
    stable_scenarios = payload["stable_scenario_count"]
    expected = {
        "intent_observation_count": plan["intent_observation_count"],
        "intent_full_match_count": plan["intent_full_match_count"],
        "semantic_observation_count": len(results),
        "actual_request_count": actual_request_count,
        "single_wire_call_count": sum(len(item["calls"]) == 1 for item in results),
        "multi_wire_call_observation_count": sum(
            len(item["calls"]) > 1 for item in results
        ),
        "contract_retry_observation_count": sum(
            _has_contract_retry(item["calls"]) for item in results
        ),
        "transport_retry_call_count": sum(
            _transport_retry_count(item["calls"]) for item in results
        ),
        "draft_ready_count": sum(item["status"] == "DRAFT_READY" for item in results),
        "run_failed_count": sum(item["status"] == "RUN_FAILED" for item in results),
        "retrieval_match_count": sum(
            item["retrieval_status"] == "MATCH" for item in results
        ),
        "retrieval_mismatch_count": sum(
            item["retrieval_status"] == "MISMATCH" for item in results
        ),
        "recommendation_match_count": sum(
            item["recommendation_status"] == "MATCH" for item in results
        ),
        "recommendation_mismatch_count": sum(
            item["recommendation_status"] == "MISMATCH" for item in results
        ),
        "clarification_end_to_end_match_count": clarification_match_count,
        "end_to_end_match_count": sum(observation_match.values())
        + clarification_match_count,
    }
    expected["end_to_end_mismatch_count"] = (
        expected["intent_observation_count"] - expected["end_to_end_match_count"]
    )
    if (
        actual_request_count > plan["maximum_actual_request_count"]
        or payload["failure_code_counts"] != _count_codes(results, "failure_code")
        or payload["validation_error_code_counts"]
        != _count_codes(results, "validation_error_codes")
        or semantic_stable > stable_scenarios
        or stable_scenarios + payload["unstable_scenario_count"] != 24
        or any(
            not isinstance(payload[field], int)
            or isinstance(payload[field], bool)
            or payload[field] != value
            for field, value in expected.items()
        )
    ):
        raise M49SemanticRunError("M49_SEMANTIC_RESULT_ACCOUNTING_INVALID")
    return {"status": "PASS", **expected,
            "stable_scenario_count": stable_scenarios,
            "unstable_scenario_count": payload["unstable_scenario_count"],
            "failure_code_counts": payload["failure_code_counts"],
            "validation_error_code_counts": payload["validation_error_code_counts"],
            "next_gate": payload["next_gate"]}


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
        raise M49SemanticRunError("M49_SEMANTIC_ORACLE_SOURCE_INVALID") from None


def run_live(
    *,
    semantic_plan_file: Path,
    approved_semantic_plan_sha256: str,
    intent_plan_file: Path,
    intent_plan_sha256: str,
    intent_results_file: Path,
    intent_results_sha256: str,
    private_output: Path,
    fixture_dir: Path = FIXTURE_DIR,
    execution_approved: bool,
) -> dict[str, Any]:
    if execution_approved is not True:
        raise M49SemanticRunError("M49_SEMANTIC_EXECUTION_NOT_APPROVED")
    plan = read_approved_semantic_plan(
        semantic_plan_file,
        approved_semantic_plan_sha256,
        intent_plan_file=intent_plan_file,
        intent_plan_sha256=intent_plan_sha256,
        intent_results_file=intent_results_file,
        intent_results_sha256=intent_results_sha256,
        fixture_dir=fixture_dir,
    )
    validate_tls_trust()
    try:
        preflight_private_output(private_output)
        intent_plan = read_approved_plan(
            intent_plan_file, intent_plan_sha256, fixture_dir
        )
        intent_results = read_intent_results(
            intent_results_file,
            intent_results_sha256,
            intent_plan,
            intent_plan_sha256,
        )
        environment = BailianConfig.from_env()
        config = BailianConfig(
            api_key=environment.api_key,
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            timeout_seconds=90.0,
            max_attempts=2,
            max_transport_retries=1,
        )
        contexts = {
            context.scenario_ref: context
            for context in load_formal_intent_contexts(fixture_dir)
        }
        oracles = _read_oracles(fixture_dir)
        intent_by_ref = {
            item["observation_ref"]: item for item in intent_results["results"]
        }
    except (
        BailianProviderError,
        M49IntentRunError,
        M49SemanticPlanError,
        OSError,
        TypeError,
        ValueError,
    ):
        raise M49SemanticRunError("M49_SEMANTIC_PREFLIGHT_FAILED") from None

    results: list[dict[str, Any]] = []
    actual_request_count = 0
    end_to_end_by_observation: dict[str, bool] = {}
    for unit in plan["units"]:
        context = contexts[unit["scenario_ref"]]
        oracle = oracles[unit["scenario_ref"]]
        source_result = intent_by_ref[unit["observation_ref"]]
        draft = ChangeIntentDraft.from_dict(
            source_result["draft"], context.request, context.tree
        )
        if (
            draft.draft_hash != unit["source_intent_draft_hash"]
            or not intent_matches_oracle(draft, oracle)
            or oracle.expected_route != "PROCEED"
        ):
            raise M49SemanticRunError("M49_SEMANTIC_SOURCE_MISMATCH")
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
        if (
            confirmation.confirmation_hash != unit["source_confirmation_hash"]
            or candidate_set.candidate_set_hash
            != unit["source_candidate_set_hash"]
        ):
            raise M49SemanticRunError("M49_SEMANTIC_SOURCE_MISMATCH")
        retrieval_match = retrieval_matches_oracle(candidate_set, oracle.retrieval)
        allowed_hashes = {
            item["wire_sha256"] for item in unit["possible_requests"]
        }
        audit: list[dict[str, Any]] = []
        provider = PlannedSemanticProvider(config, allowed_hashes, audit)
        recommendation = None
        failure_code = None
        try:
            recommendation = provider.recommend(
                confirmation, candidate_set, context.tree
            )
        except BailianProviderError as exc:
            failure_code = exc.code
        actual_request_count += len(audit)
        if actual_request_count > plan["maximum_actual_request_count"]:
            raise M49SemanticRunError("M49_SEMANTIC_CALL_LIMIT_EXCEEDED")
        recommendation_match = (
            recommendation is not None
            and recommendation_matches_oracle(
                recommendation, candidate_set, oracle.recommendation
            )
        )
        end_to_end_match = retrieval_match and recommendation_match
        end_to_end_by_observation[unit["observation_ref"]] = end_to_end_match
        status = "DRAFT_READY" if recommendation is not None else "RUN_FAILED"
        result = {
            "observation_ref": unit["observation_ref"],
            "round_index": unit["round_index"],
            "scenario_ref": unit["scenario_ref"],
            "source_intent_draft_hash": draft.draft_hash,
            "source_confirmation_hash": confirmation.confirmation_hash,
            "source_candidate_set_hash": candidate_set.candidate_set_hash,
            "status": status,
            "failure_code": failure_code,
            "calls": audit,
            "validation_error_codes": list(provider.validation_error_codes),
            "retrieval_status": "MATCH" if retrieval_match else "MISMATCH",
            "recommendation_status": (
                "MATCH"
                if recommendation_match
                else "RUN_FAILED" if recommendation is None else "MISMATCH"
            ),
            "end_to_end_status": "MATCH" if end_to_end_match else "MISMATCH",
            "draft": None if recommendation is None else recommendation.to_dict(),
        }
        results.append(result)
    clarification_matches: dict[str, bool] = {}
    for source_result in intent_results["results"]:
        if source_result["observation_ref"] in end_to_end_by_observation:
            continue
        context = contexts[source_result["scenario_ref"]]
        oracle = oracles[source_result["scenario_ref"]]
        source_draft = ChangeIntentDraft.from_dict(
            source_result["draft"], context.request, context.tree
        )
        clarification_matches[source_result["observation_ref"]] = (
            oracle.expected_route == "CLARIFY"
            and intent_matches_oracle(source_draft, oracle)
        )
    all_matches = {**end_to_end_by_observation, **clarification_matches}
    stable_scenario_count = sum(
        all(all_matches.get(f"R{round_index:02d}:{scenario_ref}", False)
            for round_index in range(1, 4))
        for scenario_ref in contexts
    )
    payload: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "purpose": "M49_SEALED_SILVER_SEMANTIC_ONLY",
        "dataset_ref": plan["dataset_ref"],
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "contains_oracle": False,
        "contains_credentials": False,
        "semantic_plan_file_sha256": approved_semantic_plan_sha256,
        "source_intent_plan_sha256": intent_plan_sha256,
        "source_intent_results_sha256": intent_results_sha256,
        "model": DEFAULT_MODEL,
        "prompt_version": BailianSemanticRecommendationV4Provider.prompt_version,
        "intent_observation_count": plan["intent_observation_count"],
        "intent_full_match_count": plan["intent_full_match_count"],
        "semantic_observation_count": len(results),
        "actual_request_count": actual_request_count,
        "single_wire_call_count": sum(len(item["calls"]) == 1 for item in results),
        "multi_wire_call_observation_count": sum(
            len(item["calls"]) > 1 for item in results
        ),
        "contract_retry_observation_count": sum(
            _has_contract_retry(item["calls"]) for item in results
        ),
        "transport_retry_call_count": sum(
            _transport_retry_count(item["calls"]) for item in results
        ),
        "draft_ready_count": sum(item["status"] == "DRAFT_READY" for item in results),
        "run_failed_count": sum(item["status"] == "RUN_FAILED" for item in results),
        "failure_code_counts": _count_codes(results, "failure_code"),
        "validation_error_code_counts": _count_codes(
            results, "validation_error_codes"
        ),
        "retrieval_match_count": sum(
            item["retrieval_status"] == "MATCH" for item in results
        ),
        "retrieval_mismatch_count": sum(
            item["retrieval_status"] == "MISMATCH" for item in results
        ),
        "recommendation_match_count": sum(
            item["recommendation_status"] == "MATCH" for item in results
        ),
        "recommendation_mismatch_count": sum(
            item["recommendation_status"] == "MISMATCH" for item in results
        ),
        "clarification_end_to_end_match_count": sum(
            clarification_matches.values()
        ),
        "end_to_end_match_count": sum(all_matches.values()),
        "end_to_end_mismatch_count": len(all_matches) - sum(all_matches.values()),
        "stable_scenario_count": stable_scenario_count,
        "unstable_scenario_count": len(contexts) - stable_scenario_count,
        "results": results,
        "next_gate": "LOCAL_SILVER_DIAGNOSTIC_REVIEW",
    }
    aggregate = validate_result(payload, plan, approved_semantic_plan_sha256)
    if not write_private_json(private_output, payload):
        raise M49SemanticRunError("M49_SEMANTIC_PRIVATE_OUTPUT_FAILED")
    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-plan-file", type=Path, required=True)
    parser.add_argument("--approved-semantic-plan-sha256", required=True)
    parser.add_argument("--intent-plan-file", type=Path, required=True)
    parser.add_argument("--intent-plan-sha256", required=True)
    parser.add_argument("--intent-results-file", type=Path, required=True)
    parser.add_argument("--intent-results-sha256", required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--execute-approved", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        aggregate = run_live(
            semantic_plan_file=args.semantic_plan_file,
            approved_semantic_plan_sha256=args.approved_semantic_plan_sha256,
            intent_plan_file=args.intent_plan_file,
            intent_plan_sha256=args.intent_plan_sha256,
            intent_results_file=args.intent_results_file,
            intent_results_sha256=args.intent_results_sha256,
            private_output=args.private_output,
            fixture_dir=args.fixture_dir,
            execution_approved=args.execute_approved,
        )
    except M49SemanticRunError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(json.dumps(aggregate, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
