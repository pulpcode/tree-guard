"""Deterministic contracts for the bounded navigation Copilot Shadow slice."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import IntentRequest
from treeguard.change_understanding_v2 import (
    ChangeUnderstandingV2,
    StructuralIntentV2,
)
from treeguard.hashing import canonical_digest
from treeguard.model_safety import contains_internal_identifier
from treeguard.models import CanonicalTree
from treeguard.retrieval import CandidateRetrievalError
from treeguard.retrieval_query import (
    DecoupledCandidateSet,
    build_copilot_retrieval_query,
    build_decoupled_candidate_set,
)
from treeguard.retrieval_role_tolerant import (
    SIMILARITY_SCALE,
    build_boundary_role_features,
)
from treeguard.semantic_recommendation import (
    CANDIDATE_RELATIONS,
    MAX_MODEL_CANDIDATES,
    MAX_MODEL_INPUT_CHARS,
    SemanticCandidateAssessment,
    SemanticCandidateView,
)


INTERPRETATION_SCHEMA_VERSION = "navigation-copilot-interpretation.v1"
CLARIFICATION_ANSWER_SCHEMA_VERSION = "navigation-copilot-clarification-answer.v1"
CLARIFICATION_ROUND_SCHEMA_VERSION = "navigation-copilot-clarification-round.v1"
CANDIDATE_SET_SCHEMA_VERSION = "navigation-copilot-candidate-set.v1"
CANDIDATE_ALGORITHM_VERSION = "treeguard.navigation-copilot-soft-rerank.v1"
SEMANTIC_INPUT_SCHEMA_VERSION = "navigation-copilot-semantic-input.v1"
SEMANTIC_PROJECTION_SCHEMA_VERSION = "navigation-copilot-semantic-projection.v1"
SEMANTIC_OUTPUT_SCHEMA_VERSION = "navigation-copilot-semantic-output.v1"
SEMANTIC_DRAFT_SCHEMA_VERSION = "navigation-copilot-semantic-draft.v1"
POLICY_DECISION_SCHEMA_VERSION = "navigation-copilot-policy-decision.v1"
POLICY_VERSION = "treeguard.navigation-copilot-policy.v1"
OUTCOME_SCHEMA_VERSION = "navigation-copilot-outcome.v1"
MAX_INTERNAL_CANDIDATES = 40

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_CANDIDATE_REF = re.compile(r"^C[0-9]{3}$")
_MAX_TEXT_CHARS = 8_000
_TARGET_NAME_WEIGHT = 300
_TARGET_PATH_WEIGHT = 150
_SCOPE_NAME_WEIGHT = 20
_SCOPE_PATH_WEIGHT = 50
_EXCLUSION_PENALTY = 200


class NavigationCopilotError(ValueError):
    """A navigation Copilot artifact failed a stable local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NavigationInterpretation:
    status: str
    source_request_hash: str
    source_snapshot_hash: str
    understanding: ChangeUnderstandingV2 | None
    degradation_code: str | None
    interpretation_hash: str

    def __post_init__(self) -> None:
        _digest(self.source_request_hash)
        _digest(self.source_snapshot_hash)
        _digest(self.interpretation_hash)
        if self.status not in {"MODEL_VALID", "MODEL_DEGRADED"}:
            raise ValueError("navigation interpretation status is invalid")
        if self.status == "MODEL_VALID":
            if (
                not isinstance(self.understanding, ChangeUnderstandingV2)
                or self.degradation_code is not None
                or self.understanding.source_request_hash
                != self.source_request_hash
                or self.understanding.source_snapshot_hash
                != self.source_snapshot_hash
            ):
                raise ValueError("valid navigation interpretation is inconsistent")
        elif self.understanding is not None or not _valid_code(
            self.degradation_code
        ):
            raise ValueError("degraded navigation interpretation is inconsistent")
        if self.interpretation_hash != canonical_digest(self._payload()):
            raise ValueError("navigation interpretation hash does not match")

    @property
    def structural_intent(self) -> StructuralIntentV2 | None:
        return (
            self.understanding.structural_intent
            if self.understanding is not None
            else None
        )

    @property
    def needs_clarification(self) -> bool:
        return (
            self.structural_intent is not None
            and self.structural_intent.clarification_question is not None
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": INTERPRETATION_SCHEMA_VERSION,
            "status": self.status,
            "source_request_hash": self.source_request_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "understanding": (
                self.understanding.to_dict()
                if self.understanding is not None
                else None
            ),
            "degradation_code": self.degradation_code,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "interpretation_hash": self.interpretation_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> "NavigationInterpretation":
        _trusted_sources(request, tree)
        keys = {
            "schema_version", "status", "source_request_hash",
            "source_snapshot_hash", "understanding", "degradation_code",
            "interpretation_hash",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise NavigationCopilotError(
                "COPILOT_INTERPRETATION_FIELDS_INVALID",
                "stored interpretation must use exact fields",
            )
        if payload["schema_version"] != INTERPRETATION_SCHEMA_VERSION:
            raise NavigationCopilotError(
                "COPILOT_INTERPRETATION_VERSION_INVALID",
                "stored interpretation version is unsupported",
            )
        try:
            understanding = (
                ChangeUnderstandingV2.from_dict(
                    payload["understanding"], request, tree
                )
                if payload["understanding"] is not None
                else None
            )
            artifact = cls(
                status=payload["status"],
                source_request_hash=payload["source_request_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                understanding=understanding,
                degradation_code=payload["degradation_code"],
                interpretation_hash=payload["interpretation_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise NavigationCopilotError(
                "COPILOT_INTERPRETATION_INVALID",
                "stored interpretation failed local validation",
            ) from None
        if (
            artifact.source_request_hash != request.request_hash
            or artifact.source_snapshot_hash != tree.snapshot_hash
        ):
            raise NavigationCopilotError(
                "COPILOT_INTERPRETATION_SOURCE_MISMATCH",
                "stored interpretation does not bind trusted sources",
            )
        return artifact

    @classmethod
    def valid(
        cls,
        understanding: ChangeUnderstandingV2,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> "NavigationInterpretation":
        _trusted_sources(request, tree)
        if (
            not isinstance(understanding, ChangeUnderstandingV2)
            or understanding.source_request_hash != request.request_hash
            or understanding.source_snapshot_hash != tree.snapshot_hash
        ):
            raise NavigationCopilotError(
                "COPILOT_INTERPRETATION_SOURCE_MISMATCH",
                "understanding does not bind trusted navigation sources",
            )
        payload = {
            "schema_version": INTERPRETATION_SCHEMA_VERSION,
            "status": "MODEL_VALID",
            "source_request_hash": request.request_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "understanding": understanding.to_dict(),
            "degradation_code": None,
        }
        return cls(
            status="MODEL_VALID",
            source_request_hash=request.request_hash,
            source_snapshot_hash=tree.snapshot_hash,
            understanding=understanding,
            degradation_code=None,
            interpretation_hash=canonical_digest(payload),
        )

    @classmethod
    def degraded(
        cls,
        request: IntentRequest,
        tree: CanonicalTree,
        *,
        degradation_code: str,
    ) -> "NavigationInterpretation":
        _trusted_sources(request, tree)
        if not _valid_code(degradation_code):
            raise NavigationCopilotError(
                "COPILOT_DEGRADATION_CODE_INVALID",
                "degradation code must be a stable code",
            )
        payload = {
            "schema_version": INTERPRETATION_SCHEMA_VERSION,
            "status": "MODEL_DEGRADED",
            "source_request_hash": request.request_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "understanding": None,
            "degradation_code": degradation_code,
        }
        return cls(
            status="MODEL_DEGRADED",
            source_request_hash=request.request_hash,
            source_snapshot_hash=tree.snapshot_hash,
            understanding=None,
            degradation_code=degradation_code,
            interpretation_hash=canonical_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class NavigationClarificationAnswer:
    source_interpretation_hash: str
    answer_text: str
    recorded_at: str
    answer_hash: str

    def __post_init__(self) -> None:
        _digest(self.source_interpretation_hash)
        _bounded_text(self.answer_text, "answer_text")
        _bounded_text(self.recorded_at, "recorded_at", maximum=128)
        _digest(self.answer_hash)
        if self.answer_hash != canonical_digest(self._payload()):
            raise ValueError("navigation clarification answer hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": CLARIFICATION_ANSWER_SCHEMA_VERSION,
            "identity_status": "UNVERIFIED_WORKBENCH_ASSERTION",
            "source_interpretation_hash": self.source_interpretation_hash,
            "answer_text": self.answer_text,
            "recorded_at": self.recorded_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "answer_hash": self.answer_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        interpretation: NavigationInterpretation,
    ) -> "NavigationClarificationAnswer":
        keys = {
            "schema_version", "identity_status",
            "source_interpretation_hash", "answer_text", "recorded_at",
            "answer_hash",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != keys
            or payload.get("schema_version")
            != CLARIFICATION_ANSWER_SCHEMA_VERSION
            or payload.get("identity_status")
            != "UNVERIFIED_WORKBENCH_ASSERTION"
        ):
            raise NavigationCopilotError(
                "COPILOT_CLARIFICATION_ANSWER_INVALID",
                "stored clarification answer violates its contract",
            )
        try:
            artifact = cls(
                source_interpretation_hash=payload["source_interpretation_hash"],
                answer_text=payload["answer_text"],
                recorded_at=payload["recorded_at"],
                answer_hash=payload["answer_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise NavigationCopilotError(
                "COPILOT_CLARIFICATION_ANSWER_INVALID",
                "stored clarification answer failed local validation",
            ) from None
        if artifact.source_interpretation_hash != interpretation.interpretation_hash:
            raise NavigationCopilotError(
                "COPILOT_CLARIFICATION_SOURCE_MISMATCH",
                "stored clarification answer is stale",
            )
        return artifact

    @classmethod
    def create(
        cls,
        interpretation: NavigationInterpretation,
        *,
        answer_text: str,
        recorded_at: str,
    ) -> "NavigationClarificationAnswer":
        if not isinstance(interpretation, NavigationInterpretation) or not (
            interpretation.status == "MODEL_VALID"
            and interpretation.needs_clarification
        ):
            raise NavigationCopilotError(
                "COPILOT_CLARIFICATION_NOT_REQUIRED",
                "clarification answer requires an unresolved valid interpretation",
            )
        payload = {
            "schema_version": CLARIFICATION_ANSWER_SCHEMA_VERSION,
            "identity_status": "UNVERIFIED_WORKBENCH_ASSERTION",
            "source_interpretation_hash": interpretation.interpretation_hash,
            "answer_text": _bounded_text(answer_text, "answer_text").strip(),
            "recorded_at": _bounded_text(
                recorded_at, "recorded_at", maximum=128
            ).strip(),
        }
        return cls(
            source_interpretation_hash=interpretation.interpretation_hash,
            answer_text=payload["answer_text"],
            recorded_at=payload["recorded_at"],
            answer_hash=canonical_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class NavigationClarificationRound:
    source_initial_interpretation_hash: str
    source_answer_hash: str
    revised_interpretation: NavigationInterpretation
    round_hash: str

    def __post_init__(self) -> None:
        _digest(self.source_initial_interpretation_hash)
        _digest(self.source_answer_hash)
        _digest(self.round_hash)
        if not isinstance(self.revised_interpretation, NavigationInterpretation):
            raise ValueError("clarification round requires revised interpretation")
        if self.round_hash != canonical_digest(self._payload()):
            raise ValueError("navigation clarification round hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": CLARIFICATION_ROUND_SCHEMA_VERSION,
            "source_initial_interpretation_hash": (
                self.source_initial_interpretation_hash
            ),
            "source_answer_hash": self.source_answer_hash,
            "revised_interpretation": self.revised_interpretation.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "round_hash": self.round_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        initial: NavigationInterpretation,
        answer: NavigationClarificationAnswer,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> "NavigationClarificationRound":
        keys = {
            "schema_version", "source_initial_interpretation_hash",
            "source_answer_hash", "revised_interpretation", "round_hash",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != keys
            or payload.get("schema_version") != CLARIFICATION_ROUND_SCHEMA_VERSION
        ):
            raise NavigationCopilotError(
                "COPILOT_CLARIFICATION_ROUND_INVALID",
                "stored clarification round violates its contract",
            )
        revised = NavigationInterpretation.from_dict(
            payload["revised_interpretation"], request, tree
        )
        expected = cls.create(initial, answer, revised)
        if expected.to_dict() != payload:
            raise NavigationCopilotError(
                "COPILOT_CLARIFICATION_SOURCE_MISMATCH",
                "stored clarification round does not replay",
            )
        return expected

    @classmethod
    def create(
        cls,
        initial: NavigationInterpretation,
        answer: NavigationClarificationAnswer,
        revised: NavigationInterpretation,
    ) -> "NavigationClarificationRound":
        if (
            not isinstance(initial, NavigationInterpretation)
            or not initial.needs_clarification
            or not isinstance(answer, NavigationClarificationAnswer)
            or answer.source_interpretation_hash != initial.interpretation_hash
            or not isinstance(revised, NavigationInterpretation)
            or revised.source_request_hash != initial.source_request_hash
            or revised.source_snapshot_hash != initial.source_snapshot_hash
        ):
            raise NavigationCopilotError(
                "COPILOT_CLARIFICATION_SOURCE_MISMATCH",
                "clarification sources do not align",
            )
        payload = {
            "schema_version": CLARIFICATION_ROUND_SCHEMA_VERSION,
            "source_initial_interpretation_hash": initial.interpretation_hash,
            "source_answer_hash": answer.answer_hash,
            "revised_interpretation": revised.to_dict(),
        }
        return cls(
            source_initial_interpretation_hash=initial.interpretation_hash,
            source_answer_hash=answer.answer_hash,
            revised_interpretation=revised,
            round_hash=canonical_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class NavigationCandidateScore:
    base_total: int
    target_bonus: int
    scope_bonus: int
    exclusion_penalty: int
    total: int
    parent_relation: str

    def __post_init__(self) -> None:
        values = (
            self.base_total,
            self.target_bonus,
            self.scope_bonus,
            self.exclusion_penalty,
            self.total,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values
        ):
            raise ValueError("navigation candidate scores must be non-negative")
        if self.total != max(
            0,
            self.base_total
            + self.target_bonus
            + self.scope_bonus
            - self.exclusion_penalty,
        ):
            raise ValueError("navigation candidate score components disagree")
        if self.parent_relation not in {
            "NONE",
            "PROPOSED_PARENT",
            "DIRECT_CHILD",
            "SAME_BRANCH",
        }:
            raise ValueError("navigation candidate parent relation is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_total": self.base_total,
            "target_bonus": self.target_bonus,
            "scope_bonus": self.scope_bonus,
            "exclusion_penalty": self.exclusion_penalty,
            "total": self.total,
            "parent_relation": self.parent_relation,
        }


@dataclass(frozen=True, slots=True)
class NavigationCandidate:
    rank: int
    node_id: str
    score: NavigationCandidateScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.score, NavigationCandidateScore)
        ):
            raise ValueError("navigation candidate is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class NavigationCandidateSet:
    source_interpretation_hash: str
    source_query_hash: str
    source_snapshot_hash: str
    status: str
    max_candidates: int
    candidates: tuple[NavigationCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_interpretation_hash,
            self.source_query_hash,
            self.source_snapshot_hash,
            self.candidate_set_hash,
        ):
            _digest(value)
        if self.status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("navigation candidate status is invalid")
        if (
            not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or not 1 <= self.max_candidates <= MAX_INTERNAL_CANDIDATES
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > self.max_candidates
        ):
            raise ValueError("navigation candidate collection is invalid")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("navigation candidate ranks are not canonical")
        order = tuple((-item.score.total, item.node_id) for item in self.candidates)
        if order != tuple(sorted(order)):
            raise ValueError("navigation candidates are not canonically ordered")
        if (self.status == "CANDIDATES_READY") != bool(self.candidates):
            raise ValueError("navigation candidate status and content disagree")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("navigation candidate set hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": CANDIDATE_SET_SCHEMA_VERSION,
            "algorithm_version": CANDIDATE_ALGORITHM_VERSION,
            "source_interpretation_hash": self.source_interpretation_hash,
            "source_query_hash": self.source_query_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "status": self.status,
            "embedding_used": False,
            "allows_addition": False,
            "max_candidates": self.max_candidates,
            "candidates": [item.to_dict() for item in self.candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "candidate_set_hash": self.candidate_set_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        interpretation: NavigationInterpretation,
        tree: CanonicalTree,
    ) -> "NavigationCandidateSet":
        if not isinstance(payload, dict):
            raise NavigationCopilotError(
                "COPILOT_CANDIDATE_SET_INVALID",
                "stored candidate set must be an object",
            )
        try:
            expected = build_navigation_candidate_set(
                request,
                interpretation,
                tree,
                max_candidates=payload["max_candidates"],
            )
        except (KeyError, TypeError, ValueError):
            raise NavigationCopilotError(
                "COPILOT_CANDIDATE_SET_INVALID",
                "stored candidate set failed deterministic replay",
            ) from None
        if expected.to_dict() != payload:
            raise NavigationCopilotError(
                "COPILOT_CANDIDATE_SOURCE_MISMATCH",
                "stored candidate set does not replay trusted sources",
            )
        return expected


def build_navigation_candidate_set(
    request: IntentRequest,
    interpretation: NavigationInterpretation,
    tree: CanonicalTree,
    *,
    max_candidates: int = MAX_INTERNAL_CANDIDATES,
) -> NavigationCandidateSet:
    _trusted_sources(request, tree)
    if (
        not isinstance(interpretation, NavigationInterpretation)
        or interpretation.source_request_hash != request.request_hash
        or interpretation.source_snapshot_hash != tree.snapshot_hash
    ):
        raise NavigationCopilotError(
            "COPILOT_INTERPRETATION_SOURCE_MISMATCH",
            "interpretation does not bind candidate sources",
        )
    if (
        not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or not 1 <= max_candidates <= MAX_INTERNAL_CANDIDATES
    ):
        raise NavigationCopilotError(
            "COPILOT_CANDIDATE_LIMIT_INVALID",
            "candidate limit exceeds the Copilot bound",
        )
    query = build_copilot_retrieval_query(
        request,
        interpretation.structural_intent,
        tree,
        source_interpretation_hash=interpretation.interpretation_hash,
    )
    base = build_decoupled_candidate_set(
        query,
        tree,
        max_candidates=max_candidates,
    )
    if base.status != "CANDIDATES_READY":
        return _navigation_candidate_set(
            interpretation,
            base,
            tree,
            max_candidates,
            (),
        )
    node_by_id = {node.node_id: node for node in tree.nodes}
    role_evidence = (
        interpretation.understanding.role_evidence
        if interpretation.understanding is not None
        else None
    )
    scored: list[tuple[int, str, NavigationCandidateScore]] = []
    for candidate in base.candidates:
        target_bonus = 0
        scope_bonus = 0
        exclusion_penalty = 0
        if role_evidence is not None:
            features = build_boundary_role_features(
                role_evidence,
                request,
                node_by_id[candidate.node_id],
            )
            target_bonus = (
                features.target_name_similarity * _TARGET_NAME_WEIGHT
                + features.target_path_similarity * _TARGET_PATH_WEIGHT
            ) // SIMILARITY_SCALE
            scope_bonus = (
                features.scope_name_similarity * _SCOPE_NAME_WEIGHT
                + features.scope_path_similarity * _SCOPE_PATH_WEIGHT
            ) // SIMILARITY_SCALE
            exclusion_penalty = (
                _EXCLUSION_PENALTY if features.exclusion_match else 0
            )
        total = max(
            0,
            candidate.score.total
            + target_bonus
            + scope_bonus
            - exclusion_penalty,
        )
        score = NavigationCandidateScore(
            base_total=candidate.score.total,
            target_bonus=target_bonus,
            scope_bonus=scope_bonus,
            exclusion_penalty=exclusion_penalty,
            total=total,
            parent_relation=candidate.score.parent_relation,
        )
        scored.append((-total, candidate.node_id, score))
    scored.sort(key=lambda item: (item[0], item[1]))
    candidates = tuple(
        NavigationCandidate(rank=index, node_id=node_id, score=score)
        for index, (_, node_id, score) in enumerate(scored, start=1)
    )
    return _navigation_candidate_set(
        interpretation,
        base,
        tree,
        max_candidates,
        candidates,
    )


@dataclass(frozen=True, slots=True)
class NavigationSemanticProjection:
    source_interpretation_hash: str
    source_candidate_set_hash: str
    source_snapshot_hash: str
    candidate_status: str
    node_kind: str
    value_type: str | None
    cardinality: str
    candidates: tuple[SemanticCandidateView, ...]
    projection_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_interpretation_hash,
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
            raise ValueError("navigation semantic candidate status is invalid")
        if self.node_kind not in {"CONCEPT", "PROPERTY", "UNKNOWN"}:
            raise ValueError("navigation semantic node kind is invalid")
        if self.cardinality not in {"SINGLE", "MULTIPLE", "UNKNOWN"}:
            raise ValueError("navigation semantic cardinality is invalid")
        if self.value_type is not None:
            _bounded_text(self.value_type, "value_type", maximum=1_000)
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_MODEL_CANDIDATES
            or tuple(item.candidate_ref for item in self.candidates)
            != tuple(f"C{index:03d}" for index in range(1, len(self.candidates) + 1))
        ):
            raise ValueError("navigation semantic candidates are invalid")
        if (self.candidate_status == "CANDIDATES_READY") != bool(self.candidates):
            raise ValueError("navigation semantic status and candidates disagree")
        if _serialized_char_count(self.to_model_dict()) > MAX_MODEL_INPUT_CHARS:
            raise ValueError("navigation semantic projection is too large")
        if self.projection_hash != canonical_digest(self.to_model_dict()):
            raise ValueError("navigation semantic projection hash does not match")

    @property
    def candidate_refs(self) -> tuple[str, ...]:
        return tuple(item.candidate_ref for item in self.candidates)

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SEMANTIC_INPUT_SCHEMA_VERSION,
            "structural_intent": {
                "node_kind": self.node_kind,
                "value_type": self.value_type,
                "cardinality": self.cardinality,
            },
            "candidate_status": self.candidate_status,
            "candidates": [item.to_dict() for item in self.candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SEMANTIC_PROJECTION_SCHEMA_VERSION,
            "source_interpretation_hash": self.source_interpretation_hash,
            "source_candidate_set_hash": self.source_candidate_set_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "model_input": self.to_model_dict(),
            "projection_hash": self.projection_hash,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        interpretation: NavigationInterpretation,
        candidate_set: NavigationCandidateSet,
        tree: CanonicalTree,
    ) -> "NavigationSemanticProjection":
        expected = build_navigation_semantic_projection(
            request, interpretation, candidate_set, tree
        )
        if not isinstance(payload, dict) or expected.to_dict() != payload:
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_SOURCE_MISMATCH",
                "stored semantic projection does not replay trusted sources",
            )
        return expected


def build_navigation_semantic_projection(
    request: IntentRequest,
    interpretation: NavigationInterpretation,
    candidate_set: NavigationCandidateSet,
    tree: CanonicalTree,
) -> NavigationSemanticProjection:
    _trusted_sources(request, tree)
    if (
        interpretation.source_request_hash != request.request_hash
        or interpretation.source_snapshot_hash != tree.snapshot_hash
        or candidate_set.source_interpretation_hash
        != interpretation.interpretation_hash
        or candidate_set.source_snapshot_hash != tree.snapshot_hash
    ):
        raise NavigationCopilotError(
            "COPILOT_SEMANTIC_SOURCE_MISMATCH",
            "semantic projection sources do not align",
        )
    query = build_copilot_retrieval_query(
        request,
        interpretation.structural_intent,
        tree,
        source_interpretation_hash=interpretation.interpretation_hash,
    )
    node_by_id = {node.node_id: node for node in tree.nodes}
    views = []
    for index, candidate in enumerate(
        candidate_set.candidates[:MAX_MODEL_CANDIDATES], start=1
    ):
        node = node_by_id[candidate.node_id]
        contract = node.value_contract
        views.append(
            SemanticCandidateView(
                candidate_ref=f"C{index:03d}",
                rank=index,
                kind=node.kind,
                label=node.label,
                name=node.name,
                path_labels=node.path_labels,
                value_type=(
                    contract.value_type if contract is not None else None
                ),
                cardinality=(
                    contract.cardinality if contract is not None else None
                ),
                parent_relation=candidate.score.parent_relation,
            )
        )
    model_payload = {
        "schema_version": SEMANTIC_INPUT_SCHEMA_VERSION,
        "structural_intent": {
            "node_kind": query.node_kind,
            "value_type": query.value_type,
            "cardinality": query.cardinality,
        },
        "candidate_status": candidate_set.status,
        "candidates": [item.to_dict() for item in views],
    }
    return NavigationSemanticProjection(
        source_interpretation_hash=interpretation.interpretation_hash,
        source_candidate_set_hash=candidate_set.candidate_set_hash,
        source_snapshot_hash=tree.snapshot_hash,
        candidate_status=candidate_set.status,
        node_kind=query.node_kind,
        value_type=query.value_type,
        cardinality=query.cardinality,
        candidates=tuple(views),
        projection_hash=canonical_digest(model_payload),
    )


@dataclass(frozen=True, slots=True)
class NavigationSemanticDraft:
    model_provider: str
    model_name: str
    prompt_version: str
    source_projection_hash: str
    source_snapshot_hash: str
    candidate_assessments: tuple[SemanticCandidateAssessment, ...]
    draft_hash: str

    def __post_init__(self) -> None:
        for value in (self.model_provider, self.model_name, self.prompt_version):
            _bounded_text(value, "model metadata", maximum=1_000)
        _digest(self.source_projection_hash)
        _digest(self.source_snapshot_hash)
        _digest(self.draft_hash)
        if not isinstance(self.candidate_assessments, tuple) or any(
            not isinstance(item, SemanticCandidateAssessment)
            for item in self.candidate_assessments
        ):
            raise ValueError("navigation semantic assessments are invalid")
        if self.draft_hash != canonical_digest(self._payload()):
            raise ValueError("navigation semantic draft hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": SEMANTIC_DRAFT_SCHEMA_VERSION,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
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
    def from_dict(
        cls,
        payload: Any,
        projection: NavigationSemanticProjection,
        tree: CanonicalTree,
    ) -> "NavigationSemanticDraft":
        keys = {
            "schema_version", "model_provider", "model_name", "prompt_version",
            "semantic_approval", "patch_eligible", "source_projection_hash",
            "source_snapshot_hash", "candidate_assessments", "draft_hash",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != keys
            or payload.get("schema_version") != SEMANTIC_DRAFT_SCHEMA_VERSION
            or payload.get("semantic_approval") is not False
            or payload.get("patch_eligible") is not False
        ):
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_DRAFT_INVALID",
                "stored semantic draft violates its contract",
            )
        expected = cls.from_model_dict(
            {
                "schema_version": SEMANTIC_OUTPUT_SCHEMA_VERSION,
                "candidate_assessments": payload["candidate_assessments"],
            },
            projection,
            tree,
            model_provider=payload["model_provider"],
            model_name=payload["model_name"],
            prompt_version=payload["prompt_version"],
        )
        if expected.to_dict() != payload:
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_SOURCE_MISMATCH",
                "stored semantic draft does not replay trusted sources",
            )
        return expected

    @classmethod
    def from_model_dict(
        cls,
        payload: Any,
        projection: NavigationSemanticProjection,
        tree: CanonicalTree,
        *,
        model_provider: str,
        model_name: str,
        prompt_version: str,
    ) -> "NavigationSemanticDraft":
        if (
            not isinstance(projection, NavigationSemanticProjection)
            or projection.source_snapshot_hash != tree.snapshot_hash
        ):
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_SOURCE_MISMATCH",
                "semantic draft does not bind the trusted projection",
            )
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "candidate_assessments",
        }:
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_MODEL_FIELDS_INVALID",
                "semantic model output must use exact fields",
            )
        if payload["schema_version"] != SEMANTIC_OUTPUT_SCHEMA_VERSION:
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_MODEL_VERSION_INVALID",
                "semantic model output version is unsupported",
            )
        assessments = _parse_assessments(
            payload["candidate_assessments"], projection
        )
        if contains_internal_identifier(
            (item.reason for item in assessments),
            (node.node_id for node in tree.nodes),
        ):
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_INTERNAL_ID_FORBIDDEN",
                "semantic reasons must not contain internal identifiers",
            )
        draft_payload = {
            "schema_version": SEMANTIC_DRAFT_SCHEMA_VERSION,
            "model_provider": _bounded_text(
                model_provider, "model_provider", maximum=1_000
            ).strip(),
            "model_name": _bounded_text(
                model_name, "model_name", maximum=1_000
            ).strip(),
            "prompt_version": _bounded_text(
                prompt_version, "prompt_version", maximum=1_000
            ).strip(),
            "semantic_approval": False,
            "patch_eligible": False,
            "source_projection_hash": projection.projection_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "candidate_assessments": [item.to_dict() for item in assessments],
        }
        return cls(
            model_provider=draft_payload["model_provider"],
            model_name=draft_payload["model_name"],
            prompt_version=draft_payload["prompt_version"],
            source_projection_hash=projection.projection_hash,
            source_snapshot_hash=tree.snapshot_hash,
            candidate_assessments=assessments,
            draft_hash=canonical_digest(draft_payload),
        )


@dataclass(frozen=True, slots=True)
class NavigationPolicyDecision:
    source_interpretation_hash: str
    source_candidate_set_hash: str
    source_projection_hash: str | None
    source_semantic_draft_hash: str | None
    status: str
    highlighted_candidate_ref: str | None
    reason_code: str
    semantic_status: str
    decision_hash: str

    def __post_init__(self) -> None:
        _digest(self.source_interpretation_hash)
        _digest(self.source_candidate_set_hash)
        for value in (
            self.source_projection_hash,
            self.source_semantic_draft_hash,
        ):
            if value is not None:
                _digest(value)
        if self.status not in {
            "CANDIDATES_AVAILABLE",
            "AMBIGUOUS",
            "NONE",
            "NEED_EVIDENCE",
        }:
            raise ValueError("navigation policy status is invalid")
        if self.highlighted_candidate_ref is not None and (
            _CANDIDATE_REF.fullmatch(self.highlighted_candidate_ref) is None
            or self.status != "CANDIDATES_AVAILABLE"
        ):
            raise ValueError("navigation highlighted candidate is invalid")
        if self.semantic_status not in {
            "SUCCEEDED",
            "SKIPPED_CLARIFICATION_PATH",
            "DEGRADED",
            "NOT_APPLICABLE",
        }:
            raise ValueError("navigation semantic status is invalid")
        if not _valid_code(self.reason_code):
            raise ValueError("navigation policy reason code is invalid")
        _digest(self.decision_hash)
        if self.decision_hash != canonical_digest(self._payload()):
            raise ValueError("navigation policy decision hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": POLICY_DECISION_SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "semantic_approval": False,
            "patch_eligible": False,
            "source_interpretation_hash": self.source_interpretation_hash,
            "source_candidate_set_hash": self.source_candidate_set_hash,
            "source_projection_hash": self.source_projection_hash,
            "source_semantic_draft_hash": self.source_semantic_draft_hash,
            "status": self.status,
            "highlighted_candidate_ref": self.highlighted_candidate_ref,
            "reason_code": self.reason_code,
            "semantic_status": self.semantic_status,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "decision_hash": self.decision_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        interpretation: NavigationInterpretation,
        candidate_set: NavigationCandidateSet,
        projection: NavigationSemanticProjection | None,
        semantic_draft: NavigationSemanticDraft | None,
    ) -> "NavigationPolicyDecision":
        if not isinstance(payload, dict):
            raise NavigationCopilotError(
                "COPILOT_POLICY_DECISION_INVALID",
                "stored policy decision must be an object",
            )
        semantic_status = payload.get("semantic_status")
        try:
            expected = apply_navigation_policy(
                interpretation,
                candidate_set,
                projection,
                semantic_draft,
                semantic_status=semantic_status,
            )
        except (TypeError, ValueError):
            raise NavigationCopilotError(
                "COPILOT_POLICY_DECISION_INVALID",
                "stored policy decision failed deterministic replay",
            ) from None
        if expected.to_dict() != payload:
            raise NavigationCopilotError(
                "COPILOT_POLICY_SOURCE_MISMATCH",
                "stored policy decision does not replay trusted sources",
            )
        return expected


def apply_navigation_policy(
    interpretation: NavigationInterpretation,
    candidate_set: NavigationCandidateSet,
    projection: NavigationSemanticProjection | None,
    semantic_draft: NavigationSemanticDraft | None,
    *,
    semantic_status: str,
) -> NavigationPolicyDecision:
    if (
        not isinstance(interpretation, NavigationInterpretation)
        or not isinstance(candidate_set, NavigationCandidateSet)
        or candidate_set.source_interpretation_hash
        != interpretation.interpretation_hash
    ):
        raise NavigationCopilotError(
            "COPILOT_POLICY_SOURCE_MISMATCH",
            "navigation policy sources do not align",
        )
    if candidate_set.status != "CANDIDATES_READY":
        return _decision(
            interpretation,
            candidate_set,
            projection,
            semantic_draft,
            status="NONE",
            highlighted=None,
            reason="COPILOT_NO_CANDIDATES",
            semantic_status="NOT_APPLICABLE",
        )
    if semantic_draft is None:
        if semantic_status not in {
            "SKIPPED_CLARIFICATION_PATH",
            "DEGRADED",
        }:
            raise NavigationCopilotError(
                "COPILOT_POLICY_SEMANTIC_STATUS_INVALID",
                "missing semantic draft requires an explicit degraded status",
            )
        return _decision(
            interpretation,
            candidate_set,
            projection,
            semantic_draft,
            status="NEED_EVIDENCE",
            highlighted=None,
            reason=(
                "COPILOT_SEMANTIC_SKIPPED_AFTER_CLARIFICATION"
                if semantic_status == "SKIPPED_CLARIFICATION_PATH"
                else "COPILOT_SEMANTIC_DEGRADED"
            ),
            semantic_status=semantic_status,
        )
    if (
        not isinstance(projection, NavigationSemanticProjection)
        or semantic_draft.source_projection_hash != projection.projection_hash
        or projection.source_candidate_set_hash
        != candidate_set.candidate_set_hash
    ):
        raise NavigationCopilotError(
            "COPILOT_POLICY_SOURCE_MISMATCH",
            "semantic sources do not align with the candidate set",
        )
    candidate_by_ref = {
        item.candidate_ref: item for item in projection.candidates
    }
    equivalents = tuple(
        item.candidate_ref
        for item in semantic_draft.candidate_assessments
        if item.relation == "SEMANTICALLY_EQUIVALENT"
        and _compatible(projection, candidate_by_ref[item.candidate_ref])
    )
    if len(equivalents) == 1:
        status = "CANDIDATES_AVAILABLE"
        highlighted = equivalents[0]
        reason = "COPILOT_UNIQUE_COMPATIBLE_EQUIVALENT"
    elif len(equivalents) > 1:
        status = "AMBIGUOUS"
        highlighted = None
        reason = "COPILOT_MULTIPLE_COMPATIBLE_EQUIVALENTS"
    else:
        status = "NEED_EVIDENCE"
        highlighted = None
        reason = "COPILOT_NO_COMPATIBLE_EQUIVALENT"
    return _decision(
        interpretation,
        candidate_set,
        projection,
        semantic_draft,
        status=status,
        highlighted=highlighted,
        reason=reason,
        semantic_status="SUCCEEDED",
    )


@dataclass(frozen=True, slots=True)
class NavigationOutcome:
    source_decision_hash: str
    action: str
    selected_candidate_ref: str | None
    selected_node_id: str | None
    candidate_miss: bool
    user_corrected: bool
    duration_ms: int
    outcome_hash: str

    def __post_init__(self) -> None:
        _digest(self.source_decision_hash)
        if self.action not in {
            "SELECT_CANDIDATE",
            "SELECT_OUTSIDE_CANDIDATE",
            "REJECT_ALL",
            "EXIT",
        }:
            raise ValueError("navigation outcome action is invalid")
        if self.selected_candidate_ref is not None and (
            _CANDIDATE_REF.fullmatch(self.selected_candidate_ref) is None
        ):
            raise ValueError("navigation outcome candidate ref is invalid")
        if self.selected_node_id is not None and (
            not isinstance(self.selected_node_id, str) or not self.selected_node_id
        ):
            raise ValueError("navigation outcome node identity is invalid")
        selected = self.action in {
            "SELECT_CANDIDATE",
            "SELECT_OUTSIDE_CANDIDATE",
        }
        if selected != (self.selected_node_id is not None):
            raise ValueError("navigation outcome target and action disagree")
        if (self.action == "SELECT_CANDIDATE") != (
            self.selected_candidate_ref is not None
        ):
            raise ValueError("navigation outcome candidate action is inconsistent")
        outside = self.action == "SELECT_OUTSIDE_CANDIDATE"
        if self.candidate_miss != outside or self.user_corrected != outside:
            raise ValueError("navigation correction flags are inconsistent")
        if (
            not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
        ):
            raise ValueError("navigation outcome duration is invalid")
        _digest(self.outcome_hash)
        if self.outcome_hash != canonical_digest(self._payload()):
            raise ValueError("navigation outcome hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": OUTCOME_SCHEMA_VERSION,
            "record_semantics": "OPERATIONAL_FEEDBACK_ONLY",
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "source_decision_hash": self.source_decision_hash,
            "action": self.action,
            "selected_candidate_ref": self.selected_candidate_ref,
            "selected_node_id": self.selected_node_id,
            "candidate_miss": self.candidate_miss,
            "user_corrected": self.user_corrected,
            "duration_ms": self.duration_ms,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "outcome_hash": self.outcome_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        decision: NavigationPolicyDecision,
        candidate_set: NavigationCandidateSet,
        tree: CanonicalTree,
    ) -> "NavigationOutcome":
        if not isinstance(payload, dict):
            raise NavigationCopilotError(
                "COPILOT_OUTCOME_INVALID",
                "stored outcome must be an object",
            )
        try:
            expected = build_navigation_outcome(
                decision,
                candidate_set,
                tree,
                action=payload["action"],
                selected_candidate_ref=payload["selected_candidate_ref"],
                selected_node_id=payload["selected_node_id"],
                duration_ms=payload["duration_ms"],
            )
        except (KeyError, TypeError, ValueError):
            raise NavigationCopilotError(
                "COPILOT_OUTCOME_INVALID",
                "stored outcome failed deterministic replay",
            ) from None
        if expected.to_dict() != payload:
            raise NavigationCopilotError(
                "COPILOT_OUTCOME_SOURCE_MISMATCH",
                "stored outcome does not replay trusted sources",
            )
        return expected


@dataclass(frozen=True, slots=True)
class NavigationShadowObservation:
    decision: NavigationPolicyDecision
    outcome: NavigationOutcome
    clarification_used: bool
    model_degraded: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.decision, NavigationPolicyDecision)
            or not isinstance(self.outcome, NavigationOutcome)
            or self.outcome.source_decision_hash != self.decision.decision_hash
            or not isinstance(self.clarification_used, bool)
            or not isinstance(self.model_degraded, bool)
        ):
            raise ValueError("navigation shadow observation is invalid")


def build_navigation_outcome(
    decision: NavigationPolicyDecision,
    candidate_set: NavigationCandidateSet,
    tree: CanonicalTree,
    *,
    action: str,
    selected_candidate_ref: str | None,
    selected_node_id: str | None,
    duration_ms: int,
) -> NavigationOutcome:
    if (
        not isinstance(decision, NavigationPolicyDecision)
        or not isinstance(candidate_set, NavigationCandidateSet)
        or decision.source_candidate_set_hash != candidate_set.candidate_set_hash
        or candidate_set.source_snapshot_hash != tree.snapshot_hash
    ):
        raise NavigationCopilotError(
            "COPILOT_OUTCOME_SOURCE_MISMATCH",
            "outcome sources do not align",
        )
    candidate_node_by_ref = {
        f"C{index:03d}": item.node_id
        for index, item in enumerate(
            candidate_set.candidates[:MAX_MODEL_CANDIDATES], start=1
        )
    }
    node_ids = {node.node_id for node in tree.nodes}
    if action == "SELECT_CANDIDATE":
        if (
            selected_candidate_ref not in candidate_node_by_ref
            or selected_node_id
            != candidate_node_by_ref.get(selected_candidate_ref)
        ):
            raise NavigationCopilotError(
                "COPILOT_OUTCOME_CANDIDATE_INVALID",
                "selected candidate does not bind the projected node",
            )
    elif action == "SELECT_OUTSIDE_CANDIDATE":
        if (
            selected_candidate_ref is not None
            or selected_node_id not in node_ids
            or selected_node_id in candidate_node_by_ref.values()
        ):
            raise NavigationCopilotError(
                "COPILOT_OUTCOME_CORRECTION_INVALID",
                "outside correction must select a non-candidate tree node",
            )
    elif action in {"REJECT_ALL", "EXIT"}:
        if selected_candidate_ref is not None or selected_node_id is not None:
            raise NavigationCopilotError(
                "COPILOT_OUTCOME_TARGET_FORBIDDEN",
                "non-selection outcomes cannot carry a target",
            )
    else:
        raise NavigationCopilotError(
            "COPILOT_OUTCOME_ACTION_INVALID",
            "unsupported outcome action",
        )
    payload = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "record_semantics": "OPERATIONAL_FEEDBACK_ONLY",
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "source_decision_hash": decision.decision_hash,
        "action": action,
        "selected_candidate_ref": selected_candidate_ref,
        "selected_node_id": selected_node_id,
        "candidate_miss": action == "SELECT_OUTSIDE_CANDIDATE",
        "user_corrected": action == "SELECT_OUTSIDE_CANDIDATE",
        "duration_ms": duration_ms,
    }
    return NavigationOutcome(
        source_decision_hash=decision.decision_hash,
        action=action,
        selected_candidate_ref=selected_candidate_ref,
        selected_node_id=selected_node_id,
        candidate_miss=payload["candidate_miss"],
        user_corrected=payload["user_corrected"],
        duration_ms=duration_ms,
        outcome_hash=canonical_digest(payload),
    )


def navigation_shadow_aggregate(
    records: tuple[NavigationShadowObservation, ...],
) -> dict[str, Any]:
    if not isinstance(records, tuple):
        raise NavigationCopilotError(
            "COPILOT_AGGREGATE_RECORDS_INVALID",
            "aggregate records must be an immutable tuple",
        )
    for record in records:
        if not isinstance(record, NavigationShadowObservation):
            raise NavigationCopilotError(
                "COPILOT_AGGREGATE_SOURCE_MISMATCH",
                "aggregate record sources do not align",
            )
    decisions = tuple(record.decision for record in records)
    outcomes = tuple(record.outcome for record in records)
    completed = sum(
        outcome.action
        in {"SELECT_CANDIDATE", "SELECT_OUTSIDE_CANDIDATE"}
        for outcome in outcomes
    )
    direct = sum(
        outcome.action == "SELECT_CANDIDATE" for outcome in outcomes
    )
    corrections = sum(outcome.candidate_miss for outcome in outcomes)
    confident = [
        outcome
        for decision, outcome in zip(decisions, outcomes)
        if decision.status == "CANDIDATES_AVAILABLE"
    ]
    confident_errors = sum(
        outcome.action in {"SELECT_OUTSIDE_CANDIDATE", "REJECT_ALL"}
        for outcome in confident
    )
    durations = sorted(
        outcome.duration_ms
        for outcome in outcomes
        if outcome.action
        in {"SELECT_CANDIDATE", "SELECT_OUTSIDE_CANDIDATE"}
    )
    median = None
    if durations:
        middle = len(durations) // 2
        median = (
            durations[middle]
            if len(durations) % 2
            else (durations[middle - 1] + durations[middle]) // 2
        )
    return {
        "report_version": "navigation-copilot-shadow-aggregate.v1",
        "valid": True,
        "case_count": len(records),
        "completed_navigation_count": completed,
        "top8_direct_selection_count": direct,
        "candidate_correction_count": corrections,
        "confident_case_count": len(confident),
        "confident_error_count": confident_errors,
        "clarification_case_count": sum(
            record.clarification_used for record in records
        ),
        "degraded_case_count": sum(
            record.model_degraded for record in records
        ),
        "evidence_covered_case_count": sum(
            decision.status != "NONE" for decision in decisions
        ),
        "median_completion_ms": median,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }


def _navigation_candidate_set(
    interpretation: NavigationInterpretation,
    base: DecoupledCandidateSet,
    tree: CanonicalTree,
    max_candidates: int,
    candidates: tuple[NavigationCandidate, ...],
) -> NavigationCandidateSet:
    payload = {
        "schema_version": CANDIDATE_SET_SCHEMA_VERSION,
        "algorithm_version": CANDIDATE_ALGORITHM_VERSION,
        "source_interpretation_hash": interpretation.interpretation_hash,
        "source_query_hash": base.source_query_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "status": base.status,
        "embedding_used": False,
        "allows_addition": False,
        "max_candidates": max_candidates,
        "candidates": [item.to_dict() for item in candidates],
    }
    return NavigationCandidateSet(
        source_interpretation_hash=interpretation.interpretation_hash,
        source_query_hash=base.source_query_hash,
        source_snapshot_hash=tree.snapshot_hash,
        status=base.status,
        max_candidates=max_candidates,
        candidates=candidates,
        candidate_set_hash=canonical_digest(payload),
    )


def _parse_assessments(
    value: Any,
    projection: NavigationSemanticProjection,
) -> tuple[SemanticCandidateAssessment, ...]:
    if not isinstance(value, list) or len(value) != len(projection.candidates):
        raise NavigationCopilotError(
            "COPILOT_SEMANTIC_CANDIDATE_COVERAGE_INVALID",
            "semantic assessments must cover all projected candidates",
        )
    parsed = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "candidate_ref",
            "relation",
            "reason",
        }:
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_ASSESSMENT_FIELDS_INVALID",
                "semantic assessment fields are invalid",
            )
        if item.get("relation") not in CANDIDATE_RELATIONS:
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_RELATION_INVALID",
                "semantic relation is unsupported",
            )
        try:
            parsed.append(
                SemanticCandidateAssessment(
                    candidate_ref=item["candidate_ref"],
                    relation=item["relation"],
                    reason=item["reason"],
                )
            )
        except (KeyError, TypeError, ValueError):
            raise NavigationCopilotError(
                "COPILOT_SEMANTIC_ASSESSMENT_INVALID",
                "semantic assessment failed local validation",
            ) from None
    result = tuple(parsed)
    if tuple(item.candidate_ref for item in result) != projection.candidate_refs:
        raise NavigationCopilotError(
            "COPILOT_SEMANTIC_CANDIDATE_COVERAGE_INVALID",
            "semantic assessments must preserve projection order",
        )
    return result


def _compatible(
    projection: NavigationSemanticProjection,
    candidate: SemanticCandidateView,
) -> bool:
    return not (
        (projection.node_kind != "UNKNOWN" and candidate.kind != projection.node_kind)
        or (
            projection.value_type is not None
            and candidate.value_type != projection.value_type
        )
        or (
            projection.cardinality != "UNKNOWN"
            and candidate.cardinality != projection.cardinality
        )
    )


def _decision(
    interpretation: NavigationInterpretation,
    candidate_set: NavigationCandidateSet,
    projection: NavigationSemanticProjection | None,
    semantic_draft: NavigationSemanticDraft | None,
    *,
    status: str,
    highlighted: str | None,
    reason: str,
    semantic_status: str,
) -> NavigationPolicyDecision:
    payload = {
        "schema_version": POLICY_DECISION_SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "semantic_approval": False,
        "patch_eligible": False,
        "source_interpretation_hash": interpretation.interpretation_hash,
        "source_candidate_set_hash": candidate_set.candidate_set_hash,
        "source_projection_hash": (
            projection.projection_hash if projection is not None else None
        ),
        "source_semantic_draft_hash": (
            semantic_draft.draft_hash if semantic_draft is not None else None
        ),
        "status": status,
        "highlighted_candidate_ref": highlighted,
        "reason_code": reason,
        "semantic_status": semantic_status,
    }
    return NavigationPolicyDecision(
        source_interpretation_hash=interpretation.interpretation_hash,
        source_candidate_set_hash=candidate_set.candidate_set_hash,
        source_projection_hash=payload["source_projection_hash"],
        source_semantic_draft_hash=payload["source_semantic_draft_hash"],
        status=status,
        highlighted_candidate_ref=highlighted,
        reason_code=reason,
        semantic_status=semantic_status,
        decision_hash=canonical_digest(payload),
    )


def _trusted_sources(request: IntentRequest, tree: CanonicalTree) -> None:
    if (
        not isinstance(request, IntentRequest)
        or not isinstance(tree, CanonicalTree)
        or not tree.is_resource_map
    ):
        raise NavigationCopilotError(
            "COPILOT_SOURCE_INVALID",
            "navigation Copilot requires trusted resource sources",
        )


def _bounded_text(
    value: Any,
    field_name: str,
    *,
    maximum: int = _MAX_TEXT_CHARS,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        raise ValueError(f"{field_name} must be bounded printable text")
    return value


def _valid_code(value: Any) -> bool:
    return isinstance(value, str) and _CODE.fullmatch(value) is not None


def _digest(value: Any) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("navigation source must be a SHA-256 digest")


def _serialized_char_count(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


__all__ = [
    "CANDIDATE_ALGORITHM_VERSION",
    "CANDIDATE_SET_SCHEMA_VERSION",
    "CLARIFICATION_ANSWER_SCHEMA_VERSION",
    "CLARIFICATION_ROUND_SCHEMA_VERSION",
    "INTERPRETATION_SCHEMA_VERSION",
    "MAX_INTERNAL_CANDIDATES",
    "OUTCOME_SCHEMA_VERSION",
    "POLICY_DECISION_SCHEMA_VERSION",
    "SEMANTIC_DRAFT_SCHEMA_VERSION",
    "SEMANTIC_INPUT_SCHEMA_VERSION",
    "SEMANTIC_OUTPUT_SCHEMA_VERSION",
    "NavigationCandidate",
    "NavigationCandidateScore",
    "NavigationCandidateSet",
    "NavigationClarificationAnswer",
    "NavigationClarificationRound",
    "NavigationCopilotError",
    "NavigationInterpretation",
    "NavigationOutcome",
    "NavigationPolicyDecision",
    "NavigationSemanticDraft",
    "NavigationSemanticProjection",
    "NavigationShadowObservation",
    "apply_navigation_policy",
    "build_navigation_candidate_set",
    "build_navigation_outcome",
    "build_navigation_semantic_projection",
    "navigation_shadow_aggregate",
]
