#!/usr/bin/env python3
"""Run the approved M4 Silver downstream isolation Semantic phase."""

from __future__ import annotations

import argparse
import importlib.util
import json
import secrets
import stat
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

APPROVAL_PREP_PATH = (
    PROJECT_ROOT
    / "scripts/prepare_fire_m4_silver_downstream_isolation_approval.py"
)
SEMANTIC_RUNNER_PATH = PROJECT_ROOT / "scripts/run_fire_m4_silver_semantic_phase.py"
DEFAULT_SILVER_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-silver-v1"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


APPROVAL_PREP = _load_module(
    "treeguard_fire_m4_downstream_isolation_approval_for_run",
    APPROVAL_PREP_PATH,
)
SEMANTIC_RUNNER = _load_module(
    "treeguard_fire_m4_semantic_provider_for_downstream_isolation",
    SEMANTIC_RUNNER_PATH,
)

from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianProviderError,
    BailianSemanticRecommendationProvider,
)
from treeguard.change_intent import ChangeIntentDraft  # noqa: E402
from treeguard.private_io import read_private_json, write_private_json  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    ScenarioCapabilitySilverAuthorization,
    run_silver_capability_scenario,
)


class M4SilverDownstreamIsolationRunError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def read_approval(
    approval_path: Path,
    approval_sha256: str,
    reference_intents_path: Path,
    reference_intents_sha256: str,
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: Path,
) -> dict[str, Any]:
    try:
        raw = approval_path.read_bytes()
        if (
            sha256(raw).hexdigest() != approval_sha256
            or stat.S_IMODE(approval_path.stat().st_mode) != 0o600
        ):
            raise ValueError
        payload = json.loads(raw.decode("utf-8"))
        expected = APPROVAL_PREP.build_approval(
            reference_intents_path,
            reference_intents_sha256,
            intent_results_path,
            intent_results_sha256,
            silver_dir,
        )
        if payload != expected:
            raise ValueError
        return payload
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverDownstreamIsolationRunError(
            "SILVER_DOWNSTREAM_ISOLATION_APPROVAL_INVALID"
        ) from None


def _write_results(
    payload: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, str]:
    for _ in range(3):
        output_path = output_dir / (
            "treeguard-m4-silver-downstream-isolation-results-"
            f"{secrets.token_hex(6)}.json"
        )
        if write_private_json(output_path, payload):
            return output_path, sha256(output_path.read_bytes()).hexdigest()
    raise M4SilverDownstreamIsolationRunError(
        "SILVER_DOWNSTREAM_ISOLATION_RESULT_WRITE_FAILED"
    )


def run(
    approval_path: Path,
    approval_sha256: str,
    reference_intents_path: Path,
    reference_intents_sha256: str,
    intent_results_path: Path,
    intent_results_sha256: str,
    silver_dir: Path = DEFAULT_SILVER_DIR,
    output_dir: Path = Path("/private/tmp"),
) -> tuple[Path, str, dict[str, int]]:
    approval = read_approval(
        approval_path,
        approval_sha256,
        reference_intents_path,
        reference_intents_sha256,
        intent_results_path,
        intent_results_sha256,
        silver_dir,
    )
    try:
        reference = read_private_json(reference_intents_path, max_bytes=128_000)
        authorization_batch = read_private_json(
            silver_dir / "silver-authorizations.json",
            max_bytes=512_000,
        )
        reference_items = {
            item["plan_unit_ref"]: item for item in reference["items"]
        }
        authorization_items = {
            item["plan_unit_ref"]: item
            for item in authorization_batch["items"]
        }
        contexts = {
            context.reviewed.plan_unit_ref: context
            for context in APPROVAL_PREP.SEMANTIC_PREP.INTENT_APPROVAL_PREP.SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
        }
    except (KeyError, OSError, TypeError, ValueError, RuntimeError):
        raise M4SilverDownstreamIsolationRunError(
            "SILVER_DOWNSTREAM_ISOLATION_SOURCE_INVALID"
        ) from None

    try:
        env_config = BailianConfig.from_env()
    except BailianProviderError:
        raise M4SilverDownstreamIsolationRunError(
            "SILVER_DOWNSTREAM_ISOLATION_CONFIG_INVALID"
        ) from None
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
    if eligible_refs != APPROVAL_PREP.REFERENCE_REFS:
        raise M4SilverDownstreamIsolationRunError(
            "SILVER_DOWNSTREAM_ISOLATION_ELIGIBILITY_INVALID"
        )

    results = []
    total_calls = 0
    for plan_unit_ref in sorted(eligible_refs):
        context = contexts[plan_unit_ref]
        reference_item = reference_items[plan_unit_ref]
        authorization = ScenarioCapabilitySilverAuthorization.from_dict(
            authorization_items[plan_unit_ref]["authorization"],
            context.reviewed,
            context.plan,
            context.tree,
        )
        request = APPROVAL_PREP.build_intent_request(context)
        draft = ChangeIntentDraft.from_model_dict(
            reference_item["intent"],
            request,
            context.tree,
            model_provider="CODEX_ASSISTED_REFERENCE",
            model_capability="SILVER_REFERENCE_INTENT",
            model_name="codex-assisted-reference",
            prompt_version="treeguard.m4.silver-reference-intent.v1",
        )
        allowed_hashes = {
            item["wire_sha256"]
            for item in approval["possible_requests"]
            if item["plan_unit_ref"] == plan_unit_ref
        }
        if len(allowed_hashes) != 1 + len(
            APPROVAL_PREP.SEMANTIC_PREP.SEMANTIC_RETRY_CODES
        ):
            raise M4SilverDownstreamIsolationRunError(
                "SILVER_DOWNSTREAM_ISOLATION_APPROVAL_INCOMPLETE"
            )
        audit: list[dict[str, str]] = []
        provider = SEMANTIC_RUNNER.ApprovedSemanticProvider(
            config,
            allowed_hashes,
            audit,
        )
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
            APPROVAL_PREP.SEMANTIC_PREP.ReplayIntentProvider(draft),
            provider,
        )
        if provider.policy_error is not None:
            raise M4SilverDownstreamIsolationRunError(provider.policy_error)
        if (
            run_result.intent.status != "MATCH"
            or run_result.retrieval.status != "MATCH"
        ):
            raise M4SilverDownstreamIsolationRunError(
                "SILVER_DOWNSTREAM_ISOLATION_REPLAY_DIVERGED"
            )
        total_calls += len(audit)
        if total_calls > approval["maximum_actual_request_count"]:
            raise M4SilverDownstreamIsolationRunError(
                "SILVER_DOWNSTREAM_ISOLATION_CALL_LIMIT_EXCEEDED"
            )
        results.append(
            {
                "calls": audit,
                "plan_unit_ref": plan_unit_ref,
                "recommendation_draft": (
                    provider.output.to_dict()
                    if provider.output is not None
                    else None
                ),
                "run": run_result.to_dict(),
                "scenario_ref": context.scenario_ref,
            }
        )
        print(
            json.dumps(
                {
                    "attempt_count": len(audit),
                    "plan_unit_ref": plan_unit_ref,
                    "recommendation_status": run_result.recommendation.status,
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
        "schema_version": (
            "treeguard-m4-silver-downstream-isolation-semantic-results.v1"
        ),
        "approval_file_sha256": approval_sha256,
        "dataset_ref": approval["dataset_ref"],
        "evaluation_role": "DOWNSTREAM_ISOLATION",
        "intent_provider_called": False,
        "end_to_end_eligible": False,
        "gate_eligible": False,
        "gold_eligible": False,
        "reference_intents_sha256": reference_intents_sha256,
        "source_intent_results_sha256": intent_results_sha256,
        "model": DEFAULT_MODEL,
        "prompt_version": BailianSemanticRecommendationProvider.prompt_version,
        "quality_tier": "SILVER",
        **counts,
        "results": results,
    }
    output_path, output_sha256 = _write_results(payload, output_dir)
    return output_path, output_sha256, counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-file", type=Path, required=True)
    parser.add_argument("--approval-sha256", required=True)
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
        output_path, digest, counts = run(
            args.approval_file,
            args.approval_sha256,
            args.reference_intents,
            args.reference_intents_sha256,
            args.intent_results,
            args.intent_results_sha256,
            args.silver_dir,
            args.output_dir,
        )
    except M4SilverDownstreamIsolationRunError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                **counts,
                "end_to_end_eligible": False,
                "intent_provider_called": False,
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
