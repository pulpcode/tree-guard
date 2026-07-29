"""File-only CLI for intent, retrieval, semantic advice, and human review."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from treeguard.adapter import TreeFormatError, adapt_tree_document
from treeguard.ai_review import (
    INTENT_PROMPT_VERSION,
    INTENT_CLARIFICATION_PROMPT_VERSION,
    SEMANTIC_PROMPT_VERSION,
    BailianConfig,
    BailianIntentDraftProvider,
    BailianProviderError,
    BailianSemanticRecommendationProvider,
)
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentClarificationAnswer,
    IntentClarificationRound,
    IntentConfirmation,
    IntentRequest,
    IntentReviewAction,
    IntentValidationError,
    apply_intent_review,
    reviewable_intent_draft_from_dict,
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
    CandidateSet,
    build_candidate_set,
)
from treeguard.semantic_recommendation import (
    RecommendationRecord,
    RecommendationReviewAction,
    SemanticRecommendationDraft,
    SemanticRecommendationError,
    apply_recommendation_review,
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

    clarify_parser = subparsers.add_parser(
        "clarify",
        help="apply one answer and recompile an intent exactly once",
    )
    clarify_parser.add_argument("tree_file", type=Path)
    clarify_parser.add_argument("request_file", type=Path)
    clarify_parser.add_argument("initial_draft_file", type=Path)
    clarify_parser.add_argument("answer_file", type=Path)
    clarify_source = clarify_parser.add_mutually_exclusive_group(required=True)
    clarify_source.add_argument("--model-output-file", type=Path)
    clarify_source.add_argument("--live", action="store_true")
    clarify_parser.add_argument(
        "--external-data-approved",
        action="store_true",
        help="confirm live inputs are fictional or explicitly approved for transfer",
    )
    clarify_parser.add_argument("--internal-output", type=Path, required=True)

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

    recommend_parser = subparsers.add_parser(
        "recommend",
        help="validate a semantic model output or call Bailian on Top-8 candidates",
    )
    _add_semantic_sources(recommend_parser)
    recommend_source = recommend_parser.add_mutually_exclusive_group(
        required=True
    )
    recommend_source.add_argument("--model-output-file", type=Path)
    recommend_source.add_argument("--live", action="store_true")
    recommend_parser.add_argument(
        "--external-data-approved",
        action="store_true",
        help="confirm live inputs are fictional or explicitly approved for transfer",
    )
    recommend_parser.add_argument("--internal-output", type=Path, required=True)

    review_parser = subparsers.add_parser(
        "review-recommendation",
        help="confirm, revise, or reject one semantic recommendation",
    )
    _add_semantic_sources(review_parser)
    review_parser.add_argument("recommendation_draft_file", type=Path)
    review_parser.add_argument("recommendation_action_file", type=Path)
    review_parser.add_argument("--internal-output", type=Path, required=True)

    replay_parser = subparsers.add_parser(
        "replay-recommendation",
        help="replay one recommendation record from all trusted file sources",
    )
    _add_semantic_sources(replay_parser)
    replay_parser.add_argument("recommendation_draft_file", type=Path)
    replay_parser.add_argument("recommendation_action_file", type=Path)
    replay_parser.add_argument("recommendation_record_file", type=Path)
    return parser


def _add_confirmation_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("tree_file", type=Path)
    parser.add_argument("request_file", type=Path)
    parser.add_argument("draft_file", type=Path)
    parser.add_argument("action_file", type=Path)


def _add_semantic_sources(parser: argparse.ArgumentParser) -> None:
    _add_confirmation_sources(parser)
    parser.add_argument("confirmation_file", type=Path)
    parser.add_argument("candidate_file", type=Path)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (
        args.command in {"draft", "clarify", "recommend"}
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

        if args.command == "clarify":
            initial_draft = ChangeIntentDraft.from_dict(
                read_private_json(
                    args.initial_draft_file,
                    max_bytes=_MAX_ARTIFACT_BYTES,
                ),
                request,
                tree,
            )
            answer = IntentClarificationAnswer.from_dict(
                read_private_json(
                    args.answer_file,
                    max_bytes=_MAX_REQUEST_BYTES,
                )
            )
            _preflight_output(args.internal_output)
            if args.live:
                provider = BailianIntentDraftProvider(
                    BailianConfig.from_env()
                )
                try:
                    clarification_round = provider.clarify(
                        request,
                        initial_draft,
                        answer,
                        tree,
                    )
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
                clarification_round = (
                    IntentClarificationRound.from_model_dict(
                        read_private_json(
                            args.model_output_file,
                            max_bytes=_MAX_MODEL_OUTPUT_BYTES,
                        ),
                        request,
                        initial_draft,
                        answer,
                        tree,
                        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                        model_capability="JSON_OBJECT",
                        model_name="unverified-file",
                        prompt_version=(
                            INTENT_CLARIFICATION_PROMPT_VERSION
                        ),
                    )
                )
                ai_report = {
                    "called": False,
                    "status": "MODEL_OUTPUT_FILE_VALIDATED",
                }
            if not write_private_json(
                args.internal_output,
                clarification_round.to_dict(),
            ):
                _print_error(
                    "INTERNAL_OUTPUT_WRITE_FAILED",
                    ai_called=ai_called,
                )
                return 2
            print(
                json.dumps(
                    {
                        "report_version": (
                            "governance-intake-aggregate.v1"
                        ),
                        "valid": True,
                        "operation": "CLARIFY",
                        "status": clarification_round.review_status,
                        "clarification_round": 1,
                        "ai": ai_report,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        draft = reviewable_intent_draft_from_dict(
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
        if args.command != "search":
            candidate_set = CandidateSet.from_dict(
                read_private_json(
                    args.candidate_file,
                    max_bytes=_MAX_ARTIFACT_BYTES,
                ),
                confirmation,
                tree,
            )
            if args.command == "recommend":
                _preflight_output(args.internal_output)
                if args.live:
                    provider = BailianSemanticRecommendationProvider(
                        BailianConfig.from_env()
                    )
                    try:
                        recommendation_draft = provider.recommend(
                            confirmation,
                            candidate_set,
                            tree,
                        )
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
                    recommendation_draft = (
                        SemanticRecommendationDraft.from_model_dict(
                            read_private_json(
                                args.model_output_file,
                                max_bytes=_MAX_MODEL_OUTPUT_BYTES,
                            ),
                            confirmation,
                            candidate_set,
                            tree,
                            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                            model_capability="JSON_OBJECT",
                            model_name="unverified-file",
                            prompt_version=SEMANTIC_PROMPT_VERSION,
                        )
                    )
                    ai_report = {
                        "called": False,
                        "status": "MODEL_OUTPUT_FILE_VALIDATED",
                    }
                if not write_private_json(
                    args.internal_output,
                    recommendation_draft.to_dict(),
                ):
                    _print_error(
                        "INTERNAL_OUTPUT_WRITE_FAILED",
                        ai_called=ai_called,
                    )
                    return 2
                print(
                    json.dumps(
                        {
                            "report_version": (
                                "governance-semantic-aggregate.v1"
                            ),
                            "valid": True,
                            "operation": "RECOMMEND",
                            "status": "READY_FOR_HUMAN_REVIEW",
                            "recommended_action": (
                                recommendation_draft.recommended_action
                            ),
                            "semantic_approval": False,
                            "patch_eligible": False,
                            "ai": ai_report,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                return 0

            recommendation_draft = SemanticRecommendationDraft.from_dict(
                read_private_json(
                    args.recommendation_draft_file,
                    max_bytes=_MAX_ARTIFACT_BYTES,
                ),
                confirmation,
                candidate_set,
                tree,
            )
            recommendation_action = RecommendationReviewAction.from_dict(
                read_private_json(
                    args.recommendation_action_file,
                    max_bytes=_MAX_ARTIFACT_BYTES,
                ),
                confirmation,
                candidate_set,
                tree,
            )
            if args.command == "review-recommendation":
                record = apply_recommendation_review(
                    recommendation_draft,
                    recommendation_action,
                    confirmation,
                    candidate_set,
                    tree,
                )
                _preflight_output(args.internal_output)
                if not write_private_json(
                    args.internal_output,
                    record.to_dict(),
                ):
                    _print_error("INTERNAL_OUTPUT_WRITE_FAILED")
                    return 2
                report = record.aggregate_report()
                report["operation"] = "REVIEW_RECOMMENDATION"
                report["ai"] = {"called": False, "status": "NOT_CALLED"}
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
                return 0

            record = RecommendationRecord.from_dict(
                read_private_json(
                    args.recommendation_record_file,
                    max_bytes=_MAX_ARTIFACT_BYTES,
                ),
                recommendation_draft,
                recommendation_action,
                confirmation,
                candidate_set,
                tree,
            )
            report = record.aggregate_report()
            report["operation"] = "REPLAY_RECOMMENDATION"
            report["ai"] = {"called": False, "status": "NOT_CALLED"}
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return 0

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
    except (
        IntentValidationError,
        CandidateRetrievalError,
        SemanticRecommendationError,
    ) as exc:
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
