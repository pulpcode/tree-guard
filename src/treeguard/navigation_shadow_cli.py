"""Private run preparation and offline aggregation for navigation Shadow."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from treeguard.hashing import canonical_digest
from treeguard.navigation_shadow_run import (
    NavigationShadowQualification,
    NavigationShadowRunError,
    NavigationShadowRunManifest,
    aggregate_shadow_qualifications,
)
from treeguard.private_io import (
    preflight_private_output,
    read_private_json,
    write_private_json,
)
from treeguard.workbench_sidecar import (
    WorkbenchSidecarError,
    validate_private_directory,
)


class NavigationShadowCliError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard-navigation-shadow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-run")
    prepare.add_argument("--run-ref", required=True)
    prepare.add_argument("--contract-commit", required=True)
    prepare.add_argument(
        "--provider-mode",
        required=True,
        choices=("SIMULATOR_LIVE", "BAILIAN_LIVE", "QWEN_LIVE"),
    )
    prepare.add_argument("--participant-ref", action="append", required=True)
    prepare.add_argument("--planned-case-count", type=int, default=30)
    prepare.add_argument("--output", type=Path, required=True)

    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--manifest", type=Path, required=True)
    aggregate.add_argument(
        "--sidecar-root", type=Path, action="append", required=True
    )
    aggregate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = _prepare(args) if args.command == "prepare-run" else _aggregate(args)
    except (
        NavigationShadowCliError,
        NavigationShadowRunError,
        WorkbenchSidecarError,
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
    ) as exc:
        code = getattr(exc, "code", "SHADOW_PRIVATE_IO_FAILED")
        _print_json(
            {
                "report_version": "navigation-copilot-shadow-cli.v1",
                "valid": False,
                "error_code": code,
            }
        )
        return 2
    _print_json(report)
    return 0


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    output = _absolute(args.output)
    validate_private_directory(output.parent)
    manifest = NavigationShadowRunManifest.create(
        run_ref=args.run_ref,
        contract_commit=args.contract_commit,
        provider_mode=args.provider_mode,
        participant_refs=tuple(args.participant_ref),
        planned_case_count=args.planned_case_count,
    )
    preflight_private_output(output)
    if not write_private_json(output, manifest.to_dict()):
        raise NavigationShadowCliError("SHADOW_RUN_PUBLISH_FAILED")
    return {
        "report_version": "navigation-copilot-shadow-run-preflight.v1",
        "valid": True,
        "status": "SHADOW_RUN_FROZEN",
        "planned_case_count": manifest.planned_case_count,
        "participant_count": len(manifest.participant_refs),
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }


def _aggregate(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _absolute(args.manifest)
    output = _absolute(args.output)
    validate_private_directory(manifest_path.parent)
    validate_private_directory(output.parent)
    manifest = NavigationShadowRunManifest.from_dict(
        read_private_json(manifest_path, max_bytes=64 * 1024)
    )
    records = _read_qualifications(
        manifest,
        tuple(_absolute(item) for item in args.sidecar_root),
    )
    report = aggregate_shadow_qualifications(manifest, records)
    preflight_private_output(output)
    if not write_private_json(output, report):
        raise NavigationShadowCliError("SHADOW_AGGREGATE_PUBLISH_FAILED")
    return report


def _read_qualifications(
    manifest: NavigationShadowRunManifest,
    roots: tuple[Path, ...],
) -> tuple[NavigationShadowQualification, ...]:
    if len(roots) > 100:
        raise NavigationShadowCliError("SHADOW_SIDECAR_ROOT_LIMIT_EXCEEDED")
    records = []
    scanned_cases = 0
    for root in roots:
        validate_private_directory(root)
        try:
            entries = sorted(os.scandir(root), key=lambda item: item.name)
        except OSError:
            raise NavigationShadowCliError("SHADOW_SIDECAR_SCAN_FAILED") from None
        for entry in entries:
            if not entry.name.startswith("NC"):
                continue
            scanned_cases += 1
            if scanned_cases > manifest.planned_case_count * 2:
                raise NavigationShadowCliError("SHADOW_SIDECAR_SCAN_LIMIT_EXCEEDED")
            case_directory = root / entry.name
            validate_private_directory(case_directory)
            path = case_directory / "10-shadow-qualification.json"
            try:
                payload = read_private_json(path, max_bytes=64 * 1024)
            except FileNotFoundError:
                raise NavigationShadowCliError(
                    "SHADOW_QUALIFICATION_MISSING"
                ) from None
            record = NavigationShadowQualification.from_dict(payload, manifest)
            decision = read_private_json(
                case_directory / "08-policy-decision.json",
                max_bytes=256 * 1024,
            )
            outcome = read_private_json(
                case_directory / "09-outcome.json",
                max_bytes=256 * 1024,
            )
            _validate_qualification_sources(record, decision, outcome)
            records.append(record)
            if len(records) > manifest.planned_case_count:
                raise NavigationShadowCliError("SHADOW_AGGREGATE_PLAN_EXCEEDED")
    return tuple(records)


def _validate_qualification_sources(
    record: NavigationShadowQualification,
    decision: Any,
    outcome: Any,
) -> None:
    decision_fields = {
        "schema_version", "policy_version", "semantic_approval", "patch_eligible",
        "source_interpretation_hash", "source_candidate_set_hash",
        "source_projection_hash", "source_semantic_draft_hash", "status",
        "highlighted_candidate_ref", "reason_code", "semantic_status",
        "decision_hash",
    }
    outcome_fields = {
        "schema_version", "record_semantics", "semantic_approval", "gold_eligible",
        "patch_eligible", "source_decision_hash", "action",
        "selected_candidate_ref", "selected_node_id", "candidate_miss",
        "user_corrected", "duration_ms", "outcome_hash",
    }
    if (
        not isinstance(decision, dict)
        or set(decision) != decision_fields
        or decision.get("schema_version")
        != "navigation-copilot-policy-decision.v1"
        or decision.get("policy_version")
        != "treeguard.navigation-copilot-policy.v1"
        or decision.get("semantic_approval") is not False
        or decision.get("patch_eligible") is not False
        or decision.get("status") not in {
            "CANDIDATES_AVAILABLE", "AMBIGUOUS", "NONE", "NEED_EVIDENCE"
        }
        or not _hash_matches(decision, "decision_hash")
    ):
        raise NavigationShadowCliError("SHADOW_DECISION_SOURCE_INVALID")
    if (
        not isinstance(outcome, dict)
        or set(outcome) != outcome_fields
        or outcome.get("schema_version") != "navigation-copilot-outcome.v1"
        or outcome.get("record_semantics") != "OPERATIONAL_FEEDBACK_ONLY"
        or outcome.get("semantic_approval") is not False
        or outcome.get("gold_eligible") is not False
        or outcome.get("patch_eligible") is not False
        or not _hash_matches(outcome, "outcome_hash")
        or outcome.get("source_decision_hash") != decision.get("decision_hash")
        or record.source_outcome_hash != outcome.get("outcome_hash")
        or record.confident
        != (decision.get("status") == "CANDIDATES_AVAILABLE")
        or record.evidence_covered != (decision.get("status") != "NONE")
        or record.duration_ms != outcome.get("duration_ms")
    ):
        raise NavigationShadowCliError("SHADOW_OUTCOME_SOURCE_INVALID")
    expected_disposition = {
        "SELECT_CANDIDATE": "FOUND_TOP8",
        "SELECT_OUTSIDE_CANDIDATE": "FOUND_OUTSIDE",
        "EXIT": "EXITED",
    }.get(outcome.get("action"))
    if outcome.get("action") == "REJECT_ALL":
        if record.target_disposition not in {
            "PRESENT_NOT_FOUND", "ABSENT", "UNKNOWN"
        }:
            raise NavigationShadowCliError("SHADOW_TARGET_DISPOSITION_INVALID")
    elif expected_disposition != record.target_disposition:
        raise NavigationShadowCliError("SHADOW_TARGET_DISPOSITION_INVALID")


def _hash_matches(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, str):
        return False
    return value == canonical_digest(
        {key: item for key, item in payload.items() if key != field}
    )


def _absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise NavigationShadowCliError("SHADOW_PATH_NOT_ABSOLUTE")
    return path


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


__all__ = ["build_parser", "main"]
