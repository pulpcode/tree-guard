#!/usr/bin/env python3
"""Prepare and run the non-gating M4.7 Semantic v3/v4 calibration.

Only the 44 M4.6 observations whose calibrated retrieval status is MATCH are
eligible.  ``prepare`` writes every possible v4 wire body to one immutable
0600 plan.  ``live`` rebuilds that plan byte-for-byte before allowing egress
and writes model artifacts only to a separate immutable 0600 result file.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

M46_SCRIPT = REPOSITORY_ROOT / "scripts/rescore_m46_silver_calibration.py"


def _load_m46_module():
    spec = importlib.util.spec_from_file_location("treeguard_m46_for_m47", M46_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4.6 reconstruction helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


M46 = _load_m46_module()

from treeguard.adapter import load_tree_export  # noqa: E402
from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianProviderError,
    BailianSemanticRecommendationV4Provider,
)
from treeguard.change_intent import (  # noqa: E402
    ChangeIntentDraft,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.private_io import (  # noqa: E402
    preflight_private_output,
    read_private_json,
    write_private_json,
)
from treeguard.retrieval import build_candidate_set  # noqa: E402
from treeguard.scenario_calibration_validation import (  # noqa: E402
    SAFE_NON_TARGETING_ACTIONS,
    ScenarioCalibrationPolicy,
)
from treeguard.scenario_capability_validation import (  # noqa: E402
    CapabilityOracle,
    recommendation_outcome_from_draft,
)
from treeguard.semantic_recommendation import (  # noqa: E402
    SemanticRecommendationDraft,
    build_semantic_candidate_projection,
)


PLAN_SCHEMA_VERSION = "fire-m47-semantic-policy-plan.v1"
RESULT_SCHEMA_VERSION = "fire-m47-semantic-policy-result.v1"
ELIGIBLE_OBSERVATION_COUNT = 44
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
SEMANTIC_STATUSES = (
    "PREFERRED_MATCH",
    "SAFE_ALTERNATIVE",
    "UNSAFE_MISMATCH",
    "RUN_FAILED",
)


class M47Error(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ExperimentContext:
    observation_ref: str
    baseline_status: str
    confirmation: Any
    candidate_set: Any
    tree: Any
    oracle: CapabilityOracle


def wire_bytes(body: dict[str, Any]) -> bytes:
    """Match the provider transport's default JSON serialization exactly."""

    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise M47Error("M47_INPUT_INVALID") from exc
    return digest.hexdigest()


def _read_private_dict(path: Path, expected_sha256: str) -> dict[str, Any]:
    if sha256_file(path) != expected_sha256:
        raise M47Error("M47_INPUT_DIGEST_MISMATCH")
    try:
        payload = read_private_json(path, max_bytes=32_000_000)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise M47Error("M47_INPUT_INVALID") from exc
    if not isinstance(payload, dict):
        raise M47Error("M47_INPUT_INVALID")
    return payload


def _safe_trace(trace: Any) -> dict[str, Any]:
    return {
        "attempt": trace.attempt,
        "model": trace.model,
        "prompt_version": trace.prompt_version,
        "stage": trace.stage,
        "thinking_status": trace.thinking_status,
        "usage": dict(trace.usage),
        "validation_error_code": trace.validation_error_code,
        "validation_status": trace.validation_status,
    }


def _reconstruct(
    *,
    dataset_dir: Path,
    original_result_file: Path,
    original_result_sha256: str,
    m46_result_file: Path,
    m46_result_sha256: str,
) -> tuple[dict[str, Any], dict[str, ExperimentContext]]:
    original = _read_private_dict(original_result_file, original_result_sha256)
    m46 = _read_private_dict(m46_result_file, m46_result_sha256)
    try:
        manifest = M46.read_json(dataset_dir / "manifest.json")
        candidates = M46.read_json(dataset_dir / "scenario-candidates.json")
        oracle_sidecar = M46.read_json(dataset_dir / "oracle-sidecar.silver.json")
        tree_result = load_tree_export(dataset_dir / manifest["tree_file"])
        if not tree_result.is_valid or tree_result.tree is None:
            raise ValueError
        tree = tree_result.tree
        if (
            manifest["source_class"] != "CLEANROOM_SYNTHETIC"
            or manifest["fictional"] is not True
            or manifest["derived_from_real"] is not False
            or original["quality_tier"] != "SILVER"
            or original["gate_eligible"] is not False
            or original["gold_eligible"] is not False
            or m46["quality_tier"] != "SILVER"
            or m46["evaluation_role"] != "CALIBRATION_ONLY"
            or m46["gate_eligible"] is not False
            or m46["gold_eligible"] is not False
            or m46["source_result_sha256"] != original_result_sha256
            or tree.snapshot_hash != oracle_sidecar["source_snapshot_hash"]
        ):
            raise ValueError
        candidate_by_ref = {
            item["candidate_ref"]: item for item in candidates["items"]
        }
        oracle_by_ref = {
            item["candidate_ref"]: item for item in oracle_sidecar["items"]
        }
        observations = {
            item["observation_ref"]: item for item in m46["observations"]
        }
        if (
            len(original["details"]) != 72
            or len(m46["observations"]) != 54
            or len(observations) != 54
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise M47Error("M47_SOURCE_POLICY_INVALID") from exc

    provider = BailianSemanticRecommendationV4Provider(
        BailianConfig(
            api_key="NOT_USED_FOR_LOCAL_PLAN",
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            max_attempts=2,
        )
    )
    contexts: dict[str, ExperimentContext] = {}
    units: list[dict[str, Any]] = []
    for detail in original["details"]:
        try:
            candidate_ref = detail["candidate_ref"]
            round_index = detail["round_index"]
            candidate = candidate_by_ref[candidate_ref]
            if candidate["expected_route"] != "PROCEED":
                continue
            observation_ref = f"R{round_index:03d}:{candidate_ref}"
            observation = observations[observation_ref]
            if observation["calibrated_retrieval_status"] != "MATCH":
                continue
            oracle_item = oracle_by_ref[candidate_ref]
            oracle = CapabilityOracle.from_dict(oracle_item["oracle"])
            run = M46.run_from_dict(detail["run"])
            if (
                run.intent.status != "MATCH"
                or run.source_overlay_hash != oracle_item["oracle_digest"]
                or run.source_snapshot_hash != tree.snapshot_hash
            ):
                raise ValueError
            request = IntentRequest.from_dict(candidate["request"], tree)
            intent_draft = ChangeIntentDraft.from_dict(
                detail["intent_draft"], request, tree
            )
            if intent_draft.draft_hash != run.source_intent_draft_hash:
                raise ValueError
            confirmation = apply_intent_review(
                request,
                intent_draft,
                IntentReviewAction(
                    expected_draft_hash=intent_draft.draft_hash,
                    decision="CONFIRM_FOR_RETRIEVAL",
                    reviewer_ref=M46.REVIEWER_REF,
                    recorded_at=M46.RECORDED_AT,
                    confirmed_intent=intent_draft.intent,
                ),
                tree,
            )
            candidate_set = build_candidate_set(confirmation, tree)
            if candidate_set.candidate_set_hash != run.source_candidate_set_hash:
                raise ValueError
            policy = ScenarioCalibrationPolicy.create(
                source_overlay_hash=run.source_overlay_hash,
                oracle=oracle,
                retrieval_mode=M46.mode_for_family(candidate["coverage_family"]),
            )
            if policy.policy_hash != observation["source_policy_hash"]:
                raise ValueError
            projection = build_semantic_candidate_projection(
                confirmation, candidate_set, tree
            )
            requests = []
            for attempt, retry_code in ((1, None),) + tuple(
                (2, code) for code in SEMANTIC_RETRY_CODES
            ):
                body = provider._semantic_request_body(
                    projection, retry_code=retry_code
                )
                encoded = wire_bytes(body)
                requests.append(
                    {
                        "attempt": attempt,
                        "retry_code": retry_code,
                        "wire_body_text": encoded.decode("utf-8"),
                        "wire_sha256": hashlib.sha256(encoded).hexdigest(),
                    }
                )
            contexts[observation_ref] = ExperimentContext(
                observation_ref=observation_ref,
                baseline_status=observation["semantic_status"],
                confirmation=confirmation,
                candidate_set=candidate_set,
                tree=tree,
                oracle=oracle,
            )
            units.append(
                {
                    "baseline_semantic_status": observation["semantic_status"],
                    "candidate_set_hash": candidate_set.candidate_set_hash,
                    "observation_ref": observation_ref,
                    "possible_requests": requests,
                    "source_policy_hash": policy.policy_hash,
                    "source_run_hash": run.run_hash,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise M47Error("M47_RECONSTRUCTION_INVALID") from exc

    units.sort(key=lambda item: item["observation_ref"])
    if len(units) != ELIGIBLE_OBSERVATION_COUNT or len(contexts) != len(units):
        raise M47Error("M47_ACCOUNTING_INVALID")
    if any(
        len(unit["possible_requests"]) != 1 + len(SEMANTIC_RETRY_CODES)
        or len({item["wire_sha256"] for item in unit["possible_requests"]})
        != 1 + len(SEMANTIC_RETRY_CODES)
        for unit in units
    ):
        raise M47Error("M47_REQUEST_PLAN_INVALID")
    forbidden_markers = (
        '"acceptable_node_ids"',
        '"capability_oracle"',
        '"oracle"',
        '"target_node_id"',
    )
    forbidden_oracle_ids = {
        node_id
        for item in oracle_by_ref.values()
        for node_id in (
            list(item["oracle"]["retrieval"]["acceptable_node_ids"])
            + [
                outcome["target_node_id"]
                for outcome in item["oracle"]["recommendation"][
                    "acceptable_outcomes"
                ]
                if outcome["target_node_id"] is not None
            ]
        )
    }
    if any(
        marker in request["wire_body_text"]
        for unit in units
        for request in unit["possible_requests"]
        for marker in forbidden_markers
    ) or any(
        json.dumps(node_id, ensure_ascii=False) in request["wire_body_text"]
        for unit in units
        for request in unit["possible_requests"]
        for node_id in forbidden_oracle_ids
    ):
        raise M47Error("M47_ORACLE_LEAK")

    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "purpose": "M47_SEMANTIC_V3_V4_POLICY_CALIBRATION_ONLY",
        "dataset_ref": manifest["dataset_ref"],
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "quality_tier": "SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gate_eligible": False,
        "gold_eligible": False,
        "contains_oracle": False,
        "contains_credentials": False,
        "endpoint": DEFAULT_BASE_URL.rstrip("/") + "/chat/completions",
        "model": DEFAULT_MODEL,
        "prompt_version": provider.prompt_version,
        "source_original_result_sha256": original_result_sha256,
        "source_m46_result_sha256": m46_result_sha256,
        "tree_fixture_sha256": sha256_file(dataset_dir / manifest["tree_file"]),
        "observation_count": len(units),
        "initial_request_count": len(units),
        "maximum_actual_request_count": len(units) * 2,
        "possible_request_body_count": len(units)
        * (1 + len(SEMANTIC_RETRY_CODES)),
        "retry_policy": "AT_MOST_ONE_COMPLETE_RETRY_AFTER_LOCAL_CONTRACT_FAILURE",
        "units": units,
    }
    return plan, contexts


def prepare_plan(**kwargs: Any) -> dict[str, Any]:
    plan, _ = _reconstruct(**kwargs)
    return plan


class ApprovedV4Provider(BailianSemanticRecommendationV4Provider):
    """Reject any request body not frozen for this observation."""

    def __init__(
        self,
        config: BailianConfig,
        allowed_hashes: set[str],
        audit: list[dict[str, str]],
        traces: list[dict[str, Any]],
    ) -> None:
        super().__init__(config, trace_sink=lambda trace: traces.append(_safe_trace(trace)))
        self.allowed_hashes = allowed_hashes
        self.audit = audit

    def _post_json(self, body: dict[str, Any]) -> Any:
        digest = hashlib.sha256(wire_bytes(body)).hexdigest()
        if digest not in self.allowed_hashes:
            raise M47Error("M47_BODY_NOT_PLANNED")
        if any(item["wire_sha256"] == digest for item in self.audit):
            raise M47Error("M47_BODY_ALREADY_SENT")
        self.audit.append({"wire_sha256": digest})
        return super()._post_json(body)


def semantic_status(
    draft: SemanticRecommendationDraft | None,
    candidate_set: Any,
    oracle: CapabilityOracle,
    *,
    provider_failed: bool,
) -> str:
    if draft is None:
        if not provider_failed:
            raise M47Error("M47_SEMANTIC_OUTPUT_MISSING")
        return "RUN_FAILED"
    outcome = recommendation_outcome_from_draft(draft, candidate_set)
    if outcome in oracle.recommendation.acceptable_outcomes:
        return "PREFERRED_MATCH"
    if (
        outcome.action in SAFE_NON_TARGETING_ACTIONS
        and outcome.target_node_id is None
        and outcome.relation is None
    ):
        return "SAFE_ALTERNATIVE"
    return "UNSAFE_MISMATCH"


def build_aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    if len(results) != ELIGIBLE_OBSERVATION_COUNT:
        raise M47Error("M47_RESULT_ACCOUNTING_INVALID")
    baseline = Counter(item["baseline_status"] for item in results)
    v4 = Counter(item["v4_status"] for item in results)
    transitions = Counter(
        f'{item["baseline_status"]}->{item["v4_status"]}' for item in results
    )
    contract_legal = sum(item["v4_status"] != "RUN_FAILED" for item in results)
    regressions_to_unsafe = sum(
        item["baseline_status"] in {"PREFERRED_MATCH", "SAFE_ALTERNATIVE"}
        and item["v4_status"] == "UNSAFE_MISMATCH"
        for item in results
    )
    attempt_counts = Counter(len(item.get("calls", ())) for item in results)
    promising = (
        contract_legal >= 43
        and regressions_to_unsafe == 0
        and v4["PREFERRED_MATCH"] >= 12
        and v4["UNSAFE_MISMATCH"] < 7
    )
    return {
        "observation_count": len(results),
        "baseline_counts": {key: baseline[key] for key in SEMANTIC_STATUSES},
        "v4_counts": {key: v4[key] for key in SEMANTIC_STATUSES},
        "transition_counts": dict(sorted(transitions.items())),
        "contract_legal_count": contract_legal,
        "first_pass_count": attempt_counts[1],
        "retry_observation_count": attempt_counts[2],
        "actual_request_count": sum(
            len(item.get("calls", ())) for item in results
        ),
        "baseline_preferred_or_safe_to_unsafe_count": regressions_to_unsafe,
        "decision": (
            "PROMISING_FOR_SEALED_VALIDATION"
            if promising
            else "NOT_PROMISING"
        ),
    }


def run_live(
    *,
    plan_file: Path,
    expected_plan_sha256: str,
    private_output: Path,
    **reconstruction_kwargs: Any,
) -> dict[str, Any]:
    plan_payload = _read_private_dict(plan_file, expected_plan_sha256)
    rebuilt_plan, contexts = _reconstruct(**reconstruction_kwargs)
    if plan_payload != rebuilt_plan:
        raise M47Error("M47_PLAN_REPLAY_MISMATCH")
    try:
        preflight_private_output(private_output)
        environment = BailianConfig.from_env()
        config = BailianConfig(
            api_key=environment.api_key,
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            timeout_seconds=90.0,
            max_attempts=2,
        )
    except (BailianProviderError, OSError, ValueError) as exc:
        raise M47Error("M47_LIVE_PREFLIGHT_FAILED") from exc

    results: list[dict[str, Any]] = []
    actual_request_count = 0
    for unit in plan_payload["units"]:
        observation_ref = unit["observation_ref"]
        context = contexts[observation_ref]
        allowed_hashes = {
            item["wire_sha256"] for item in unit["possible_requests"]
        }
        audit: list[dict[str, str]] = []
        traces: list[dict[str, Any]] = []
        provider = ApprovedV4Provider(config, allowed_hashes, audit, traces)
        draft = None
        failure_code = None
        try:
            draft = provider.recommend(
                context.confirmation,
                context.candidate_set,
                context.tree,
            )
        except BailianProviderError as exc:
            failure_code = exc.code
        except M47Error:
            raise
        except Exception:
            failure_code = "SEMANTIC_PROVIDER_UNEXPECTED_FAILURE"
        actual_request_count += len(audit)
        if actual_request_count > plan_payload["maximum_actual_request_count"]:
            raise M47Error("M47_CALL_LIMIT_EXCEEDED")
        v4_status = semantic_status(
            draft,
            context.candidate_set,
            context.oracle,
            provider_failed=draft is None,
        )
        results.append(
            {
                "observation_ref": observation_ref,
                "baseline_status": context.baseline_status,
                "v4_status": v4_status,
                "failure_code": failure_code,
                "calls": audit,
                "traces": traces,
                "recommendation_draft": None if draft is None else draft.to_dict(),
            }
        )
        print(
            json.dumps(
                {
                    "attempt_count": len(audit),
                    "baseline_status": context.baseline_status,
                    "observation_ref": observation_ref,
                    "v4_status": v4_status,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    aggregate = build_aggregate(results)
    output = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "quality_tier": "SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gate_eligible": False,
        "gold_eligible": False,
        "plan_sha256": expected_plan_sha256,
        "model": DEFAULT_MODEL,
        "prompt_version": BailianSemanticRecommendationV4Provider.prompt_version,
        "actual_request_count": actual_request_count,
        "aggregate": aggregate,
        "results": results,
    }
    if not write_private_json(private_output, output):
        raise M47Error("M47_PRIVATE_OUTPUT_FAILED")
    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "live"))
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--original-result-file", type=Path, required=True)
    parser.add_argument("--original-result-sha256", required=True)
    parser.add_argument("--m46-result-file", type=Path, required=True)
    parser.add_argument("--m46-result-sha256", required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--expected-plan-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reconstruction = {
        "dataset_dir": args.dataset_dir,
        "original_result_file": args.original_result_file,
        "original_result_sha256": args.original_result_sha256,
        "m46_result_file": args.m46_result_file,
        "m46_result_sha256": args.m46_result_sha256,
    }
    try:
        if args.mode == "prepare":
            preflight_private_output(args.private_output)
            plan = prepare_plan(**reconstruction)
            if not write_private_json(args.private_output, plan):
                raise M47Error("M47_PRIVATE_OUTPUT_FAILED")
            output = {
                "status": "PASS",
                "observation_count": plan["observation_count"],
                "possible_request_body_count": plan["possible_request_body_count"],
                "private_output_sha256": sha256_file(args.private_output),
            }
        else:
            if args.plan_file is None or args.expected_plan_sha256 is None:
                raise M47Error("M47_PLAN_REQUIRED")
            aggregate = run_live(
                plan_file=args.plan_file,
                expected_plan_sha256=args.expected_plan_sha256,
                private_output=args.private_output,
                **reconstruction,
            )
            output = {"status": "PASS", "aggregate": aggregate}
    except M47Error as exc:
        print(json.dumps({"status": "FAIL", "code": exc.code}, sort_keys=True))
        return 1
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
