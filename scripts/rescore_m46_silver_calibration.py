#!/usr/bin/env python3
"""Offline A/B rescore of exposed M4.5 Silver observations.

The input may contain private model artifacts.  This command only writes a
0600 private policy/observation file and prints an aggregate allowlisted report.
It performs no model or network calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from treeguard.adapter import load_tree_export  # noqa: E402
from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianProviderError,
    BailianSemanticRecommendationProvider,
)
from treeguard.change_intent import (  # noqa: E402
    ChangeIntentDraft,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.private_io import write_private_json  # noqa: E402
from treeguard.retrieval import build_candidate_set  # noqa: E402
from treeguard.scenario_calibration_validation import (  # noqa: E402
    ScenarioCalibrationPolicy,
    build_calibration_comparison_report,
    score_calibration_observation,
)
from treeguard.scenario_capability_validation import (  # noqa: E402
    CapabilityOracle,
    CapabilityStageResult,
    ScenarioCapabilityRun,
)
from treeguard.semantic_recommendation import SemanticRecommendationDraft  # noqa: E402


RECORDED_AT = "2031-08-03T12:30:00Z"
REVIEWER_REF = "codex-m45-silver-runtime"
TARGET_HIT_FAMILIES = {
    "UNIQUE_REUSE",
    "MULTI_ACCEPTABLE",
    "TOP_K_BOUNDARY",
    "CROSS_BRANCH_CONFLICT",
}
BOUNDED_EVIDENCE_FAMILIES = {
    "HARD_NEGATIVE",
    "KIND_CONFLICT",
    "CARDINALITY_CONFLICT",
    "EXPLICIT_NULL_NEW",
}


class RescoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = strict_json_loads(path.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        raise RescoreError("M46_INPUT_INVALID") from exc
    if not isinstance(payload, dict):
        raise RescoreError("M46_INPUT_INVALID")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise RescoreError("M46_INPUT_INVALID") from exc
    return digest.hexdigest()


def run_from_dict(payload: Any) -> ScenarioCapabilityRun:
    if not isinstance(payload, dict):
        raise RescoreError("M46_RUN_INVALID")
    try:
        return ScenarioCapabilityRun(
            source_overlay_hash=payload["source_overlay_hash"],
            source_reviewed_hash=payload["source_reviewed_hash"],
            source_snapshot_hash=payload["source_snapshot_hash"],
            source_request_hash=payload["source_request_hash"],
            source_intent_draft_hash=payload["source_intent_draft_hash"],
            source_candidate_set_hash=payload["source_candidate_set_hash"],
            source_recommendation_draft_hash=payload[
                "source_recommendation_draft_hash"
            ],
            plan_unit_ref=payload["plan_unit_ref"],
            candidate_ref=payload["candidate_ref"],
            expected_route=payload["expected_route"],
            intent=CapabilityStageResult.from_dict(payload["intent"]),
            retrieval=CapabilityStageResult.from_dict(payload["retrieval"]),
            recommendation=CapabilityStageResult.from_dict(payload["recommendation"]),
            full_path_status=payload["full_path_status"],
            run_hash=payload["run_hash"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RescoreError("M46_RUN_INVALID") from exc


def mode_for_family(family: Any) -> str:
    if family in TARGET_HIT_FAMILIES:
        return "TARGET_HIT"
    if family in BOUNDED_EVIDENCE_FAMILIES:
        return "BOUNDED_EVIDENCE"
    raise RescoreError("M46_FAMILY_POLICY_MISSING")


def _safe_trace(trace: Any) -> dict[str, Any]:
    return {
        "stage": trace.stage,
        "attempt": trace.attempt,
        "model": trace.model,
        "prompt_version": trace.prompt_version,
        "validation_status": trace.validation_status,
        "validation_error_code": trace.validation_error_code,
        "thinking_status": trace.thinking_status,
        "usage": dict(trace.usage),
    }


def rescore(
    *,
    dataset_dir: Path,
    result_file: Path,
    expected_result_sha256: str,
    private_output: Path,
    complete_semantic_live: bool = False,
    preflight_file: Path | None = None,
    expected_preflight_sha256: str | None = None,
) -> dict[str, Any]:
    if sha256_file(result_file) != expected_result_sha256:
        raise RescoreError("M46_RESULT_DIGEST_MISMATCH")
    manifest = read_json(dataset_dir / "manifest.json")
    candidates = read_json(dataset_dir / "scenario-candidates.json")
    oracle_sidecar = read_json(dataset_dir / "oracle-sidecar.silver.json")
    result = read_json(result_file)
    if complete_semantic_live:
        if preflight_file is None or expected_preflight_sha256 is None:
            raise RescoreError("M46_LIVE_PREFLIGHT_REQUIRED")
        if sha256_file(preflight_file) != expected_preflight_sha256:
            raise RescoreError("M46_LIVE_PREFLIGHT_DIGEST_MISMATCH")
        preflight = read_json(preflight_file)
        preflight_report = preflight.get("comparison_report")
        if (
            preflight.get("schema_version")
            != "fire-m46-silver-calibration-rescore.v1"
            or preflight.get("source_result_sha256") != expected_result_sha256
            or preflight.get("supplemental_execution") is not False
            or preflight.get("supplement_count") != 0
            or not isinstance(preflight_report, dict)
            or preflight_report.get("policy_version")
            != "treeguard.m46-silver-calibration.v1"
            or preflight_report.get("newly_semantic_eligible_count") != 20
            or preflight_report.get("full_path_reassessment_status")
            != "INCOMPLETE_SEMANTIC_COVERAGE"
        ):
            raise RescoreError("M46_LIVE_PREFLIGHT_INVALID")
    if (
        manifest.get("source_class") != "CLEANROOM_SYNTHETIC"
        or manifest.get("fictional") is not True
        or manifest.get("derived_from_real") is not False
        or result.get("quality_tier") != "SILVER"
        or result.get("gate_eligible") is not False
        or result.get("gold_eligible") is not False
        or result.get("evaluation_role") != "CALIBRATION"
        or result.get("model") != DEFAULT_MODEL
        or result.get("dataset_ref") != manifest.get("dataset_ref")
        or oracle_sidecar.get("dataset_ref") != manifest.get("dataset_ref")
        or candidates.get("dataset_ref") != manifest.get("dataset_ref")
    ):
        raise RescoreError("M46_SOURCE_POLICY_INVALID")

    tree_result = load_tree_export(dataset_dir / manifest["tree_file"])
    if not tree_result.is_valid or tree_result.tree is None:
        raise RescoreError("M46_TREE_INVALID")
    tree = tree_result.tree
    if tree.snapshot_hash != oracle_sidecar.get("source_snapshot_hash"):
        raise RescoreError("M46_TREE_SOURCE_MISMATCH")

    candidate_by_ref = {
        item["candidate_ref"]: item for item in candidates.get("items", [])
    }
    oracle_by_ref = {
        item["candidate_ref"]: item for item in oracle_sidecar.get("items", [])
    }
    if set(candidate_by_ref) != set(oracle_by_ref) or len(candidate_by_ref) != 24:
        raise RescoreError("M46_SOURCE_ACCOUNTING_INVALID")
    details = result.get("details")
    if not isinstance(details, list) or len(details) != 72:
        raise RescoreError("M46_RESULT_ACCOUNTING_INVALID")

    policies: dict[str, ScenarioCalibrationPolicy] = {}
    observations = []
    supplements: list[dict[str, Any]] = []
    provider_config = None
    if complete_semantic_live:
        try:
            environment = BailianConfig.from_env()
            provider_config = BailianConfig(
                api_key=environment.api_key,
                base_url=DEFAULT_BASE_URL,
                model=DEFAULT_MODEL,
                timeout_seconds=90.0,
                max_attempts=2,
            )
        except BailianProviderError as exc:
            raise RescoreError("M46_PROVIDER_CONFIG_INVALID") from exc
    for detail in details:
        if not isinstance(detail, dict):
            raise RescoreError("M46_RESULT_ACCOUNTING_INVALID")
        candidate_ref = detail.get("candidate_ref")
        round_index = detail.get("round_index")
        if candidate_ref not in candidate_by_ref or round_index not in (1, 2, 3):
            raise RescoreError("M46_RESULT_ACCOUNTING_INVALID")
        candidate = candidate_by_ref[candidate_ref]
        if candidate.get("expected_route") != "PROCEED":
            continue
        oracle_item = oracle_by_ref[candidate_ref]
        oracle = CapabilityOracle.from_dict(oracle_item["oracle"])
        run = run_from_dict(detail.get("run"))
        if (
            run.source_overlay_hash != oracle_item.get("oracle_digest")
            or run.source_snapshot_hash != tree.snapshot_hash
            or run.expected_route != "PROCEED"
        ):
            raise RescoreError("M46_RUN_SOURCE_MISMATCH")

        mode = mode_for_family(candidate.get("coverage_family"))
        policy = ScenarioCalibrationPolicy.create(
            source_overlay_hash=run.source_overlay_hash,
            oracle=oracle,
            retrieval_mode=mode,
        )
        existing = policies.setdefault(candidate_ref, policy)
        if existing != policy:
            raise RescoreError("M46_POLICY_DRIFT")

        request = IntentRequest.from_dict(candidate["request"], tree)
        intent_payload = detail.get("intent_draft")
        intent_draft = (
            None
            if intent_payload is None
            else ChangeIntentDraft.from_dict(intent_payload, request, tree)
        )
        candidate_set = None
        confirmation = None
        if run.intent.status == "MATCH":
            if intent_draft is None or intent_draft.draft_hash != run.source_intent_draft_hash:
                raise RescoreError("M46_INTENT_SOURCE_MISMATCH")
            confirmation = apply_intent_review(
                request,
                intent_draft,
                IntentReviewAction(
                    expected_draft_hash=intent_draft.draft_hash,
                    decision="CONFIRM_FOR_RETRIEVAL",
                    reviewer_ref=REVIEWER_REF,
                    recorded_at=RECORDED_AT,
                    confirmed_intent=intent_draft.intent,
                ),
                tree,
            )
            candidate_set = build_candidate_set(confirmation, tree)
            if candidate_set.candidate_set_hash != run.source_candidate_set_hash:
                raise RescoreError("M46_RETRIEVAL_SOURCE_MISMATCH")
        elif intent_draft is not None and intent_draft.draft_hash != run.source_intent_draft_hash:
            raise RescoreError("M46_INTENT_SOURCE_MISMATCH")

        recommendation_payload = detail.get("recommendation_draft")
        if recommendation_payload is None:
            recommendation_draft = None
        else:
            if confirmation is None or candidate_set is None:
                raise RescoreError("M46_SEMANTIC_SOURCE_MISMATCH")
            recommendation_draft = SemanticRecommendationDraft.from_dict(
                recommendation_payload,
                confirmation,
                candidate_set,
                tree,
            )
            if recommendation_draft.draft_hash != run.source_recommendation_draft_hash:
                raise RescoreError("M46_SEMANTIC_SOURCE_MISMATCH")

        observation_ref = f"R{round_index:03d}:{candidate_ref}"
        observation = score_calibration_observation(
            run,
            oracle,
            policy,
            observation_ref=observation_ref,
            candidate_set=candidate_set,
            recommendation_draft=recommendation_draft,
        )
        if observation.newly_semantic_eligible and complete_semantic_live:
            if confirmation is None or candidate_set is None or provider_config is None:
                raise RescoreError("M46_SEMANTIC_SOURCE_MISMATCH")
            traces: list[dict[str, Any]] = []
            provider = BailianSemanticRecommendationProvider(
                provider_config,
                trace_sink=lambda trace: traces.append(_safe_trace(trace)),
            )
            supplemental_draft = None
            failure_code = None
            try:
                supplemental_draft = provider.recommend(
                    confirmation,
                    candidate_set,
                    tree,
                )
            except BailianProviderError as exc:
                failure_code = exc.code
            except Exception:
                failure_code = "SEMANTIC_PROVIDER_UNEXPECTED_FAILURE"
            observation = score_calibration_observation(
                run,
                oracle,
                policy,
                observation_ref=observation_ref,
                candidate_set=candidate_set,
                recommendation_draft=supplemental_draft,
                semantic_observation_source="SUPPLEMENTAL_CALIBRATION",
                semantic_provider_failed=supplemental_draft is None,
            )
            supplements.append(
                {
                    "observation_ref": observation_ref,
                    "failure_code": failure_code,
                    "traces": traces,
                    "recommendation_draft": (
                        None
                        if supplemental_draft is None
                        else supplemental_draft.to_dict()
                    ),
                }
            )
            print(
                json.dumps(
                    {
                        "observation_ref": observation_ref,
                        "semantic_status": observation.semantic_status,
                        "source": "SUPPLEMENTAL_CALIBRATION",
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        observations.append(observation)

    if len(observations) != 54 or len(policies) != 18:
        raise RescoreError("M46_RESULT_ACCOUNTING_INVALID")
    report = build_calibration_comparison_report(tuple(observations))
    private_payload = {
        "schema_version": "fire-m46-silver-calibration-rescore.v1",
        "dataset_ref": manifest["dataset_ref"],
        "quality_tier": "SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gate_eligible": False,
        "gold_eligible": False,
        "source_result_sha256": expected_result_sha256,
        "model": DEFAULT_MODEL,
        "semantic_prompt_version": BailianSemanticRecommendationProvider.prompt_version,
        "supplemental_execution": complete_semantic_live,
        "supplement_count": len(supplements),
        "policies": [policies[key].to_dict() for key in sorted(policies)],
        "observations": [item.to_dict() for item in observations],
        "supplements": supplements,
        "comparison_report": report.to_dict(),
    }
    if not write_private_json(private_output, private_payload):
        raise RescoreError("M46_PRIVATE_OUTPUT_FAILED")
    return {"status": "PASS", "comparison_report": report.to_dict()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--expected-result-sha256", required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--complete-semantic-live", action="store_true")
    parser.add_argument("--preflight-file", type=Path)
    parser.add_argument("--expected-preflight-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = rescore(
            dataset_dir=args.dataset_dir,
            result_file=args.result_file,
            expected_result_sha256=args.expected_result_sha256,
            private_output=args.private_output,
            complete_semantic_live=args.complete_semantic_live,
            preflight_file=args.preflight_file,
            expected_preflight_sha256=args.expected_preflight_sha256,
        )
    except RescoreError as exc:
        print(json.dumps({"status": "FAIL", "code": exc.code}, sort_keys=True))
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
