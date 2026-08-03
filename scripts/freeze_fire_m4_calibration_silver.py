#!/usr/bin/env python3
"""Freeze Codex-assisted M4 calibration decisions as non-gating Silver data."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import stat
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CALIBRATION_PREP_PATH = PROJECT_ROOT / "scripts/prepare_fire_m4_calibration_data.py"
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-silver-v1"
)
OUTPUT_FILES = {
    "manifest.json",
    "preflight-report.json",
    "review-summary.json",
    "silver-authorizations.json",
}
ASSESSMENT_CODES = {
    "U001": [],
    "U002": ["CROSS_BRANCH_PARENT_CONFLICT_REVIEWED"],
    "U003": ["NODE_KIND_CONFLICT_REVIEWED"],
    "U004": ["CARDINALITY_CONFLICT_REVIEWED"],
    "U005": ["CLARIFICATION_QUALITY_NOT_SCORED"],
    "U007": [],
    "U008": [],
    "U009": [],
}


def _load_calibration_prep():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_calibration_prep_for_silver",
        CALIBRATION_PREP_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load calibration preparation module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CALIBRATION_PREP = _load_calibration_prep()

from treeguard.private_io import write_private_json  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    ScenarioCapabilitySilverAuthorization,
    freeze_silver_capability_authorization,
)


class M4SilverDataError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _common() -> dict[str, Any]:
    return {
        "assessment_authority": "CODEX_ASSISTED",
        "dataset_ref": "fictional-fire-m4-calibration-silver-v1",
        "derived_from_real": False,
        "evaluation_role": "CALIBRATION",
        "execution_scope": "CALIBRATION_ONLY",
        "exposure_status": "EXPOSED",
        "fictional": True,
        "gate_eligible": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "quality_tier": "SILVER",
        "semantic_approval": False,
        "source_class": "CLEANROOM_SYNTHETIC",
    }


def build_artifacts(recorded_at: str) -> dict[str, bytes]:
    try:
        source_artifacts = CALIBRATION_PREP.build_artifacts()
        source_candidate_sha256 = _digest(
            source_artifacts["scenario-candidates.json"]
        )
        source_review_packet_sha256 = _digest(
            source_artifacts["human-review-packet.json"]
        )
        contexts = CALIBRATION_PREP.load_calibration_execution_contexts()
        items = []
        for context in contexts:
            authorization = freeze_silver_capability_authorization(
                context.reviewed,
                context.plan,
                context.tree,
                assessor_ref="codex-assisted-m4-silver",
                recorded_at=recorded_at,
                oracle=context.oracle,
            )
            items.append(
                {
                    "assessment_codes": ASSESSMENT_CODES[
                        context.reviewed.plan_unit_ref
                    ],
                    "authorization": authorization.to_dict(),
                    "decision": "SILVER_ACCEPTED",
                    "execution_eligible": True,
                    "plan_unit_ref": context.reviewed.plan_unit_ref,
                    "scenario_ref": context.scenario_ref,
                    "source_candidate_item_sha256": (
                        context.candidate_item_sha256
                    ),
                }
            )
    except M4SilverDataError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError):
        raise M4SilverDataError("SILVER_SOURCE_REPLAY_FAILED") from None
    if (
        len(items) != 8
        or sum(item["authorization"]["oracle"]["expected_route"] == "PROCEED" for item in items) != 7
        or sum(item["authorization"]["oracle"]["expected_route"] == "CLARIFY" for item in items) != 1
        or {item["plan_unit_ref"] for item in items} != set(ASSESSMENT_CODES)
    ):
        raise M4SilverDataError("SILVER_ACCOUNTING_INVALID")

    common = _common()
    authorizations = {
        **common,
        "accepted_count": 8,
        "execution_count": 8,
        "items": items,
        "recorded_at": recorded_at,
        "schema_version": "fire-m4-calibration-silver-authorizations.v1",
        "source_candidate_sha256": source_candidate_sha256,
        "source_review_packet_sha256": source_review_packet_sha256,
        "status": "SILVER_ACCEPTED",
    }
    authorization_bytes = canonical_json_bytes(authorizations)
    review_summary = {
        **common,
        "accepted_count": 8,
        "assessor_ref": "codex-assisted-m4-silver",
        "decision_counts": {"SILVER_ACCEPTED": 8},
        "limitation_counts": {
            code: sum(code in item["assessment_codes"] for item in items)
            for code in sorted(
                {code for codes in ASSESSMENT_CODES.values() for code in codes}
            )
        },
        "recorded_at": recorded_at,
        "review_method": "CODEX_ASSISTED_REVIEW",
        "schema_version": "fire-m4-calibration-silver-review-summary.v1",
        "source_candidate_sha256": source_candidate_sha256,
        "source_review_packet_sha256": source_review_packet_sha256,
        "status": "SILVER_ACCEPTED",
    }
    review_summary_bytes = canonical_json_bytes(review_summary)
    manifest = {
        **common,
        "accepted_count": 8,
        "authorization_file": "silver-authorizations.json",
        "authorization_sha256": _digest(authorization_bytes),
        "execution_count": 8,
        "execution_eligible": True,
        "limitations": [
            "CODEX_ASSISTED_NON_AUTHORITATIVE",
            "NOT_GOLD",
            "NOT_A_QUALITY_GATE",
            "NOT_PRODUCTION_ACCURACY_EVIDENCE",
            "NO_AUTOMATIC_GOLD_UPGRADE",
        ],
        "recorded_at": recorded_at,
        "review_summary_file": "review-summary.json",
        "review_summary_sha256": _digest(review_summary_bytes),
        "schema_version": "fire-m4-calibration-silver-manifest.v1",
        "source_candidate_sha256": source_candidate_sha256,
        "source_review_packet_sha256": source_review_packet_sha256,
        "status": "FROZEN_FOR_CALIBRATION",
    }
    manifest_bytes = canonical_json_bytes(manifest)
    preflight = {
        **common,
        "accepted_count": 8,
        "authorization_sha256": _digest(authorization_bytes),
        "checks": [
            "SOURCE_CANDIDATE_BYTES_REPLAYED",
            "ALL_EIGHT_CODEX_DECISIONS_RECORDED",
            "SILVER_AUTHORIZATIONS_SOURCE_BOUND",
            "NON_GOLD_POLICY_FIXED",
            "CALIBRATION_EXECUTION_ONLY",
        ],
        "execution_count": 8,
        "finding_counts": {},
        "schema_version": "fire-m4-calibration-silver-preflight.v1",
        "source_candidate_sha256": source_candidate_sha256,
        "status": "PASS",
    }
    return {
        "manifest.json": manifest_bytes,
        "preflight-report.json": canonical_json_bytes(preflight),
        "review-summary.json": review_summary_bytes,
        "silver-authorizations.json": authorization_bytes,
    }


def validate_staging(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    output_path = Path(output_dir)
    try:
        entries = tuple(output_path.iterdir())
        if (
            {path.name for path in entries} != OUTPUT_FILES
            or stat.S_IMODE(output_path.stat().st_mode) != 0o700
            or any(
                path.is_symlink()
                or not path.is_file()
                or stat.S_IMODE(path.stat().st_mode) != 0o600
                for path in entries
            )
        ):
            raise M4SilverDataError("SILVER_STAGING_FILES_INVALID")
        manifest = json.loads((output_path / "manifest.json").read_text())
        expected = build_artifacts(manifest["recorded_at"])
        if any((output_path / name).read_bytes() != payload for name, payload in expected.items()):
            raise M4SilverDataError("SILVER_STAGING_DIGEST_MISMATCH")
        payload = json.loads(
            (output_path / "silver-authorizations.json").read_text()
        )
        contexts = {
            context.reviewed.plan_unit_ref: context
            for context in CALIBRATION_PREP.load_calibration_execution_contexts()
        }
        for item in payload["items"]:
            context = contexts[item["plan_unit_ref"]]
            ScenarioCapabilitySilverAuthorization.from_dict(
                item["authorization"],
                context.reviewed,
                context.plan,
                context.tree,
            )
        report = json.loads((output_path / "preflight-report.json").read_text())
    except M4SilverDataError:
        raise
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4SilverDataError("SILVER_STAGING_INVALID") from None
    return report


def prepare(recorded_at: str, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    output_path = Path(output_dir)
    temporary_path: Path | None = None
    try:
        output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if output_path.exists() or output_path.is_symlink():
            raise M4SilverDataError("SILVER_STAGING_ALREADY_EXISTS")
        temporary_path = output_path.parent / (
            f".{output_path.name}.treeguard-{secrets.token_hex(12)}.tmp"
        )
        temporary_path.mkdir(mode=0o700, exist_ok=False)
        os.chmod(temporary_path, 0o700)
        for name, payload in build_artifacts(recorded_at).items():
            if not write_private_json(
                temporary_path / name,
                json.loads(payload.decode("utf-8")),
            ):
                raise M4SilverDataError("SILVER_STAGING_WRITE_FAILED")
        report = validate_staging(temporary_path)
        os.rename(temporary_path, output_path)
        temporary_path = None
        return report
    except M4SilverDataError:
        raise
    except OSError:
        raise M4SilverDataError("SILVER_STAGING_WRITE_FAILED") from None
    finally:
        if temporary_path is not None:
            try:
                shutil.rmtree(temporary_path)
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--recorded-at")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.check:
            report = validate_staging(args.output_dir)
        else:
            if not args.recorded_at:
                raise M4SilverDataError("SILVER_RECORDED_AT_REQUIRED")
            report = prepare(args.recorded_at, args.output_dir)
    except M4SilverDataError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "accepted_count": report["accepted_count"],
                "execution_count": report["execution_count"],
                "quality_tier": report["quality_tier"],
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
