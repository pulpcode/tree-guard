"""Validated change-intent drafts and explicit retrieval-only confirmation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalNode, CanonicalTree


REQUEST_SCHEMA_VERSION = "intent-request.v1"
MODEL_OUTPUT_SCHEMA_VERSION = "change-intent-model-output.v1"
DRAFT_SCHEMA_VERSION = "change-intent-draft.v1"
ACTION_SCHEMA_VERSION = "intent-review-action.v1"
CONFIRMATION_SCHEMA_VERSION = "intent-confirmation.v1"
MODEL_PROVENANCE_STATUS = "UNVERIFIED_FILE_ASSERTION"

NODE_KINDS = {"CONCEPT", "PROPERTY", "UNKNOWN"}
CARDINALITIES = {"SINGLE", "MULTIPLE", "UNKNOWN"}
OWNERSHIP_CLASSES = {
    "LONG_LIVED_SUBJECT_PROPERTY",
    "CURRENT_PARTICIPATION_STATE",
    "TASK_LEVEL_PROPERTY",
    "UNKNOWN",
}
REVIEW_DECISIONS = {"CONFIRM_FOR_RETRIEVAL", "REJECT_DRAFT"}

_REQUEST_KEYS = {
    "schema_version",
    "requirement_text",
    "proposed_parent_node_id",
    "node_kind_hint",
    "value_type_hint",
    "cardinality_hint",
}
_CONTENT_KEYS = {
    "subject",
    "role",
    "scenario",
    "lifecycle",
    "ownership",
    "node_kind",
    "value_type",
    "cardinality",
    "confirmed_facts",
    "assumptions",
    "evidence_gaps",
    "clarification_question",
}
_MODEL_OUTPUT_KEYS = _CONTENT_KEYS | {"schema_version"}
_DRAFT_KEYS = {
    "schema_version",
    "model_provider",
    "model_capability",
    "model_name",
    "prompt_version",
    "model_provenance_status",
    "source_request_hash",
    "source_snapshot_hash",
    "review_status",
    "intent",
    "draft_hash",
}
_ACTION_KEYS = {
    "schema_version",
    "expected_draft_hash",
    "decision",
    "reviewer_ref",
    "recorded_at",
    "confirmed_intent",
}
_CONFIRMATION_KEYS = {
    "schema_version",
    "status",
    "identity_status",
    "semantic_approval",
    "patch_eligible",
    "source_request_hash",
    "source_snapshot_hash",
    "source_draft_hash",
    "source_action_hash",
    "proposed_parent_node_id",
    "reviewer_ref",
    "recorded_at",
    "intent",
    "confirmation_hash",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SURROGATE_CHARACTER = re.compile(r"[\ud800-\udfff]")
_FABRICATED_INTERNAL_ID = re.compile(
    r"(?i)(?:"
    r"\b(?:node|tree)[-_:/]\d[A-Za-z0-9._:@/-]*\b"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
    r"|\b[0-9a-f]{24}\b"
    r"|\b[0-9a-f]{64}\b"
    r")"
)
_MAX_REQUIREMENT_CHARS = 8_000
_MAX_TEXT_CHARS = 1_000
_MAX_LIST_ITEMS = 20


class IntentValidationError(ValueError):
    """An intent input or persisted artifact failed a stable local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class IntentContent:
    subject: str | None
    role: str | None
    scenario: str | None
    lifecycle: str | None
    ownership: str
    node_kind: str
    value_type: str | None
    cardinality: str
    confirmed_facts: tuple[str, ...]
    assumptions: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    clarification_question: str | None

    def __post_init__(self) -> None:
        for field_name in ("subject", "role", "scenario", "lifecycle", "value_type"):
            _optional_text(getattr(self, field_name), field_name)
        if self.ownership not in OWNERSHIP_CLASSES:
            raise ValueError("unsupported intent ownership")
        if self.node_kind not in NODE_KINDS:
            raise ValueError("unsupported intent node_kind")
        if self.cardinality not in CARDINALITIES:
            raise ValueError("unsupported intent cardinality")
        for field_name in ("confirmed_facts", "assumptions", "evidence_gaps"):
            _validate_text_tuple(getattr(self, field_name), field_name)
        _optional_text(self.clarification_question, "clarification_question")

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        *,
        error_code: str = "INTENT_CONTENT_INVALID",
    ) -> "IntentContent":
        if not isinstance(payload, dict) or set(payload) != _CONTENT_KEYS:
            raise IntentValidationError(
                error_code,
                "intent content must use the exact contract fields",
            )
        try:
            return cls(
                subject=_optional_text(payload["subject"], "subject"),
                role=_optional_text(payload["role"], "role"),
                scenario=_optional_text(payload["scenario"], "scenario"),
                lifecycle=_optional_text(payload["lifecycle"], "lifecycle"),
                ownership=_enum(
                    payload["ownership"],
                    OWNERSHIP_CLASSES,
                    "ownership",
                ),
                node_kind=_enum(payload["node_kind"], NODE_KINDS, "node_kind"),
                value_type=_optional_text(payload["value_type"], "value_type"),
                cardinality=_enum(
                    payload["cardinality"],
                    CARDINALITIES,
                    "cardinality",
                ),
                confirmed_facts=_text_tuple(
                    payload["confirmed_facts"],
                    "confirmed_facts",
                ),
                assumptions=_text_tuple(payload["assumptions"], "assumptions"),
                evidence_gaps=_text_tuple(
                    payload["evidence_gaps"],
                    "evidence_gaps",
                ),
                clarification_question=_optional_text(
                    payload["clarification_question"],
                    "clarification_question",
                ),
            )
        except ValueError:
            raise IntentValidationError(
                error_code,
                "intent content failed local validation",
            ) from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "role": self.role,
            "scenario": self.scenario,
            "lifecycle": self.lifecycle,
            "ownership": self.ownership,
            "node_kind": self.node_kind,
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "confirmed_facts": list(self.confirmed_facts),
            "assumptions": list(self.assumptions),
            "evidence_gaps": list(self.evidence_gaps),
            "clarification_question": self.clarification_question,
        }

    def all_text(self) -> tuple[str, ...]:
        scalars = (
            self.subject,
            self.role,
            self.scenario,
            self.lifecycle,
            self.value_type,
            self.clarification_question,
        )
        return tuple(value for value in scalars if value is not None) + (
            self.confirmed_facts
            + self.assumptions
            + self.evidence_gaps
        )


@dataclass(frozen=True, slots=True)
class IntentRequest:
    requirement_text: str
    proposed_parent_node_id: str | None
    node_kind_hint: str
    value_type_hint: str | None
    cardinality_hint: str

    def __post_init__(self) -> None:
        _required_text(
            self.requirement_text,
            "requirement_text",
            max_chars=_MAX_REQUIREMENT_CHARS,
        )
        _optional_identifier(
            self.proposed_parent_node_id,
            "proposed_parent_node_id",
        )
        if self.node_kind_hint not in NODE_KINDS:
            raise ValueError("unsupported request node_kind_hint")
        _optional_text(self.value_type_hint, "value_type_hint")
        if self.cardinality_hint not in CARDINALITIES:
            raise ValueError("unsupported request cardinality_hint")

    @classmethod
    def from_dict(cls, payload: Any, tree: CanonicalTree) -> "IntentRequest":
        _require_resource_tree(tree)
        if not isinstance(payload, dict) or set(payload) != _REQUEST_KEYS:
            raise IntentValidationError(
                "INTENT_REQUEST_FIELDS_INVALID",
                "intent request must use the exact contract fields",
            )
        if payload["schema_version"] != REQUEST_SCHEMA_VERSION:
            raise IntentValidationError(
                "INTENT_REQUEST_VERSION_INVALID",
                "unsupported intent request schema_version",
            )
        try:
            requirement_text = _required_text(
                payload["requirement_text"],
                "requirement_text",
                max_chars=_MAX_REQUIREMENT_CHARS,
            )
            proposed_parent_node_id = _optional_identifier(
                payload["proposed_parent_node_id"],
                "proposed_parent_node_id",
            )
            request = cls(
                requirement_text=requirement_text,
                proposed_parent_node_id=proposed_parent_node_id,
                node_kind_hint=_enum(
                    payload["node_kind_hint"],
                    NODE_KINDS,
                    "node_kind_hint",
                ),
                value_type_hint=_optional_text(
                    payload["value_type_hint"],
                    "value_type_hint",
                ),
                cardinality_hint=_enum(
                    payload["cardinality_hint"],
                    CARDINALITIES,
                    "cardinality_hint",
                ),
            )
        except ValueError:
            raise IntentValidationError(
                "INTENT_REQUEST_VALUE_INVALID",
                "intent request failed local validation",
            ) from None
        if proposed_parent_node_id is not None:
            nodes = {node.node_id: node for node in tree.nodes}
            parent = nodes.get(proposed_parent_node_id)
            if parent is None or parent.kind == "UNSUPPORTED":
                raise IntentValidationError(
                    "INTENT_PARENT_UNKNOWN",
                    "proposed parent is not an eligible node in the source tree",
                )
        return request

    @property
    def request_hash(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "requirement_text": self.requirement_text,
            "proposed_parent_node_id": self.proposed_parent_node_id,
            "node_kind_hint": self.node_kind_hint,
            "value_type_hint": self.value_type_hint,
            "cardinality_hint": self.cardinality_hint,
        }

    def to_model_dict(self, tree: CanonicalTree) -> dict[str, Any]:
        """Return an allowlisted model view without stable identifiers or VALUE."""

        _require_resource_tree(tree)
        parent_view = None
        if self.proposed_parent_node_id is not None:
            parent = next(
                (
                    node
                    for node in tree.nodes
                    if node.node_id == self.proposed_parent_node_id
                ),
                None,
            )
            if parent is None or parent.kind == "UNSUPPORTED":
                raise IntentValidationError(
                    "INTENT_PARENT_UNKNOWN",
                    "proposed parent is not an eligible node in the source tree",
                )
            parent_view = _node_model_view(parent)
        return {
            "requirement_text": self.requirement_text,
            "hints": {
                "node_kind": self.node_kind_hint,
                "value_type": self.value_type_hint,
                "cardinality": self.cardinality_hint,
            },
            "proposed_parent": parent_view,
        }


@dataclass(frozen=True, slots=True)
class ChangeIntentDraft:
    model_provider: str
    model_capability: str
    model_name: str
    prompt_version: str
    source_request_hash: str
    source_snapshot_hash: str
    review_status: str
    intent: IntentContent
    draft_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "model_provider",
            "model_capability",
            "model_name",
            "prompt_version",
        ):
            _required_text(getattr(self, field_name), field_name)
        _validate_digest(self.source_request_hash, "source_request_hash")
        _validate_digest(self.source_snapshot_hash, "source_snapshot_hash")
        if self.review_status not in {
            "READY_FOR_HUMAN_REVIEW",
            "NEEDS_CLARIFICATION",
        }:
            raise ValueError("unsupported intent draft review_status")
        if not isinstance(self.intent, IntentContent):
            raise ValueError("intent draft requires IntentContent")
        expected_review_status = (
            "NEEDS_CLARIFICATION"
            if self.intent.clarification_question is not None
            else "READY_FOR_HUMAN_REVIEW"
        )
        if self.review_status != expected_review_status:
            raise ValueError("intent draft review_status does not match its intent")
        payload = self._payload()
        _validate_digest(self.draft_hash, "draft_hash")
        if self.draft_hash != canonical_digest(payload):
            raise ValueError("intent draft_hash does not match its payload")

    @classmethod
    def from_model_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        tree: CanonicalTree,
        *,
        model_provider: str,
        model_capability: str,
        model_name: str,
        prompt_version: str,
    ) -> "ChangeIntentDraft":
        _require_resource_tree(tree)
        if not isinstance(payload, dict) or set(payload) != _MODEL_OUTPUT_KEYS:
            raise IntentValidationError(
                "INTENT_MODEL_FIELDS_INVALID",
                "model output must use the exact contract fields",
            )
        if payload["schema_version"] != MODEL_OUTPUT_SCHEMA_VERSION:
            raise IntentValidationError(
                "INTENT_MODEL_VERSION_INVALID",
                "unsupported intent model output schema_version",
            )
        intent = IntentContent.from_dict(
            {key: payload[key] for key in _CONTENT_KEYS},
            error_code="INTENT_MODEL_CONTENT_INVALID",
        )
        _reject_internal_ids(intent, tree)
        review_status = (
            "NEEDS_CLARIFICATION"
            if intent.clarification_question is not None
            else "READY_FOR_HUMAN_REVIEW"
        )
        draft_payload = {
            "schema_version": DRAFT_SCHEMA_VERSION,
            "model_provider": _required_text(
                model_provider,
                "model_provider",
            ),
            "model_capability": _required_text(
                model_capability,
                "model_capability",
            ),
            "model_name": _required_text(model_name, "model_name"),
            "prompt_version": _required_text(prompt_version, "prompt_version"),
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "source_request_hash": request.request_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "review_status": review_status,
            "intent": intent.to_dict(),
        }
        return cls(
            model_provider=draft_payload["model_provider"],
            model_capability=draft_payload["model_capability"],
            model_name=draft_payload["model_name"],
            prompt_version=draft_payload["prompt_version"],
            source_request_hash=request.request_hash,
            source_snapshot_hash=tree.snapshot_hash,
            review_status=review_status,
            intent=intent,
            draft_hash=canonical_digest(draft_payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> "ChangeIntentDraft":
        if not isinstance(payload, dict) or set(payload) != _DRAFT_KEYS:
            raise IntentValidationError(
                "INTENT_DRAFT_FIELDS_INVALID",
                "stored intent draft must use the exact contract fields",
            )
        if (
            payload["schema_version"] != DRAFT_SCHEMA_VERSION
            or payload["model_provenance_status"] != MODEL_PROVENANCE_STATUS
        ):
            raise IntentValidationError(
                "INTENT_DRAFT_VERSION_INVALID",
                "stored intent draft version or provenance is unsupported",
            )
        intent = IntentContent.from_dict(
            payload["intent"],
            error_code="INTENT_DRAFT_CONTENT_INVALID",
        )
        _reject_internal_ids(intent, tree)
        try:
            draft = cls(
                model_provider=payload["model_provider"],
                model_capability=payload["model_capability"],
                model_name=payload["model_name"],
                prompt_version=payload["prompt_version"],
                source_request_hash=payload["source_request_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                review_status=payload["review_status"],
                intent=intent,
                draft_hash=payload["draft_hash"],
            )
        except (TypeError, ValueError):
            raise IntentValidationError(
                "INTENT_DRAFT_INVALID",
                "stored intent draft failed integrity validation",
            ) from None
        verify_intent_draft_against_sources(draft, request, tree)
        return draft

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": DRAFT_SCHEMA_VERSION,
            "model_provider": self.model_provider,
            "model_capability": self.model_capability,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "source_request_hash": self.source_request_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "review_status": self.review_status,
            "intent": self.intent.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["draft_hash"] = self.draft_hash
        return payload


@dataclass(frozen=True, slots=True)
class IntentReviewAction:
    expected_draft_hash: str
    decision: str
    reviewer_ref: str
    recorded_at: str
    confirmed_intent: IntentContent | None

    def __post_init__(self) -> None:
        _validate_digest(self.expected_draft_hash, "expected_draft_hash")
        if self.decision not in REVIEW_DECISIONS:
            raise ValueError("unsupported intent review decision")
        _identifier(self.reviewer_ref, "reviewer_ref")
        _timestamp(self.recorded_at)
        if (
            self.decision == "CONFIRM_FOR_RETRIEVAL"
            and not isinstance(self.confirmed_intent, IntentContent)
        ) or (
            self.decision == "REJECT_DRAFT"
            and self.confirmed_intent is not None
        ):
            raise ValueError("action decision and confirmed intent are inconsistent")

    @classmethod
    def from_dict(cls, payload: Any) -> "IntentReviewAction":
        if not isinstance(payload, dict) or set(payload) != _ACTION_KEYS:
            raise IntentValidationError(
                "INTENT_ACTION_FIELDS_INVALID",
                "intent review action must use the exact contract fields",
            )
        if payload["schema_version"] != ACTION_SCHEMA_VERSION:
            raise IntentValidationError(
                "INTENT_ACTION_VERSION_INVALID",
                "unsupported intent review action schema_version",
            )
        try:
            decision = _enum(
                payload["decision"],
                REVIEW_DECISIONS,
                "decision",
            )
            confirmed_intent = (
                None
                if payload["confirmed_intent"] is None
                else IntentContent.from_dict(
                    payload["confirmed_intent"],
                    error_code="INTENT_ACTION_CONTENT_INVALID",
                )
            )
            action = cls(
                expected_draft_hash=_digest(
                    payload["expected_draft_hash"],
                    "expected_draft_hash",
                ),
                decision=decision,
                reviewer_ref=_identifier(payload["reviewer_ref"], "reviewer_ref"),
                recorded_at=_timestamp(payload["recorded_at"]),
                confirmed_intent=confirmed_intent,
            )
        except ValueError:
            raise IntentValidationError(
                "INTENT_ACTION_VALUE_INVALID",
                "intent review action failed local validation",
            ) from None
        if (
            decision == "CONFIRM_FOR_RETRIEVAL"
            and confirmed_intent is None
        ) or (
            decision == "REJECT_DRAFT"
            and confirmed_intent is not None
        ):
            raise IntentValidationError(
                "INTENT_ACTION_DECISION_INVALID",
                "action decision and confirmed_intent are inconsistent",
            )
        return action

    @property
    def action_hash(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTION_SCHEMA_VERSION,
            "expected_draft_hash": self.expected_draft_hash,
            "decision": self.decision,
            "reviewer_ref": self.reviewer_ref,
            "recorded_at": self.recorded_at,
            "confirmed_intent": (
                self.confirmed_intent.to_dict()
                if self.confirmed_intent is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class IntentConfirmation:
    status: str
    source_request_hash: str
    source_snapshot_hash: str
    source_draft_hash: str
    source_action_hash: str
    proposed_parent_node_id: str | None
    reviewer_ref: str
    recorded_at: str
    intent: IntentContent | None
    confirmation_hash: str

    def __post_init__(self) -> None:
        if self.status not in {"CONFIRMED_FOR_RETRIEVAL", "REJECTED"}:
            raise ValueError("unsupported intent confirmation status")
        for field_name in (
            "source_request_hash",
            "source_snapshot_hash",
            "source_draft_hash",
            "source_action_hash",
            "confirmation_hash",
        ):
            _validate_digest(getattr(self, field_name), field_name)
        _optional_identifier(
            self.proposed_parent_node_id,
            "proposed_parent_node_id",
        )
        _identifier(self.reviewer_ref, "reviewer_ref")
        _timestamp(self.recorded_at)
        if (
            self.status == "CONFIRMED_FOR_RETRIEVAL"
            and not isinstance(self.intent, IntentContent)
        ) or (self.status == "REJECTED" and self.intent is not None):
            raise ValueError("confirmation status and intent are inconsistent")
        if self.confirmation_hash != canonical_digest(self._payload()):
            raise ValueError("confirmation_hash does not match its payload")

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        draft: ChangeIntentDraft,
        action: IntentReviewAction,
        tree: CanonicalTree,
    ) -> "IntentConfirmation":
        if not isinstance(payload, dict) or set(payload) != _CONFIRMATION_KEYS:
            raise IntentValidationError(
                "INTENT_CONFIRMATION_FIELDS_INVALID",
                "stored intent confirmation must use the exact contract fields",
            )
        if (
            payload["schema_version"] != CONFIRMATION_SCHEMA_VERSION
            or payload["identity_status"] != "UNVERIFIED_FILE_ASSERTION"
            or payload["semantic_approval"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise IntentValidationError(
                "INTENT_CONFIRMATION_POLICY_INVALID",
                "stored intent confirmation violates the retrieval-only policy",
            )
        intent = (
            None
            if payload["intent"] is None
            else IntentContent.from_dict(
                payload["intent"],
                error_code="INTENT_CONFIRMATION_CONTENT_INVALID",
            )
        )
        try:
            confirmation = cls(
                status=payload["status"],
                source_request_hash=payload["source_request_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                source_draft_hash=payload["source_draft_hash"],
                source_action_hash=payload["source_action_hash"],
                proposed_parent_node_id=payload["proposed_parent_node_id"],
                reviewer_ref=payload["reviewer_ref"],
                recorded_at=payload["recorded_at"],
                intent=intent,
                confirmation_hash=payload["confirmation_hash"],
            )
        except (TypeError, ValueError):
            raise IntentValidationError(
                "INTENT_CONFIRMATION_INVALID",
                "stored intent confirmation failed integrity validation",
            ) from None
        verify_intent_confirmation_against_sources(
            confirmation,
            request,
            draft,
            action,
            tree,
        )
        return confirmation

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": CONFIRMATION_SCHEMA_VERSION,
            "status": self.status,
            "identity_status": "UNVERIFIED_FILE_ASSERTION",
            "semantic_approval": False,
            "patch_eligible": False,
            "source_request_hash": self.source_request_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_draft_hash": self.source_draft_hash,
            "source_action_hash": self.source_action_hash,
            "proposed_parent_node_id": self.proposed_parent_node_id,
            "reviewer_ref": self.reviewer_ref,
            "recorded_at": self.recorded_at,
            "intent": self.intent.to_dict() if self.intent is not None else None,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["confirmation_hash"] = self.confirmation_hash
        return payload


def apply_intent_review(
    request: IntentRequest,
    draft: ChangeIntentDraft,
    action: IntentReviewAction,
    tree: CanonicalTree,
) -> IntentConfirmation:
    """Create one retrieval-only confirmation from trusted source artifacts."""

    verify_intent_draft_against_sources(draft, request, tree)
    if action.expected_draft_hash != draft.draft_hash:
        raise IntentValidationError(
            "INTENT_ACTION_STALE",
            "intent action does not bind the current draft",
        )
    if action.confirmed_intent is not None:
        _reject_internal_ids(action.confirmed_intent, tree)
    status = (
        "CONFIRMED_FOR_RETRIEVAL"
        if action.decision == "CONFIRM_FOR_RETRIEVAL"
        else "REJECTED"
    )
    payload = {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "status": status,
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "semantic_approval": False,
        "patch_eligible": False,
        "source_request_hash": request.request_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": draft.draft_hash,
        "source_action_hash": action.action_hash,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "reviewer_ref": action.reviewer_ref,
        "recorded_at": action.recorded_at,
        "intent": (
            action.confirmed_intent.to_dict()
            if action.confirmed_intent is not None
            else None
        ),
    }
    return IntentConfirmation(
        status=status,
        source_request_hash=request.request_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=draft.draft_hash,
        source_action_hash=action.action_hash,
        proposed_parent_node_id=request.proposed_parent_node_id,
        reviewer_ref=action.reviewer_ref,
        recorded_at=action.recorded_at,
        intent=action.confirmed_intent,
        confirmation_hash=canonical_digest(payload),
    )


def verify_intent_draft_against_sources(
    draft: ChangeIntentDraft,
    request: IntentRequest,
    tree: CanonicalTree,
) -> None:
    _require_resource_tree(tree)
    if (
        draft.source_request_hash != request.request_hash
        or draft.source_snapshot_hash != tree.snapshot_hash
    ):
        raise IntentValidationError(
            "INTENT_DRAFT_SOURCE_MISMATCH",
            "intent draft does not match trusted request and snapshot",
        )
    _reject_internal_ids(draft.intent, tree)


def verify_intent_confirmation_against_sources(
    confirmation: IntentConfirmation,
    request: IntentRequest,
    draft: ChangeIntentDraft,
    action: IntentReviewAction,
    tree: CanonicalTree,
) -> None:
    expected = apply_intent_review(request, draft, action, tree)
    if confirmation.to_dict() != expected.to_dict():
        raise IntentValidationError(
            "INTENT_CONFIRMATION_SOURCE_MISMATCH",
            "intent confirmation does not match trusted source replay",
        )


def _require_resource_tree(tree: CanonicalTree) -> None:
    if not isinstance(tree, CanonicalTree) or tree.source_map_type != "resource":
        raise IntentValidationError(
            "INTENT_SOURCE_NOT_RESOURCE",
            "intent governance accepts resource snapshots only",
        )


def _node_model_view(node: CanonicalNode) -> dict[str, Any]:
    contract = node.value_contract
    return {
        "kind": node.kind,
        "label": node.label,
        "name": node.name,
        "path": list(node.path_labels),
        "value_type": contract.value_type if contract is not None else None,
        "cardinality": contract.cardinality if contract is not None else None,
        "has_constraints": bool(contract and contract.constraints),
    }


def _reject_internal_ids(intent: IntentContent, tree: CanonicalTree) -> None:
    text_values = intent.all_text()
    if any(_FABRICATED_INTERNAL_ID.search(text) for text in text_values):
        raise IntentValidationError(
            "INTENT_MODEL_INTERNAL_ID_FORBIDDEN",
            "intent content must not contain identifier-like values",
        )
    for node in tree.nodes:
        node_id = node.node_id
        if not node_id:
            continue
        if any(
            (node_id in text if len(node_id) >= 4 else node_id == text)
            for text in text_values
        ):
            raise IntentValidationError(
                "INTENT_MODEL_INTERNAL_ID_FORBIDDEN",
                "intent content must not contain internal node identifiers",
            )


def _required_text(
    value: Any,
    field_name: str,
    *,
    max_chars: int = _MAX_TEXT_CHARS,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > max_chars
        or _CONTROL_CHARACTER.search(value) is not None
        or _SURROGATE_CHARACTER.search(value) is not None
    ):
        raise ValueError(f"{field_name} must be bounded printable text")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > _MAX_LIST_ITEMS
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{field_name} must be a bounded unique text array")
    result = tuple(_required_text(item, field_name) for item in value)
    _validate_text_tuple(result, field_name)
    return result


def _validate_text_tuple(value: Any, field_name: str) -> None:
    if (
        not isinstance(value, tuple)
        or len(value) > _MAX_LIST_ITEMS
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{field_name} must be an immutable unique tuple")
    for item in value:
        _required_text(item, field_name)


def _enum(value: Any, allowed: set[str], field_name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{field_name} uses an unsupported enum value")
    return value


def _digest(value: Any, field_name: str) -> str:
    _validate_digest(value, field_name)
    return value


def _validate_digest(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a SHA-256 digest")


def _identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an opaque identifier")
    return value


def _optional_identifier(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field_name)


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ValueError("recorded_at must be strict RFC3339")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at must include a timezone")
    return value


__all__ = [
    "ACTION_SCHEMA_VERSION",
    "CARDINALITIES",
    "CONFIRMATION_SCHEMA_VERSION",
    "ChangeIntentDraft",
    "DRAFT_SCHEMA_VERSION",
    "IntentConfirmation",
    "IntentContent",
    "IntentRequest",
    "IntentReviewAction",
    "IntentValidationError",
    "MODEL_OUTPUT_SCHEMA_VERSION",
    "MODEL_PROVENANCE_STATUS",
    "NODE_KINDS",
    "OWNERSHIP_CLASSES",
    "REQUEST_SCHEMA_VERSION",
    "REVIEW_DECISIONS",
    "apply_intent_review",
    "verify_intent_confirmation_against_sources",
    "verify_intent_draft_against_sources",
]
