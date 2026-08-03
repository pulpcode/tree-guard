#!/usr/bin/env python3
"""Prepare exact Semantic bodies for the M4 Silver downstream isolation run."""

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

SEMANTIC_PREP_PATH = (
    PROJECT_ROOT / "scripts/prepare_fire_m4_silver_semantic_approval.py"
)
DEFAULT_SILVER_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-silver-v1"
)
REFERENCE_REFS = frozenset({"U001", "U002", "U004", "U008", "U009"})
REFERENCE_TOP_LEVEL_KEYS = frozenset(
    {
        "assessment_authority",
        "dataset_ref",
        "end_to_end_eligible",
        "gate_eligible",
        "gold_eligible",
        "intended_use",
        "items",
        "quality_tier",
        "recorded_at",
        "schema_version",
        "source_intent_results_sha256",
        "status",
    }
)
REFERENCE_ITEM_KEYS = frozenset(
    {
        "assessment_codes",
        "authorization_hash",
        "intent",
        "plan_unit_ref",
        "request_hash",
    }
)


def _load_semantic_prep():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_semantic_for_downstream_isolation",
        SEMANTIC_PREP_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Semantic approval preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SEMANTIC_PREP = _load_semantic_prep()

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


class M4SilverDownstreamIsolationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _read_reference_intents(
    path: Path,
    expected_sha256: str,
    source_intent_results_sha256: str,
) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        if (
            sha256(raw).hexdigest() != expected_sha256
            or stat.S_IMODE(path.stat().st_mode) != 0o600
            or not isinstance(payload, dict)
            or set(payload) != REFERENCE_TOP_LEVEL_KEYS
            or payload["schema_version"]
            != "treeguard-m4-silver-reference-intents.v1"
            or payload["assessment_authority"] != "CODEX_ASSISTED"
            or payload["dataset_ref"]
            != "fictional-fire-m4-calibration-silver-v1"
            or payload["quality_tier"] != "SILVER"
            or payload["intended_use"] != "DOWNSTREAM_ISOLATION_ONLY"
            or payload["status"] != "SILVER_REFERENCE_ACCEPTED"
            or payload["end_to_end_eligible"] is not False
            or payload["gate_eligible"] is not False
            or payload["gold_eligible"] is not False
            or payload["source_intent_results_sha256"]
            != source_intent_results_sha256
            or not isinstance(payload["recorded_at"], str)
            or not isinstance(payload["items"], list)
            or len(payload["items"]) != len(REFERENCE_REFS)
        ):
            raise ValueError
        refs = set()
        for item in payload["items"]:
            if (
                not isinstance(item, dict)
                or set(item) != REFERENCE_ITEM_KEYS
                or item["plan_unit_ref"] not in REFERENCE_REFS
                or not isinstance(item["assessment_codes"], list)
                or item["assessment_codes"] != sorted(set(item["assessment_codes"]))
                or any(
                    not isinstance(code, str) or not code
                    for code in item["assessment_codes"]
                )
                or not isinstance(item["intent"], dict)
            ):
                raise ValueError
            refs.add(item["plan_unit_ref"])
        if refs != REFERENCE_REFS:
            raise ValueError
        return payload
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        raise M4SilverDownstreamIsolationError(
            "SILVER_REFERENCE_INTENTS_INVALID"
        ) from None


def build_intent_request(context: Any) -> IntentRequest:
    return IntentRequest.from_dict(
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


def build_approval(
    reference_intents_path: Path,
    reference_intents_sha256: str,
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: str | Path = DEFAULT_SILVER_DIR,
) -> dict[str, Any]:
    source_results = SEMANTIC_PREP.read_intent_results(
        intent_results_path,
        intent_results_sha256,
    )
    reference = _read_reference_intents(
        reference_intents_path,
        reference_intents_sha256,
        intent_results_sha256,
    )
    silver_path = Path(silver_dir)
    try:
        SEMANTIC_PREP.INTENT_APPROVAL_PREP.SILVER_FREEZE.validate_staging(
            silver_path
        )
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
            for context in SEMANTIC_PREP.INTENT_APPROVAL_PREP.SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
        }
        source_items = {
            item["plan_unit_ref"]: item for item in source_results["results"]
        }
        reference_items = {
            item["plan_unit_ref"]: item for item in reference["items"]
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
        for plan_unit_ref in sorted(REFERENCE_REFS):
            context = contexts[plan_unit_ref]
            source_item = source_items[plan_unit_ref]
            reference_item = reference_items[plan_unit_ref]
            authorization = ScenarioCapabilitySilverAuthorization.from_dict(
                authorization_items[plan_unit_ref]["authorization"],
                context.reviewed,
                context.plan,
                context.tree,
            )
            request = build_intent_request(context)
            if (
                source_item["request_hash"] != request.request_hash
                or source_item["authorization_hash"]
                != authorization.authorization_hash
                or reference_item["request_hash"] != request.request_hash
                or reference_item["authorization_hash"]
                != authorization.authorization_hash
                or authorization.oracle.expected_route != "PROCEED"
            ):
                raise ValueError
            draft = ChangeIntentDraft.from_model_dict(
                reference_item["intent"],
                request,
                context.tree,
                model_provider="CODEX_ASSISTED_REFERENCE",
                model_capability="SILVER_REFERENCE_INTENT",
                model_name="codex-assisted-reference",
                prompt_version="treeguard.m4.silver-reference-intent.v1",
            )
            if draft.review_status != "READY_FOR_HUMAN_REVIEW":
                raise ValueError
            capture = SEMANTIC_PREP.CaptureSemanticProvider()
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
                SEMANTIC_PREP.ReplayIntentProvider(draft),
                capture,
            )
            if run.intent.status != "MATCH":
                raise ValueError
            semantic_eligible = capture.call is not None
            replay.append(
                {
                    "intent_status": run.intent.status,
                    "plan_unit_ref": plan_unit_ref,
                    "recommendation_status": run.recommendation.status,
                    "retrieval_status": run.retrieval.status,
                    "semantic_eligible": semantic_eligible,
                    "source_intent_status": source_item["status"],
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
                (2, code) for code in SEMANTIC_PREP.SEMANTIC_RETRY_CODES
            )
            for attempt, retry_code in variants:
                body = provider._semantic_request_body(
                    projection,
                    retry_code=retry_code,
                )
                encoded = SEMANTIC_PREP.wire_bytes(body)
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
    except M4SilverDownstreamIsolationError:
        raise
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverDownstreamIsolationError(
            "SILVER_DOWNSTREAM_ISOLATION_SOURCE_INVALID"
        ) from None

    semantic_scenario_count = sum(item["semantic_eligible"] for item in replay)
    if (
        len(replay) != len(REFERENCE_REFS)
        or len(possible_requests)
        != semantic_scenario_count
        * (1 + len(SEMANTIC_PREP.SEMANTIC_RETRY_CODES))
        or len({item["wire_sha256"] for item in possible_requests})
        != len(possible_requests)
    ):
        raise M4SilverDownstreamIsolationError(
            "SILVER_DOWNSTREAM_ISOLATION_ACCOUNTING_INVALID"
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
        raise M4SilverDownstreamIsolationError(
            "SILVER_DOWNSTREAM_ISOLATION_ORACLE_LEAK"
        )
    return {
        "schema_version": (
            "treeguard-m4-silver-downstream-isolation-semantic-approval.v2"
        ),
        "purpose": "M4_FIRE_SILVER_DOWNSTREAM_ISOLATION_ONLY",
        "dataset_ref": reference["dataset_ref"],
        "endpoint": DEFAULT_BASE_URL.rstrip("/") + "/chat/completions",
        "model": DEFAULT_MODEL,
        "prompt_version": provider.prompt_version,
        "external_data_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "quality_tier": "SILVER",
        "evaluation_role": "DOWNSTREAM_ISOLATION",
        "intent_provider_called": False,
        "end_to_end_eligible": False,
        "gate_eligible": False,
        "gold_eligible": False,
        "contains_oracle": False,
        "contains_credentials": False,
        "reference_intents_sha256": reference_intents_sha256,
        "source_intent_results_sha256": intent_results_sha256,
        "silver_authorizations_sha256": sha256(authorization_raw).hexdigest(),
        "scenario_count": len(REFERENCE_REFS),
        "intent_replay": replay,
        "semantic_scenario_count": semantic_scenario_count,
        "initial_request_count": semantic_scenario_count,
        "maximum_actual_request_count": semantic_scenario_count * 2,
        "possible_request_body_count": len(possible_requests),
        "retry_policy": "AT_MOST_ONE_COMPLETE_RETRY_AFTER_LOCAL_CONTRACT_FAILURE",
        "possible_requests": possible_requests,
    }


def write_approval(
    reference_intents_path: Path,
    reference_intents_sha256: str,
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: str | Path = DEFAULT_SILVER_DIR,
    output_dir: str | Path = "/private/tmp",
) -> tuple[Path, str, dict[str, Any]]:
    approval = build_approval(
        reference_intents_path,
        reference_intents_sha256,
        intent_results_path,
        intent_results_sha256,
        silver_dir,
    )
    handle, output_name = tempfile.mkstemp(
        prefix="treeguard-m4-silver-downstream-isolation-approval-",
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
    parser.add_argument("--reference-intents", type=Path, required=True)
    parser.add_argument("--reference-intents-sha256", required=True)
    parser.add_argument("--intent-results", type=Path, required=True)
    parser.add_argument("--intent-results-sha256", required=True)
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("/private/tmp"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path, digest, approval = write_approval(
            args.reference_intents,
            args.reference_intents_sha256,
            args.intent_results,
            args.intent_results_sha256,
            args.silver_dir,
            args.output_dir,
        )
    except M4SilverDownstreamIsolationError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    stage_counts: dict[str, int] = {}
    for item in approval["intent_replay"]:
        key = f'{item["intent_status"]}/{item["retrieval_status"]}'
        stage_counts[key] = stage_counts.get(key, 0) + 1
    print(
        json.dumps(
            {
                "approval_file": str(output_path),
                "approval_file_sha256": digest,
                "contains_credentials": False,
                "contains_oracle": False,
                "end_to_end_eligible": False,
                "intent_provider_called": False,
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
