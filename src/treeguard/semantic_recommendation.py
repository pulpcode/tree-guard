"""Bounded candidate projection and locally constrained semantic recommendations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from treeguard.change_intent import (
    MODEL_PROVENANCE_STATUS,
    IntentConfirmation,
    IntentContent,
)
from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree
from treeguard.retrieval import (
    DEFAULT_MAX_CANDIDATES,
    CandidateRetrievalError,
    CandidateSet,
    RetrievalCandidate,
    verify_candidate_set_against_sources,
)


MODEL_INPUT_SCHEMA_VERSION = "semantic-recommendation-model-input.v1"
MODEL_OUTPUT_SCHEMA_VERSION = "semantic-recommendation-model-output.v1"
CONTENT_SCHEMA_VERSION = "semantic-recommendation-content.v1"
DRAFT_SCHEMA_VERSION = "semantic-recommendation-draft.v1"
REVIEW_ACTION_SCHEMA_VERSION = "recommendation-review-action.v1"
RECORD_SCHEMA_VERSION = "recommendation-record.v1"
PROJECTION_VERSION = "treeguard.semantic-candidate-projection.v1"
MAX_MODEL_CANDIDATES = 8
MAX_MODEL_INPUT_CHARS = 48_000

CANDIDATE_RELATIONS = {
    "SEMANTICALLY_EQUIVALENT",
    "REUSES_CONTRACT",
    "CONTEXTUALLY_RELATED",
    "NOT_EQUIVALENT",
    "NEED_EVIDENCE",
}
RECOMMENDED_ACTIONS = {
    "USE_EXISTING_NODE",
    "ADD_NODE_FROM_CONTRACT",
    "ADD_CONTEXT_FIELD",
    "NEED_CLARIFICATION",
    "NEED_EVIDENCE",
    "ABSTAIN",
}
REVIEW_DECISIONS = {
    "CONFIRM_RECOMMENDATION",
    "REVISE_RECOMMENDATION",
    "REJECT_RECOMMENDATION",
}

_POSITIVE_ACTION_RELATIONS = {
    "USE_EXISTING_NODE": "SEMANTICALLY_EQUIVALENT",
    "ADD_NODE_FROM_CONTRACT": "REUSES_CONTRACT",
    "ADD_CONTEXT_FIELD": "CONTEXTUALLY_RELATED",
}
_MODEL_OUTPUT_KEYS = {
    "schema_version",
    "candidate_assessments",
    "recommended_action",
    "selected_candidate_ref",
    "rationale",
    "uncertainties",
    "evidence_gaps",
    "clarification_question",
}
_DRAFT_KEYS = _MODEL_OUTPUT_KEYS | {
    "model_provider",
    "model_capability",
    "model_name",
    "prompt_version",
    "model_provenance_status",
    "semantic_approval",
    "patch_eligible",
    "source_confirmation_hash",
    "source_candidate_set_hash",
    "source_snapshot_hash",
    "source_projection_hash",
    "draft_hash",
}
_CONTENT_KEYS = _MODEL_OUTPUT_KEYS
_REVIEW_ACTION_KEYS = {
    "schema_version",
    "identity_status",
    "expected_draft_hash",
    "decision",
    "reviewer_ref",
    "recorded_at",
    "reviewer_reasoning",
    "revised_recommendation",
}
_RECORD_KEYS = {
    "schema_version",
    "record_semantics",
    "identity_status",
    "status",
    "semantic_approval",
    "patch_eligible",
    "gold_eligible",
    "source_confirmation_hash",
    "source_candidate_set_hash",
    "source_snapshot_hash",
    "source_draft_hash",
    "source_action_hash",
    "reviewer_ref",
    "recorded_at",
    "reviewer_reasoning",
    "effective_recommendation",
    "record_hash",
}
_ASSESSMENT_KEYS = {"candidate_ref", "relation", "reason"}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_REF = re.compile(r"^C00[1-8]$")
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
_MAX_TEXT_CHARS = 1_000
_MAX_REASONING_CHARS = 8_000
_MAX_LIST_ITEMS = 20
_MAX_PATH_ITEMS = 128


class SemanticRecommendationError(ValueError):
    """A semantic recommendation failed its deterministic local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SemanticCandidateView:
    candidate_ref: str
    rank: int
    kind: str
    label: str
    name: str
    path_labels: tuple[str, ...]
    value_type: str | None
    cardinality: str | None
    parent_relation: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_ref, str)
            or _CANDIDATE_REF.fullmatch(self.candidate_ref) is None
        ):
            raise ValueError("semantic candidate_ref is invalid")
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or self.rank > MAX_MODEL_CANDIDATES
        ):
            raise ValueError("semantic candidate rank is invalid")
        if (
            not isinstance(self.kind, str)
            or self.kind not in {"CONCEPT", "PROPERTY"}
        ):
            raise ValueError("semantic candidate kind is unsupported")
        _required_text(self.label, "label")
        _required_text(self.name, "name")
        if (
            not isinstance(self.path_labels, tuple)
            or not self.path_labels
            or len(self.path_labels) > _MAX_PATH_ITEMS
        ):
            raise ValueError("semantic candidate path is invalid")
        for item in self.path_labels:
            _required_text(item, "path_labels")
        if self.value_type is not None:
            _required_text(self.value_type, "value_type")
        if (
            self.cardinality is not None
            and (
                not isinstance(self.cardinality, str)
                or self.cardinality not in {"SINGLE", "MULTIPLE"}
            )
        ):
            raise ValueError("semantic candidate cardinality is invalid")
        if (
            not isinstance(self.parent_relation, str)
            or self.parent_relation
            not in {
                "NONE",
                "PROPOSED_PARENT",
                "DIRECT_CHILD",
                "SAME_BRANCH",
            }
        ):
            raise ValueError("semantic candidate parent relation is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ref": self.candidate_ref,
            "rank": self.rank,
            "kind": self.kind,
            "label": self.label,
            "name": self.name,
            "path_labels": list(self.path_labels),
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "parent_relation": self.parent_relation,
        }


@dataclass(frozen=True, slots=True)
class SemanticCandidateProjection:
    source_confirmation_hash: str
    source_candidate_set_hash: str
    source_snapshot_hash: str
    candidate_status: str
    intent: IntentContent
    candidates: tuple[SemanticCandidateView, ...]
    projection_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_confirmation_hash,
            self.source_candidate_set_hash,
            self.source_snapshot_hash,
            self.projection_hash,
        ):
            _validate_digest(value)
        if (
            not isinstance(self.candidate_status, str)
            or self.candidate_status
            not in {
                "CANDIDATES_READY",
                "NO_CANDIDATES",
                "INSUFFICIENT_SIGNAL",
            }
        ):
            raise ValueError("semantic projection candidate status is invalid")
        if not isinstance(self.intent, IntentContent):
            raise ValueError("semantic projection requires confirmed intent")
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_MODEL_CANDIDATES
            or any(
                not isinstance(item, SemanticCandidateView)
                for item in self.candidates
            )
        ):
            raise ValueError("semantic projection candidates are invalid")
        if self.candidate_status == "CANDIDATES_READY" and not self.candidates:
            raise ValueError("ready semantic projection requires candidates")
        if self.candidate_status != "CANDIDATES_READY" and self.candidates:
            raise ValueError("non-ready semantic projection cannot contain candidates")
        expected_refs = tuple(
            f"C{index:03d}" for index in range(1, len(self.candidates) + 1)
        )
        if tuple(item.candidate_ref for item in self.candidates) != expected_refs:
            raise ValueError("semantic candidate refs must be contiguous")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("semantic candidate ranks must be contiguous")
        model_payload = self.to_model_dict()
        if _serialized_char_count(model_payload) > MAX_MODEL_INPUT_CHARS:
            raise ValueError("semantic candidate projection exceeds its size limit")
        if self.projection_hash != canonical_digest(model_payload):
            raise ValueError("semantic projection_hash does not match its payload")

    @property
    def candidate_refs(self) -> tuple[str, ...]:
        return tuple(item.candidate_ref for item in self.candidates)

    def to_model_dict(self) -> dict[str, Any]:
        """Return the bounded model view without stable IDs, hashes, or VALUE."""

        return {
            "schema_version": MODEL_INPUT_SCHEMA_VERSION,
            "projection_version": PROJECTION_VERSION,
            "intent": self.intent.to_dict(),
            "candidate_status": self.candidate_status,
            "candidates": [item.to_dict() for item in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class SemanticCandidateAssessment:
    candidate_ref: str
    relation: str
    reason: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_ref, str)
            or _CANDIDATE_REF.fullmatch(self.candidate_ref) is None
        ):
            raise ValueError("semantic assessment candidate_ref is invalid")
        if (
            not isinstance(self.relation, str)
            or self.relation not in CANDIDATE_RELATIONS
        ):
            raise ValueError("semantic assessment relation is unsupported")
        _required_text(self.reason, "reason")

    def to_dict(self) -> dict[str, str]:
        return {
            "candidate_ref": self.candidate_ref,
            "relation": self.relation,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SemanticRecommendationDraft:
    model_provider: str
    model_capability: str
    model_name: str
    prompt_version: str
    source_confirmation_hash: str
    source_candidate_set_hash: str
    source_snapshot_hash: str
    source_projection_hash: str
    candidate_assessments: tuple[SemanticCandidateAssessment, ...]
    recommended_action: str
    selected_candidate_ref: str | None
    rationale: str
    uncertainties: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    clarification_question: str | None
    draft_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "model_provider",
            "model_capability",
            "model_name",
            "prompt_version",
        ):
            _required_text(getattr(self, field_name), field_name)
        for value in (
            self.source_confirmation_hash,
            self.source_candidate_set_hash,
            self.source_snapshot_hash,
            self.source_projection_hash,
            self.draft_hash,
        ):
            _validate_digest(value)
        if (
            not isinstance(self.candidate_assessments, tuple)
            or len(self.candidate_assessments) > MAX_MODEL_CANDIDATES
            or any(
                not isinstance(item, SemanticCandidateAssessment)
                for item in self.candidate_assessments
            )
        ):
            raise ValueError("semantic candidate assessments are invalid")
        _validate_assessment_sequence(self.candidate_assessments)
        if (
            not isinstance(self.recommended_action, str)
            or self.recommended_action not in RECOMMENDED_ACTIONS
        ):
            raise ValueError("semantic recommended action is unsupported")
        if (
            self.selected_candidate_ref is not None
            and (
                not isinstance(self.selected_candidate_ref, str)
                or _CANDIDATE_REF.fullmatch(
                    self.selected_candidate_ref
                )
                is None
            )
        ):
            raise ValueError("semantic selected candidate_ref is invalid")
        _required_text(self.rationale, "rationale")
        _validate_text_tuple(self.uncertainties, "uncertainties")
        _validate_text_tuple(self.evidence_gaps, "evidence_gaps")
        if self.clarification_question is not None:
            _required_text(
                self.clarification_question,
                "clarification_question",
            )
        _validate_action_shape(
            self.recommended_action,
            self.selected_candidate_ref,
            self.candidate_assessments,
            self.evidence_gaps,
            self.clarification_question,
        )
        if self.draft_hash != canonical_digest(self._payload()):
            raise ValueError("semantic draft_hash does not match its payload")

    @classmethod
    def from_model_dict(
        cls,
        payload: Any,
        confirmation: IntentConfirmation,
        candidate_set: CandidateSet,
        tree: CanonicalTree,
        *,
        model_provider: str,
        model_capability: str,
        model_name: str,
        prompt_version: str,
    ) -> "SemanticRecommendationDraft":
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        if not isinstance(payload, dict) or set(payload) != _MODEL_OUTPUT_KEYS:
            raise SemanticRecommendationError(
                "SEMANTIC_MODEL_FIELDS_INVALID",
                "semantic model output must use the exact contract fields",
            )
        if payload["schema_version"] != MODEL_OUTPUT_SCHEMA_VERSION:
            raise SemanticRecommendationError(
                "SEMANTIC_MODEL_VERSION_INVALID",
                "semantic model output schema_version is unsupported",
            )
        assessments = _parse_assessments(
            payload["candidate_assessments"],
            projection,
        )
        action = _parse_enum(
            payload["recommended_action"],
            RECOMMENDED_ACTIONS,
            "SEMANTIC_ACTION_INVALID",
        )
        selected_candidate_ref = _parse_selected_ref(
            payload["selected_candidate_ref"],
            projection,
        )
        rationale = _parse_required_text(payload["rationale"], "rationale")
        uncertainties = _parse_text_tuple(
            payload["uncertainties"],
            "uncertainties",
        )
        evidence_gaps = _parse_text_tuple(
            payload["evidence_gaps"],
            "evidence_gaps",
        )
        clarification_question = _parse_optional_text(
            payload["clarification_question"],
            "clarification_question",
        )
        _validate_source_policy(
            action,
            selected_candidate_ref,
            assessments,
            evidence_gaps,
            clarification_question,
            projection,
        )
        _reject_internal_ids(
            (
                rationale,
                *(item.reason for item in assessments),
                *uncertainties,
                *evidence_gaps,
                *(
                    (clarification_question,)
                    if clarification_question is not None
                    else ()
                ),
            ),
            tree,
        )
        metadata = {
            "model_provider": _parse_required_text(
                model_provider,
                "model_provider",
            ),
            "model_capability": _parse_required_text(
                model_capability,
                "model_capability",
            ),
            "model_name": _parse_required_text(model_name, "model_name"),
            "prompt_version": _parse_required_text(
                prompt_version,
                "prompt_version",
            ),
        }
        draft_payload = {
            "schema_version": DRAFT_SCHEMA_VERSION,
            **metadata,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "semantic_approval": False,
            "patch_eligible": False,
            "source_confirmation_hash": confirmation.confirmation_hash,
            "source_candidate_set_hash": candidate_set.candidate_set_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "source_projection_hash": projection.projection_hash,
            "candidate_assessments": [
                item.to_dict() for item in assessments
            ],
            "recommended_action": action,
            "selected_candidate_ref": selected_candidate_ref,
            "rationale": rationale,
            "uncertainties": list(uncertainties),
            "evidence_gaps": list(evidence_gaps),
            "clarification_question": clarification_question,
        }
        return cls(
            **metadata,
            source_confirmation_hash=confirmation.confirmation_hash,
            source_candidate_set_hash=candidate_set.candidate_set_hash,
            source_snapshot_hash=tree.snapshot_hash,
            source_projection_hash=projection.projection_hash,
            candidate_assessments=assessments,
            recommended_action=action,
            selected_candidate_ref=selected_candidate_ref,
            rationale=rationale,
            uncertainties=uncertainties,
            evidence_gaps=evidence_gaps,
            clarification_question=clarification_question,
            draft_hash=canonical_digest(draft_payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        confirmation: IntentConfirmation,
        candidate_set: CandidateSet,
        tree: CanonicalTree,
    ) -> "SemanticRecommendationDraft":
        if not isinstance(payload, dict) or set(payload) != _DRAFT_KEYS:
            raise SemanticRecommendationError(
                "SEMANTIC_DRAFT_FIELDS_INVALID",
                "stored semantic draft must use the exact contract fields",
            )
        if (
            payload["schema_version"] != DRAFT_SCHEMA_VERSION
            or payload["model_provenance_status"] != MODEL_PROVENANCE_STATUS
            or payload["semantic_approval"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise SemanticRecommendationError(
                "SEMANTIC_DRAFT_POLICY_INVALID",
                "stored semantic draft violates the non-executable policy",
            )
        model_payload = {
            key: payload[key] for key in _MODEL_OUTPUT_KEYS
        }
        model_payload["schema_version"] = MODEL_OUTPUT_SCHEMA_VERSION
        draft = cls.from_model_dict(
            model_payload,
            confirmation,
            candidate_set,
            tree,
            model_provider=payload["model_provider"],
            model_capability=payload["model_capability"],
            model_name=payload["model_name"],
            prompt_version=payload["prompt_version"],
        )
        if payload != draft.to_dict():
            raise SemanticRecommendationError(
                "SEMANTIC_DRAFT_SOURCE_MISMATCH",
                "stored semantic draft does not match its trusted sources",
            )
        return draft

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": DRAFT_SCHEMA_VERSION,
            "model_provider": self.model_provider,
            "model_capability": self.model_capability,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "semantic_approval": False,
            "patch_eligible": False,
            "source_confirmation_hash": self.source_confirmation_hash,
            "source_candidate_set_hash": self.source_candidate_set_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_projection_hash": self.source_projection_hash,
            "candidate_assessments": [
                item.to_dict() for item in self.candidate_assessments
            ],
            "recommended_action": self.recommended_action,
            "selected_candidate_ref": self.selected_candidate_ref,
            "rationale": self.rationale,
            "uncertainties": list(self.uncertainties),
            "evidence_gaps": list(self.evidence_gaps),
            "clarification_question": self.clarification_question,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["draft_hash"] = self.draft_hash
        return payload

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_OUTPUT_SCHEMA_VERSION,
            "candidate_assessments": [
                item.to_dict() for item in self.candidate_assessments
            ],
            "recommended_action": self.recommended_action,
            "selected_candidate_ref": self.selected_candidate_ref,
            "rationale": self.rationale,
            "uncertainties": list(self.uncertainties),
            "evidence_gaps": list(self.evidence_gaps),
            "clarification_question": self.clarification_question,
        }

    def to_content(self) -> "SemanticRecommendationContent":
        return SemanticRecommendationContent(
            candidate_assessments=self.candidate_assessments,
            recommended_action=self.recommended_action,
            selected_candidate_ref=self.selected_candidate_ref,
            rationale=self.rationale,
            uncertainties=self.uncertainties,
            evidence_gaps=self.evidence_gaps,
            clarification_question=self.clarification_question,
        )


@dataclass(frozen=True, slots=True)
class SemanticRecommendationContent:
    candidate_assessments: tuple[SemanticCandidateAssessment, ...]
    recommended_action: str
    selected_candidate_ref: str | None
    rationale: str
    uncertainties: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    clarification_question: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_assessments, tuple)
            or len(self.candidate_assessments) > MAX_MODEL_CANDIDATES
            or any(
                not isinstance(item, SemanticCandidateAssessment)
                for item in self.candidate_assessments
            )
        ):
            raise ValueError("semantic recommendation content is invalid")
        _validate_assessment_sequence(self.candidate_assessments)
        if (
            not isinstance(self.recommended_action, str)
            or self.recommended_action not in RECOMMENDED_ACTIONS
        ):
            raise ValueError("semantic recommendation action is unsupported")
        if (
            self.selected_candidate_ref is not None
            and (
                not isinstance(self.selected_candidate_ref, str)
                or _CANDIDATE_REF.fullmatch(
                    self.selected_candidate_ref
                )
                is None
            )
        ):
            raise ValueError("semantic recommendation selection is invalid")
        _required_text(self.rationale, "rationale")
        _validate_text_tuple(self.uncertainties, "uncertainties")
        _validate_text_tuple(self.evidence_gaps, "evidence_gaps")
        if self.clarification_question is not None:
            _required_text(
                self.clarification_question,
                "clarification_question",
            )
        _validate_action_shape(
            self.recommended_action,
            self.selected_candidate_ref,
            self.candidate_assessments,
            self.evidence_gaps,
            self.clarification_question,
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        confirmation: IntentConfirmation,
        candidate_set: CandidateSet,
        tree: CanonicalTree,
    ) -> "SemanticRecommendationContent":
        if not isinstance(payload, dict) or set(payload) != _CONTENT_KEYS:
            raise SemanticRecommendationError(
                "SEMANTIC_CONTENT_FIELDS_INVALID",
                "semantic recommendation content must use exact fields",
            )
        if payload["schema_version"] != CONTENT_SCHEMA_VERSION:
            raise SemanticRecommendationError(
                "SEMANTIC_CONTENT_VERSION_INVALID",
                "semantic recommendation content version is unsupported",
            )
        model_payload = dict(payload)
        model_payload["schema_version"] = MODEL_OUTPUT_SCHEMA_VERSION
        validated = SemanticRecommendationDraft.from_model_dict(
            model_payload,
            confirmation,
            candidate_set,
            tree,
            model_provider="HUMAN_REVIEW_ACTION",
            model_capability="STRUCTURED_REVISION",
            model_name="NOT_APPLICABLE",
            prompt_version="treeguard.human-recommendation-revision.v1",
        )
        return validated.to_content()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONTENT_SCHEMA_VERSION,
            "candidate_assessments": [
                item.to_dict() for item in self.candidate_assessments
            ],
            "recommended_action": self.recommended_action,
            "selected_candidate_ref": self.selected_candidate_ref,
            "rationale": self.rationale,
            "uncertainties": list(self.uncertainties),
            "evidence_gaps": list(self.evidence_gaps),
            "clarification_question": self.clarification_question,
        }


@dataclass(frozen=True, slots=True)
class RecommendationReviewAction:
    expected_draft_hash: str
    decision: str
    reviewer_ref: str
    recorded_at: str
    reviewer_reasoning: str | None
    revised_recommendation: SemanticRecommendationContent | None

    def __post_init__(self) -> None:
        _validate_digest(self.expected_draft_hash)
        if (
            not isinstance(self.decision, str)
            or self.decision not in REVIEW_DECISIONS
        ):
            raise ValueError("recommendation review decision is unsupported")
        _validate_identifier(self.reviewer_ref)
        _validate_timestamp(self.recorded_at)
        if self.reviewer_reasoning is not None:
            _required_text(
                self.reviewer_reasoning,
                "reviewer_reasoning",
                max_chars=_MAX_REASONING_CHARS,
            )
        if (
            self.decision == "REVISE_RECOMMENDATION"
            and not isinstance(
                self.revised_recommendation,
                SemanticRecommendationContent,
            )
        ) or (
            self.decision != "REVISE_RECOMMENDATION"
            and self.revised_recommendation is not None
        ):
            raise ValueError("review decision and revision are inconsistent")

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        confirmation: IntentConfirmation,
        candidate_set: CandidateSet,
        tree: CanonicalTree,
    ) -> "RecommendationReviewAction":
        if not isinstance(payload, dict) or set(payload) != _REVIEW_ACTION_KEYS:
            raise SemanticRecommendationError(
                "RECOMMENDATION_ACTION_FIELDS_INVALID",
                "recommendation review action must use exact fields",
            )
        if (
            payload["schema_version"] != REVIEW_ACTION_SCHEMA_VERSION
            or payload["identity_status"] != "UNVERIFIED_FILE_ASSERTION"
        ):
            raise SemanticRecommendationError(
                "RECOMMENDATION_ACTION_POLICY_INVALID",
                "recommendation action identity or version is unsupported",
            )
        try:
            expected_draft_hash = _parse_digest(
                payload["expected_draft_hash"],
                "expected_draft_hash",
            )
            decision = _parse_enum(
                payload["decision"],
                REVIEW_DECISIONS,
                "RECOMMENDATION_ACTION_DECISION_INVALID",
            )
            reviewer_ref = _parse_identifier(
                payload["reviewer_ref"],
                "reviewer_ref",
            )
            recorded_at = _parse_timestamp(payload["recorded_at"])
            reviewer_reasoning = _parse_optional_bounded_text(
                payload["reviewer_reasoning"],
                "reviewer_reasoning",
                max_chars=_MAX_REASONING_CHARS,
            )
            revised_recommendation = (
                None
                if payload["revised_recommendation"] is None
                else SemanticRecommendationContent.from_dict(
                    payload["revised_recommendation"],
                    confirmation,
                    candidate_set,
                    tree,
                )
            )
            action = cls(
                expected_draft_hash=expected_draft_hash,
                decision=decision,
                reviewer_ref=reviewer_ref,
                recorded_at=recorded_at,
                reviewer_reasoning=reviewer_reasoning,
                revised_recommendation=revised_recommendation,
            )
        except SemanticRecommendationError:
            raise
        except ValueError:
            raise SemanticRecommendationError(
                "RECOMMENDATION_ACTION_VALUE_INVALID",
                "recommendation review action failed local validation",
            ) from None
        return action

    @property
    def action_hash(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REVIEW_ACTION_SCHEMA_VERSION,
            "identity_status": "UNVERIFIED_FILE_ASSERTION",
            "expected_draft_hash": self.expected_draft_hash,
            "decision": self.decision,
            "reviewer_ref": self.reviewer_ref,
            "recorded_at": self.recorded_at,
            "reviewer_reasoning": self.reviewer_reasoning,
            "revised_recommendation": (
                self.revised_recommendation.to_dict()
                if self.revised_recommendation is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class RecommendationRecord:
    status: str
    source_confirmation_hash: str
    source_candidate_set_hash: str
    source_snapshot_hash: str
    source_draft_hash: str
    source_action_hash: str
    reviewer_ref: str
    recorded_at: str
    reviewer_reasoning: str | None
    effective_recommendation: SemanticRecommendationContent | None
    record_hash: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, str)
            or self.status not in {"CONFIRMED", "REVISED", "REJECTED"}
        ):
            raise ValueError("recommendation record status is unsupported")
        for value in (
            self.source_confirmation_hash,
            self.source_candidate_set_hash,
            self.source_snapshot_hash,
            self.source_draft_hash,
            self.source_action_hash,
            self.record_hash,
        ):
            _validate_digest(value)
        _validate_identifier(self.reviewer_ref)
        _validate_timestamp(self.recorded_at)
        if self.reviewer_reasoning is not None:
            _required_text(
                self.reviewer_reasoning,
                "reviewer_reasoning",
                max_chars=_MAX_REASONING_CHARS,
            )
        if (
            self.status in {"CONFIRMED", "REVISED"}
            and not isinstance(
                self.effective_recommendation,
                SemanticRecommendationContent,
            )
        ) or (
            self.status == "REJECTED"
            and self.effective_recommendation is not None
        ):
            raise ValueError("record status and recommendation are inconsistent")
        if self.record_hash != canonical_digest(self._payload()):
            raise ValueError("recommendation record_hash does not match its payload")

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        draft: SemanticRecommendationDraft,
        action: RecommendationReviewAction,
        confirmation: IntentConfirmation,
        candidate_set: CandidateSet,
        tree: CanonicalTree,
    ) -> "RecommendationRecord":
        if not isinstance(payload, dict) or set(payload) != _RECORD_KEYS:
            raise SemanticRecommendationError(
                "RECOMMENDATION_RECORD_FIELDS_INVALID",
                "stored recommendation record must use exact fields",
            )
        if (
            payload["schema_version"] != RECORD_SCHEMA_VERSION
            or payload["record_semantics"] != "OPERATIONAL_FEEDBACK_ONLY"
            or payload["identity_status"] != "UNVERIFIED_FILE_ASSERTION"
            or payload["semantic_approval"] is not False
            or payload["patch_eligible"] is not False
            or payload["gold_eligible"] is not False
        ):
            raise SemanticRecommendationError(
                "RECOMMENDATION_RECORD_POLICY_INVALID",
                "stored recommendation record violates the sidecar policy",
            )
        expected = apply_recommendation_review(
            draft,
            action,
            confirmation,
            candidate_set,
            tree,
        )
        if payload != expected.to_dict():
            raise SemanticRecommendationError(
                "RECOMMENDATION_RECORD_SOURCE_MISMATCH",
                "stored recommendation record does not match trusted replay",
            )
        return expected

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RECORD_SCHEMA_VERSION,
            "record_semantics": "OPERATIONAL_FEEDBACK_ONLY",
            "identity_status": "UNVERIFIED_FILE_ASSERTION",
            "status": self.status,
            "semantic_approval": False,
            "patch_eligible": False,
            "gold_eligible": False,
            "source_confirmation_hash": self.source_confirmation_hash,
            "source_candidate_set_hash": self.source_candidate_set_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_draft_hash": self.source_draft_hash,
            "source_action_hash": self.source_action_hash,
            "reviewer_ref": self.reviewer_ref,
            "recorded_at": self.recorded_at,
            "reviewer_reasoning": self.reviewer_reasoning,
            "effective_recommendation": (
                self.effective_recommendation.to_dict()
                if self.effective_recommendation is not None
                else None
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["record_hash"] = self.record_hash
        return payload

    def aggregate_report(self) -> dict[str, Any]:
        return {
            "report_version": "recommendation-record-aggregate.v1",
            "valid": True,
            "record_semantics": "OPERATIONAL_FEEDBACK_ONLY",
            "status": self.status,
            "semantic_approval": False,
            "patch_eligible": False,
            "gold_eligible": False,
        }


def apply_recommendation_review(
    draft: SemanticRecommendationDraft,
    action: RecommendationReviewAction,
    confirmation: IntentConfirmation,
    candidate_set: CandidateSet,
    tree: CanonicalTree,
) -> RecommendationRecord:
    """Create one non-executable operational record from trusted sources."""

    trusted_draft = SemanticRecommendationDraft.from_dict(
        draft.to_dict(),
        confirmation,
        candidate_set,
        tree,
    )
    trusted_action = RecommendationReviewAction.from_dict(
        action.to_dict(),
        confirmation,
        candidate_set,
        tree,
    )
    if trusted_action.expected_draft_hash != trusted_draft.draft_hash:
        raise SemanticRecommendationError(
            "RECOMMENDATION_ACTION_STALE",
            "recommendation action does not bind the current draft",
        )
    if trusted_action.decision == "CONFIRM_RECOMMENDATION":
        status = "CONFIRMED"
        effective_recommendation = trusted_draft.to_content()
    elif trusted_action.decision == "REVISE_RECOMMENDATION":
        status = "REVISED"
        effective_recommendation = trusted_action.revised_recommendation
    else:
        status = "REJECTED"
        effective_recommendation = None
    payload = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_semantics": "OPERATIONAL_FEEDBACK_ONLY",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "status": status,
        "semantic_approval": False,
        "patch_eligible": False,
        "gold_eligible": False,
        "source_confirmation_hash": confirmation.confirmation_hash,
        "source_candidate_set_hash": candidate_set.candidate_set_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": trusted_draft.draft_hash,
        "source_action_hash": trusted_action.action_hash,
        "reviewer_ref": trusted_action.reviewer_ref,
        "recorded_at": trusted_action.recorded_at,
        "reviewer_reasoning": trusted_action.reviewer_reasoning,
        "effective_recommendation": (
            effective_recommendation.to_dict()
            if effective_recommendation is not None
            else None
        ),
    }
    return RecommendationRecord(
        status=status,
        source_confirmation_hash=confirmation.confirmation_hash,
        source_candidate_set_hash=candidate_set.candidate_set_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=trusted_draft.draft_hash,
        source_action_hash=trusted_action.action_hash,
        reviewer_ref=trusted_action.reviewer_ref,
        recorded_at=trusted_action.recorded_at,
        reviewer_reasoning=trusted_action.reviewer_reasoning,
        effective_recommendation=effective_recommendation,
        record_hash=canonical_digest(payload),
    )


def build_semantic_candidate_projection(
    confirmation: IntentConfirmation,
    candidate_set: CandidateSet,
    tree: CanonicalTree,
) -> SemanticCandidateProjection:
    """Build the fixed Top-8 model view from a trusted baseline Top-20 source."""

    if (
        not isinstance(confirmation, IntentConfirmation)
        or not isinstance(candidate_set, CandidateSet)
        or not isinstance(tree, CanonicalTree)
    ):
        raise SemanticRecommendationError(
            "SEMANTIC_SOURCE_INVALID",
            "semantic projection requires trusted typed sources",
        )
    if candidate_set.max_candidates != DEFAULT_MAX_CANDIDATES:
        raise SemanticRecommendationError(
            "SEMANTIC_CANDIDATE_POLICY_INVALID",
            "semantic projection requires the baseline Top-20 candidate source",
        )
    try:
        verify_candidate_set_against_sources(
            candidate_set,
            confirmation,
            tree,
        )
    except CandidateRetrievalError:
        raise SemanticRecommendationError(
            "SEMANTIC_CANDIDATE_SOURCE_MISMATCH",
            "candidate set does not match trusted semantic sources",
        ) from None
    if confirmation.intent is None:
        raise SemanticRecommendationError(
            "SEMANTIC_INTENT_NOT_CONFIRMED",
            "semantic projection requires confirmed intent",
        )
    candidates = tuple(
        _candidate_view(candidate)
        for candidate in candidate_set.candidates[:MAX_MODEL_CANDIDATES]
    )
    model_payload = {
        "schema_version": MODEL_INPUT_SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "intent": confirmation.intent.to_dict(),
        "candidate_status": candidate_set.status,
        "candidates": [item.to_dict() for item in candidates],
    }
    if _serialized_char_count(model_payload) > MAX_MODEL_INPUT_CHARS:
        raise SemanticRecommendationError(
            "SEMANTIC_PROJECTION_TOO_LARGE",
            "semantic candidate projection exceeds its context budget",
        )
    return SemanticCandidateProjection(
        source_confirmation_hash=confirmation.confirmation_hash,
        source_candidate_set_hash=candidate_set.candidate_set_hash,
        source_snapshot_hash=tree.snapshot_hash,
        candidate_status=candidate_set.status,
        intent=confirmation.intent,
        candidates=candidates,
        projection_hash=canonical_digest(model_payload),
    )


def _candidate_view(candidate: RetrievalCandidate) -> SemanticCandidateView:
    return SemanticCandidateView(
        candidate_ref=f"C{candidate.rank:03d}",
        rank=candidate.rank,
        kind=candidate.kind,
        label=candidate.label,
        name=candidate.name,
        path_labels=candidate.path_labels,
        value_type=candidate.value_type,
        cardinality=candidate.cardinality,
        parent_relation=candidate.score.parent_relation,
    )


def _parse_assessments(
    value: Any,
    projection: SemanticCandidateProjection,
) -> tuple[SemanticCandidateAssessment, ...]:
    if not isinstance(value, list) or len(value) > MAX_MODEL_CANDIDATES:
        raise SemanticRecommendationError(
            "SEMANTIC_ASSESSMENTS_INVALID",
            "candidate_assessments must be a bounded array",
        )
    assessments: list[SemanticCandidateAssessment] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _ASSESSMENT_KEYS:
            raise SemanticRecommendationError(
                "SEMANTIC_ASSESSMENTS_INVALID",
                "candidate assessments must use exact fields",
            )
        candidate_ref = item["candidate_ref"]
        if (
            not isinstance(candidate_ref, str)
            or _CANDIDATE_REF.fullmatch(candidate_ref) is None
        ):
            raise SemanticRecommendationError(
                "SEMANTIC_CANDIDATE_REF_INVALID",
                "candidate assessment reference is invalid",
            )
        relation = _parse_enum(
            item["relation"],
            CANDIDATE_RELATIONS,
            "SEMANTIC_RELATION_INVALID",
        )
        assessments.append(
            SemanticCandidateAssessment(
                candidate_ref=candidate_ref,
                relation=relation,
                reason=_parse_required_text(item["reason"], "reason"),
            )
        )
    refs = tuple(item.candidate_ref for item in assessments)
    if refs != projection.candidate_refs:
        raise SemanticRecommendationError(
            "SEMANTIC_CANDIDATE_COVERAGE_INVALID",
            "candidate assessments must cover the projected candidates in order",
        )
    return tuple(assessments)


def _serialized_char_count(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _parse_selected_ref(
    value: Any,
    projection: SemanticCandidateProjection,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in projection.candidate_refs:
        raise SemanticRecommendationError(
            "SEMANTIC_SELECTED_CANDIDATE_INVALID",
            "selected candidate is not in the projected candidate set",
        )
    return value


def _validate_source_policy(
    action: str,
    selected_candidate_ref: str | None,
    assessments: tuple[SemanticCandidateAssessment, ...],
    evidence_gaps: tuple[str, ...],
    clarification_question: str | None,
    projection: SemanticCandidateProjection,
) -> None:
    try:
        _validate_action_shape(
            action,
            selected_candidate_ref,
            assessments,
            evidence_gaps,
            clarification_question,
        )
    except ValueError:
        raise SemanticRecommendationError(
            "SEMANTIC_ACTION_POLICY_INVALID",
            "semantic recommendation violates its cross-field action policy",
        ) from None
    if (
        projection.candidate_status
        in {"NO_CANDIDATES", "INSUFFICIENT_SIGNAL"}
        and action in _POSITIVE_ACTION_RELATIONS
    ):
        raise SemanticRecommendationError(
            "SEMANTIC_ACTION_POLICY_INVALID",
            "empty or insufficient candidates cannot support a positive action",
        )
    if (
        assessments
        and all(item.relation == "NEED_EVIDENCE" for item in assessments)
        and action in _POSITIVE_ACTION_RELATIONS
    ):
        raise SemanticRecommendationError(
            "SEMANTIC_ACTION_POLICY_INVALID",
            "all-evidence-gap candidates cannot support a positive action",
        )
    if action == "ADD_CONTEXT_FIELD":
        intent = projection.intent
        if intent.scenario is None or not intent.confirmed_facts:
            raise SemanticRecommendationError(
                "SEMANTIC_CONTEXT_EVIDENCE_REQUIRED",
                "context extension requires a scenario and confirmed fact",
            )


def _validate_action_shape(
    action: str,
    selected_candidate_ref: str | None,
    assessments: tuple[SemanticCandidateAssessment, ...],
    evidence_gaps: tuple[str, ...],
    clarification_question: str | None,
) -> None:
    if not isinstance(action, str):
        raise ValueError("semantic action must be a string")
    relation_by_ref = {
        item.candidate_ref: item.relation for item in assessments
    }
    required_relation = _POSITIVE_ACTION_RELATIONS.get(action)
    if required_relation is not None:
        if (
            selected_candidate_ref is None
            or relation_by_ref.get(selected_candidate_ref) != required_relation
        ):
            raise ValueError("positive action requires a matching selected candidate")
    elif selected_candidate_ref is not None:
        raise ValueError("non-positive action cannot select a candidate")
    if action == "ABSTAIN" and any(
        item.relation
        in {
            "SEMANTICALLY_EQUIVALENT",
            "REUSES_CONTRACT",
            "CONTEXTUALLY_RELATED",
        }
        for item in assessments
    ):
        raise ValueError("abstain cannot carry a positive candidate relation")
    if action == "NEED_CLARIFICATION":
        if clarification_question is None:
            raise ValueError("clarification action requires one question")
    elif clarification_question is not None:
        raise ValueError("only clarification action may contain a question")
    if action == "NEED_EVIDENCE" and not evidence_gaps:
        raise ValueError("evidence action requires at least one evidence gap")


def _validate_assessment_sequence(
    assessments: tuple[SemanticCandidateAssessment, ...],
) -> None:
    refs = tuple(item.candidate_ref for item in assessments)
    expected = tuple(
        f"C{index:03d}" for index in range(1, len(assessments) + 1)
    )
    if refs != expected:
        raise ValueError(
            "semantic candidate assessments must be contiguous and ordered"
        )


def _reject_internal_ids(text_values: tuple[str, ...], tree: CanonicalTree) -> None:
    if any(_FABRICATED_INTERNAL_ID.search(text) for text in text_values):
        raise SemanticRecommendationError(
            "SEMANTIC_INTERNAL_ID_FORBIDDEN",
            "semantic recommendation text must not contain identifier-like values",
        )
    for node in tree.nodes:
        node_id = node.node_id
        if not node_id:
            continue
        if any(
            (node_id in text if len(node_id) >= 4 else node_id == text)
            for text in text_values
        ):
            raise SemanticRecommendationError(
                "SEMANTIC_INTERNAL_ID_FORBIDDEN",
                "semantic recommendation text must not contain internal identifiers",
            )


def _parse_enum(value: Any, allowed: set[str], code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SemanticRecommendationError(code, "value is not allowlisted")
    return value


def _parse_required_text(value: Any, field_name: str) -> str:
    try:
        return _required_text(value, field_name).strip()
    except ValueError:
        raise SemanticRecommendationError(
            "SEMANTIC_TEXT_INVALID",
            f"{field_name} must be bounded printable text",
        ) from None


def _parse_optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _parse_required_text(value, field_name)


def _parse_text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > _MAX_LIST_ITEMS:
        raise SemanticRecommendationError(
            "SEMANTIC_TEXT_LIST_INVALID",
            f"{field_name} must be a bounded unique text array",
        )
    parsed: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _parse_required_text(item, field_name)
        if text in seen:
            raise SemanticRecommendationError(
                "SEMANTIC_TEXT_LIST_INVALID",
                f"{field_name} must be a bounded unique text array",
            )
        seen.add(text)
        parsed.append(text)
    return tuple(parsed)


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


def _validate_text_tuple(value: Any, field_name: str) -> None:
    if not isinstance(value, tuple) or len(value) > _MAX_LIST_ITEMS:
        raise ValueError(f"{field_name} must be an immutable unique tuple")
    seen: set[str] = set()
    for item in value:
        _required_text(item, field_name)
        if item in seen:
            raise ValueError(f"{field_name} must be an immutable unique tuple")
        seen.add(item)


def _validate_digest(value: Any) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("semantic source hash must be a SHA-256 digest")


def _parse_digest(value: Any, field_name: str) -> str:
    try:
        _validate_digest(value)
    except ValueError:
        raise SemanticRecommendationError(
            "RECOMMENDATION_DIGEST_INVALID",
            f"{field_name} must be a SHA-256 digest",
        ) from None
    return value


def _validate_identifier(value: Any) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("reviewer_ref must be an opaque identifier")


def _parse_identifier(value: Any, field_name: str) -> str:
    try:
        _validate_identifier(value)
    except ValueError:
        raise SemanticRecommendationError(
            "RECOMMENDATION_IDENTIFIER_INVALID",
            f"{field_name} must be an opaque identifier",
        ) from None
    return value


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ValueError("recorded_at must use strict RFC3339")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at must include a timezone")


def _parse_timestamp(value: Any) -> str:
    try:
        _validate_timestamp(value)
    except (TypeError, ValueError):
        raise SemanticRecommendationError(
            "RECOMMENDATION_TIMESTAMP_INVALID",
            "recorded_at must use strict RFC3339",
        ) from None
    return value


def _parse_optional_bounded_text(
    value: Any,
    field_name: str,
    *,
    max_chars: int,
) -> str | None:
    if value is None:
        return None
    try:
        return _required_text(
            value,
            field_name,
            max_chars=max_chars,
        ).strip()
    except ValueError:
        raise SemanticRecommendationError(
            "RECOMMENDATION_REASONING_INVALID",
            f"{field_name} must be bounded printable text",
        ) from None


__all__ = [
    "CANDIDATE_RELATIONS",
    "CONTENT_SCHEMA_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "MAX_MODEL_CANDIDATES",
    "MAX_MODEL_INPUT_CHARS",
    "MODEL_INPUT_SCHEMA_VERSION",
    "MODEL_OUTPUT_SCHEMA_VERSION",
    "PROJECTION_VERSION",
    "RECORD_SCHEMA_VERSION",
    "RECOMMENDED_ACTIONS",
    "REVIEW_ACTION_SCHEMA_VERSION",
    "REVIEW_DECISIONS",
    "RecommendationRecord",
    "RecommendationReviewAction",
    "SemanticCandidateAssessment",
    "SemanticCandidateProjection",
    "SemanticCandidateView",
    "SemanticRecommendationContent",
    "SemanticRecommendationDraft",
    "SemanticRecommendationError",
    "apply_recommendation_review",
    "build_semantic_candidate_projection",
]
