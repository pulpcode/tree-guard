#!/usr/bin/env python3
"""Prepare exact Bailian Intent wire bodies for the M4 Silver experiment."""

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

SILVER_FREEZE_PATH = PROJECT_ROOT / "scripts/freeze_fire_m4_calibration_silver.py"
DEFAULT_SILVER_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-silver-v1"
)
RETRY_CODES = (
    "INTENT_MODEL_CONTENT_INVALID",
    "INTENT_MODEL_ASSUMPTIONS_INVALID",
    "INTENT_MODEL_CARDINALITY_INVALID",
    "INTENT_MODEL_CLARIFICATION_QUESTION_INVALID",
    "INTENT_MODEL_CONFIRMED_FACTS_INVALID",
    "INTENT_MODEL_EVIDENCE_GAPS_INVALID",
    "INTENT_MODEL_LIFECYCLE_INVALID",
    "INTENT_MODEL_NODE_KIND_INVALID",
    "INTENT_MODEL_OWNERSHIP_INVALID",
    "INTENT_MODEL_ROLE_INVALID",
    "INTENT_MODEL_SCENARIO_INVALID",
    "INTENT_MODEL_SUBJECT_INVALID",
    "INTENT_MODEL_VALUE_TYPE_INVALID",
    "INTENT_MODEL_FIELDS_INVALID",
    "INTENT_MODEL_INTERNAL_ID_FORBIDDEN",
    "INTENT_MODEL_RESPONSE_INVALID",
    "INTENT_MODEL_VERSION_INVALID",
)
SCENARIO_COUNT = 8
POSSIBLE_REQUEST_BODY_COUNT = SCENARIO_COUNT * (1 + len(RETRY_CODES))


def _load_silver_freeze():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_for_intent_approval",
        SILVER_FREEZE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Silver freeze module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SILVER_FREEZE = _load_silver_freeze()

from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianIntentDraftProvider,
)
from treeguard.change_intent import REQUEST_SCHEMA_VERSION, IntentRequest  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    ScenarioCapabilitySilverAuthorization,
)


class M4SilverIntentApprovalError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def wire_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def build_approval(silver_dir: str | Path = DEFAULT_SILVER_DIR) -> dict[str, Any]:
    silver_path = Path(silver_dir)
    try:
        report = SILVER_FREEZE.validate_staging(silver_path)
        if report["status"] != "PASS":
            raise ValueError
        manifest_raw = (silver_path / "manifest.json").read_bytes()
        authorization_raw = (silver_path / "silver-authorizations.json").read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8"))
        authorization_batch = json.loads(authorization_raw.decode("utf-8"))
        contexts = {
            context.reviewed.plan_unit_ref: context
            for context in SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
        }
        authorizations = {
            item["plan_unit_ref"]: item
            for item in authorization_batch["items"]
        }
        provider = BailianIntentDraftProvider(
            BailianConfig(
                api_key="NOT_USED_FOR_LOCAL_APPROVAL_PREPARATION",
                base_url=DEFAULT_BASE_URL,
                model=DEFAULT_MODEL,
                max_attempts=2,
            )
        )
        possible_requests = []
        for plan_unit_ref in sorted(contexts):
            context = contexts[plan_unit_ref]
            authorization_item = authorizations[plan_unit_ref]
            authorization = ScenarioCapabilitySilverAuthorization.from_dict(
                authorization_item["authorization"],
                context.reviewed,
                context.plan,
                context.tree,
            )
            if (
                authorization_item["decision"] != "SILVER_ACCEPTED"
                or authorization_item["execution_eligible"] is not True
                or authorization.authorization_hash
                != authorization_item["authorization"]["authorization_hash"]
            ):
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
            model_input = request.to_model_dict(context.tree)
            variants = ((1, None),) + tuple((2, code) for code in RETRY_CODES)
            for attempt, retry_code in variants:
                body = provider._intent_request_body(
                    model_input,
                    retry_code=retry_code,
                )
                encoded = wire_bytes(body)
                possible_requests.append(
                    {
                        "attempt": attempt,
                        "plan_unit_ref": plan_unit_ref,
                        "retry_code": retry_code,
                        "scenario_ref": context.scenario_ref,
                        "stage": "INTENT",
                        "wire_body_text": encoded.decode("utf-8"),
                        "wire_sha256": sha256(encoded).hexdigest(),
                    }
                )
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverIntentApprovalError(
            "SILVER_INTENT_APPROVAL_SOURCE_INVALID"
        ) from None
    if (
        len(possible_requests) != POSSIBLE_REQUEST_BODY_COUNT
        or len({item["wire_sha256"] for item in possible_requests})
        != POSSIBLE_REQUEST_BODY_COUNT
    ):
        raise M4SilverIntentApprovalError(
            "SILVER_INTENT_APPROVAL_ACCOUNTING_INVALID"
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
        raise M4SilverIntentApprovalError(
            "SILVER_INTENT_APPROVAL_ORACLE_LEAK"
        )
    return {
        "schema_version": "treeguard-m4-silver-bailian-intent-approval.v1",
        "purpose": "M4_FIRE_SILVER_CALIBRATION_INTENT_PHASE_ONLY",
        "dataset_ref": manifest["dataset_ref"],
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
        "silver_manifest_sha256": sha256(manifest_raw).hexdigest(),
        "silver_authorizations_sha256": sha256(authorization_raw).hexdigest(),
        "scenario_count": SCENARIO_COUNT,
        "initial_request_count": SCENARIO_COUNT,
        "maximum_actual_request_count": 16,
        "possible_request_body_count": POSSIBLE_REQUEST_BODY_COUNT,
        "retry_policy": "AT_MOST_ONE_RETRY_USING_THE_ACTUAL_LOCAL_ERROR_CODE",
        "possible_requests": possible_requests,
    }


def write_approval(
    silver_dir: str | Path = DEFAULT_SILVER_DIR,
    output_dir: str | Path = "/private/tmp",
) -> tuple[Path, str]:
    approval = build_approval(silver_dir)
    handle, output_name = tempfile.mkstemp(
        prefix="treeguard-m4-silver-intent-approval-",
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
    if stat.S_IMODE(output_path.stat().st_mode) != 0o600:
        output_path.unlink(missing_ok=True)
        raise M4SilverIntentApprovalError(
            "SILVER_INTENT_APPROVAL_WRITE_INVALID"
        )
    return output_path, sha256(content).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("/private/tmp"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path, digest = write_approval(args.silver_dir, args.output_dir)
    except M4SilverIntentApprovalError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "approval_file": str(output_path),
                "approval_file_sha256": digest,
                "contains_credentials": False,
                "contains_oracle": False,
                "maximum_actual_request_count": 16,
                "mode": "0o600",
                "possible_request_body_count": POSSIBLE_REQUEST_BODY_COUNT,
                "scenario_count": SCENARIO_COUNT,
                "status": "READY_FOR_EXPLICIT_EGRESS_APPROVAL",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
