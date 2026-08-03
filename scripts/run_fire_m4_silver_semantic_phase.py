#!/usr/bin/env python3
"""Run the approved Bailian Semantic phase for M4 Silver calibration."""

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

SEMANTIC_APPROVAL_PREP_PATH = (
    PROJECT_ROOT / "scripts/prepare_fire_m4_silver_semantic_approval.py"
)
DEFAULT_SILVER_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-silver-v1"
)


def _load_semantic_approval_prep():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_semantic_approval_for_run",
        SEMANTIC_APPROVAL_PREP_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Semantic approval preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SEMANTIC_APPROVAL_PREP = _load_semantic_approval_prep()

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


class M4SilverSemanticRunError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ApprovedSemanticProvider(BailianSemanticRecommendationProvider):
    def __init__(
        self,
        config: BailianConfig,
        allowed_hashes: set[str],
        audit: list[dict[str, str]],
    ) -> None:
        self.validation_error_codes: list[str] = []
        super().__init__(config, trace_sink=self._capture_validation_trace)
        self.allowed_hashes = allowed_hashes
        self.audit = audit
        self.policy_error: str | None = None
        self.output: Any = None

    def _capture_validation_trace(self, trace: Any) -> None:
        if (
            trace.validation_status == "FAILED"
            and trace.validation_error_code is not None
            and trace.validation_error_code.startswith("SEMANTIC_")
        ):
            self.validation_error_codes.append(trace.validation_error_code)

    def _post_json(self, body: dict[str, Any]) -> Any:
        digest = sha256(SEMANTIC_APPROVAL_PREP.wire_bytes(body)).hexdigest()
        if digest not in self.allowed_hashes:
            self.policy_error = "SILVER_SEMANTIC_BODY_NOT_APPROVED"
            raise RuntimeError(self.policy_error)
        if any(item["wire_sha256"] == digest for item in self.audit):
            self.policy_error = "SILVER_SEMANTIC_BODY_ALREADY_SENT"
            raise RuntimeError(self.policy_error)
        self.audit.append({"wire_sha256": digest})
        return super()._post_json(body)

    def recommend(self, confirmation: Any, candidate_set: Any, tree: Any) -> Any:
        self.output = super().recommend(confirmation, candidate_set, tree)
        return self.output


def _read_approval(
    path: Path,
    expected_sha256: str,
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: Path,
) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if (
            sha256(raw).hexdigest() != expected_sha256
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise ValueError
        payload = json.loads(raw.decode("utf-8"))
        expected = SEMANTIC_APPROVAL_PREP.build_approval(
            intent_results_path,
            intent_results_sha256,
            silver_dir,
        )
        if payload != expected:
            raise ValueError
        return payload
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverSemanticRunError(
            "SILVER_SEMANTIC_APPROVAL_INVALID"
        ) from None


def _write_results(payload: dict[str, Any], output_dir: Path) -> tuple[Path, str]:
    handle, output_name = tempfile.mkstemp(
        prefix="treeguard-m4-silver-semantic-results-",
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
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: Path = DEFAULT_SILVER_DIR,
    output_dir: Path = Path("/private/tmp"),
) -> tuple[Path, str, dict[str, int]]:
    approval = _read_approval(
        approval_path,
        approval_sha256,
        intent_results_path,
        intent_results_sha256,
        silver_dir,
    )
    intent_results = SEMANTIC_APPROVAL_PREP.read_intent_results(
        intent_results_path,
        intent_results_sha256,
    )
    try:
        authorization_batch = json.loads(
            (silver_dir / "silver-authorizations.json").read_text()
        )
        authorization_items = {
            item["plan_unit_ref"]: item
            for item in authorization_batch["items"]
        }
        contexts = {
            context.reviewed.plan_unit_ref: context
            for context in SEMANTIC_APPROVAL_PREP.INTENT_APPROVAL_PREP.SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
        }
        intent_result_items = {
            item["plan_unit_ref"]: item for item in intent_results["results"]
        }
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverSemanticRunError("SILVER_SEMANTIC_SOURCE_INVALID") from None

    env_config = BailianConfig.from_env()
    config = BailianConfig(
        api_key=env_config.api_key,
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        timeout_seconds=90.0,
        max_attempts=2,
    )
    eligible_refs = {
        item["plan_unit_ref"]
        for item in approval["intent_replay"]
        if item["semantic_eligible"] is True
    }
    results = []
    total_calls = 0
    for plan_unit_ref in sorted(eligible_refs):
        context = contexts[plan_unit_ref]
        intent_result = intent_result_items[plan_unit_ref]
        authorization = ScenarioCapabilitySilverAuthorization.from_dict(
            authorization_items[plan_unit_ref]["authorization"],
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
        draft = ChangeIntentDraft.from_dict(
            intent_result["draft"],
            request,
            context.tree,
        )
        allowed_hashes = {
            item["wire_sha256"]
            for item in approval["possible_requests"]
            if item["plan_unit_ref"] == plan_unit_ref
        }
        if len(allowed_hashes) != 1 + len(
            SEMANTIC_APPROVAL_PREP.SEMANTIC_RETRY_CODES
        ):
            raise M4SilverSemanticRunError(
                "SILVER_SEMANTIC_APPROVAL_INCOMPLETE"
            )
        audit: list[dict[str, str]] = []
        provider = ApprovedSemanticProvider(config, allowed_hashes, audit)
        run_result = run_silver_capability_scenario(
            authorization,
            context.reviewed,
            context.action,
            context.batch,
            context.batch_candidate,
            context.projection,
            context.plan,
            context.profile,
            context.tree,
            SEMANTIC_APPROVAL_PREP.ReplayIntentProvider(draft),
            provider,
        )
        if provider.policy_error is not None:
            raise M4SilverSemanticRunError(provider.policy_error)
        if (
            run_result.intent.status != "MATCH"
            or run_result.retrieval.status != "MATCH"
        ):
            raise M4SilverSemanticRunError(
                "SILVER_SEMANTIC_REPLAY_DIVERGED"
            )
        total_calls += len(audit)
        if total_calls > approval["maximum_actual_request_count"]:
            raise M4SilverSemanticRunError(
                "SILVER_SEMANTIC_CALL_LIMIT_EXCEEDED"
            )
        results.append(
            {
                "calls": audit,
                "plan_unit_ref": plan_unit_ref,
                "recommendation_draft": (
                    provider.output.to_dict() if provider.output is not None else None
                ),
                "run": run_result.to_dict(),
                "scenario_ref": context.scenario_ref,
                "validation_error_codes": list(
                    provider.validation_error_codes
                ),
            }
        )
        print(
            json.dumps(
                {
                    "attempt_count": len(audit),
                    "plan_unit_ref": plan_unit_ref,
                    "recommendation_status": run_result.recommendation.status,
                    "validation_error_codes": provider.validation_error_codes,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
    counts = {
        "actual_request_count": total_calls,
        "recommendation_match_count": sum(
            item["run"]["recommendation"]["status"] == "MATCH"
            for item in results
        ),
        "recommendation_mismatch_count": sum(
            item["run"]["recommendation"]["status"] == "MISMATCH"
            for item in results
        ),
        "recommendation_run_failed_count": sum(
            item["run"]["recommendation"]["status"] == "RUN_FAILED"
            for item in results
        ),
        "semantic_scenario_count": len(results),
    }
    payload = {
        "schema_version": "treeguard-m4-silver-bailian-semantic-results.v2",
        "approval_file_sha256": approval_sha256,
        "dataset_ref": approval["dataset_ref"],
        "evaluation_role": "CALIBRATION",
        "gate_eligible": False,
        "gold_eligible": False,
        "intent_replay": approval["intent_replay"],
        "intent_results_sha256": intent_results_sha256,
        "model": DEFAULT_MODEL,
        "prompt_version": BailianSemanticRecommendationProvider.prompt_version,
        "quality_tier": "SILVER",
        "validation_error_code_counts": _validation_error_code_counts(
            results
        ),
        **counts,
        "results": results,
    }
    output_path, output_sha256 = _write_results(payload, output_dir)
    return output_path, output_sha256, counts


def _validation_error_code_counts(
    results: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        for code in result["validation_error_codes"]:
            counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-file", type=Path, required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--intent-results", type=Path, required=True)
    parser.add_argument("--intent-results-sha256", required=True)
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("/private/tmp"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path, digest, counts = run(
            args.approval_file,
            args.approval_sha256,
            args.intent_results,
            args.intent_results_sha256,
            args.silver_dir,
            args.output_dir,
        )
    except M4SilverSemanticRunError as exc:
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
