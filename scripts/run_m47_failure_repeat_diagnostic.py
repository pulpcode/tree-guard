#!/usr/bin/env python3
"""Repeat only M4.7 run failures without changing or rescoring the main A/B."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
M47_PATH = PROJECT_ROOT / "scripts/run_m47_semantic_policy_calibration.py"


def _load_m47():
    spec = importlib.util.spec_from_file_location("treeguard_m47_for_repeat", M47_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4.7 calibration helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


M47 = _load_m47()

from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianProviderError,
)
from treeguard.private_io import (  # noqa: E402
    preflight_private_output,
    write_private_json,
)


PLAN_SCHEMA_VERSION = "fire-m47-failure-repeat-plan.v1"
RESULT_SCHEMA_VERSION = "fire-m47-failure-repeat-result.v1"
REPETITIONS = 2
FAILED_UNIT_COUNT = 2


def build_repeat_plan(
    source_plan: dict[str, Any],
    source_result: dict[str, Any],
    *,
    source_plan_sha256: str,
    source_result_sha256: str,
) -> dict[str, Any]:
    try:
        if (
            source_plan["schema_version"] != M47.PLAN_SCHEMA_VERSION
            or source_result["schema_version"] != M47.RESULT_SCHEMA_VERSION
            or source_result["plan_sha256"] != source_plan_sha256
            or source_result["quality_tier"] != "SILVER"
            or source_result["evaluation_role"] != "CALIBRATION_ONLY"
            or source_result["gate_eligible"] is not False
            or source_result["gold_eligible"] is not False
        ):
            raise ValueError
        failed = {
            item["observation_ref"]: item
            for item in source_result["results"]
            if item["v4_status"] == "RUN_FAILED"
        }
        units = {
            item["observation_ref"]: item for item in source_plan["units"]
        }
        if len(failed) != FAILED_UNIT_COUNT or not set(failed) <= set(units):
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise M47.M47Error("M47_REPEAT_SOURCE_INVALID") from exc
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "purpose": "M47_FAILURE_STABILITY_DIAGNOSTIC_ONLY",
        "quality_tier": "SILVER",
        "evaluation_role": "DIAGNOSTIC_ONLY",
        "gate_eligible": False,
        "gold_eligible": False,
        "rescores_main_result": False,
        "model": source_plan["model"],
        "prompt_version": source_plan["prompt_version"],
        "source_plan_sha256": source_plan_sha256,
        "source_result_sha256": source_result_sha256,
        "failed_unit_count": len(failed),
        "repetitions_per_unit": REPETITIONS,
        "maximum_actual_request_count": len(failed) * REPETITIONS * 2,
        "units": [
            {
                "observation_ref": ref,
                "source_failure_code": failed[ref]["failure_code"],
                "possible_requests": units[ref]["possible_requests"],
            }
            for ref in sorted(failed)
        ],
    }


def _load_sources(
    *,
    source_plan_file: Path,
    source_plan_sha256: str,
    source_result_file: Path,
    source_result_sha256: str,
    reconstruction: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_plan = M47._read_private_dict(source_plan_file, source_plan_sha256)
    source_result = M47._read_private_dict(source_result_file, source_result_sha256)
    rebuilt_plan, contexts = M47._reconstruct(**reconstruction)
    if source_plan != rebuilt_plan:
        raise M47.M47Error("M47_REPEAT_SOURCE_REPLAY_MISMATCH")
    repeat_plan = build_repeat_plan(
        source_plan,
        source_result,
        source_plan_sha256=source_plan_sha256,
        source_result_sha256=source_result_sha256,
    )
    return repeat_plan, source_result, contexts


def run_live(
    *,
    repeat_plan_file: Path,
    repeat_plan_sha256: str,
    private_output: Path,
    **source_kwargs: Any,
) -> dict[str, Any]:
    approved = M47._read_private_dict(repeat_plan_file, repeat_plan_sha256)
    rebuilt, _source_result, contexts = _load_sources(**source_kwargs)
    if approved != rebuilt:
        raise M47.M47Error("M47_REPEAT_PLAN_REPLAY_MISMATCH")
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
        raise M47.M47Error("M47_REPEAT_PREFLIGHT_FAILED") from exc

    results: list[dict[str, Any]] = []
    request_count = 0
    for unit in approved["units"]:
        context = contexts[unit["observation_ref"]]
        allowed = {item["wire_sha256"] for item in unit["possible_requests"]}
        for repetition in range(1, approved["repetitions_per_unit"] + 1):
            audit: list[dict[str, str]] = []
            traces: list[dict[str, Any]] = []
            provider = M47.ApprovedV4Provider(config, allowed, audit, traces)
            draft = None
            failure_code = None
            try:
                draft = provider.recommend(
                    context.confirmation, context.candidate_set, context.tree
                )
            except BailianProviderError as exc:
                failure_code = exc.code
            except M47.M47Error:
                raise
            except Exception:
                failure_code = "SEMANTIC_PROVIDER_UNEXPECTED_FAILURE"
            request_count += len(audit)
            if request_count > approved["maximum_actual_request_count"]:
                raise M47.M47Error("M47_REPEAT_CALL_LIMIT_EXCEEDED")
            status = M47.semantic_status(
                draft,
                context.candidate_set,
                context.oracle,
                provider_failed=draft is None,
            )
            results.append(
                {
                    "observation_ref": unit["observation_ref"],
                    "repetition": repetition,
                    "status": status,
                    "failure_code": failure_code,
                    "calls": audit,
                    "traces": traces,
                    "recommendation_draft": (
                        None if draft is None else draft.to_dict()
                    ),
                }
            )
            print(
                json.dumps(
                    {
                        "attempt_count": len(audit),
                        "observation_ref": unit["observation_ref"],
                        "repetition": repetition,
                        "status": status,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    counts = Counter(item["status"] for item in results)
    aggregate = {
        "diagnostic_observation_count": len(results),
        "actual_request_count": request_count,
        "status_counts": {
            key: counts[key] for key in M47.SEMANTIC_STATUSES
        },
        "all_previous_failures_produced_contract_legal_output": all(
            any(
                item["observation_ref"] == unit["observation_ref"]
                and item["status"] != "RUN_FAILED"
                for item in results
            )
            for unit in approved["units"]
        ),
    }
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "quality_tier": "SILVER",
        "evaluation_role": "DIAGNOSTIC_ONLY",
        "gate_eligible": False,
        "gold_eligible": False,
        "rescores_main_result": False,
        "repeat_plan_sha256": repeat_plan_sha256,
        "aggregate": aggregate,
        "results": results,
    }
    if not write_private_json(private_output, payload):
        raise M47.M47Error("M47_REPEAT_PRIVATE_OUTPUT_FAILED")
    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "live"))
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--original-result-file", type=Path, required=True)
    parser.add_argument("--original-result-sha256", required=True)
    parser.add_argument("--m46-result-file", type=Path, required=True)
    parser.add_argument("--m46-result-sha256", required=True)
    parser.add_argument("--source-plan-file", type=Path, required=True)
    parser.add_argument("--source-plan-sha256", required=True)
    parser.add_argument("--source-result-file", type=Path, required=True)
    parser.add_argument("--source-result-sha256", required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--repeat-plan-file", type=Path)
    parser.add_argument("--repeat-plan-sha256")
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
    sources = {
        "source_plan_file": args.source_plan_file,
        "source_plan_sha256": args.source_plan_sha256,
        "source_result_file": args.source_result_file,
        "source_result_sha256": args.source_result_sha256,
        "reconstruction": reconstruction,
    }
    try:
        if args.mode == "prepare":
            preflight_private_output(args.private_output)
            plan, _, _ = _load_sources(**sources)
            if not write_private_json(args.private_output, plan):
                raise M47.M47Error("M47_REPEAT_PRIVATE_OUTPUT_FAILED")
            output = {
                "status": "PASS",
                "failed_unit_count": plan["failed_unit_count"],
                "planned_diagnostic_observation_count": (
                    plan["failed_unit_count"] * plan["repetitions_per_unit"]
                ),
                "private_output_sha256": M47.sha256_file(args.private_output),
            }
        else:
            if args.repeat_plan_file is None or args.repeat_plan_sha256 is None:
                raise M47.M47Error("M47_REPEAT_PLAN_REQUIRED")
            aggregate = run_live(
                repeat_plan_file=args.repeat_plan_file,
                repeat_plan_sha256=args.repeat_plan_sha256,
                private_output=args.private_output,
                **sources,
            )
            output = {"status": "PASS", "aggregate": aggregate}
    except M47.M47Error as exc:
        print(json.dumps({"status": "FAIL", "code": exc.code}, sort_keys=True))
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
