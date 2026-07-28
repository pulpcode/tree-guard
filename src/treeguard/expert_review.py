"""Append-only, source-bound expert review sessions with deterministic replay."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from treeguard.ai_review import (
    AIReviewDraft,
    AIReviewValidationError,
    DISPOSITIONS,
)
from treeguard.evidence import LLMEvidencePack
from treeguard.expert_synthesis import (
    ExpertSynthesisDraft,
    ExpertSynthesisValidationError,
    expected_bailian_approval_payload_hash,
)
from treeguard.hashing import canonical_digest
from treeguard.models import freeze_json, thaw_json


SCHEMA_VERSION = "expert-review-session.v1"
WORKFLOW_VERSION = "treeguard.expert-review-workflow.v1"
REVIEW_MODE = "ASSISTED"
ACTOR_IDENTITY_STATUS = "UNVERIFIED_FILE_ASSERTION"
INITIAL_AI_PROVENANCE_STATUS = "UNVERIFIED_FILE_BUNDLE"

OPEN = "OPEN"
DELIBERATING = "DELIBERATING"
NEED_EVIDENCE = "NEED_EVIDENCE"
PROVISIONAL = "PROVISIONAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
STATES = {
    OPEN,
    DELIBERATING,
    NEED_EVIDENCE,
    PROVISIONAL,
    APPROVED,
    REJECTED,
}
TERMINAL_STATES = {APPROVED, REJECTED}

EXPERT_THOUGHT_SUBMITTED = "EXPERT_THOUGHT_SUBMITTED"
AI_SYNTHESIS_RECORDED = "AI_SYNTHESIS_RECORDED"
EXPERT_STATUS_RECORDED = "EXPERT_STATUS_RECORDED"
EXPERT_FINAL_DECISION_RECORDED = "EXPERT_FINAL_DECISION_RECORDED"
EVENT_TYPES = {
    EXPERT_THOUGHT_SUBMITTED,
    AI_SYNTHESIS_RECORDED,
    EXPERT_STATUS_RECORDED,
    EXPERT_FINAL_DECISION_RECORDED,
}

DOMAIN_EXPERT = "DOMAIN_EXPERT"
SCHEMA_STEWARD = "SCHEMA_STEWARD"
AI_ASSISTANT = "AI_ASSISTANT"
ACTOR_ROLES = {DOMAIN_EXPERT, SCHEMA_STEWARD, AI_ASSISTANT}

FINAL_DISPOSITIONS = frozenset(DISPOSITIONS - {"NEED_EVIDENCE", "ABSTAIN"})
AI_DRAFT_RELATIONS = {"ACCEPTED", "REVISED", "REJECTED", "NOT_USED"}

_SESSION_KEYS = {
    "schema_version",
    "workflow_version",
    "review_mode",
    "actor_identity_status",
    "initial_ai_provenance_status",
    "session_id",
    "case_id",
    "source_pack_hash",
    "source_ai_draft_hash",
    "genesis_hash",
    "state",
    "events",
    "head_event_hash",
    "session_hash",
}
_EVENT_KEYS = {
    "sequence",
    "action_id",
    "event_type",
    "actor_role",
    "actor_ref",
    "recorded_at",
    "payload",
    "previous_event_hash",
    "event_hash",
}
_THOUGHT_KEYS = {"thought_ref", "raw_text", "evidence_refs"}
_SYNTHESIS_KEYS = {
    "provider",
    "model",
    "prompt_version",
    "external_approval",
    "draft",
}
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
_STATUS_KEYS = {
    "target_state",
    "rationale",
    "evidence_refs",
    "proposed_disposition",
}
_FINAL_KEYS = {
    "target_state",
    "final_disposition",
    "rationale",
    "evidence_refs",
    "ai_draft_relation",
    "expected_session_hash",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_THOUGHT_REF = re.compile(r"^T[0-9]{3}$")
_SAFE_REF = re.compile(r"^[FXCT][0-9]{3}$")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SURROGATE_CHARACTER = re.compile(r"[\ud800-\udfff]")
_OPAQUE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]*$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
_MAX_EVENTS = 512
_MAX_THOUGHTS = 20
_MAX_RAW_TEXT_CHARS = 8_000
_MAX_RATIONALE_CHARS = 4_000


class ExpertReviewError(ValueError):
    """An expert review action or stored session is invalid."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ExpertReviewEvent:
    sequence: int
    action_id: str
    event_type: str
    actor_role: str
    actor_ref: str
    recorded_at: str
    payload: Mapping[str, Any]
    previous_event_hash: str
    event_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_json(thaw_json(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "action_id": self.action_id,
            "event_type": self.event_type,
            "actor_role": self.actor_role,
            "actor_ref": self.actor_ref,
            "recorded_at": self.recorded_at,
            "payload": thaw_json(self.payload),
            "previous_event_hash": self.previous_event_hash,
            "event_hash": self.event_hash,
        }


@dataclass(frozen=True, slots=True)
class ExpertReviewSession:
    schema_version: str
    workflow_version: str
    review_mode: str
    actor_identity_status: str
    initial_ai_provenance_status: str
    session_id: str
    case_id: str
    source_pack_hash: str
    source_ai_draft_hash: str
    genesis_hash: str
    state: str
    events: tuple[ExpertReviewEvent, ...]
    head_event_hash: str
    session_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple):
            raise ValueError("expert review events must be an immutable tuple")

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        evidence_pack: LLMEvidencePack,
        ai_review_draft: AIReviewDraft,
    ) -> "ExpertReviewSession":
        _validate_sources(evidence_pack, ai_review_draft)
        if not isinstance(payload, dict) or set(payload) != _SESSION_KEYS:
            raise ExpertReviewError(
                "EXPERT_SESSION_FIELDS_INVALID",
                "expert review session must use the exact contract fields",
            )
        if payload["schema_version"] != SCHEMA_VERSION:
            raise ExpertReviewError(
                "EXPERT_SESSION_SCHEMA_UNSUPPORTED",
                "expert review session schema_version is unsupported",
            )
        if payload["workflow_version"] != WORKFLOW_VERSION:
            raise ExpertReviewError(
                "EXPERT_SESSION_WORKFLOW_UNSUPPORTED",
                "expert review workflow_version is unsupported",
            )
        if payload["review_mode"] != REVIEW_MODE:
            raise ExpertReviewError(
                "EXPERT_SESSION_MODE_INVALID",
                "expert review v1 only supports assisted review",
            )
        if payload["actor_identity_status"] != ACTOR_IDENTITY_STATUS:
            raise ExpertReviewError(
                "EXPERT_SESSION_IDENTITY_STATUS_INVALID",
                "file review actor identity must remain explicitly unverified",
            )
        if (
            payload["initial_ai_provenance_status"]
            != INITIAL_AI_PROVENANCE_STATUS
        ):
            raise ExpertReviewError(
                "EXPERT_SESSION_AI_PROVENANCE_INVALID",
                "file review AI provenance must remain explicitly unverified",
            )
        _validate_digest(payload["session_id"], "session_id")
        expected_ai_hash = canonical_digest(ai_review_draft.to_dict())
        if (
            payload["case_id"] != evidence_pack.case_id
            or payload["source_pack_hash"] != evidence_pack.pack_hash
            or payload["source_ai_draft_hash"] != expected_ai_hash
        ):
            raise ExpertReviewError(
                "EXPERT_SESSION_SOURCE_MISMATCH",
                "expert review session does not match its trusted sources",
            )
        expected_genesis = _genesis_hash(
            session_id=payload["session_id"],
            case_id=evidence_pack.case_id,
            source_pack_hash=evidence_pack.pack_hash,
            source_ai_draft_hash=expected_ai_hash,
        )
        if payload["genesis_hash"] != expected_genesis:
            raise ExpertReviewError(
                "EXPERT_SESSION_GENESIS_INVALID",
                "expert review genesis hash does not match its sources",
            )
        raw_events = payload["events"]
        if not isinstance(raw_events, list) or len(raw_events) > _MAX_EVENTS:
            raise ExpertReviewError(
                "EXPERT_SESSION_EVENTS_INVALID",
                "expert review events must be a bounded array",
            )

        state = OPEN
        head_hash = expected_genesis
        parsed_events: list[ExpertReviewEvent] = []
        for sequence, raw_event in enumerate(raw_events, start=1):
            pre_session_hash = _compute_session_hash(
                session_id=payload["session_id"],
                case_id=evidence_pack.case_id,
                source_pack_hash=evidence_pack.pack_hash,
                source_ai_draft_hash=expected_ai_hash,
                genesis_hash=expected_genesis,
                state=state,
                events=tuple(parsed_events),
                head_event_hash=head_hash,
            )
            event, state = _parse_event(
                raw_event,
                expected_sequence=sequence,
                expected_previous_hash=head_hash,
                pre_event_state=state,
                pre_session_hash=pre_session_hash,
                prior_events=tuple(parsed_events),
                session_id=payload["session_id"],
                evidence_pack=evidence_pack,
                ai_review_draft=ai_review_draft,
            )
            parsed_events.append(event)
            head_hash = event.event_hash

        if payload["state"] != state:
            raise ExpertReviewError(
                "EXPERT_SESSION_STATE_INVALID",
                "stored expert review state does not match event replay",
            )
        if payload["head_event_hash"] != head_hash:
            raise ExpertReviewError(
                "EXPERT_SESSION_HEAD_INVALID",
                "stored expert review head does not match event replay",
            )
        expected_session_hash = _compute_session_hash(
            session_id=payload["session_id"],
            case_id=evidence_pack.case_id,
            source_pack_hash=evidence_pack.pack_hash,
            source_ai_draft_hash=expected_ai_hash,
            genesis_hash=expected_genesis,
            state=state,
            events=tuple(parsed_events),
            head_event_hash=head_hash,
        )
        if payload["session_hash"] != expected_session_hash:
            raise ExpertReviewError(
                "EXPERT_SESSION_HASH_INVALID",
                "stored expert review session hash does not match its payload",
            )
        return cls(
            schema_version=SCHEMA_VERSION,
            workflow_version=WORKFLOW_VERSION,
            review_mode=REVIEW_MODE,
            actor_identity_status=ACTOR_IDENTITY_STATUS,
            initial_ai_provenance_status=INITIAL_AI_PROVENANCE_STATUS,
            session_id=payload["session_id"],
            case_id=evidence_pack.case_id,
            source_pack_hash=evidence_pack.pack_hash,
            source_ai_draft_hash=expected_ai_hash,
            genesis_hash=expected_genesis,
            state=state,
            events=tuple(parsed_events),
            head_event_hash=head_hash,
            session_hash=expected_session_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_version": self.workflow_version,
            "review_mode": self.review_mode,
            "actor_identity_status": self.actor_identity_status,
            "initial_ai_provenance_status": self.initial_ai_provenance_status,
            "session_id": self.session_id,
            "case_id": self.case_id,
            "source_pack_hash": self.source_pack_hash,
            "source_ai_draft_hash": self.source_ai_draft_hash,
            "genesis_hash": self.genesis_hash,
            "state": self.state,
            "events": [event.to_dict() for event in self.events],
            "head_event_hash": self.head_event_hash,
            "session_hash": self.session_hash,
        }

    def aggregate_report(self) -> dict[str, Any]:
        event_counts = {
            event_type: sum(
                event.event_type == event_type for event in self.events
            )
            for event_type in sorted(EVENT_TYPES)
        }
        thought_count = event_counts[EXPERT_THOUGHT_SUBMITTED]
        return {
            "report_version": "expert-review-aggregate.v1",
            "valid": True,
            "integrity_check": "VALID",
            "review_mode": self.review_mode,
            "actor_identity_status": self.actor_identity_status,
            "initial_ai_provenance_status": self.initial_ai_provenance_status,
            "authoritative_head_status": "NOT_AVAILABLE_FILE_MODE",
            "state": self.state,
            "event_count": len(self.events),
            "event_type_counts": event_counts,
            "revision_count": max(0, thought_count - 1),
            "final_decision_present": bool(
                event_counts[EXPERT_FINAL_DECISION_RECORDED]
            ),
            "gold_eligible": False,
            "patch_eligible": False,
        }


def open_expert_review_session(
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
    *,
    session_id: str,
) -> ExpertReviewSession:
    """Open an empty assisted-review ledger bound to frozen source artifacts."""

    _validate_sources(evidence_pack, ai_review_draft)
    _validate_digest(session_id, "session_id")
    source_ai_draft_hash = canonical_digest(ai_review_draft.to_dict())
    genesis_hash = _genesis_hash(
        session_id=session_id,
        case_id=evidence_pack.case_id,
        source_pack_hash=evidence_pack.pack_hash,
        source_ai_draft_hash=source_ai_draft_hash,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "review_mode": REVIEW_MODE,
        "actor_identity_status": ACTOR_IDENTITY_STATUS,
        "initial_ai_provenance_status": INITIAL_AI_PROVENANCE_STATUS,
        "session_id": session_id,
        "case_id": evidence_pack.case_id,
        "source_pack_hash": evidence_pack.pack_hash,
        "source_ai_draft_hash": source_ai_draft_hash,
        "genesis_hash": genesis_hash,
        "state": OPEN,
        "events": [],
        "head_event_hash": genesis_hash,
    }
    payload["session_hash"] = canonical_digest(payload)
    return ExpertReviewSession.from_dict(
        payload,
        evidence_pack,
        ai_review_draft,
    )


def submit_expert_thought(
    session: ExpertReviewSession,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
    *,
    action_id: str,
    actor_role: str,
    actor_ref: str,
    recorded_at: str,
    raw_text: str,
    evidence_refs: tuple[str, ...] = (),
) -> ExpertReviewSession:
    trusted = _trusted_session(session, evidence_pack, ai_review_draft)
    thought_count = sum(
        event.event_type == EXPERT_THOUGHT_SUBMITTED
        for event in trusted.events
    )
    if thought_count >= _MAX_THOUGHTS:
        raise ExpertReviewError(
            "EXPERT_THOUGHT_LIMIT_EXCEEDED",
            "expert review session reached its thought limit",
        )
    payload = {
        "thought_ref": f"T{thought_count + 1:03d}",
        "raw_text": raw_text,
        "evidence_refs": list(evidence_refs),
    }
    return _append_event(
        trusted,
        evidence_pack,
        ai_review_draft,
        action_id=action_id,
        event_type=EXPERT_THOUGHT_SUBMITTED,
        actor_role=actor_role,
        actor_ref=actor_ref,
        recorded_at=recorded_at,
        event_payload=payload,
        next_state=DELIBERATING,
    )


def record_ai_synthesis(
    session: ExpertReviewSession,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
    *,
    action_id: str,
    actor_ref: str,
    recorded_at: str,
    provider: str,
    model: str,
    prompt_version: str,
    external_approval: Mapping[str, Any] | None,
    synthesis_draft: ExpertSynthesisDraft,
) -> ExpertReviewSession:
    trusted = _trusted_session(session, evidence_pack, ai_review_draft)
    try:
        trusted_draft = ExpertSynthesisDraft.from_dict(
            synthesis_draft.to_dict(),
            evidence_pack,
            ai_review_draft,
            source_session_hash=trusted.session_hash,
            source_thought_refs=synthesis_draft.source_thought_refs,
        )
    except ExpertSynthesisValidationError as exc:
        raise ExpertReviewError(exc.code, str(exc)) from None
    available_thought_refs = {
        event.payload["thought_ref"]
        for event in trusted.events
        if event.event_type == EXPERT_THOUGHT_SUBMITTED
    }
    if not set(trusted_draft.source_thought_refs).issubset(
        available_thought_refs
    ):
        raise ExpertReviewError(
            "EXPERT_SYNTHESIS_THOUGHT_SOURCE_INVALID",
            "expert synthesis references an unavailable expert thought",
        )
    payload = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "external_approval": (
            thaw_json(external_approval)
            if external_approval is not None
            else None
        ),
        "draft": trusted_draft.to_dict(),
    }
    return _append_event(
        trusted,
        evidence_pack,
        ai_review_draft,
        action_id=action_id,
        event_type=AI_SYNTHESIS_RECORDED,
        actor_role=AI_ASSISTANT,
        actor_ref=actor_ref,
        recorded_at=recorded_at,
        event_payload=payload,
        next_state=trusted.state,
    )


def record_expert_status(
    session: ExpertReviewSession,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
    *,
    action_id: str,
    actor_ref: str,
    recorded_at: str,
    target_state: str,
    rationale: str,
    evidence_refs: tuple[str, ...],
    proposed_disposition: str | None,
) -> ExpertReviewSession:
    trusted = _trusted_session(session, evidence_pack, ai_review_draft)
    payload = {
        "target_state": target_state,
        "rationale": rationale,
        "evidence_refs": list(evidence_refs),
        "proposed_disposition": proposed_disposition,
    }
    return _append_event(
        trusted,
        evidence_pack,
        ai_review_draft,
        action_id=action_id,
        event_type=EXPERT_STATUS_RECORDED,
        actor_role=DOMAIN_EXPERT,
        actor_ref=actor_ref,
        recorded_at=recorded_at,
        event_payload=payload,
        next_state=target_state,
    )


def record_expert_final_decision(
    session: ExpertReviewSession,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
    *,
    action_id: str,
    actor_ref: str,
    recorded_at: str,
    target_state: str,
    final_disposition: str | None,
    rationale: str,
    evidence_refs: tuple[str, ...],
    ai_draft_relation: str,
    expected_session_hash: str,
) -> ExpertReviewSession:
    trusted = _trusted_session(session, evidence_pack, ai_review_draft)
    if expected_session_hash != trusted.session_hash:
        raise ExpertReviewError(
            "EXPERT_SESSION_CONCURRENT_MODIFICATION",
            "final decision expected_session_hash is stale",
        )
    payload = {
        "target_state": target_state,
        "final_disposition": final_disposition,
        "rationale": rationale,
        "evidence_refs": list(evidence_refs),
        "ai_draft_relation": ai_draft_relation,
        "expected_session_hash": expected_session_hash,
    }
    return _append_event(
        trusted,
        evidence_pack,
        ai_review_draft,
        action_id=action_id,
        event_type=EXPERT_FINAL_DECISION_RECORDED,
        actor_role=DOMAIN_EXPERT,
        actor_ref=actor_ref,
        recorded_at=recorded_at,
        event_payload=payload,
        next_state=target_state,
    )


def verify_expert_review_session_against_sources(
    session: ExpertReviewSession,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
) -> None:
    _trusted_session(session, evidence_pack, ai_review_draft)


def _trusted_session(
    session: ExpertReviewSession,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
) -> ExpertReviewSession:
    if not isinstance(session, ExpertReviewSession):
        raise ExpertReviewError(
            "EXPERT_SESSION_INVALID",
            "expert review action requires an ExpertReviewSession",
        )
    trusted = ExpertReviewSession.from_dict(
        session.to_dict(),
        evidence_pack,
        ai_review_draft,
    )
    if trusted != session:
        raise ExpertReviewError(
            "EXPERT_SESSION_INVALID",
            "expert review session is not canonical",
        )
    return trusted


def _append_event(
    session: ExpertReviewSession,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
    *,
    action_id: str,
    event_type: str,
    actor_role: str,
    actor_ref: str,
    recorded_at: str,
    event_payload: dict[str, Any],
    next_state: str,
) -> ExpertReviewSession:
    if len(session.events) >= _MAX_EVENTS:
        raise ExpertReviewError(
            "EXPERT_SESSION_EVENT_LIMIT_EXCEEDED",
            "expert review session reached its event limit",
        )
    sequence = len(session.events) + 1
    raw_event = {
        "sequence": sequence,
        "action_id": action_id,
        "event_type": event_type,
        "actor_role": actor_role,
        "actor_ref": actor_ref,
        "recorded_at": recorded_at,
        "payload": event_payload,
        "previous_event_hash": session.head_event_hash,
    }
    raw_event["event_hash"] = _event_hash(session.session_id, raw_event)
    raw_session = session.to_dict()
    raw_session["events"].append(raw_event)
    raw_session["state"] = next_state
    raw_session["head_event_hash"] = raw_event["event_hash"]
    raw_session.pop("session_hash")
    raw_session["session_hash"] = canonical_digest(raw_session)
    return ExpertReviewSession.from_dict(
        raw_session,
        evidence_pack,
        ai_review_draft,
    )


def _parse_event(
    payload: Any,
    *,
    expected_sequence: int,
    expected_previous_hash: str,
    pre_event_state: str,
    pre_session_hash: str,
    prior_events: tuple[ExpertReviewEvent, ...],
    session_id: str,
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
) -> tuple[ExpertReviewEvent, str]:
    if not isinstance(payload, dict) or set(payload) != _EVENT_KEYS:
        raise ExpertReviewError(
            "EXPERT_EVENT_FIELDS_INVALID",
            "expert review event must use the exact contract fields",
        )
    if (
        not isinstance(payload["sequence"], int)
        or isinstance(payload["sequence"], bool)
        or payload["sequence"] != expected_sequence
    ):
        raise ExpertReviewError(
            "EXPERT_EVENT_SEQUENCE_INVALID",
            "expert review event sequence is not contiguous",
        )
    action_id = payload["action_id"]
    _validate_digest(action_id, "action_id")
    if any(event.action_id == action_id for event in prior_events):
        raise ExpertReviewError(
            "EXPERT_ACTION_ALREADY_APPLIED",
            "expert review action_id has already been applied",
        )
    event_type = payload["event_type"]
    actor_role = payload["actor_role"]
    if (
        not isinstance(event_type, str)
        or event_type not in EVENT_TYPES
        or not isinstance(actor_role, str)
        or actor_role not in ACTOR_ROLES
    ):
        raise ExpertReviewError(
            "EXPERT_EVENT_TYPE_INVALID",
            "expert review event type or actor role is unsupported",
        )
    actor_ref = _identifier(payload["actor_ref"], "actor_ref", max_chars=128)
    recorded_at = _timestamp(payload["recorded_at"])
    if prior_events and _timestamp_value(recorded_at) < _timestamp_value(
        prior_events[-1].recorded_at
    ):
        raise ExpertReviewError(
            "EXPERT_EVENT_TIME_ORDER_INVALID",
            "expert review event timestamps must be non-decreasing",
        )
    if payload["previous_event_hash"] != expected_previous_hash:
        raise ExpertReviewError(
            "EXPERT_EVENT_PREVIOUS_HASH_INVALID",
            "expert review event previous hash is invalid",
        )
    if pre_event_state in TERMINAL_STATES:
        raise ExpertReviewError(
            "EXPERT_SESSION_TERMINAL",
            "terminal expert review sessions cannot accept more events",
        )

    event_payload = payload["payload"]
    if event_type == EXPERT_THOUGHT_SUBMITTED:
        parsed_payload, next_state = _parse_thought_payload(
            event_payload,
            actor_role=actor_role,
            prior_events=prior_events,
            evidence_pack=evidence_pack,
        )
    elif event_type == AI_SYNTHESIS_RECORDED:
        parsed_payload, next_state = _parse_synthesis_payload(
            event_payload,
            actor_role=actor_role,
            recorded_at=recorded_at,
            pre_event_state=pre_event_state,
            pre_session_hash=pre_session_hash,
            prior_events=prior_events,
            evidence_pack=evidence_pack,
            ai_review_draft=ai_review_draft,
        )
    elif event_type == EXPERT_STATUS_RECORDED:
        parsed_payload, next_state = _parse_status_payload(
            event_payload,
            actor_role=actor_role,
            pre_event_state=pre_event_state,
            prior_events=prior_events,
            evidence_pack=evidence_pack,
        )
    else:
        parsed_payload, next_state = _parse_final_payload(
            event_payload,
            actor_role=actor_role,
            pre_event_state=pre_event_state,
            pre_session_hash=pre_session_hash,
            prior_events=prior_events,
            evidence_pack=evidence_pack,
            ai_review_draft=ai_review_draft,
        )

    canonical_event = {
        "sequence": expected_sequence,
        "action_id": action_id,
        "event_type": event_type,
        "actor_role": actor_role,
        "actor_ref": actor_ref,
        "recorded_at": recorded_at,
        "payload": parsed_payload,
        "previous_event_hash": expected_previous_hash,
    }
    expected_event_hash = _event_hash(session_id, canonical_event)
    if payload["event_hash"] != expected_event_hash:
        raise ExpertReviewError(
            "EXPERT_EVENT_HASH_INVALID",
            "expert review event hash does not match its payload",
        )
    event = ExpertReviewEvent(
        sequence=expected_sequence,
        action_id=action_id,
        event_type=event_type,
        actor_role=actor_role,
        actor_ref=actor_ref,
        recorded_at=recorded_at,
        payload=freeze_json(parsed_payload),
        previous_event_hash=expected_previous_hash,
        event_hash=expected_event_hash,
    )
    return event, next_state


def _parse_thought_payload(
    payload: Any,
    *,
    actor_role: str,
    prior_events: tuple[ExpertReviewEvent, ...],
    evidence_pack: LLMEvidencePack,
) -> tuple[dict[str, Any], str]:
    if actor_role not in {DOMAIN_EXPERT, SCHEMA_STEWARD}:
        raise ExpertReviewError(
            "EXPERT_THOUGHT_ACTOR_INVALID",
            "only a domain expert or schema steward may submit thoughts",
        )
    if not isinstance(payload, dict) or set(payload) != _THOUGHT_KEYS:
        raise ExpertReviewError(
            "EXPERT_THOUGHT_FIELDS_INVALID",
            "expert thought must use the exact contract fields",
        )
    prior_thought_count = sum(
        event.event_type == EXPERT_THOUGHT_SUBMITTED for event in prior_events
    )
    expected_ref = f"T{prior_thought_count + 1:03d}"
    if (
        not isinstance(payload["thought_ref"], str)
        or payload["thought_ref"] != expected_ref
        or _THOUGHT_REF.fullmatch(payload["thought_ref"]) is None
        or prior_thought_count >= _MAX_THOUGHTS
    ):
        raise ExpertReviewError(
            "EXPERT_THOUGHT_REF_INVALID",
            "expert thought reference is not the next deterministic T reference",
        )
    raw_text = _bounded_text(
        payload["raw_text"],
        "raw_text",
        max_chars=_MAX_RAW_TEXT_CHARS,
        preserve=True,
    )
    refs = _parse_refs(
        payload["evidence_refs"],
        evidence_pack.allowed_refs,
        allow_empty=True,
    )
    return {
        "thought_ref": expected_ref,
        "raw_text": raw_text,
        "evidence_refs": list(refs),
    }, DELIBERATING


def _parse_synthesis_payload(
    payload: Any,
    *,
    actor_role: str,
    recorded_at: str,
    pre_event_state: str,
    pre_session_hash: str,
    prior_events: tuple[ExpertReviewEvent, ...],
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
) -> tuple[dict[str, Any], str]:
    if actor_role != AI_ASSISTANT:
        raise ExpertReviewError(
            "EXPERT_SYNTHESIS_ACTOR_INVALID",
            "only the AI assistant role may record an AI synthesis",
        )
    if pre_event_state != DELIBERATING:
        raise ExpertReviewError(
            "EXPERT_SYNTHESIS_STATE_INVALID",
            "AI synthesis may only be recorded during deliberation",
        )
    if any(
        event.event_type == AI_SYNTHESIS_RECORDED for event in prior_events
    ):
        raise ExpertReviewError(
            "EXPERT_SYNTHESIS_LIMIT_EXCEEDED",
            "expert review v1 allows at most one AI synthesis",
        )
    if not isinstance(payload, dict) or set(payload) != _SYNTHESIS_KEYS:
        raise ExpertReviewError(
            "EXPERT_SYNTHESIS_EVENT_FIELDS_INVALID",
            "AI synthesis event must use the exact contract fields",
        )
    provider = _identifier(payload["provider"], "provider", max_chars=64)
    model = _identifier(payload["model"], "model", max_chars=128)
    prompt_version = _identifier(
        payload["prompt_version"],
        "prompt_version",
        max_chars=128,
    )
    external_approval = _parse_external_approval(
        payload["external_approval"],
        provider=provider,
        model=model,
        prompt_version=prompt_version,
    )
    if (
        external_approval is not None
        and _timestamp_value(external_approval["approved_at"])
        > _timestamp_value(recorded_at)
    ):
        raise ExpertReviewError(
            "EXTERNAL_APPROVAL_TIME_INVALID",
            "external approval must precede the recorded AI synthesis",
        )
    draft_payload = payload["draft"]
    if not isinstance(draft_payload, dict):
        raise ExpertReviewError(
            "EXPERT_SYNTHESIS_DRAFT_INVALID",
            "AI synthesis event requires a stored synthesis draft",
        )
    source_refs = draft_payload.get("source_thought_refs")
    available_refs = {
        event.payload["thought_ref"]
        for event in prior_events
        if event.event_type == EXPERT_THOUGHT_SUBMITTED
    }
    if (
        not isinstance(source_refs, list)
        or not source_refs
        or len(source_refs) > _MAX_THOUGHTS
        or any(
            not isinstance(item, str)
            or _THOUGHT_REF.fullmatch(item) is None
            or item not in available_refs
            for item in source_refs
        )
        or len(source_refs) != len(set(source_refs))
    ):
        raise ExpertReviewError(
            "EXPERT_SYNTHESIS_DRAFT_INVALID",
            "AI synthesis source thought refs are invalid",
        )
    try:
        trusted_draft = ExpertSynthesisDraft.from_dict(
            draft_payload,
            evidence_pack,
            ai_review_draft,
            source_session_hash=pre_session_hash,
            source_thought_refs=tuple(source_refs),
        )
    except ExpertSynthesisValidationError as exc:
        raise ExpertReviewError(exc.code, str(exc)) from None
    if provider == "BAILIAN_OPENAI_COMPATIBLE":
        assert external_approval is not None
        thought_text_by_ref = {
            event.payload["thought_ref"]: event.payload["raw_text"]
            for event in prior_events
            if event.event_type == EXPERT_THOUGHT_SUBMITTED
        }
        expert_thoughts = tuple(
            (thought_ref, thought_text_by_ref[thought_ref])
            for thought_ref in trusted_draft.source_thought_refs
        )
        try:
            expected_approval_hash = expected_bailian_approval_payload_hash(
                evidence_pack,
                ai_review_draft,
                endpoint=external_approval["endpoint"],
                model=model,
                prompt_version=prompt_version,
                expert_thoughts=expert_thoughts,
            )
        except (ExpertSynthesisValidationError, KeyError) as exc:
            raise ExpertReviewError(
                getattr(exc, "code", "EXTERNAL_APPROVAL_SOURCE_MISMATCH"),
                "external approval request plan could not be reconstructed",
            ) from None
        if not hmac.compare_digest(
            external_approval["approval_payload_hash"],
            expected_approval_hash,
        ):
            raise ExpertReviewError(
                "EXTERNAL_EXPERT_PAYLOAD_APPROVAL_REQUIRED",
                "stored approval does not cover the reconstructed request plan",
            )
    return {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "external_approval": external_approval,
        "draft": trusted_draft.to_dict(),
    }, pre_event_state


def _parse_external_approval(
    value: Any,
    *,
    provider: str,
    model: str,
    prompt_version: str,
) -> dict[str, Any] | None:
    if value is None:
        if provider == "BAILIAN_OPENAI_COMPATIBLE":
            raise ExpertReviewError(
                "EXTERNAL_EXPERT_PAYLOAD_APPROVAL_REQUIRED",
                "external Bailian synthesis requires an approval record",
            )
        return None
    if not isinstance(value, dict) or set(value) != _EXTERNAL_APPROVAL_KEYS:
        raise ExpertReviewError(
            "EXTERNAL_APPROVAL_FIELDS_INVALID",
            "external approval must use the exact contract fields",
        )
    if (
        value["schema_version"]
        != "external-expert-synthesis-approval.v1"
        or value["approval_status"] != "APPROVED"
        or value["identity_status"] != "UNVERIFIED_FILE_ASSERTION"
    ):
        raise ExpertReviewError(
            "EXTERNAL_APPROVAL_STATUS_INVALID",
            "external approval must be an explicitly approved file assertion",
        )
    _validate_digest(
        value["approval_payload_hash"],
        "approval_payload_hash",
    )
    parsed_provider = _identifier(
        value["provider"],
        "approval provider",
        max_chars=64,
    )
    parsed_model = _identifier(
        value["model"],
        "approval model",
        max_chars=128,
    )
    parsed_prompt = _identifier(
        value["prompt_version"],
        "approval prompt_version",
        max_chars=128,
    )
    approved_by = _identifier(
        value["approved_by"],
        "approved_by",
        max_chars=128,
    )
    approved_at = _timestamp(value["approved_at"])
    endpoint = _bounded_text(
        value["endpoint"],
        "endpoint",
        max_chars=512,
        preserve=True,
    )
    if (
        parsed_provider != provider
        or parsed_model != model
        or parsed_prompt != prompt_version
    ):
        raise ExpertReviewError(
            "EXTERNAL_APPROVAL_SOURCE_MISMATCH",
            "external approval does not match the recorded provider plan",
        )
    return {
        "schema_version": "external-expert-synthesis-approval.v1",
        "approval_status": "APPROVED",
        "approval_payload_hash": value["approval_payload_hash"],
        "provider": parsed_provider,
        "endpoint": endpoint,
        "model": parsed_model,
        "prompt_version": parsed_prompt,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
    }


def _parse_status_payload(
    payload: Any,
    *,
    actor_role: str,
    pre_event_state: str,
    prior_events: tuple[ExpertReviewEvent, ...],
    evidence_pack: LLMEvidencePack,
) -> tuple[dict[str, Any], str]:
    if actor_role != DOMAIN_EXPERT:
        raise ExpertReviewError(
            "EXPERT_STATUS_ACTOR_INVALID",
            "only a domain expert may record an expert status",
        )
    if not isinstance(payload, dict) or set(payload) != _STATUS_KEYS:
        raise ExpertReviewError(
            "EXPERT_STATUS_FIELDS_INVALID",
            "expert status must use the exact contract fields",
        )
    target_state = payload["target_state"]
    if (
        not isinstance(target_state, str)
        or target_state not in {NEED_EVIDENCE, PROVISIONAL}
    ):
        raise ExpertReviewError(
            "EXPERT_STATUS_TARGET_INVALID",
            "expert status target must be NEED_EVIDENCE or PROVISIONAL",
        )
    if pre_event_state == DELIBERATING:
        pass
    elif pre_event_state == PROVISIONAL and target_state == NEED_EVIDENCE:
        pass
    else:
        raise ExpertReviewError(
            "EXPERT_STATUS_STATE_INVALID",
            "expert status transition is not allowed from the current state",
        )
    rationale = _bounded_text(
        payload["rationale"],
        "rationale",
        max_chars=_MAX_RATIONALE_CHARS,
        preserve=True,
    )
    refs = _parse_refs(
        payload["evidence_refs"],
        _available_refs(prior_events, evidence_pack),
        allow_empty=False,
    )
    proposed_disposition = payload["proposed_disposition"]
    if target_state == NEED_EVIDENCE:
        if proposed_disposition is not None:
            raise ExpertReviewError(
                "EXPERT_STATUS_DISPOSITION_INVALID",
                "NEED_EVIDENCE cannot carry a proposed disposition",
            )
    elif (
        not isinstance(proposed_disposition, str)
        or proposed_disposition not in FINAL_DISPOSITIONS
    ):
        raise ExpertReviewError(
            "EXPERT_STATUS_DISPOSITION_INVALID",
            "PROVISIONAL requires an allowlisted proposed disposition",
        )
    return {
        "target_state": target_state,
        "rationale": rationale,
        "evidence_refs": list(refs),
        "proposed_disposition": proposed_disposition,
    }, target_state


def _parse_final_payload(
    payload: Any,
    *,
    actor_role: str,
    pre_event_state: str,
    pre_session_hash: str,
    prior_events: tuple[ExpertReviewEvent, ...],
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
) -> tuple[dict[str, Any], str]:
    if actor_role != DOMAIN_EXPERT:
        raise ExpertReviewError(
            "EXPERT_FINAL_ACTOR_INVALID",
            "only a domain expert may record a final decision",
        )
    if pre_event_state != PROVISIONAL:
        raise ExpertReviewError(
            "EXPERT_FINAL_STATE_INVALID",
            "final expert decision requires a provisional session",
        )
    if not isinstance(payload, dict) or set(payload) != _FINAL_KEYS:
        raise ExpertReviewError(
            "EXPERT_FINAL_FIELDS_INVALID",
            "final expert decision must use the exact contract fields",
        )
    if payload["expected_session_hash"] != pre_session_hash:
        raise ExpertReviewError(
            "EXPERT_SESSION_CONCURRENT_MODIFICATION",
            "final decision expected_session_hash is stale",
        )
    target_state = payload["target_state"]
    final_disposition = payload["final_disposition"]
    if target_state == APPROVED:
        if (
            not isinstance(final_disposition, str)
            or final_disposition not in FINAL_DISPOSITIONS
        ):
            raise ExpertReviewError(
                "EXPERT_FINAL_DISPOSITION_INVALID",
                "approved expert decision requires a final disposition",
            )
        provisional_events = [
            event
            for event in prior_events
            if event.event_type == EXPERT_STATUS_RECORDED
            and event.payload["target_state"] == PROVISIONAL
        ]
        if (
            not provisional_events
            or provisional_events[-1].payload["proposed_disposition"]
            != final_disposition
        ):
            raise ExpertReviewError(
                "EXPERT_FINAL_PROVISIONAL_MISMATCH",
                "approved disposition must match the latest provisional decision",
            )
    elif target_state == REJECTED:
        if final_disposition is not None:
            raise ExpertReviewError(
                "EXPERT_FINAL_DISPOSITION_INVALID",
                "rejected expert decision cannot carry a final disposition",
            )
    else:
        raise ExpertReviewError(
            "EXPERT_FINAL_TARGET_INVALID",
            "final expert decision must target APPROVED or REJECTED",
        )
    relation = payload["ai_draft_relation"]
    if (
        not isinstance(relation, str)
        or relation not in AI_DRAFT_RELATIONS
    ):
        raise ExpertReviewError(
            "EXPERT_FINAL_AI_RELATION_INVALID",
            "final expert decision AI relation is unsupported",
        )
    if relation == "ACCEPTED" and (
        target_state != APPROVED
        or ai_review_draft.suggested_disposition not in FINAL_DISPOSITIONS
        or final_disposition != ai_review_draft.suggested_disposition
    ):
        raise ExpertReviewError(
            "EXPERT_FINAL_AI_RELATION_INVALID",
            "ACCEPTED requires the same final disposition as the initial AI draft",
        )
    rationale = _bounded_text(
        payload["rationale"],
        "rationale",
        max_chars=_MAX_RATIONALE_CHARS,
        preserve=True,
    )
    refs = _parse_refs(
        payload["evidence_refs"],
        _available_refs(prior_events, evidence_pack),
        allow_empty=False,
    )
    return {
        "target_state": target_state,
        "final_disposition": final_disposition,
        "rationale": rationale,
        "evidence_refs": list(refs),
        "ai_draft_relation": relation,
        "expected_session_hash": pre_session_hash,
    }, target_state


def _available_refs(
    prior_events: tuple[ExpertReviewEvent, ...],
    evidence_pack: LLMEvidencePack,
) -> frozenset[str]:
    thought_refs = {
        event.payload["thought_ref"]
        for event in prior_events
        if event.event_type == EXPERT_THOUGHT_SUBMITTED
    }
    return evidence_pack.allowed_refs | frozenset(thought_refs)


def _parse_refs(
    value: Any,
    allowed_refs: frozenset[str],
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or len(value) > 20
        or any(
            not isinstance(item, str)
            or _SAFE_REF.fullmatch(item) is None
            or item not in allowed_refs
            for item in value
        )
        or len(value) != len(set(value))
    ):
        raise ExpertReviewError(
            "EXPERT_EVIDENCE_REF_INVALID",
            "expert review contains an unavailable or duplicate reference",
        )
    return tuple(value)


def _validate_sources(
    evidence_pack: LLMEvidencePack,
    ai_review_draft: AIReviewDraft,
) -> None:
    try:
        evidence_pack.validate()
        trusted_draft = AIReviewDraft.from_dict(
            ai_review_draft.to_dict(),
            evidence_pack,
        )
    except (ValueError, AIReviewValidationError):
        raise ExpertReviewError(
            "EXPERT_SESSION_SOURCE_INVALID",
            "expert review sources failed local integrity validation",
        ) from None
    if trusted_draft != ai_review_draft:
        raise ExpertReviewError(
            "EXPERT_SESSION_SOURCE_INVALID",
            "expert review AI draft is not source-bound",
        )


def _genesis_hash(
    *,
    session_id: str,
    case_id: str,
    source_pack_hash: str,
    source_ai_draft_hash: str,
) -> str:
    return canonical_digest(
        {
            "hash_domain": "treeguard.expert-review-genesis.v1",
            "schema_version": SCHEMA_VERSION,
            "workflow_version": WORKFLOW_VERSION,
            "review_mode": REVIEW_MODE,
            "actor_identity_status": ACTOR_IDENTITY_STATUS,
            "initial_ai_provenance_status": INITIAL_AI_PROVENANCE_STATUS,
            "session_id": session_id,
            "case_id": case_id,
            "source_pack_hash": source_pack_hash,
            "source_ai_draft_hash": source_ai_draft_hash,
        }
    )


def _event_hash(session_id: str, event: Mapping[str, Any]) -> str:
    event_payload = {
        key: thaw_json(value)
        for key, value in event.items()
        if key != "event_hash"
    }
    return canonical_digest(
        {
            "hash_domain": "treeguard.expert-review-event.v1",
            "session_id": session_id,
            **event_payload,
        }
    )


def _compute_session_hash(
    *,
    session_id: str,
    case_id: str,
    source_pack_hash: str,
    source_ai_draft_hash: str,
    genesis_hash: str,
    state: str,
    events: tuple[ExpertReviewEvent, ...],
    head_event_hash: str,
) -> str:
    return canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "workflow_version": WORKFLOW_VERSION,
            "review_mode": REVIEW_MODE,
            "actor_identity_status": ACTOR_IDENTITY_STATUS,
            "initial_ai_provenance_status": INITIAL_AI_PROVENANCE_STATUS,
            "session_id": session_id,
            "case_id": case_id,
            "source_pack_hash": source_pack_hash,
            "source_ai_draft_hash": source_ai_draft_hash,
            "genesis_hash": genesis_hash,
            "state": state,
            "events": [event.to_dict() for event in events],
            "head_event_hash": head_event_hash,
        }
    )


def _identifier(value: Any, field_name: str, *, max_chars: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > max_chars
        or _OPAQUE_IDENTIFIER.fullmatch(value) is None
    ):
        raise ExpertReviewError(
            "EXPERT_IDENTIFIER_INVALID",
            f"{field_name} must be a safe bounded identifier",
        )
    return value


def _bounded_text(
    value: Any,
    field_name: str,
    *,
    max_chars: int,
    preserve: bool,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > max_chars
        or _CONTROL_CHARACTER.search(value) is not None
        or _SURROGATE_CHARACTER.search(value) is not None
    ):
        raise ExpertReviewError(
            "EXPERT_TEXT_INVALID",
            f"{field_name} must be safe bounded non-empty text",
        )
    return value if preserve else value.strip()


def _timestamp(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 20 <= len(value) <= 35
        or _RFC3339.fullmatch(value) is None
    ):
        raise ExpertReviewError(
            "EXPERT_TIMESTAMP_INVALID",
            "recorded_at must be a bounded RFC3339 timestamp",
        )
    _timestamp_value(value)
    return value


def _timestamp_value(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ExpertReviewError(
            "EXPERT_TIMESTAMP_INVALID",
            "recorded_at must be an RFC3339 timestamp",
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExpertReviewError(
            "EXPERT_TIMESTAMP_INVALID",
            "recorded_at must include a timezone",
        )
    return parsed


def _validate_digest(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ExpertReviewError(
            "EXPERT_DIGEST_INVALID",
            f"{field_name} must be a SHA-256 digest",
        )


__all__ = [
    "AI_ASSISTANT",
    "ACTOR_IDENTITY_STATUS",
    "AI_DRAFT_RELATIONS",
    "AI_SYNTHESIS_RECORDED",
    "APPROVED",
    "DELIBERATING",
    "DOMAIN_EXPERT",
    "EVENT_TYPES",
    "EXPERT_FINAL_DECISION_RECORDED",
    "EXPERT_STATUS_RECORDED",
    "EXPERT_THOUGHT_SUBMITTED",
    "ExpertReviewError",
    "ExpertReviewEvent",
    "ExpertReviewSession",
    "FINAL_DISPOSITIONS",
    "INITIAL_AI_PROVENANCE_STATUS",
    "NEED_EVIDENCE",
    "OPEN",
    "PROVISIONAL",
    "REJECTED",
    "REVIEW_MODE",
    "SCHEMA_STEWARD",
    "SCHEMA_VERSION",
    "WORKFLOW_VERSION",
    "open_expert_review_session",
    "record_ai_synthesis",
    "record_expert_final_decision",
    "record_expert_status",
    "submit_expert_thought",
    "verify_expert_review_session_against_sources",
]
