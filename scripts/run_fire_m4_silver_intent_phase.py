#!/usr/bin/env python3
"""Run the approved Bailian Intent phase for the M4 Silver calibration."""

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

APPROVAL_PREP_PATH = (
    PROJECT_ROOT / "scripts/prepare_fire_m4_silver_intent_approval.py"
)
DEFAULT_SILVER_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-silver-v1"
)


def _load_approval_prep():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_intent_approval_for_run",
        APPROVAL_PREP_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Intent approval preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


APPROVAL_PREP = _load_approval_prep()

from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianIntentDraftProvider,
    BailianProviderError,
)
from treeguard.change_intent import REQUEST_SCHEMA_VERSION, IntentRequest  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    ScenarioCapabilitySilverAuthorization,
)


class M4SilverIntentRunError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ApprovedIntentProvider(BailianIntentDraftProvider):
    def __init__(
        self,
        config: BailianConfig,
        allowed_hashes: set[str],
        audit: list[dict[str, str]],
    ) -> None:
        super().__init__(config)
        self.allowed_hashes = allowed_hashes
        self.audit = audit

    def _post_json(self, body: dict[str, Any]) -> Any:
        digest = sha256(APPROVAL_PREP.wire_bytes(body)).hexdigest()
        if digest not in self.allowed_hashes:
            raise M4SilverIntentRunError("SILVER_INTENT_BODY_NOT_APPROVED")
        if any(item["wire_sha256"] == digest for item in self.audit):
            raise M4SilverIntentRunError("SILVER_INTENT_BODY_ALREADY_SENT")
        self.audit.append({"wire_sha256": digest})
        return super()._post_json(body)


def _read_approval(path: Path, expected_sha256: str) -> dict[str, Any]:
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
            != "treeguard-m4-silver-bailian-intent-approval.v1"
            or payload["purpose"]
            != "M4_FIRE_SILVER_CALIBRATION_INTENT_PHASE_ONLY"
            or payload["endpoint"]
            != DEFAULT_BASE_URL.rstrip("/") + "/chat/completions"
            or payload["model"] != DEFAULT_MODEL
            or payload["quality_tier"] != "SILVER"
            or payload["evaluation_role"] != "CALIBRATION"
            or payload["gold_eligible"] is not False
            or payload["gate_eligible"] is not False
            or payload["contains_oracle"] is not False
            or payload["contains_credentials"] is not False
            or payload["possible_request_body_count"]
            != APPROVAL_PREP.POSSIBLE_REQUEST_BODY_COUNT
            or payload["maximum_actual_request_count"] != 16
        ):
            raise ValueError
        possible = payload["possible_requests"]
        if (
            len(possible) != APPROVAL_PREP.POSSIBLE_REQUEST_BODY_COUNT
            or len({item["wire_sha256"] for item in possible})
            != APPROVAL_PREP.POSSIBLE_REQUEST_BODY_COUNT
            or any(
                sha256(item["wire_body_text"].encode("utf-8")).hexdigest()
                != item["wire_sha256"]
                for item in possible
            )
        ):
            raise ValueError
        return payload
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        raise M4SilverIntentRunError("SILVER_INTENT_APPROVAL_INVALID") from None


def _write_results(payload: dict[str, Any], output_dir: Path) -> tuple[Path, str]:
    handle, output_name = tempfile.mkstemp(
        prefix="treeguard-m4-silver-intent-results-",
        suffix=".json",
        dir=output_dir,
        text=False,
    )
    output_path = Path(output_name)
    try:
        content = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        with os.fdopen(handle, "wb") as output:
            output.write(content)
        os.chmod(output_path, 0o600)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return output_path, sha256(content).hexdigest()


def run(
    approval_path: Path,
    approval_sha256: str,
    silver_dir: Path = DEFAULT_SILVER_DIR,
    output_dir: Path = Path("/private/tmp"),
) -> tuple[Path, str, dict[str, int]]:
    approval = _read_approval(approval_path, approval_sha256)
    try:
        APPROVAL_PREP.SILVER_FREEZE.validate_staging(silver_dir)
        manifest_raw = (silver_dir / "manifest.json").read_bytes()
        authorization_raw = (
            silver_dir / "silver-authorizations.json"
        ).read_bytes()
        if (
            sha256(manifest_raw).hexdigest()
            != approval["silver_manifest_sha256"]
            or sha256(authorization_raw).hexdigest()
            != approval["silver_authorizations_sha256"]
        ):
            raise ValueError
        authorization_batch = json.loads(authorization_raw.decode("utf-8"))
        authorization_items = {
            item["plan_unit_ref"]: item
            for item in authorization_batch["items"]
        }
        contexts = {
            context.reviewed.plan_unit_ref: context
            for context in APPROVAL_PREP.SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
        }
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverIntentRunError("SILVER_INTENT_SOURCE_INVALID") from None

    env_config = BailianConfig.from_env()
    config = BailianConfig(
        api_key=env_config.api_key,
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        timeout_seconds=90.0,
        max_attempts=2,
    )
    possible = approval["possible_requests"]
    results = []
    total_calls = 0
    for plan_unit_ref in sorted(contexts):
        context = contexts[plan_unit_ref]
        authorization_item = authorization_items[plan_unit_ref]
        authorization = ScenarioCapabilitySilverAuthorization.from_dict(
            authorization_item["authorization"],
            context.reviewed,
            context.plan,
            context.tree,
        )
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
        allowed_hashes = {
            item["wire_sha256"]
            for item in possible
            if item["plan_unit_ref"] == plan_unit_ref
        }
        if len(allowed_hashes) != 1 + len(APPROVAL_PREP.RETRY_CODES):
            raise M4SilverIntentRunError("SILVER_INTENT_APPROVAL_INCOMPLETE")
        audit: list[dict[str, str]] = []
        provider = ApprovedIntentProvider(config, allowed_hashes, audit)
        try:
            draft = provider.draft(request, context.tree)
        except BailianProviderError as exc:
            result = {
                "authorization_hash": authorization.authorization_hash,
                "calls": audit,
                "draft": None,
                "failure_code": exc.code,
                "plan_unit_ref": plan_unit_ref,
                "request_hash": request.request_hash,
                "scenario_ref": context.scenario_ref,
                "status": "RUN_FAILED",
            }
        else:
            result = {
                "authorization_hash": authorization.authorization_hash,
                "calls": audit,
                "draft": draft.to_dict(),
                "failure_code": None,
                "plan_unit_ref": plan_unit_ref,
                "request_hash": request.request_hash,
                "scenario_ref": context.scenario_ref,
                "status": "DRAFT_READY",
            }
        total_calls += len(audit)
        if total_calls > 16:
            raise M4SilverIntentRunError("SILVER_INTENT_CALL_LIMIT_EXCEEDED")
        results.append(result)
        print(
            json.dumps(
                {
                    "attempt_count": len(audit),
                    "failure_code": result["failure_code"],
                    "plan_unit_ref": plan_unit_ref,
                    "status": result["status"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
    counts = {
        "actual_request_count": total_calls,
        "draft_ready_count": sum(
            item["status"] == "DRAFT_READY" for item in results
        ),
        "run_failed_count": sum(
            item["status"] == "RUN_FAILED" for item in results
        ),
    }
    payload = {
        "schema_version": "treeguard-m4-silver-bailian-intent-results.v1",
        "approval_file_sha256": approval_sha256,
        "dataset_ref": approval["dataset_ref"],
        "evaluation_role": "CALIBRATION",
        "gate_eligible": False,
        "gold_eligible": False,
        "model": DEFAULT_MODEL,
        "prompt_version": BailianIntentDraftProvider.prompt_version,
        "quality_tier": "SILVER",
        "scenario_count": 8,
        **counts,
        "results": results,
    }
    output_path, output_sha256 = _write_results(payload, output_dir)
    return output_path, output_sha256, counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-file", type=Path, required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("/private/tmp"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path, digest, counts = run(
            args.approval_file,
            args.approval_sha256,
            args.silver_dir,
            args.output_dir,
        )
    except M4SilverIntentRunError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                **counts,
                "mode": "0o600",
                "result_file": str(output_path),
                "result_file_sha256": digest,
                "status": "COMPLETE",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
