"""Internal-only smoke CLI for one AI-assisted business-version review case."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from treeguard.adapter import TreeFormatError, load_tree_export
from treeguard.ai_review import (
    BailianAIReviewProvider,
    BailianConfig,
    BailianProviderError,
    PROMPT_VERSION,
)
from treeguard.business_review import (
    BusinessVersionReviewError,
    mine_business_version_pair,
)
from treeguard.evidence import (
    EvidenceProjectionError,
    build_business_review_evidence_pack,
)
from treeguard.private_io import write_private_json

_MODEL_PREFLIGHT_ERROR_CODES = {
    "BAILIAN_API_KEY_INVALID",
    "BAILIAN_API_KEY_MISSING",
    "BAILIAN_ATTEMPTS_INVALID",
    "BAILIAN_BASE_URL_INVALID",
    "BAILIAN_ENV_FILE_INVALID",
    "BAILIAN_ENV_FILE_UNSAFE",
    "BAILIAN_MODEL_INVALID",
    "BAILIAN_TIMEOUT_INVALID",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard-ai-review")
    parser.add_argument("base_file", help="older business-version tree export")
    parser.add_argument("target_file", help="newer business-version tree export")
    parser.add_argument("--base-position", type=int, default=0)
    parser.add_argument("--target-position", type=int, default=1)
    parser.add_argument("--case-index", type=int, default=0)
    parser.add_argument(
        "--live",
        action="store_true",
        help="call Bailian; use fictional or explicitly approved desensitized data only",
    )
    parser.add_argument(
        "--external-data-approved",
        action="store_true",
        help="confirm the selected files are fictional or approved for external transfer",
    )
    parser.add_argument(
        "--internal-output",
        type=Path,
        help="write sensitive full artifacts to an explicitly approved internal path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.live and not args.external_data_approved:
        _print_error("EXTERNAL_DATA_APPROVAL_REQUIRED")
        return 2
    try:
        base_result = load_tree_export(args.base_file)
        target_result = load_tree_export(args.target_file)
    except TreeFormatError:
        _print_error("TREE_FORMAT_ERROR")
        return 2
    if not base_result.is_valid or not target_result.is_valid:
        _print_error("TREE_CONFORMANCE_ERROR")
        return 2
    assert base_result.tree is not None
    assert target_result.tree is not None

    try:
        review_run = mine_business_version_pair(
            base_result.tree,
            target_result.tree,
            base_position=args.base_position,
            target_position=args.target_position,
        )
    except (BusinessVersionReviewError, ValueError) as exc:
        _print_error(getattr(exc, "code", "BUSINESS_REVIEW_ERROR"))
        return 2

    if not review_run.review_cases:
        if args.internal_output is not None and not write_private_json(
            args.internal_output,
            {
                "review": review_run.to_dict(),
                "evidence_pack": None,
                "ai_review_draft": None,
                "model_call": None,
            },
        ):
            _print_error("INTERNAL_OUTPUT_WRITE_FAILED")
            return 2
        report = {
            "report_version": "ai-review-smoke.v1",
            "valid": True,
            "status": "NO_REVIEW_CASE",
            "review": review_run.aggregate_report(),
            "ai": {"called": False, "status": "NOT_CALLED"},
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0

    try:
        evidence_pack = build_business_review_evidence_pack(
            review_run,
            base_result.tree,
            target_result.tree,
            case_index=args.case_index,
        )
    except EvidenceProjectionError as exc:
        _print_error(exc.code)
        return 2

    draft = None
    model_call = None
    ai_report = {
        "called": False,
        "status": "NOT_CALLED",
    }
    if args.live:
        provider = None
        try:
            provider = BailianAIReviewProvider(BailianConfig.from_env())
            draft = provider.review(evidence_pack)
            model_call = {
                "provider": provider.provider_name,
                "capability": provider.capability,
                "model": provider.config.model,
                "prompt_version": PROMPT_VERSION,
                "status": "COMPLETED",
            }
            ai_report = {
                "called": True,
                "status": "COMPLETED",
                "provider": provider.provider_name,
                "capability": provider.capability,
                "model": provider.config.model,
                "suggested_disposition": draft.suggested_disposition,
            }
        except BailianProviderError as exc:
            if exc.code in _MODEL_PREFLIGHT_ERROR_CODES:
                _print_error(exc.code)
                return 2
            model_call = {
                "provider": "BAILIAN_OPENAI_COMPATIBLE",
                "capability": "JSON_OBJECT",
                "model": (
                    provider.config.model if provider is not None else None
                ),
                "prompt_version": PROMPT_VERSION,
                "status": "ABSTAIN",
                "error_code": exc.code,
            }
            ai_report = {
                "called": True,
                "status": "ABSTAIN",
                "error_code": exc.code,
            }

    if args.internal_output is not None:
        internal_payload = {
            "review": review_run.to_dict(),
            "evidence_pack": evidence_pack.to_dict(),
            "ai_review_draft": draft.to_dict() if draft is not None else None,
            "model_call": model_call,
        }
        if not write_private_json(args.internal_output, internal_payload):
            _print_error("INTERNAL_OUTPUT_WRITE_FAILED")
            return 2

    report = {
        "report_version": "ai-review-smoke.v1",
        "valid": ai_report["status"] != "ABSTAIN",
        "status": (
            "AI_REVIEW_COMPLETED"
            if draft is not None
            else (
                "AI_REVIEW_ABSTAIN"
                if ai_report["status"] == "ABSTAIN"
                else "EVIDENCE_PACK_READY"
            )
        ),
        "review": review_run.aggregate_report(),
        "evidence": {
            "focus_node_count": len(evidence_pack.focus_nodes),
            "context_node_count": len(evidence_pack.context_nodes),
            "candidate_node_count": len(evidence_pack.candidate_nodes),
            "gate_status": evidence_pack.gate_status,
        },
        "ai": ai_report,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 3


def _print_error(code: str) -> None:
    print(
        json.dumps(
            {
                "report_version": "ai-review-smoke.v1",
                "valid": False,
                "status": "REJECTED",
                "error_code": code,
                "ai": {
                    "called": False,
                    "status": "NOT_CALLED",
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
