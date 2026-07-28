"""File-only CLI for atomic expert-review actions and deterministic replay."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from treeguard.adapter import TreeFormatError, adapt_tree_document
from treeguard.ai_cli import _write_internal_output
from treeguard.ai_review import (
    AIReviewDraft,
    AIReviewValidationError,
    BailianConfig,
    BailianProviderError,
)
from treeguard.business_review import (
    BusinessVersionReviewError,
    mine_business_version_pair,
)
from treeguard.evidence import (
    EvidenceProjectionError,
    build_business_review_evidence_pack,
)
from treeguard.expert_review import (
    DOMAIN_EXPERT,
    SCHEMA_STEWARD,
    EXPERT_FINAL_DECISION_RECORDED,
    EXPERT_STATUS_RECORDED,
    EXPERT_THOUGHT_SUBMITTED,
    ExpertReviewError,
    ExpertReviewSession,
    open_expert_review_session,
    record_ai_synthesis,
    record_expert_final_decision,
    record_expert_status,
    submit_expert_thought,
)
from treeguard.expert_synthesis import (
    BailianExpertSynthesisProvider,
    ExpertSynthesisValidationError,
    PROMPT_VERSION as EXPERT_SYNTHESIS_PROMPT_VERSION,
)
from treeguard.hashing import canonical_digest
from treeguard.json_utils import (
    StrictJSONError,
    strict_json_loads,
)


ACTION_SCHEMA_VERSION = "expert-review-action.v1"
_ACTION_KEYS = {
    "schema_version",
    "action_id",
    "case_id",
    "expected_session_hash",
    "action_type",
    "actor_role",
    "actor_ref",
    "recorded_at",
    "payload",
}
_THOUGHT_ACTION_KEYS = {"raw_text", "evidence_refs"}
_STATUS_ACTION_KEYS = {
    "target_state",
    "rationale",
    "evidence_refs",
    "proposed_disposition",
}
_FINAL_ACTION_KEYS = {
    "target_state",
    "final_disposition",
    "rationale",
    "evidence_refs",
    "ai_draft_relation",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
_EXTERNAL_APPROVAL_KEYS = {
    "schema_version",
    "approval_status",
    "approval_payload_hash",
    "provider",
    "endpoint",
    "model",
    "prompt_version",
    "approved_by",
    "approved_at",
    "identity_status",
}
_MAX_ACTION_BYTES = 64_000
_MAX_INTERNAL_INPUT_BYTES = 16_000_000
_MAX_TREE_INPUT_BYTES = 64_000_000
_MODEL_PREFLIGHT_ERROR_CODES = {
    "BAILIAN_API_KEY_INVALID",
    "BAILIAN_API_KEY_MISSING",
    "BAILIAN_ATTEMPTS_INVALID",
    "BAILIAN_BASE_URL_INVALID",
    "BAILIAN_ENV_FILE_INVALID",
    "BAILIAN_ENV_FILE_UNSAFE",
    "BAILIAN_MODEL_INVALID",
    "BAILIAN_TIMEOUT_INVALID",
    "EXPERT_SYNTHESIS_CONTEXT_BUDGET_EXCEEDED",
    "EXPERT_SYNTHESIS_DIGEST_INVALID",
    "EXPERT_SYNTHESIS_SOURCE_INVALID",
    "EXPERT_SYNTHESIS_THOUGHTS_INVALID",
    "EXTERNAL_EXPERT_PAYLOAD_APPROVAL_REQUIRED",
}


class _ModelAttemptError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("external model call failed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard-expert-review")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser(
        "apply",
        help="append one expert action and write a new immutable session file",
    )
    _add_source_arguments(apply_parser)
    apply_parser.add_argument("action_file", type=Path)
    apply_parser.add_argument("--session-input", type=Path)
    apply_parser.add_argument("--internal-output", type=Path, required=True)
    apply_parser.add_argument(
        "--live-synthesis",
        action="store_true",
        help="call Bailian after a thought action",
    )
    apply_parser.add_argument(
        "--external-data-approved",
        action="store_true",
        help="approve the selected fictional or desensitized tree/AI payload",
    )
    apply_parser.add_argument(
        "--external-approval-file",
        type=Path,
        help="private APPROVED manifest derived from prepare-approval output",
    )

    approval_parser = subparsers.add_parser(
        "prepare-approval",
        help="compute the exact external request-plan hash without calling a model",
    )
    _add_source_arguments(approval_parser)
    approval_parser.add_argument("action_file", type=Path)
    approval_parser.add_argument("--session-input", type=Path)
    approval_parser.add_argument("--internal-output", type=Path, required=True)

    replay_parser = subparsers.add_parser(
        "replay",
        help="verify an existing session without any model or network call",
    )
    _add_source_arguments(replay_parser)
    replay_parser.add_argument("session_file", type=Path)
    return parser


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("base_file", help="older business-version tree export")
    parser.add_argument("target_file", help="newer business-version tree export")
    parser.add_argument("ai_bundle_file", type=Path)
    parser.add_argument("--base-position", type=int, default=0)
    parser.add_argument("--target-position", type=int, default=1)
    parser.add_argument("--case-index", type=int, default=0)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "apply" and args.live_synthesis:
        if not args.external_data_approved:
            _print_error("EXTERNAL_DATA_APPROVAL_REQUIRED")
            return 2
        if args.external_approval_file is None:
            _print_error("EXTERNAL_EXPERT_PAYLOAD_APPROVAL_REQUIRED")
            return 2
    try:
        evidence_pack, ai_review_draft = _load_sources(args)
        if args.command == "replay":
            stored_session = _read_json_file(
                args.session_file,
                max_bytes=_MAX_INTERNAL_INPUT_BYTES,
            )
            session = ExpertReviewSession.from_dict(
                stored_session,
                evidence_pack,
                ai_review_draft,
            )
            report = session.aggregate_report()
            report["operation"] = "REPLAY"
            report["ai"] = {"called": False, "status": "NOT_CALLED"}
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return 0

        action = _read_json_file(
            args.action_file,
            max_bytes=_MAX_ACTION_BYTES,
        )
        action = _parse_action(action)
        if args.command == "prepare-approval":
            if action["action_type"] != EXPERT_THOUGHT_SUBMITTED:
                raise ExpertReviewError(
                    "EXTERNAL_APPROVAL_ACTION_INVALID",
                    "external approval can only be prepared for a thought action",
                )
            session = _load_or_open_session(
                args,
                action,
                evidence_pack,
                ai_review_draft,
            )
            session = _apply_thought(
                session,
                action,
                evidence_pack,
                ai_review_draft,
            )
            thought_event = session.events[-1]
            provider = BailianExpertSynthesisProvider(
                _approval_preparation_config()
            )
            approval_hash = provider.approval_payload_hash(
                evidence_pack,
                ai_review_draft,
                (
                    (
                        thought_event.payload["thought_ref"],
                        thought_event.payload["raw_text"],
                    ),
                ),
            )
            approval_manifest = {
                "schema_version": "external-expert-synthesis-approval.v1",
                "approval_status": "PENDING",
                "approval_payload_hash": approval_hash,
                "provider": provider.provider_name,
                "endpoint": (
                    provider.config.base_url.rstrip("/") + "/chat/completions"
                ),
                "model": provider.config.model,
                "prompt_version": EXPERT_SYNTHESIS_PROMPT_VERSION,
                "approved_by": None,
                "approved_at": None,
                "identity_status": "UNVERIFIED_FILE_ASSERTION",
            }
            if not _write_internal_output(
                args.internal_output,
                approval_manifest,
            ):
                _print_error("INTERNAL_OUTPUT_WRITE_FAILED")
                return 2
            print(
                json.dumps(
                    {
                        "report_version": "expert-review-aggregate.v1",
                        "valid": True,
                        "operation": "PREPARE_EXTERNAL_APPROVAL",
                        "status": "APPROVAL_REQUEST_WRITTEN",
                        "ai": {"called": False, "status": "NOT_CALLED"},
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if args.live_synthesis and (
            action["action_type"] != EXPERT_THOUGHT_SUBMITTED
        ):
            raise ExpertReviewError(
                "LIVE_SYNTHESIS_ACTION_INVALID",
                "live synthesis is only allowed for a thought action",
            )
        session = _load_or_open_session(
            args,
            action,
            evidence_pack,
            ai_review_draft,
        )
        external_approval = None
        if args.live_synthesis:
            _preflight_internal_output(args.internal_output)
            external_approval = _parse_external_approval_manifest(
                _read_json_file(
                    args.external_approval_file,
                    max_bytes=_MAX_ACTION_BYTES,
                ),
                require_approved=True,
            )

        session, ai_report = _apply_action(
            session,
            action,
            evidence_pack,
            ai_review_draft,
            live_synthesis=args.live_synthesis,
            external_approval=external_approval,
        )
        if not _write_internal_output(args.internal_output, session.to_dict()):
            _print_error(
                "INTERNAL_OUTPUT_WRITE_FAILED",
                ai_called=ai_report["called"],
            )
            return 2
        report = session.aggregate_report()
        report["operation"] = "APPLY"
        report["ai"] = ai_report
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except _ModelAttemptError as exc:
        _print_error(exc.code, ai_called=True)
        return 3
    except BailianProviderError as exc:
        ai_called = exc.code not in _MODEL_PREFLIGHT_ERROR_CODES
        _print_error(exc.code, ai_called=ai_called)
        return 3 if ai_called else 2
    except (
        AIReviewValidationError,
        BusinessVersionReviewError,
        EvidenceProjectionError,
        ExpertReviewError,
        ExpertSynthesisValidationError,
        TreeFormatError,
    ) as exc:
        _print_error(getattr(exc, "code", "EXPERT_REVIEW_REJECTED"))
        return 2
    except (
        StrictJSONError,
        OSError,
        RecursionError,
        TypeError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        _print_error("EXPERT_REVIEW_INPUT_INVALID")
        return 2


def _load_sources(args: argparse.Namespace):
    base_document = _read_json_file(
        Path(args.base_file),
        max_bytes=_MAX_TREE_INPUT_BYTES,
    )
    target_document = _read_json_file(
        Path(args.target_file),
        max_bytes=_MAX_TREE_INPUT_BYTES,
    )
    base_result = adapt_tree_document(base_document, source_hint=str(args.base_file))
    target_result = adapt_tree_document(
        target_document,
        source_hint=str(args.target_file),
    )
    if not base_result.is_valid or not target_result.is_valid:
        raise ExpertReviewError(
            "TREE_CONFORMANCE_ERROR",
            "expert review source tree failed conformance",
        )
    assert base_result.tree is not None
    assert target_result.tree is not None
    review_run = mine_business_version_pair(
        base_result.tree,
        target_result.tree,
        base_position=args.base_position,
        target_position=args.target_position,
    )
    evidence_pack = build_business_review_evidence_pack(
        review_run,
        base_result.tree,
        target_result.tree,
        case_index=args.case_index,
    )
    bundle = _read_json_file(
        args.ai_bundle_file,
        max_bytes=_MAX_INTERNAL_INPUT_BYTES,
    )
    if (
        not isinstance(bundle, dict)
        or not isinstance(bundle.get("ai_review_draft"), dict)
    ):
        raise ExpertReviewError(
            "AI_REVIEW_DRAFT_REQUIRED",
            "AI bundle must contain a non-null ai_review_draft",
        )
    ai_review_draft = AIReviewDraft.from_dict(
        bundle["ai_review_draft"],
        evidence_pack,
    )
    return evidence_pack, ai_review_draft


def _load_or_open_session(
    args: argparse.Namespace,
    action: dict[str, Any],
    evidence_pack,
    ai_review_draft,
):
    if action["case_id"] != evidence_pack.case_id:
        raise ExpertReviewError(
            "EXPERT_ACTION_CASE_MISMATCH",
            "expert action does not match the selected review case",
        )
    if args.session_input is None:
        if action["action_type"] != EXPERT_THOUGHT_SUBMITTED:
            raise ExpertReviewError(
                "EXPERT_SESSION_INITIAL_ACTION_INVALID",
                "a new expert review session must begin with a thought",
            )
        if action["expected_session_hash"] is not None:
            raise ExpertReviewError(
                "EXPERT_ACTION_SESSION_MISMATCH",
                "an initial expert action must use a null expected_session_hash",
            )
        return open_expert_review_session(
            evidence_pack,
            ai_review_draft,
            session_id=secrets.token_hex(32),
        )
    stored_session = _read_json_file(
        args.session_input,
        max_bytes=_MAX_INTERNAL_INPUT_BYTES,
    )
    session = ExpertReviewSession.from_dict(
        stored_session,
        evidence_pack,
        ai_review_draft,
    )
    if action["expected_session_hash"] != session.session_hash:
        raise ExpertReviewError(
            "EXPERT_SESSION_CONCURRENT_MODIFICATION",
            "expert action expected_session_hash is stale",
        )
    return session


def _parse_action(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _ACTION_KEYS:
        raise ExpertReviewError(
            "EXPERT_ACTION_FIELDS_INVALID",
            "expert action must use the exact contract fields",
        )
    if value["schema_version"] != ACTION_SCHEMA_VERSION:
        raise ExpertReviewError(
            "EXPERT_ACTION_SCHEMA_UNSUPPORTED",
            "expert action schema_version is unsupported",
        )
    if (
        not isinstance(value["action_id"], str)
        or _DIGEST.fullmatch(value["action_id"]) is None
        or not isinstance(value["case_id"], str)
        or _DIGEST.fullmatch(value["case_id"]) is None
        or (
            value["expected_session_hash"] is not None
            and (
                not isinstance(value["expected_session_hash"], str)
                or _DIGEST.fullmatch(value["expected_session_hash"]) is None
            )
        )
    ):
        raise ExpertReviewError(
            "EXPERT_ACTION_SOURCE_FIELDS_INVALID",
            "expert action source and idempotency fields are invalid",
        )
    action_type = value["action_type"]
    payload = value["payload"]
    if action_type == EXPERT_THOUGHT_SUBMITTED:
        expected_payload_keys = _THOUGHT_ACTION_KEYS
        allowed_roles = {DOMAIN_EXPERT, SCHEMA_STEWARD}
    elif action_type == EXPERT_STATUS_RECORDED:
        expected_payload_keys = _STATUS_ACTION_KEYS
        allowed_roles = {DOMAIN_EXPERT}
    elif action_type == EXPERT_FINAL_DECISION_RECORDED:
        expected_payload_keys = _FINAL_ACTION_KEYS
        allowed_roles = {DOMAIN_EXPERT}
    else:
        raise ExpertReviewError(
            "EXPERT_ACTION_TYPE_INVALID",
            "expert action type is unsupported",
        )
    if not isinstance(payload, dict) or set(payload) != expected_payload_keys:
        raise ExpertReviewError(
            "EXPERT_ACTION_PAYLOAD_INVALID",
            "expert action payload must use the exact fields for its type",
        )
    if (
        not isinstance(value["actor_role"], str)
        or value["actor_role"] not in allowed_roles
    ):
        raise ExpertReviewError(
            "EXPERT_ACTION_ACTOR_INVALID",
            "expert action actor role is not authorized for its type",
        )
    if not isinstance(value["actor_ref"], str) or not isinstance(
        value["recorded_at"], str
    ):
        raise ExpertReviewError(
            "EXPERT_ACTION_COMMON_FIELDS_INVALID",
            "expert action actor_ref and recorded_at must be strings",
        )
    return value


def _apply_action(
    session,
    action: dict[str, Any],
    evidence_pack,
    ai_review_draft,
    *,
    live_synthesis: bool,
    external_approval: dict[str, Any] | None,
):
    action_type = action["action_type"]
    payload = action["payload"]
    if action_type == EXPERT_THOUGHT_SUBMITTED:
        session = _apply_thought(
            session,
            action,
            evidence_pack,
            ai_review_draft,
        )
        if not live_synthesis:
            return session, {"called": False, "status": "NOT_CALLED"}
        thought_event = session.events[-1]
        if (
            session.state != "DELIBERATING"
            or any(
                event.event_type == "AI_SYNTHESIS_RECORDED"
                for event in session.events
            )
        ):
            raise ExpertReviewError(
                "EXPERT_SYNTHESIS_LIMIT_EXCEEDED",
                "this session cannot accept another AI synthesis",
            )
        if _parse_timestamp(thought_event.recorded_at) > datetime.now(
            timezone.utc
        ):
            raise ExpertReviewError(
                "EXPERT_ACTION_TIME_IN_FUTURE",
                "live synthesis refuses an expert action timestamp in the future",
            )
        provider = BailianExpertSynthesisProvider(BailianConfig.from_env())
        assert external_approval is not None
        expected_endpoint = (
            provider.config.base_url.rstrip("/") + "/chat/completions"
        )
        if (
            external_approval["provider"] != provider.provider_name
            or external_approval["endpoint"] != expected_endpoint
            or external_approval["model"] != provider.config.model
            or external_approval["prompt_version"]
            != EXPERT_SYNTHESIS_PROMPT_VERSION
        ):
            raise ExpertReviewError(
                "EXTERNAL_APPROVAL_SOURCE_MISMATCH",
                "external approval does not match the configured request plan",
            )
        thoughts = (
            (
                thought_event.payload["thought_ref"],
                thought_event.payload["raw_text"],
            ),
        )
        try:
            synthesis = provider.synthesize(
                evidence_pack,
                ai_review_draft,
                source_session_hash=session.session_hash,
                expert_thoughts=thoughts,
                approved_external_payload_hash=(
                    external_approval["approval_payload_hash"]
                ),
            )
            session = record_ai_synthesis(
                session,
                evidence_pack,
                ai_review_draft,
                action_id=canonical_digest(
                    {
                        "parent_action_id": action["action_id"],
                        "source_session_hash": session.session_hash,
                        "prompt_version": EXPERT_SYNTHESIS_PROMPT_VERSION,
                        "model": provider.config.model,
                        "event_type": "AI_SYNTHESIS_RECORDED",
                    }
                ),
                actor_ref="bailian-json-assistant",
                recorded_at=_system_timestamp(),
                provider=provider.provider_name,
                model=provider.config.model,
                prompt_version=EXPERT_SYNTHESIS_PROMPT_VERSION,
                external_approval=external_approval,
                synthesis_draft=synthesis,
            )
        except BailianProviderError as exc:
            if exc.code in _MODEL_PREFLIGHT_ERROR_CODES:
                raise
            raise _ModelAttemptError(exc.code) from None
        except ExpertReviewError as exc:
            raise _ModelAttemptError(exc.code) from None
        return session, {"called": True, "status": "COMPLETED"}
    if action_type == EXPERT_STATUS_RECORDED:
        session = record_expert_status(
            session,
            evidence_pack,
            ai_review_draft,
            action_id=action["action_id"],
            actor_ref=action["actor_ref"],
            recorded_at=action["recorded_at"],
            target_state=payload["target_state"],
            rationale=payload["rationale"],
            evidence_refs=_action_refs(payload["evidence_refs"]),
            proposed_disposition=payload["proposed_disposition"],
        )
    else:
        session = record_expert_final_decision(
            session,
            evidence_pack,
            ai_review_draft,
            action_id=action["action_id"],
            actor_ref=action["actor_ref"],
            recorded_at=action["recorded_at"],
            target_state=payload["target_state"],
            final_disposition=payload["final_disposition"],
            rationale=payload["rationale"],
            evidence_refs=_action_refs(payload["evidence_refs"]),
            ai_draft_relation=payload["ai_draft_relation"],
            expected_session_hash=action["expected_session_hash"],
        )
    return session, {"called": False, "status": "NOT_CALLED"}


def _apply_thought(
    session,
    action: dict[str, Any],
    evidence_pack,
    ai_review_draft,
):
    payload = action["payload"]
    return submit_expert_thought(
        session,
        evidence_pack,
        ai_review_draft,
        action_id=action["action_id"],
        actor_role=action["actor_role"],
        actor_ref=action["actor_ref"],
        recorded_at=action["recorded_at"],
        raw_text=payload["raw_text"],
        evidence_refs=_action_refs(payload["evidence_refs"]),
    )


def _approval_preparation_config() -> BailianConfig:
    return BailianConfig.from_env(
        api_key_override="treeguard-approval-preparation-token",
    )


def _parse_external_approval_manifest(
    value: Any,
    *,
    require_approved: bool,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _EXTERNAL_APPROVAL_KEYS:
        raise ExpertReviewError(
            "EXTERNAL_APPROVAL_FIELDS_INVALID",
            "external approval manifest must use the exact contract fields",
        )
    expected_status = "APPROVED" if require_approved else "PENDING"
    if (
        value["schema_version"]
        != "external-expert-synthesis-approval.v1"
        or value["approval_status"] != expected_status
        or value["identity_status"] != "UNVERIFIED_FILE_ASSERTION"
        or not isinstance(value["approval_payload_hash"], str)
        or _DIGEST.fullmatch(value["approval_payload_hash"]) is None
        or not isinstance(value["provider"], str)
        or not isinstance(value["endpoint"], str)
        or not value["endpoint"]
        or len(value["endpoint"]) > 512
        or not isinstance(value["model"], str)
        or not isinstance(value["prompt_version"], str)
    ):
        raise ExpertReviewError(
            "EXTERNAL_APPROVAL_STATUS_INVALID",
            "external approval manifest status or source fields are invalid",
        )
    for field_name, max_chars in (
        ("provider", 64),
        ("model", 128),
        ("prompt_version", 128),
    ):
        if (
            len(value[field_name]) > max_chars
            or _OPAQUE_IDENTIFIER.fullmatch(value[field_name]) is None
        ):
            raise ExpertReviewError(
                "EXTERNAL_APPROVAL_STATUS_INVALID",
                "external approval identifiers are invalid",
            )
    if require_approved:
        if (
            not isinstance(value["approved_by"], str)
            or _OPAQUE_IDENTIFIER.fullmatch(value["approved_by"]) is None
            or not isinstance(value["approved_at"], str)
        ):
            raise ExpertReviewError(
                "EXTERNAL_APPROVAL_STATUS_INVALID",
                "approved manifest requires an asserted approver and time",
            )
        try:
            approved_at = _parse_timestamp(value["approved_at"])
        except ValueError:
            raise ExpertReviewError(
                "EXTERNAL_APPROVAL_STATUS_INVALID",
                "external approval time is invalid",
            ) from None
        if approved_at > datetime.now(timezone.utc):
            raise ExpertReviewError(
                "EXTERNAL_APPROVAL_STATUS_INVALID",
                "external approval time cannot be in the future",
            )
    elif value["approved_by"] is not None or value["approved_at"] is not None:
        raise ExpertReviewError(
            "EXTERNAL_APPROVAL_STATUS_INVALID",
            "pending approval manifest cannot contain approval identity",
        )
    return value


def _system_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    if _RFC3339.fullmatch(value) is None:
        raise ValueError("timestamp is not strict RFC3339")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _preflight_internal_output(path: Path) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        pass
    except OSError:
        raise ExpertReviewError(
            "INTERNAL_OUTPUT_WRITE_FAILED",
            "internal output path cannot be inspected safely",
        ) from None
    else:
        raise ExpertReviewError(
            "INTERNAL_OUTPUT_WRITE_FAILED",
            "internal output path already exists",
        )

    probe = path.parent / (
        f".{path.name}.treeguard-preflight-{secrets.token_hex(8)}.tmp"
    )
    descriptor = -1
    try:
        descriptor = os.open(
            probe,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(descriptor)
        descriptor = -1
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise ExpertReviewError(
            "INTERNAL_OUTPUT_WRITE_FAILED",
            "internal output directory is not writable",
        ) from None
    finally:
        try:
            os.unlink(probe)
        except OSError:
            pass


def _action_refs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ExpertReviewError(
            "EXPERT_ACTION_REFS_INVALID",
            "expert action evidence_refs must be an array",
        )
    return tuple(value)


def _read_json_file(path: Path, *, max_bytes: int) -> Any:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size > max_bytes
            or file_stat.st_mode & 0o077
        ):
            raise OSError("input is not a bounded regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise OSError("input exceeds its size limit")
        return strict_json_loads(raw.decode("utf-8"))
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _print_error(code: str, *, ai_called: bool = False) -> None:
    print(
        json.dumps(
            {
                "report_version": "expert-review-aggregate.v1",
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
