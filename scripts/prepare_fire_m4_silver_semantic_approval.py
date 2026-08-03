#!/usr/bin/env python3
"""Replay Silver Intent results and prepare exact Semantic wire bodies."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import stat
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

INTENT_APPROVAL_PREP_PATH = (
    PROJECT_ROOT / "scripts/prepare_fire_m4_silver_intent_approval.py"
)
DEFAULT_SILVER_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-silver-v1"
)
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


def _load_intent_approval_prep():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_intent_for_semantic_approval",
        INTENT_APPROVAL_PREP_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Intent approval preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


INTENT_APPROVAL_PREP = _load_intent_approval_prep()

from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianSemanticRecommendationProvider,
)
from treeguard.change_intent import (  # noqa: E402
    REQUEST_SCHEMA_VERSION,
    ChangeIntentDraft,
    IntentRequest,
)
from treeguard.scenario_capability_validation import (  # noqa: E402
    ScenarioCapabilitySilverAuthorization,
    run_silver_capability_scenario,
)
from treeguard.semantic_recommendation import (  # noqa: E402
    build_semantic_candidate_projection,
)


class M4SilverSemanticApprovalError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReplayIntentProvider:
    def __init__(self, draft: ChangeIntentDraft | None) -> None:
        self._draft = draft

    def draft(self, request: IntentRequest, tree: Any) -> ChangeIntentDraft:
        if self._draft is None:
            raise RuntimeError("frozen Intent phase failed")
        return self._draft


class CaptureSemanticProvider:
    def __init__(self) -> None:
        self.call: tuple[Any, Any, Any] | None = None

    def recommend(self, confirmation: Any, candidate_set: Any, tree: Any) -> Any:
        self.call = (confirmation, candidate_set, tree)
        raise RuntimeError("Semantic request intentionally stopped before egress")


def wire_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def read_intent_results(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if (
            sha256(raw).hexdigest() != expected_sha256
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise ValueError
        payload = json.loads(raw.decode("utf-8"))
        if (
            payload["schema_version"]
            != "treeguard-m4-silver-bailian-intent-results.v1"
            or payload["quality_tier"] != "SILVER"
            or payload["evaluation_role"] != "CALIBRATION"
            or payload["gold_eligible"] is not False
            or payload["gate_eligible"] is not False
            or payload["scenario_count"] != 8
            or payload["actual_request_count"] > 16
            or len(payload["results"]) != 8
        ):
            raise ValueError
        return payload
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        raise M4SilverSemanticApprovalError(
            "SILVER_INTENT_RESULTS_INVALID"
        ) from None


def build_approval(
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: str | Path = DEFAULT_SILVER_DIR,
) -> dict[str, Any]:
    intent_results = read_intent_results(
        intent_results_path,
        intent_results_sha256,
    )
    silver_path = Path(silver_dir)
    try:
        INTENT_APPROVAL_PREP.SILVER_FREEZE.validate_staging(silver_path)
        authorization_raw = (
            silver_path / "silver-authorizations.json"
        ).read_bytes()
        authorization_batch = json.loads(authorization_raw.decode("utf-8"))
        authorization_items = {
            item["plan_unit_ref"]: item
            for item in authorization_batch["items"]
        }
        contexts = {
            context.reviewed.plan_unit_ref: context
            for context in INTENT_APPROVAL_PREP.SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
        }
        results = {
            item["plan_unit_ref"]: item for item in intent_results["results"]
        }
        provider = BailianSemanticRecommendationProvider(
            BailianConfig(
                api_key="NOT_USED_FOR_LOCAL_APPROVAL_PREPARATION",
                base_url=DEFAULT_BASE_URL,
                model=DEFAULT_MODEL,
                max_attempts=2,
            )
        )
        possible_requests = []
        replay = []
        for plan_unit_ref in sorted(contexts):
            context = contexts[plan_unit_ref]
            result = results[plan_unit_ref]
            authorization = ScenarioCapabilitySilverAuthorization.from_dict(
                authorization_items[plan_unit_ref]["authorization"],
                context.reviewed,
                context.plan,
                context.tree,
            )
            if result["authorization_hash"] != authorization.authorization_hash:
                raise ValueError
            request = IntentRequest.from_dict(
                {
                    "schema_version": REQUEST_SCHEMA_VERSION,
                    "requirement_text": context.reviewed.request.requirement_text,
                    "proposed_parent_node_id": (
                        context.reviewed.request.proposed_parent_node_id
                    ),
                    "node_kind_hint": context.reviewed.request.node_kind_hint,
                    "value_type_hint": context.reviewed.request.value_type_hint,
                    "cardinality_hint": context.reviewed.request.cardinality_hint,
                },
                context.tree,
            )
            if result["request_hash"] != request.request_hash:
                raise ValueError
            draft = (
                ChangeIntentDraft.from_dict(result["draft"], request, context.tree)
                if result["status"] == "DRAFT_READY"
                else None
            )
            capture = CaptureSemanticProvider()
            run = run_silver_capability_scenario(
                authorization,
                context.reviewed,
                context.action,
                context.batch,
                context.batch_candidate,
                context.projection,
                context.plan,
                context.profile,
                context.tree,
                ReplayIntentProvider(draft),
                capture,
            )
            semantic_eligible = capture.call is not None
            replay.append(
                {
                    "intent_status": run.intent.status,
                    "plan_unit_ref": plan_unit_ref,
                    "recommendation_status": run.recommendation.status,
                    "retrieval_status": run.retrieval.status,
                    "semantic_eligible": semantic_eligible,
                }
            )
            if not semantic_eligible:
                continue
            confirmation, candidate_set, tree = capture.call
            projection = build_semantic_candidate_projection(
                confirmation,
                candidate_set,
                tree,
            )
            variants = ((1, None),) + tuple(
                (2, code) for code in SEMANTIC_RETRY_CODES
            )
            for attempt, retry_code in variants:
                body = provider._semantic_request_body(
                    projection,
                    retry_code=retry_code,
                )
                encoded = wire_bytes(body)
                possible_requests.append(
                    {
                        "attempt": attempt,
                        "plan_unit_ref": plan_unit_ref,
                        "retry_code": retry_code,
                        "scenario_ref": context.scenario_ref,
                        "stage": "SEMANTIC_RECOMMENDATION",
                        "wire_body_text": encoded.decode("utf-8"),
                        "wire_sha256": sha256(encoded).hexdigest(),
                    }
                )
    except M4SilverSemanticApprovalError:
        raise
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverSemanticApprovalError(
            "SILVER_SEMANTIC_APPROVAL_SOURCE_INVALID"
        ) from None
    semantic_scenario_count = sum(item["semantic_eligible"] for item in replay)
    if (
        len(replay) != 8
        or len(possible_requests)
        != semantic_scenario_count * (1 + len(SEMANTIC_RETRY_CODES))
        or len({item["wire_sha256"] for item in possible_requests})
        != len(possible_requests)
    ):
        raise M4SilverSemanticApprovalError(
            "SILVER_SEMANTIC_APPROVAL_ACCOUNTING_INVALID"
        )
    forbidden = (
        '"acceptable_node_ids"',
        '"authorization_hash"',
        '"capability_oracle"',
        '"oracle"',
        '"target_node_id"',
    )
    if any(
        marker in item["wire_body_text"]
        for marker in forbidden
        for item in possible_requests
    ):
        raise M4SilverSemanticApprovalError(
            "SILVER_SEMANTIC_APPROVAL_ORACLE_LEAK"
        )
    return {
        "schema_version": "treeguard-m4-silver-bailian-semantic-approval.v2",
        "purpose": "M4_FIRE_SILVER_CALIBRATION_SEMANTIC_PHASE_ONLY",
        "dataset_ref": intent_results["dataset_ref"],
        "endpoint": DEFAULT_BASE_URL.rstrip("/") + "/chat/completions",
        "model": DEFAULT_MODEL,
        "prompt_version": provider.prompt_version,
        "external_data_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "quality_tier": "SILVER",
        "evaluation_role": "CALIBRATION",
        "gate_eligible": False,
        "gold_eligible": False,
        "contains_oracle": False,
        "contains_credentials": False,
        "intent_results_sha256": intent_results_sha256,
        "silver_authorizations_sha256": sha256(authorization_raw).hexdigest(),
        "intent_replay": replay,
        "semantic_scenario_count": semantic_scenario_count,
        "initial_request_count": semantic_scenario_count,
        "maximum_actual_request_count": semantic_scenario_count * 2,
        "possible_request_body_count": len(possible_requests),
        "retry_policy": "AT_MOST_ONE_COMPLETE_RETRY_AFTER_LOCAL_CONTRACT_FAILURE",
        "possible_requests": possible_requests,
    }


def write_approval(
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: str | Path = DEFAULT_SILVER_DIR,
    output_dir: str | Path = "/private/tmp",
) -> tuple[Path, str, dict[str, Any]]:
    approval = build_approval(
        intent_results_path,
        intent_results_sha256,
        silver_dir,
    )
    handle, output_name = tempfile.mkstemp(
        prefix="treeguard-m4-silver-semantic-approval-",
        suffix=".json",
        dir=output_dir,
        text=False,
    )
    output_path = Path(output_name)
    try:
        content = (
            json.dumps(approval, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        with os.fdopen(handle, "wb") as output:
            output.write(content)
        os.chmod(output_path, 0o600)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return output_path, sha256(content).hexdigest(), approval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent-results", type=Path, required=True)
    parser.add_argument("--intent-results-sha256", required=True)
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("/private/tmp"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path, digest, approval = write_approval(
            args.intent_results,
            args.intent_results_sha256,
            args.silver_dir,
            args.output_dir,
        )
    except M4SilverSemanticApprovalError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    stage_counts: dict[str, int] = {}
    for item in approval["intent_replay"]:
        key = (
            f'{item["intent_status"]}/'
            f'{item["retrieval_status"]}/'
            f'{item["recommendation_status"]}'
        )
        stage_counts[key] = stage_counts.get(key, 0) + 1
    print(
        json.dumps(
            {
                "approval_file": str(output_path),
                "approval_file_sha256": digest,
                "contains_credentials": False,
                "contains_oracle": False,
                "maximum_actual_request_count": approval[
                    "maximum_actual_request_count"
                ],
                "mode": "0o600",
                "possible_request_body_count": approval[
                    "possible_request_body_count"
                ],
                "semantic_scenario_count": approval["semantic_scenario_count"],
                "stage_counts": stage_counts,
                "status": "READY_FOR_EXPLICIT_EGRESS_APPROVAL",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
