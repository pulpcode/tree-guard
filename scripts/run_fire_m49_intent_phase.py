#!/usr/bin/env python3
"""Run the approved M4.9 Intent observations against exact frozen bodies."""

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
    M49RuntimePlanError,
    build_plan,
    load_formal_intent_contexts,
    validate_plan,
    wire_bytes,
)
from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianIntentDraftProvider,
    BailianProviderError,
)
from treeguard.private_io import (  # noqa: E402
    preflight_private_output,
    read_private_json,
    write_private_json,
)


RESULT_SCHEMA_VERSION = "fire-m49-sealed-intent-results.v1"
INTENT_MAXIMUM_ACTUAL_REQUEST_COUNT = 144
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
    "plan_file_sha256",
    "model",
    "prompt_version",
    "round_count",
    "observation_count",
    "actual_request_count",
    "first_pass_count",
    "retry_observation_count",
    "draft_ready_count",
    "run_failed_count",
    "failure_code_counts",
    "results",
    "next_gate",
}
RESULT_ITEM_KEYS = {
    "observation_ref",
    "round_index",
    "scenario_ref",
    "source_candidate_digest",
    "request_hash",
    "status",
    "failure_code",
    "calls",
    "draft",
}


class M49IntentRunError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PlannedIntentProvider(BailianIntentDraftProvider):
    """Reject an unplanned body before the transport boundary."""

    def __init__(
        self,
        config: BailianConfig,
        allowed_hashes: set[str],
        audit: list[dict[str, Any]],
    ) -> None:
        super().__init__(config)
        self.allowed_hashes = frozenset(allowed_hashes)
        self.audit = audit

    def _post_json(self, body: dict[str, Any]) -> Any:
        digest = hashlib.sha256(wire_bytes(body)).hexdigest()
        if digest not in self.allowed_hashes:
            raise M49IntentRunError("M49_INTENT_BODY_NOT_PLANNED")
        if len(self.audit) >= 2:
            raise M49IntentRunError("M49_INTENT_UNIT_CALL_LIMIT_EXCEEDED")
        self.audit.append(
            {
                "attempt": len(self.audit) + 1,
                "wire_sha256": digest,
            }
        )
        return super()._post_json(body)


def validate_tls_trust() -> None:
    """Reject a Python runtime with no loaded CA roots before batch egress."""

    try:
        trusted_roots = ssl.create_default_context().get_ca_certs()
    except (OSError, ssl.SSLError):
        raise M49IntentRunError("M49_INTENT_TLS_TRUST_UNAVAILABLE") from None
    if not trusted_roots:
        raise M49IntentRunError("M49_INTENT_TLS_TRUST_UNAVAILABLE")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise M49IntentRunError("M49_INTENT_PLAN_INVALID") from None
    return digest.hexdigest()


def read_approved_plan(
    path: Path,
    expected_sha256: str,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
    try:
        plan = read_private_json(path, max_bytes=30_000_000)
        if (
            _sha256_file(path) != expected_sha256
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise ValueError
        validate_plan(plan, fixture_dir=fixture_dir)
        if plan != build_plan(fixture_dir):
            raise ValueError
    except (
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        M49RuntimePlanError,
    ):
        raise M49IntentRunError("M49_INTENT_PLAN_INVALID") from None
    return plan


def validate_result(payload: Any, plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != RESULT_KEYS:
        raise M49IntentRunError("M49_INTENT_RESULT_FIELDS_INVALID")
    results = payload["results"]
    if (
        payload["schema_version"] != RESULT_SCHEMA_VERSION
        or payload["purpose"] != "M49_SEALED_SILVER_INTENT_ONLY"
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
        or payload["dataset_ref"] != plan["dataset_ref"]
        or not isinstance(payload["plan_file_sha256"], str)
        or len(payload["plan_file_sha256"]) != 64
        or payload["model"] != DEFAULT_MODEL
        or payload["prompt_version"] != "treeguard.change-intent.zh.v4"
        or payload["round_count"] != 3
        or payload["observation_count"] != 72
        or not isinstance(results, list)
        or len(results) != 72
        or any(
            not isinstance(item, dict) or set(item) != RESULT_ITEM_KEYS
            for item in results
        )
    ):
        raise M49IntentRunError("M49_INTENT_RESULT_POLICY_INVALID")
    expected_refs = [unit["observation_ref"] for unit in plan["units"]]
    if [item["observation_ref"] for item in results] != expected_refs:
        raise M49IntentRunError("M49_INTENT_RESULT_ORDER_INVALID")
    planned_by_ref = {
        unit["observation_ref"]: unit for unit in plan["units"]
    }
    actual_calls = sum(len(item["calls"]) for item in results)
    statuses = [item["status"] for item in results]
    failure_counts: dict[str, int] = {}
    for item in results:
        planned = planned_by_ref[item["observation_ref"]]
        allowed_hashes = {
            request["wire_sha256"]
            for request in planned["intent_possible_requests"]
        }
        if item["failure_code"] is not None:
            failure_counts[item["failure_code"]] = (
                failure_counts.get(item["failure_code"], 0) + 1
            )
        if (
            item["status"] not in {"DRAFT_READY", "RUN_FAILED"}
            or len(item["calls"]) not in {1, 2}
            or any(
                not isinstance(call, dict)
                or set(call) != {"attempt", "wire_sha256"}
                or call["attempt"] not in {1, 2}
                or call["wire_sha256"] not in allowed_hashes
                for call in item["calls"]
            )
            or [call["attempt"] for call in item["calls"]]
            != list(range(1, len(item["calls"]) + 1))
            or item["round_index"] != planned["round_index"]
            or item["scenario_ref"] != planned["scenario_ref"]
            or item["source_candidate_digest"]
            != planned["source_candidate_digest"]
            or (item["status"] == "DRAFT_READY")
            != (item["draft"] is not None and item["failure_code"] is None)
            or (item["status"] == "RUN_FAILED")
            != (item["draft"] is None and isinstance(item["failure_code"], str))
        ):
            raise M49IntentRunError("M49_INTENT_RESULT_ITEM_INVALID")
    expected_counts = {
        "actual_request_count": actual_calls,
        "first_pass_count": sum(len(item["calls"]) == 1 for item in results),
        "retry_observation_count": sum(len(item["calls"]) == 2 for item in results),
        "draft_ready_count": statuses.count("DRAFT_READY"),
        "run_failed_count": statuses.count("RUN_FAILED"),
    }
    if (
        actual_calls > INTENT_MAXIMUM_ACTUAL_REQUEST_COUNT
        or payload["failure_code_counts"] != dict(sorted(failure_counts.items()))
        or any(
            not isinstance(payload[field], int)
            or isinstance(payload[field], bool)
            or payload[field] != value
            for field, value in expected_counts.items()
        )
    ):
        raise M49IntentRunError("M49_INTENT_RESULT_ACCOUNTING_INVALID")
    if payload["next_gate"] != "FREEZE_EXACT_SEMANTIC_REQUEST_PLAN":
        raise M49IntentRunError("M49_INTENT_RESULT_POLICY_INVALID")
    return {
        "status": "PASS",
        **expected_counts,
        "failure_code_counts": payload["failure_code_counts"],
        "next_gate": payload["next_gate"],
    }


def run_live(
    *,
    plan_file: Path,
    approved_plan_sha256: str,
    private_output: Path,
    fixture_dir: Path = FIXTURE_DIR,
    execution_approved: bool,
) -> dict[str, Any]:
    if execution_approved is not True:
        raise M49IntentRunError("M49_INTENT_EXECUTION_NOT_APPROVED")
    plan = read_approved_plan(plan_file, approved_plan_sha256, fixture_dir)
    validate_tls_trust()
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
        contexts = {
            context.scenario_ref: context
            for context in load_formal_intent_contexts(fixture_dir)
        }
    except (BailianProviderError, OSError, ValueError, M49RuntimePlanError):
        raise M49IntentRunError("M49_INTENT_PREFLIGHT_FAILED") from None

    results: list[dict[str, Any]] = []
    actual_request_count = 0
    for unit in plan["units"]:
        context = contexts[unit["scenario_ref"]]
        if context.source_candidate_digest != unit["source_candidate_digest"]:
            raise M49IntentRunError("M49_INTENT_SOURCE_MISMATCH")
        allowed_hashes = {
            item["wire_sha256"] for item in unit["intent_possible_requests"]
        }
        audit: list[dict[str, Any]] = []
        provider = PlannedIntentProvider(config, allowed_hashes, audit)
        draft = None
        failure_code = None
        try:
            draft = provider.draft(context.request, context.tree)
        except BailianProviderError as exc:
            failure_code = exc.code
        actual_request_count += len(audit)
        if actual_request_count > INTENT_MAXIMUM_ACTUAL_REQUEST_COUNT:
            raise M49IntentRunError("M49_INTENT_CALL_LIMIT_EXCEEDED")
        status = "DRAFT_READY" if draft is not None else "RUN_FAILED"
        results.append(
            {
                "observation_ref": unit["observation_ref"],
                "round_index": unit["round_index"],
                "scenario_ref": unit["scenario_ref"],
                "source_candidate_digest": unit["source_candidate_digest"],
                "request_hash": context.request.request_hash,
                "status": status,
                "failure_code": failure_code,
                "calls": audit,
                "draft": None if draft is None else draft.to_dict(),
            }
        )
    failure_code_counts: dict[str, int] = {}
    for item in results:
        if item["failure_code"] is not None:
            failure_code_counts[item["failure_code"]] = (
                failure_code_counts.get(item["failure_code"], 0) + 1
            )
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "purpose": "M49_SEALED_SILVER_INTENT_ONLY",
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
        "plan_file_sha256": approved_plan_sha256,
        "model": DEFAULT_MODEL,
        "prompt_version": BailianIntentDraftProvider.prompt_version,
        "round_count": 3,
        "observation_count": 72,
        "actual_request_count": actual_request_count,
        "first_pass_count": sum(len(item["calls"]) == 1 for item in results),
        "retry_observation_count": sum(
            len(item["calls"]) == 2 for item in results
        ),
        "draft_ready_count": sum(
            item["status"] == "DRAFT_READY" for item in results
        ),
        "run_failed_count": sum(
            item["status"] == "RUN_FAILED" for item in results
        ),
        "failure_code_counts": dict(sorted(failure_code_counts.items())),
        "results": results,
        "next_gate": "FREEZE_EXACT_SEMANTIC_REQUEST_PLAN",
    }
    aggregate = validate_result(payload, plan)
    if not write_private_json(private_output, payload):
        raise M49IntentRunError("M49_INTENT_PRIVATE_OUTPUT_FAILED")
    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--approved-plan-sha256", required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--execute-approved", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        aggregate = run_live(
            plan_file=args.plan_file,
            approved_plan_sha256=args.approved_plan_sha256,
            private_output=args.private_output,
            fixture_dir=args.fixture_dir,
            execution_approved=args.execute_approved,
        )
    except M49IntentRunError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(json.dumps(aggregate, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
