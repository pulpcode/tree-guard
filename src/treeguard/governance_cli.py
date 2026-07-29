"""File-only CLI for change-intent drafting, confirmation, and retrieval."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from treeguard.adapter import TreeFormatError, adapt_tree_document
from treeguard.ai_review import (
    INTENT_PROMPT_VERSION,
    BailianConfig,
    BailianIntentDraftProvider,
    BailianProviderError,
)
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentConfirmation,
    IntentRequest,
    IntentReviewAction,
    IntentValidationError,
    apply_intent_review,
)
from treeguard.json_utils import StrictJSONError
from treeguard.private_io import (
    preflight_private_output,
    read_private_json,
    write_private_json,
)
from treeguard.retrieval import (
    DEFAULT_MAX_CANDIDATES,
    CandidateRetrievalError,
    build_candidate_set,
)


_MAX_TREE_BYTES = 64_000_000
_MAX_REQUEST_BYTES = 64_000
_MAX_MODEL_OUTPUT_BYTES = 2_000_000
_MAX_ARTIFACT_BYTES = 16_000_000
_MODEL_PREFLIGHT_ERROR_CODES = {
    "BAILIAN_API_KEY_INVALID",
    "BAILIAN_API_KEY_MISSING",
    "BAILIAN_ATTEMPTS_INVALID",
    "BAILIAN_BASE_URL_INVALID",
    "BAILIAN_ENV_FILE_INVALID",
    "BAILIAN_ENV_FILE_UNSAFE",
    "BAILIAN_MODEL_INVALID",
    "BAILIAN_REQUEST_INVALID",
    "BAILIAN_TIMEOUT_INVALID",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard-governance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft_parser = subparsers.add_parser(
        "draft",
        help="validate a model output file or call Bailian to draft one intent",
    )
    draft_parser.add_argument("tree_file", type=Path)
    draft_parser.add_argument("request_file", type=Path)
    draft_source = draft_parser.add_mutually_exclusive_group(required=True)
    draft_source.add_argument("--model-output-file", type=Path)
    draft_source.add_argument("--live", action="store_true")
    draft_parser.add_argument(
        "--external-data-approved",
        action="store_true",
        help="confirm live inputs are fictional or explicitly approved for transfer",
    )
    draft_parser.add_argument("--internal-output", type=Path, required=True)

    confirm_parser = subparsers.add_parser(
        "confirm",
        help="apply one retrieval-only human review action",
    )
    _add_confirmation_sources(confirm_parser)
    confirm_parser.add_argument("--internal-output", type=Path, required=True)

    search_parser = subparsers.add_parser(
        "search",
        help="replay confirmation sources and retrieve full-tree candidates",
    )
    _add_confirmation_sources(search_parser)
    search_parser.add_argument("confirmation_file", type=Path)
    search_parser.add_argument(
        "--max-candidates",
        type=int,
        default=DEFAULT_MAX_CANDIDATES,
    )
    search_parser.add_argument("--internal-output", type=Path, required=True)
    return parser


def _add_confirmation_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("tree_file", type=Path)
    parser.add_argument("request_file", type=Path)
    parser.add_argument("draft_file", type=Path)
    parser.add_argument("action_file", type=Path)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (
        args.command == "draft"
        and args.live
        and not args.external_data_approved
    ):
        _print_error("EXTERNAL_DATA_APPROVAL_REQUIRED")
        return 2

    ai_called = False
    try:
        tree = _load_tree(args.tree_file)
        request = IntentRequest.from_dict(
            read_private_json(
                args.request_file,
                max_bytes=_MAX_REQUEST_BYTES,
            ),
            tree,
        )
        if args.command == "draft":
            _preflight_output(args.internal_output)
            if args.live:
                provider = BailianIntentDraftProvider(BailianConfig.from_env())
                try:
                    draft = provider.draft(request, tree)
                    ai_called = True
                except BailianProviderError as exc:
                    ai_called = exc.code not in _MODEL_PREFLIGHT_ERROR_CODES
                    raise
                ai_report = {
                    "called": True,
                    "status": "COMPLETED",
                    "provider": provider.provider_name,
                    "capability": provider.capability,
                    "model": provider.config.model,
                }
            else:
                assert args.model_output_file is not None
                draft = ChangeIntentDraft.from_model_dict(
                    read_private_json(
                        args.model_output_file,
                        max_bytes=_MAX_MODEL_OUTPUT_BYTES,
                    ),
                    request,
                    tree,
                    model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                    model_capability="JSON_OBJECT",
                    model_name="unverified-file",
                    prompt_version=INTENT_PROMPT_VERSION,
                )
                ai_report = {
                    "called": False,
                    "status": "MODEL_OUTPUT_FILE_VALIDATED",
                }
            if not write_private_json(args.internal_output, draft.to_dict()):
                _print_error(
                    "INTERNAL_OUTPUT_WRITE_FAILED",
                    ai_called=ai_called,
                )
                return 2
            print(
                json.dumps(
                    {
                        "report_version": "governance-intake-aggregate.v1",
                        "valid": True,
                        "operation": "DRAFT",
                        "status": draft.review_status,
                        "ai": ai_report,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        draft = ChangeIntentDraft.from_dict(
            read_private_json(
                args.draft_file,
                max_bytes=_MAX_ARTIFACT_BYTES,
            ),
            request,
            tree,
        )
        action = IntentReviewAction.from_dict(
            read_private_json(
                args.action_file,
                max_bytes=_MAX_REQUEST_BYTES,
            )
        )
        if args.command == "confirm":
            confirmation = apply_intent_review(request, draft, action, tree)
            _preflight_output(args.internal_output)
            if not write_private_json(
                args.internal_output,
                confirmation.to_dict(),
            ):
                _print_error("INTERNAL_OUTPUT_WRITE_FAILED")
                return 2
            print(
                json.dumps(
                    {
                        "report_version": "governance-intake-aggregate.v1",
                        "valid": True,
                        "operation": "CONFIRM",
                        "status": confirmation.status,
                        "semantic_approval": False,
                        "patch_eligible": False,
                        "ai": {"called": False, "status": "NOT_CALLED"},
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        confirmation = IntentConfirmation.from_dict(
            read_private_json(
                args.confirmation_file,
                max_bytes=_MAX_ARTIFACT_BYTES,
            ),
            request,
            draft,
            action,
            tree,
        )
        candidate_set = build_candidate_set(
            confirmation,
            tree,
            max_candidates=args.max_candidates,
        )
        _preflight_output(args.internal_output)
        if not write_private_json(
            args.internal_output,
            candidate_set.to_dict(),
        ):
            _print_error("INTERNAL_OUTPUT_WRITE_FAILED")
            return 2
        report = candidate_set.aggregate_report()
        report["operation"] = "SEARCH"
        report["ai"] = {"called": False, "status": "NOT_CALLED"}
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except BailianProviderError as exc:
        if exc.code in _MODEL_PREFLIGHT_ERROR_CODES:
            _print_error(exc.code)
            return 2
        _print_error(exc.code, ai_called=ai_called)
        return 3
    except (IntentValidationError, CandidateRetrievalError) as exc:
        _print_error(exc.code)
        return 2
    except TreeFormatError:
        _print_error("TREE_FORMAT_ERROR")
        return 2
    except (
        StrictJSONError,
        OSError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ):
        _print_error("GOVERNANCE_INPUT_INVALID")
        return 2


def _load_tree(path: Path):
    document = read_private_json(path, max_bytes=_MAX_TREE_BYTES)
    result = adapt_tree_document(document)
    if not result.is_valid or result.tree is None:
        raise IntentValidationError(
            "TREE_CONFORMANCE_ERROR",
            "tree input failed canonical conformance",
        )
    return result.tree


def _preflight_output(path: Path) -> None:
    try:
        preflight_private_output(path)
    except OSError:
        raise IntentValidationError(
            "INTERNAL_OUTPUT_WRITE_FAILED",
            "private output cannot be created safely",
        ) from None


def _print_error(code: str, *, ai_called: bool = False) -> None:
    print(
        json.dumps(
            {
                "report_version": "governance-intake-aggregate.v1",
                "valid": False,
                "status": "REJECTED",
                "error_code": code,
                "ai": {
                    "called": ai_called,
                    "status": "ABSTAIN" if ai_called else "NOT_CALLED",
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
