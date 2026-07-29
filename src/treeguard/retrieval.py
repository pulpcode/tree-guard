"""Deterministic lexical/structural full-tree candidate retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import IntentConfirmation, IntentContent
from treeguard.hashing import canonical_digest
from treeguard.lexical import text_terms
from treeguard.models import CanonicalNode, CanonicalTree


SCHEMA_VERSION = "candidate-set.v1"
ALGORITHM_VERSION = "treeguard.lexical-structural-retrieval.v1"
RETRIEVAL_SEMANTICS = "BASELINE_LEXICAL_STRUCTURE"
DEFAULT_MAX_CANDIDATES = 20

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SCORE_KEYS = {
    "name_overlap",
    "path_overlap",
    "subject_match",
    "kind_match",
    "value_type_match",
    "cardinality_match",
    "parent_relation",
    "total",
}
_CANDIDATE_KEYS = {
    "rank",
    "node_id",
    "node_hash",
    "kind",
    "label",
    "name",
    "path_labels",
    "value_type",
    "cardinality",
    "score",
}
_SET_KEYS = {
    "schema_version",
    "algorithm_version",
    "retrieval_semantics",
    "source_confirmation_hash",
    "source_snapshot_hash",
    "status",
    "embedding_used",
    "allows_addition",
    "query_term_count",
    "max_candidates",
    "candidates",
    "candidate_set_hash",
}


class CandidateRetrievalError(ValueError):
    """A confirmed intent cannot safely produce a candidate set."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CandidateScore:
    name_overlap: int
    path_overlap: int
    subject_match: bool
    kind_match: bool
    value_type_match: bool
    cardinality_match: bool
    parent_relation: str
    total: int

    def __post_init__(self) -> None:
        for field_name in ("name_overlap", "path_overlap", "total"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError("candidate score counts must be non-negative integers")
        for field_name in (
            "subject_match",
            "kind_match",
            "value_type_match",
            "cardinality_match",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError("candidate score match flags must be boolean")
        if self.parent_relation not in {
            "NONE",
            "PROPOSED_PARENT",
            "DIRECT_CHILD",
            "SAME_BRANCH",
        }:
            raise ValueError("unsupported candidate parent relation")
        if self.total != (
            self.name_overlap * 20
            + self.path_overlap * 8
            + int(self.subject_match) * 16
            + int(self.kind_match) * 4
            + int(self.value_type_match) * 3
            + int(self.cardinality_match) * 2
            + {
                "NONE": 0,
                "PROPOSED_PARENT": 3,
                "DIRECT_CHILD": 12,
                "SAME_BRANCH": 6,
            }[self.parent_relation]
        ):
            raise ValueError("candidate total does not match score components")

    @classmethod
    def from_dict(cls, payload: Any) -> "CandidateScore":
        if not isinstance(payload, dict) or set(payload) != _SCORE_KEYS:
            raise CandidateRetrievalError(
                "CANDIDATE_SCORE_INVALID",
                "candidate score must use the exact fields",
            )
        try:
            return cls(**payload)
        except (TypeError, ValueError):
            raise CandidateRetrievalError(
                "CANDIDATE_SCORE_INVALID",
                "candidate score failed local validation",
            ) from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name_overlap": self.name_overlap,
            "path_overlap": self.path_overlap,
            "subject_match": self.subject_match,
            "kind_match": self.kind_match,
            "value_type_match": self.value_type_match,
            "cardinality_match": self.cardinality_match,
            "parent_relation": self.parent_relation,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    rank: int
    node_id: str
    node_hash: str
    kind: str
    label: str
    name: str
    path_labels: tuple[str, ...]
    value_type: str | None
    cardinality: str | None
    score: CandidateScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.node_hash, str)
            or _DIGEST.fullmatch(self.node_hash) is None
            or not isinstance(self.kind, str)
            or not self.kind
            or not isinstance(self.label, str)
            or not self.label
            or not isinstance(self.name, str)
            or not self.name
            or not isinstance(self.path_labels, tuple)
            or not self.path_labels
            or any(not isinstance(item, str) or not item for item in self.path_labels)
            or (
                self.value_type is not None
                and (not isinstance(self.value_type, str) or not self.value_type)
            )
            or (
                self.cardinality is not None
                and self.cardinality not in {"SINGLE", "MULTIPLE"}
            )
            or not isinstance(self.score, CandidateScore)
        ):
            raise ValueError("retrieval candidate is invalid")

    @classmethod
    def from_dict(cls, payload: Any) -> "RetrievalCandidate":
        if not isinstance(payload, dict) or set(payload) != _CANDIDATE_KEYS:
            raise CandidateRetrievalError(
                "CANDIDATE_ITEM_INVALID",
                "candidate item must use the exact fields",
            )
        if not isinstance(payload["path_labels"], list):
            raise CandidateRetrievalError(
                "CANDIDATE_ITEM_INVALID",
                "candidate path_labels must be an array",
            )
        try:
            return cls(
                rank=payload["rank"],
                node_id=payload["node_id"],
                node_hash=payload["node_hash"],
                kind=payload["kind"],
                label=payload["label"],
                name=payload["name"],
                path_labels=tuple(payload["path_labels"]),
                value_type=payload["value_type"],
                cardinality=payload["cardinality"],
                score=CandidateScore.from_dict(payload["score"]),
            )
        except (TypeError, ValueError):
            raise CandidateRetrievalError(
                "CANDIDATE_ITEM_INVALID",
                "candidate item failed local validation",
            ) from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "node_hash": self.node_hash,
            "kind": self.kind,
            "label": self.label,
            "name": self.name,
            "path_labels": list(self.path_labels),
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CandidateSet:
    source_confirmation_hash: str
    source_snapshot_hash: str
    status: str
    query_term_count: int
    max_candidates: int
    candidates: tuple[RetrievalCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_confirmation_hash,
            self.source_snapshot_hash,
            self.candidate_set_hash,
        ):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise ValueError("candidate-set hashes must be SHA-256 digests")
        if self.status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("unsupported candidate-set status")
        if (
            not isinstance(self.query_term_count, int)
            or isinstance(self.query_term_count, bool)
            or self.query_term_count < 0
            or not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or self.max_candidates < 1
            or self.max_candidates > 100
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > self.max_candidates
        ):
            raise ValueError("candidate-set counts are invalid")
        if self.status == "CANDIDATES_READY" and not self.candidates:
            raise ValueError("ready candidate-set must contain candidates")
        if self.status != "CANDIDATES_READY" and self.candidates:
            raise ValueError("non-ready candidate-set cannot contain candidates")
        if self.status == "INSUFFICIENT_SIGNAL" and self.query_term_count != 0:
            raise ValueError("insufficient signal must have zero query terms")
        if self.status != "INSUFFICIENT_SIGNAL" and self.query_term_count == 0:
            raise ValueError("retrieval result requires at least one query term")
        ranks = tuple(candidate.rank for candidate in self.candidates)
        if ranks != tuple(range(1, len(self.candidates) + 1)):
            raise ValueError("candidate ranks must be contiguous")
        sort_keys = tuple(
            (-candidate.score.total, candidate.node_id)
            for candidate in self.candidates
        )
        if sort_keys != tuple(sorted(sort_keys)):
            raise ValueError("candidates must use deterministic score and ID order")
        if len({candidate.node_id for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise ValueError("candidate node IDs must be unique")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("candidate_set_hash does not match its payload")

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        confirmation: IntentConfirmation,
        tree: CanonicalTree,
    ) -> "CandidateSet":
        if not isinstance(payload, dict) or set(payload) != _SET_KEYS:
            raise CandidateRetrievalError(
                "CANDIDATE_SET_FIELDS_INVALID",
                "stored candidate set must use the exact contract fields",
            )
        if (
            payload["schema_version"] != SCHEMA_VERSION
            or payload["algorithm_version"] != ALGORITHM_VERSION
            or payload["retrieval_semantics"] != RETRIEVAL_SEMANTICS
            or payload["embedding_used"] is not False
            or payload["allows_addition"] is not False
        ):
            raise CandidateRetrievalError(
                "CANDIDATE_SET_POLICY_INVALID",
                "stored candidate set violates the baseline retrieval policy",
            )
        if not isinstance(payload["candidates"], list):
            raise CandidateRetrievalError(
                "CANDIDATE_SET_INVALID",
                "stored candidates must be an array",
            )
        try:
            candidate_set = cls(
                source_confirmation_hash=payload["source_confirmation_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                status=payload["status"],
                query_term_count=payload["query_term_count"],
                max_candidates=payload["max_candidates"],
                candidates=tuple(
                    RetrievalCandidate.from_dict(item)
                    for item in payload["candidates"]
                ),
                candidate_set_hash=payload["candidate_set_hash"],
            )
        except (TypeError, ValueError):
            raise CandidateRetrievalError(
                "CANDIDATE_SET_INVALID",
                "stored candidate set failed integrity validation",
            ) from None
        verify_candidate_set_against_sources(candidate_set, confirmation, tree)
        return candidate_set

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "source_confirmation_hash": self.source_confirmation_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "status": self.status,
            "embedding_used": False,
            "allows_addition": False,
            "query_term_count": self.query_term_count,
            "max_candidates": self.max_candidates,
            "candidates": [item.to_dict() for item in self.candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["candidate_set_hash"] = self.candidate_set_hash
        return payload

    def aggregate_report(self) -> dict[str, Any]:
        return {
            "report_version": "candidate-retrieval-aggregate.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": False,
            "allows_addition": False,
            "query_term_count": self.query_term_count,
            "candidate_count": len(self.candidates),
        }


def build_candidate_set(
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> CandidateSet:
    """Search the complete resource tree without treating absence as add approval."""

    if not isinstance(confirmation, IntentConfirmation):
        raise CandidateRetrievalError(
            "CANDIDATE_CONFIRMATION_INVALID",
            "candidate retrieval requires an IntentConfirmation",
        )
    if (
        not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or max_candidates < 1
        or max_candidates > 100
    ):
        raise CandidateRetrievalError(
            "CANDIDATE_LIMIT_INVALID",
            "max_candidates must be between one and one hundred",
        )
    if not isinstance(tree, CanonicalTree) or tree.source_map_type != "resource":
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_NOT_RESOURCE",
            "candidate retrieval accepts resource snapshots only",
        )
    if confirmation.source_snapshot_hash != tree.snapshot_hash:
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_STALE",
            "intent confirmation does not bind the current snapshot",
        )
    if (
        confirmation.status != "CONFIRMED_FOR_RETRIEVAL"
        or confirmation.intent is None
    ):
        raise CandidateRetrievalError(
            "CANDIDATE_INTENT_NOT_CONFIRMED",
            "only retrieval-confirmed intent can produce candidates",
        )

    query_terms = _intent_terms(confirmation.intent)
    if not query_terms:
        return _candidate_set(
            confirmation,
            tree,
            status="INSUFFICIENT_SIGNAL",
            query_term_count=0,
            max_candidates=max_candidates,
            candidates=(),
        )

    parent = _parent_node(confirmation, tree)
    scored: list[tuple[int, str, CanonicalNode, CandidateScore]] = []
    for node in tree.nodes:
        if node.kind == "UNSUPPORTED":
            continue
        score = _score_node(
            node,
            query_terms,
            confirmation,
            parent,
        )
        if (
            score.name_overlap == 0
            and score.path_overlap == 0
            and score.parent_relation == "NONE"
        ):
            continue
        scored.append((-score.total, node.node_id, node, score))
    scored.sort(key=lambda item: (item[0], item[1]))

    candidates = tuple(
        _candidate_from_node(rank, node, score)
        for rank, (_, _, node, score) in enumerate(
            scored[:max_candidates],
            start=1,
        )
    )
    return _candidate_set(
        confirmation,
        tree,
        status="CANDIDATES_READY" if candidates else "NO_CANDIDATES",
        query_term_count=len(query_terms),
        max_candidates=max_candidates,
        candidates=candidates,
    )


def verify_candidate_set_against_sources(
    candidate_set: CandidateSet,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
) -> None:
    expected = build_candidate_set(
        confirmation,
        tree,
        max_candidates=candidate_set.max_candidates,
    )
    if candidate_set.to_dict() != expected.to_dict():
        raise CandidateRetrievalError(
            "CANDIDATE_SET_SOURCE_MISMATCH",
            "candidate set does not match trusted source replay",
        )


def _intent_terms(intent: IntentContent) -> set[str]:
    text_values = (
        intent.subject,
        intent.role,
        intent.scenario,
        intent.lifecycle,
        intent.value_type,
        *intent.confirmed_facts,
        *intent.assumptions,
    )
    return set().union(
        *(text_terms(value) for value in text_values if value is not None)
    )


def _score_node(
    node: CanonicalNode,
    query_terms: set[str],
    confirmation: IntentConfirmation,
    parent: CanonicalNode | None,
) -> CandidateScore:
    intent = confirmation.intent
    assert intent is not None
    name_terms = text_terms(" ".join((node.name, node.label)))
    path_terms = text_terms(" ".join(node.path_labels[:-1]))
    name_overlap = len(query_terms & name_terms)
    path_overlap = len(query_terms & path_terms)
    subject_terms = (
        text_terms(intent.subject) if intent.subject is not None else set()
    )
    node_name_terms = text_terms(node.name)
    subject_match = bool(
        subject_terms
        and node_name_terms
        and node_name_terms <= subject_terms
    )
    contract = node.value_contract
    kind_match = intent.node_kind != "UNKNOWN" and node.kind == intent.node_kind
    value_type_match = (
        intent.value_type is not None
        and contract is not None
        and contract.value_type == intent.value_type
    )
    cardinality_match = (
        intent.cardinality != "UNKNOWN"
        and contract is not None
        and contract.cardinality == intent.cardinality
    )
    parent_relation = _parent_relation(node, parent)
    total = (
        name_overlap * 20
        + path_overlap * 8
        + int(subject_match) * 16
        + int(kind_match) * 4
        + int(value_type_match) * 3
        + int(cardinality_match) * 2
        + {
            "NONE": 0,
            "PROPOSED_PARENT": 3,
            "DIRECT_CHILD": 12,
            "SAME_BRANCH": 6,
        }[parent_relation]
    )
    return CandidateScore(
        name_overlap=name_overlap,
        path_overlap=path_overlap,
        subject_match=subject_match,
        kind_match=kind_match,
        value_type_match=value_type_match,
        cardinality_match=cardinality_match,
        parent_relation=parent_relation,
        total=total,
    )


def _parent_node(
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
) -> CanonicalNode | None:
    if confirmation.proposed_parent_node_id is None:
        return None
    parent = next(
        (
            node
            for node in tree.nodes
            if node.node_id == confirmation.proposed_parent_node_id
        ),
        None,
    )
    if parent is None or parent.kind == "UNSUPPORTED":
        raise CandidateRetrievalError(
            "CANDIDATE_PARENT_UNKNOWN",
            "confirmed proposed parent is unavailable in the source tree",
        )
    return parent


def _parent_relation(
    node: CanonicalNode,
    parent: CanonicalNode | None,
) -> str:
    if parent is None:
        return "NONE"
    if node.parent_node_id == parent.node_id:
        return "DIRECT_CHILD"
    if node.node_id == parent.node_id:
        return "PROPOSED_PARENT"
    parent_path = parent.path_labels
    if (
        len(node.path_labels) > len(parent_path)
        and node.path_labels[: len(parent_path)] == parent_path
    ):
        return "SAME_BRANCH"
    return "NONE"


def _candidate_from_node(
    rank: int,
    node: CanonicalNode,
    score: CandidateScore,
) -> RetrievalCandidate:
    contract = node.value_contract
    return RetrievalCandidate(
        rank=rank,
        node_id=node.node_id,
        node_hash=node.node_hash,
        kind=node.kind,
        label=node.label,
        name=node.name,
        path_labels=node.path_labels,
        value_type=contract.value_type if contract is not None else None,
        cardinality=contract.cardinality if contract is not None else None,
        score=score,
    )


def _candidate_set(
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    status: str,
    query_term_count: int,
    max_candidates: int,
    candidates: tuple[RetrievalCandidate, ...],
) -> CandidateSet:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "source_confirmation_hash": confirmation.confirmation_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "status": status,
        "embedding_used": False,
        "allows_addition": False,
        "query_term_count": query_term_count,
        "max_candidates": max_candidates,
        "candidates": [item.to_dict() for item in candidates],
    }
    return CandidateSet(
        source_confirmation_hash=confirmation.confirmation_hash,
        source_snapshot_hash=tree.snapshot_hash,
        status=status,
        query_term_count=query_term_count,
        max_candidates=max_candidates,
        candidates=candidates,
        candidate_set_hash=canonical_digest(payload),
    )


__all__ = [
    "ALGORITHM_VERSION",
    "CandidateRetrievalError",
    "CandidateScore",
    "CandidateSet",
    "DEFAULT_MAX_CANDIDATES",
    "RETRIEVAL_SEMANTICS",
    "RetrievalCandidate",
    "SCHEMA_VERSION",
    "build_candidate_set",
    "verify_candidate_set_against_sources",
]
