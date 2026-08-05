"""Relation-only semantic output and deterministic recommendation policy v2."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import IntentConfirmation, MODEL_PROVENANCE_STATUS
from treeguard.change_understanding_v2 import (
    ChangeUnderstandingV2,
    StructuralIntentV2,
)
from treeguard.hashing import canonical_digest
from treeguard.model_safety import contains_internal_identifier
from treeguard.models import CanonicalTree
from treeguard.semantic_recommendation import (
    CANDIDATE_RELATIONS,
    MAX_MODEL_CANDIDATES,
    MAX_MODEL_INPUT_CHARS,
    SemanticCandidateAssessment,
    SemanticCandidateProjection,
    SemanticCandidateView,
)


MODEL_INPUT_SCHEMA_VERSION = "semantic-relation-model-input.v2"
MODEL_OUTPUT_SCHEMA_VERSION = "semantic-relation-model-output.v2"
PROJECTION_VERSION = "treeguard.semantic-relation-projection.v2"
DRAFT_SCHEMA_VERSION = "semantic-relation-draft.v2"
DECISION_SCHEMA_VERSION = "recommendation-policy-decision.v2"
POLICY_VERSION = "treeguard.deterministic-recommendation-policy.v2"
_MODEL_OUTPUT_KEYS = {"schema_version", "candidate_assessments"}
_ASSESSMENT_KEYS = {"candidate_ref", "relation", "reason"}
_DRAFT_KEYS = {
    "schema_version",
    "model_provider",
    "model_capability",
    "model_name",
    "prompt_version",
    "model_provenance_status",
    "semantic_approval",
    "patch_eligible",
    "source_projection_hash",
    "source_snapshot_hash",
    "candidate_assessments",
    "draft_hash",
}
_DECISION_KEYS = {
    "schema_version",
    "policy_version",
    "semantic_approval",
    "patch_eligible",
    "source_understanding_hash",
    "source_projection_hash",
    "source_relation_draft_hash",
    "recommended_action",
    "selected_candidate_ref",
    "decision_reason_code",
    "decision_hash",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_REF = re.compile(r"^C00[1-8]$")


class SemanticPolicyV2Error(ValueError):
    """A v2 semantic relation or deterministic policy contract failed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SemanticRelationProjectionV2:
    source_understanding_hash: str
    source_confirmation_hash: str
    source_candidate_set_hash: str
    source_snapshot_hash: str
    candidate_status: str
    structural_intent: StructuralIntentV2
    candidates: tuple[SemanticCandidateView, ...]
    projection_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_understanding_hash,
            self.source_confirmation_hash,
            self.source_candidate_set_hash,
            self.source_snapshot_hash,
            self.projection_hash,
        ):
            _digest(value)
        if self.candidate_status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("semantic v2 candidate status is invalid")
        if not isinstance(self.structural_intent, StructuralIntentV2):
            raise ValueError("semantic v2 projection requires StructuralIntentV2")
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_MODEL_CANDIDATES
            or any(
                not isinstance(item, SemanticCandidateView)
                for item in self.candidates
            )
        ):
            raise ValueError("semantic v2 candidates are invalid")
        expected_refs = tuple(
            f"C{index:03d}" for index in range(1, len(self.candidates) + 1)
        )
        if tuple(item.candidate_ref for item in self.candidates) != expected_refs:
            raise ValueError("semantic v2 candidate refs are not contiguous")
        if (self.candidate_status == "CANDIDATES_READY") != bool(
            self.candidates
        ):
            raise ValueError("semantic v2 candidate status and items disagree")
        model_payload = self.to_model_dict()
        if _serialized_char_count(model_payload) > MAX_MODEL_INPUT_CHARS:
            raise ValueError("semantic v2 projection exceeds its size limit")
        if self.projection_hash != canonical_digest(model_payload):
            raise ValueError("semantic v2 projection hash does not match")

    @property
    def candidate_refs(self) -> tuple[str, ...]:
        return tuple(item.candidate_ref for item in self.candidates)

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_INPUT_SCHEMA_VERSION,
            "projection_version": PROJECTION_VERSION,
            "structural_intent": {
                "node_kind": self.structural_intent.node_kind,
                "value_type": self.structural_intent.value_type,
                "cardinality": self.structural_intent.cardinality,
            },
            "candidate_status": self.candidate_status,
            "candidates": [item.to_dict() for item in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class SemanticRelationDraftV2:
    model_provider: str
    model_capability: str
    model_name: str
    prompt_version: str
    source_projection_hash: str
    source_snapshot_hash: str
    candidate_assessments: tuple[SemanticCandidateAssessment, ...]
    draft_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.model_provider,
            self.model_capability,
            self.model_name,
            self.prompt_version,
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("semantic v2 model metadata is invalid")
        _digest(self.source_projection_hash)
        _digest(self.source_snapshot_hash)
        if (
            not isinstance(self.candidate_assessments, tuple)
            or len(self.candidate_assessments) > MAX_MODEL_CANDIDATES
            or any(
                not isinstance(item, SemanticCandidateAssessment)
                for item in self.candidate_assessments
            )
        ):
            raise ValueError("semantic v2 assessments are invalid")
        expected_refs = tuple(
            f"C{index:03d}"
            for index in range(1, len(self.candidate_assessments) + 1)
        )
        if (
            tuple(item.candidate_ref for item in self.candidate_assessments)
            != expected_refs
        ):
            raise ValueError("semantic v2 assessment refs are not contiguous")
        _digest(self.draft_hash)
        if self.draft_hash != canonical_digest(self._payload()):
            raise ValueError("semantic v2 draft hash does not match")

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
            "source_projection_hash": self.source_projection_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "candidate_assessments": [
                item.to_dict() for item in self.candidate_assessments
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "draft_hash": self.draft_hash}

    @classmethod
    def from_model_dict(
        cls,
        payload: Any,
        projection: SemanticRelationProjectionV2,
        tree: CanonicalTree,
        *,
        model_provider: str,
        model_capability: str,
        model_name: str,
        prompt_version: str,
    ) -> "SemanticRelationDraftV2":
        _validate_projection_sources(projection, tree)
        if not isinstance(payload, dict) or set(payload) != _MODEL_OUTPUT_KEYS:
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_MODEL_FIELDS_INVALID",
                "semantic v2 model output must use exact fields",
            )
        if payload["schema_version"] != MODEL_OUTPUT_SCHEMA_VERSION:
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_MODEL_VERSION_INVALID",
                "semantic v2 model output version is unsupported",
            )
        assessments = _parse_assessments(
            payload["candidate_assessments"],
            projection,
        )
        if contains_internal_identifier(
            (item.reason for item in assessments),
            (node.node_id for node in tree.nodes),
        ):
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_INTERNAL_ID_FORBIDDEN",
                "semantic v2 reasons must not contain internal identifiers",
            )
        metadata = {
            "model_provider": _model_text(model_provider),
            "model_capability": _model_text(model_capability),
            "model_name": _model_text(model_name),
            "prompt_version": _model_text(prompt_version),
        }
        draft_payload = {
            "schema_version": DRAFT_SCHEMA_VERSION,
            **metadata,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "semantic_approval": False,
            "patch_eligible": False,
            "source_projection_hash": projection.projection_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "candidate_assessments": [item.to_dict() for item in assessments],
        }
        return cls(
            **metadata,
            source_projection_hash=projection.projection_hash,
            source_snapshot_hash=tree.snapshot_hash,
            candidate_assessments=assessments,
            draft_hash=canonical_digest(draft_payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        projection: SemanticRelationProjectionV2,
        tree: CanonicalTree,
    ) -> "SemanticRelationDraftV2":
        if not isinstance(payload, dict) or set(payload) != _DRAFT_KEYS:
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_DRAFT_FIELDS_INVALID",
                "stored semantic v2 draft must use exact fields",
            )
        if (
            payload["schema_version"] != DRAFT_SCHEMA_VERSION
            or payload["model_provenance_status"] != MODEL_PROVENANCE_STATUS
            or payload["semantic_approval"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_DRAFT_POLICY_INVALID",
                "stored semantic v2 draft violates fixed policy",
            )
        model_payload = {
            "schema_version": MODEL_OUTPUT_SCHEMA_VERSION,
            "candidate_assessments": payload["candidate_assessments"],
        }
        draft = cls.from_model_dict(
            model_payload,
            projection,
            tree,
            model_provider=payload["model_provider"],
            model_capability=payload["model_capability"],
            model_name=payload["model_name"],
            prompt_version=payload["prompt_version"],
        )
        if draft.to_dict() != payload:
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_DRAFT_SOURCE_MISMATCH",
                "stored semantic v2 draft does not replay from trusted sources",
            )
        return draft


@dataclass(frozen=True, slots=True)
class RecommendationPolicyDecisionV2:
    source_understanding_hash: str
    source_projection_hash: str
    source_relation_draft_hash: str
    recommended_action: str
    selected_candidate_ref: str | None
    decision_reason_code: str
    decision_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_understanding_hash,
            self.source_projection_hash,
            self.source_relation_draft_hash,
            self.decision_hash,
        ):
            _digest(value)
        if self.recommended_action not in {
            "USE_EXISTING_NODE",
            "NEED_CLARIFICATION",
            "NEED_EVIDENCE",
            "ABSTAIN",
        }:
            raise ValueError("semantic v2 policy action is unsupported")
        if self.selected_candidate_ref is not None and (
            not isinstance(self.selected_candidate_ref, str)
            or _CANDIDATE_REF.fullmatch(self.selected_candidate_ref) is None
        ):
            raise ValueError("semantic v2 selected candidate is invalid")
        if self.decision_reason_code not in {
            "UNIQUE_COMPATIBLE_EQUIVALENT",
            "MULTIPLE_COMPATIBLE_EQUIVALENTS",
            "CANDIDATE_EVIDENCE_REQUIRED",
            "NO_COMPATIBLE_EQUIVALENT",
        }:
            raise ValueError("semantic v2 decision reason is unsupported")
        if (self.recommended_action == "USE_EXISTING_NODE") != (
            self.selected_candidate_ref is not None
        ):
            raise ValueError("semantic v2 action and target disagree")
        expected_decision_shape = {
            "UNIQUE_COMPATIBLE_EQUIVALENT": ("USE_EXISTING_NODE", True),
            "MULTIPLE_COMPATIBLE_EQUIVALENTS": (
                "NEED_CLARIFICATION",
                False,
            ),
            "CANDIDATE_EVIDENCE_REQUIRED": ("NEED_EVIDENCE", False),
            "NO_COMPATIBLE_EQUIVALENT": ("ABSTAIN", False),
        }
        expected_action, requires_target = expected_decision_shape[
            self.decision_reason_code
        ]
        if self.recommended_action != expected_action or (
            (self.selected_candidate_ref is not None) != requires_target
        ):
            raise ValueError("semantic v2 action and reason disagree")
        _digest(self.decision_hash)
        if self.decision_hash != canonical_digest(self._payload()):
            raise ValueError("semantic v2 decision hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "semantic_approval": False,
            "patch_eligible": False,
            "source_understanding_hash": self.source_understanding_hash,
            "source_projection_hash": self.source_projection_hash,
            "source_relation_draft_hash": self.source_relation_draft_hash,
            "recommended_action": self.recommended_action,
            "selected_candidate_ref": self.selected_candidate_ref,
            "decision_reason_code": self.decision_reason_code,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "decision_hash": self.decision_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        draft: SemanticRelationDraftV2,
        projection: SemanticRelationProjectionV2,
        understanding: ChangeUnderstandingV2,
    ) -> "RecommendationPolicyDecisionV2":
        if not isinstance(payload, dict) or set(payload) != _DECISION_KEYS:
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_DECISION_FIELDS_INVALID",
                "stored policy decision must use exact fields",
            )
        if (
            payload["schema_version"] != DECISION_SCHEMA_VERSION
            or payload["policy_version"] != POLICY_VERSION
            or payload["semantic_approval"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_DECISION_POLICY_INVALID",
                "stored policy decision violates fixed policy",
            )
        trusted = apply_deterministic_recommendation_policy_v2(
            draft,
            projection,
            understanding,
        )
        if trusted.to_dict() != payload:
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_DECISION_SOURCE_MISMATCH",
                "stored decision does not replay from trusted sources",
            )
        return trusted


def build_semantic_relation_projection_v2(
    understanding: ChangeUnderstandingV2,
    legacy_projection: SemanticCandidateProjection,
    confirmation: IntentConfirmation,
) -> SemanticRelationProjectionV2:
    """Migrate one trusted v1 candidate projection without changing Retrieval."""

    if (
        not isinstance(understanding, ChangeUnderstandingV2)
        or not isinstance(legacy_projection, SemanticCandidateProjection)
        or not isinstance(confirmation, IntentConfirmation)
    ):
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_SOURCE_INVALID",
            "semantic v2 migration requires trusted typed sources",
        )
    if understanding.review_status != "READY_FOR_HUMAN_REVIEW":
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_CLARIFICATION_REQUIRED",
            "unresolved structural intent cannot enter semantic comparison",
        )
    if (
        understanding.source_snapshot_hash
        != legacy_projection.source_snapshot_hash
        or legacy_projection.source_confirmation_hash
        != confirmation.confirmation_hash
        or understanding.source_request_hash
        != confirmation.source_request_hash
        or understanding.source_snapshot_hash
        != confirmation.source_snapshot_hash
    ):
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_SOURCE_MISMATCH",
            "semantic v2 sources bind different snapshots",
        )
    model_payload = {
        "schema_version": MODEL_INPUT_SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "structural_intent": {
            "node_kind": understanding.structural_intent.node_kind,
            "value_type": understanding.structural_intent.value_type,
            "cardinality": understanding.structural_intent.cardinality,
        },
        "candidate_status": legacy_projection.candidate_status,
        "candidates": [
            item.to_dict() for item in legacy_projection.candidates
        ],
    }
    if _serialized_char_count(model_payload) > MAX_MODEL_INPUT_CHARS:
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_PROJECTION_TOO_LARGE",
            "semantic v2 projection exceeds its context budget",
        )
    return SemanticRelationProjectionV2(
        source_understanding_hash=understanding.understanding_hash,
        source_confirmation_hash=confirmation.confirmation_hash,
        source_candidate_set_hash=legacy_projection.source_candidate_set_hash,
        source_snapshot_hash=legacy_projection.source_snapshot_hash,
        candidate_status=legacy_projection.candidate_status,
        structural_intent=understanding.structural_intent,
        candidates=legacy_projection.candidates,
        projection_hash=canonical_digest(model_payload),
    )


def apply_deterministic_recommendation_policy_v2(
    draft: SemanticRelationDraftV2,
    projection: SemanticRelationProjectionV2,
    understanding: ChangeUnderstandingV2,
) -> RecommendationPolicyDecisionV2:
    if (
        not isinstance(draft, SemanticRelationDraftV2)
        or not isinstance(projection, SemanticRelationProjectionV2)
        or not isinstance(understanding, ChangeUnderstandingV2)
        or draft.source_projection_hash != projection.projection_hash
        or draft.source_snapshot_hash != projection.source_snapshot_hash
        or projection.source_understanding_hash
        != understanding.understanding_hash
        or projection.structural_intent != understanding.structural_intent
    ):
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_POLICY_SOURCE_MISMATCH",
            "semantic v2 policy sources do not align",
        )
    candidate_by_ref = {
        item.candidate_ref: item for item in projection.candidates
    }
    equivalent_refs = tuple(
        assessment.candidate_ref
        for assessment in draft.candidate_assessments
        if assessment.relation == "SEMANTICALLY_EQUIVALENT"
        and _compatible(
            understanding.structural_intent,
            candidate_by_ref[assessment.candidate_ref],
        )
    )
    if len(equivalent_refs) == 1:
        action = "USE_EXISTING_NODE"
        selected_ref = equivalent_refs[0]
        reason = "UNIQUE_COMPATIBLE_EQUIVALENT"
    elif len(equivalent_refs) > 1:
        action = "NEED_CLARIFICATION"
        selected_ref = None
        reason = "MULTIPLE_COMPATIBLE_EQUIVALENTS"
    elif any(
        item.relation == "NEED_EVIDENCE"
        for item in draft.candidate_assessments
    ):
        action = "NEED_EVIDENCE"
        selected_ref = None
        reason = "CANDIDATE_EVIDENCE_REQUIRED"
    else:
        action = "ABSTAIN"
        selected_ref = None
        reason = "NO_COMPATIBLE_EQUIVALENT"
    decision_payload = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "semantic_approval": False,
        "patch_eligible": False,
        "source_understanding_hash": understanding.understanding_hash,
        "source_projection_hash": projection.projection_hash,
        "source_relation_draft_hash": draft.draft_hash,
        "recommended_action": action,
        "selected_candidate_ref": selected_ref,
        "decision_reason_code": reason,
    }
    return RecommendationPolicyDecisionV2(
        source_understanding_hash=understanding.understanding_hash,
        source_projection_hash=projection.projection_hash,
        source_relation_draft_hash=draft.draft_hash,
        recommended_action=action,
        selected_candidate_ref=selected_ref,
        decision_reason_code=reason,
        decision_hash=canonical_digest(decision_payload),
    )


def _parse_assessments(
    value: Any,
    projection: SemanticRelationProjectionV2,
) -> tuple[SemanticCandidateAssessment, ...]:
    if not isinstance(value, list) or len(value) > MAX_MODEL_CANDIDATES:
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_ASSESSMENTS_INVALID",
            "semantic v2 assessments must be a bounded array",
        )
    assessments = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _ASSESSMENT_KEYS:
            raise SemanticPolicyV2Error(
                "SEMANTIC_V2_ASSESSMENTS_INVALID",
                "semantic v2 assessment fields are invalid",
            )
        try:
            assessment = SemanticCandidateAssessment(
                candidate_ref=item["candidate_ref"],
                relation=item["relation"],
                reason=item["reason"],
            )
        except (KeyError, TypeError, ValueError):
            code = (
                "SEMANTIC_V2_RELATION_INVALID"
                if isinstance(item.get("relation"), str)
                and item.get("relation") not in CANDIDATE_RELATIONS
                else "SEMANTIC_V2_ASSESSMENTS_INVALID"
            )
            raise SemanticPolicyV2Error(
                code,
                "semantic v2 assessment failed local validation",
            ) from None
        assessments.append(assessment)
    parsed = tuple(assessments)
    if tuple(item.candidate_ref for item in parsed) != projection.candidate_refs:
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_CANDIDATE_COVERAGE_INVALID",
            "semantic v2 assessments must cover candidates in order",
        )
    return parsed


def _compatible(
    intent: StructuralIntentV2,
    candidate: SemanticCandidateView,
) -> bool:
    return not (
        (intent.node_kind != "UNKNOWN" and candidate.kind != intent.node_kind)
        or (
            intent.value_type is not None
            and candidate.value_type != intent.value_type
        )
        or (
            intent.cardinality != "UNKNOWN"
            and candidate.cardinality != intent.cardinality
        )
    )


def _validate_projection_sources(
    projection: SemanticRelationProjectionV2,
    tree: CanonicalTree,
) -> None:
    if (
        not isinstance(projection, SemanticRelationProjectionV2)
        or not isinstance(tree, CanonicalTree)
        or projection.source_snapshot_hash != tree.snapshot_hash
    ):
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_SOURCE_MISMATCH",
            "semantic v2 projection does not bind the trusted tree",
        )


def _model_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1_000:
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_MODEL_METADATA_INVALID",
            "semantic v2 model metadata is invalid",
        )
    normalized = value.strip()
    if any(
        ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF
        for char in normalized
    ):
        raise SemanticPolicyV2Error(
            "SEMANTIC_V2_MODEL_METADATA_INVALID",
            "semantic v2 model metadata contains forbidden characters",
        )
    return normalized


def _serialized_char_count(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _digest(value: Any) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("semantic v2 source must be a SHA-256 digest")


__all__ = [
    "DECISION_SCHEMA_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "MODEL_INPUT_SCHEMA_VERSION",
    "MODEL_OUTPUT_SCHEMA_VERSION",
    "POLICY_VERSION",
    "PROJECTION_VERSION",
    "RecommendationPolicyDecisionV2",
    "SemanticPolicyV2Error",
    "SemanticRelationDraftV2",
    "SemanticRelationProjectionV2",
    "apply_deterministic_recommendation_policy_v2",
    "build_semantic_relation_projection_v2",
]
