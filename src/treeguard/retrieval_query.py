"""Deterministic decoupled query representation for retrieval experiments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import (
    CARDINALITIES,
    NODE_KINDS,
    IntentConfirmation,
    IntentRequest,
)
from treeguard.hashing import canonical_digest
from treeguard.lexical import text_terms
from treeguard.models import CanonicalNode, CanonicalTree
from treeguard.retrieval import CandidateRetrievalError


QUERY_SCHEMA_VERSION = "retrieval-query.v1"
DOCUMENT_SCHEMA_VERSION = "node-search-document.v1"
RESULT_SCHEMA_VERSION = "decoupled-candidate-set.v1"
ALGORITHM_VERSION = "treeguard.decoupled-weighted-lexical-retrieval.v1"
RETRIEVAL_SEMANTICS = "DECOUPLED_REQUIREMENT_LEXICAL_STRUCTURE"
DEFAULT_MAX_CANDIDATES = 20

_PARENT_RELATION_WEIGHT = {
    "NONE": 0,
    "PROPOSED_PARENT": 20,
    "DIRECT_CHILD": 80,
    "SAME_BRANCH": 40,
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    """Trusted request text plus locally validated structural constraints."""

    source_request_hash: str
    source_confirmation_hash: str
    source_snapshot_hash: str
    requirement_terms: tuple[str, ...]
    expansion_terms: tuple[str, ...]
    node_kind: str
    value_type: str | None
    cardinality: str
    proposed_parent_node_id: str | None
    query_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_request_hash,
            self.source_confirmation_hash,
            self.source_snapshot_hash,
            self.query_hash,
        ):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise ValueError("retrieval query hashes must be SHA-256 digests")
        for values in (self.requirement_terms, self.expansion_terms):
            if (
                not isinstance(values, tuple)
                or values != tuple(sorted(set(values)))
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise ValueError("retrieval query terms must be sorted and unique")
        if set(self.requirement_terms) & set(self.expansion_terms):
            raise ValueError("retrieval query term sources must be disjoint")
        if self.node_kind not in NODE_KINDS:
            raise ValueError("retrieval query node kind is invalid")
        if self.cardinality not in CARDINALITIES:
            raise ValueError("retrieval query cardinality is invalid")
        if self.value_type is not None and (
            not isinstance(self.value_type, str) or not self.value_type
        ):
            raise ValueError("retrieval query value type is invalid")
        if self.proposed_parent_node_id is not None and (
            not isinstance(self.proposed_parent_node_id, str)
            or not self.proposed_parent_node_id
        ):
            raise ValueError("retrieval query parent is invalid")
        if self.query_hash != canonical_digest(self._payload()):
            raise ValueError("retrieval query hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_SCHEMA_VERSION,
            "source_request_hash": self.source_request_hash,
            "source_confirmation_hash": self.source_confirmation_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "requirement_terms": list(self.requirement_terms),
            "expansion_terms": list(self.expansion_terms),
            "node_kind": self.node_kind,
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "proposed_parent_node_id": self.proposed_parent_node_id,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["query_hash"] = self.query_hash
        return payload


@dataclass(frozen=True, slots=True)
class NodeSearchDocument:
    node_id: str
    node_hash: str
    kind: str
    value_type: str | None
    cardinality: str | None
    name_terms: tuple[str, ...]
    path_terms: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.node_hash, str)
            or _DIGEST.fullmatch(self.node_hash) is None
            or not isinstance(self.kind, str)
            or not self.kind
            or (
                self.value_type is not None
                and (not isinstance(self.value_type, str) or not self.value_type)
            )
            or self.cardinality not in {"SINGLE", "MULTIPLE", None}
        ):
            raise ValueError("search document identity or contract is invalid")
        for values in (self.name_terms, self.path_terms):
            if (
                not isinstance(values, tuple)
                or values != tuple(sorted(set(values)))
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise ValueError("search document terms must be sorted and unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DOCUMENT_SCHEMA_VERSION,
            "node_id": self.node_id,
            "node_hash": self.node_hash,
            "kind": self.kind,
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "name_terms": list(self.name_terms),
            "path_terms": list(self.path_terms),
        }


@dataclass(frozen=True, slots=True)
class DecoupledCandidateScore:
    requirement_name: int
    requirement_path: int
    expansion_name: int
    expansion_path: int
    kind_match: bool
    value_type_match: bool
    cardinality_match: bool
    parent_relation: str
    total: int

    def __post_init__(self) -> None:
        counts = (
            self.requirement_name,
            self.requirement_path,
            self.expansion_name,
            self.expansion_path,
            self.total,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts
        ):
            raise ValueError("decoupled candidate scores must be non-negative integers")
        if any(
            not isinstance(value, bool)
            for value in (
                self.kind_match,
                self.value_type_match,
                self.cardinality_match,
            )
        ):
            raise ValueError("decoupled candidate match flags must be boolean")
        if self.parent_relation not in _PARENT_RELATION_WEIGHT:
            raise ValueError("unsupported decoupled parent relation")
        expected = (
            self.requirement_name
            + self.requirement_path
            + self.expansion_name
            + self.expansion_path
            + int(self.kind_match) * 40
            + int(self.value_type_match) * 30
            + int(self.cardinality_match) * 20
            + _PARENT_RELATION_WEIGHT[self.parent_relation]
        )
        if self.total != expected:
            raise ValueError("decoupled candidate total does not match components")

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_name": self.requirement_name,
            "requirement_path": self.requirement_path,
            "expansion_name": self.expansion_name,
            "expansion_path": self.expansion_path,
            "kind_match": self.kind_match,
            "value_type_match": self.value_type_match,
            "cardinality_match": self.cardinality_match,
            "parent_relation": self.parent_relation,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class DecoupledRetrievalCandidate:
    rank: int
    node_id: str
    score: DecoupledCandidateScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.score, DecoupledCandidateScore)
        ):
            raise ValueError("decoupled retrieval candidate is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DecoupledCandidateSet:
    source_query_hash: str
    source_snapshot_hash: str
    status: str
    requirement_term_count: int
    expansion_term_count: int
    max_candidates: int
    candidates: tuple[DecoupledRetrievalCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_query_hash,
            self.source_snapshot_hash,
            self.candidate_set_hash,
        ):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise ValueError("decoupled candidate hashes must be SHA-256 digests")
        if self.status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("unsupported decoupled candidate status")
        if (
            not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or self.max_candidates < 1
            or self.max_candidates > 100
            or not isinstance(self.requirement_term_count, int)
            or isinstance(self.requirement_term_count, bool)
            or self.requirement_term_count < 0
            or not isinstance(self.expansion_term_count, int)
            or isinstance(self.expansion_term_count, bool)
            or self.expansion_term_count < 0
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > self.max_candidates
        ):
            raise ValueError("decoupled candidate limit is invalid")
        ranks = tuple(candidate.rank for candidate in self.candidates)
        if ranks != tuple(range(1, len(self.candidates) + 1)):
            raise ValueError("decoupled candidate ranks are not canonical")
        if self.status == "CANDIDATES_READY" and not self.candidates:
            raise ValueError("ready decoupled result requires candidates")
        if self.status != "CANDIDATES_READY" and self.candidates:
            raise ValueError("non-ready decoupled result cannot contain candidates")
        if any(
            not isinstance(candidate, DecoupledRetrievalCandidate)
            for candidate in self.candidates
        ):
            raise ValueError("decoupled candidate items are invalid")
        term_count = self.requirement_term_count + self.expansion_term_count
        if self.status == "INSUFFICIENT_SIGNAL" and term_count != 0:
            raise ValueError("insufficient signal must have no query terms")
        if self.status != "INSUFFICIENT_SIGNAL" and term_count == 0:
            raise ValueError("retrieval result requires query terms")
        order = tuple((-item.score.total, item.node_id) for item in self.candidates)
        if order != tuple(sorted(order)):
            raise ValueError("decoupled candidates are not canonically ordered")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("decoupled candidate hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "source_query_hash": self.source_query_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "status": self.status,
            "embedding_used": False,
            "allows_addition": False,
            "requirement_term_count": self.requirement_term_count,
            "expansion_term_count": self.expansion_term_count,
            "max_candidates": self.max_candidates,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["candidate_set_hash"] = self.candidate_set_hash
        return payload

    def aggregate_report(self) -> dict[str, Any]:
        return {
            "report_version": "decoupled-retrieval-aggregate.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": False,
            "allows_addition": False,
            "requirement_term_count": self.requirement_term_count,
            "expansion_term_count": self.expansion_term_count,
            "candidate_count": len(self.candidates),
        }


def build_retrieval_query(
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    include_model_expansion: bool = True,
) -> RetrievalQuery:
    """Build a query whose primary signal does not depend on model rewriting."""

    _validate_sources(request, confirmation, tree)
    intent = confirmation.intent
    assert intent is not None
    requirement_terms = text_terms(request.requirement_text)
    expansion_terms: set[str] = set()
    if include_model_expansion:
        values = (intent.subject, *intent.confirmed_facts)
        expansion_terms = set().union(
            *(text_terms(value) for value in values if value is not None)
        )
        expansion_terms -= requirement_terms
    node_kind = (
        request.node_kind_hint
        if request.node_kind_hint != "UNKNOWN"
        else intent.node_kind
    )
    value_type = request.value_type_hint or intent.value_type
    cardinality = (
        request.cardinality_hint
        if request.cardinality_hint != "UNKNOWN"
        else intent.cardinality
    )
    payload = {
        "schema_version": QUERY_SCHEMA_VERSION,
        "source_request_hash": request.request_hash,
        "source_confirmation_hash": confirmation.confirmation_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "requirement_terms": sorted(requirement_terms),
        "expansion_terms": sorted(expansion_terms),
        "node_kind": node_kind,
        "value_type": value_type,
        "cardinality": cardinality,
        "proposed_parent_node_id": request.proposed_parent_node_id,
    }
    return RetrievalQuery(
        source_request_hash=request.request_hash,
        source_confirmation_hash=confirmation.confirmation_hash,
        source_snapshot_hash=tree.snapshot_hash,
        requirement_terms=tuple(payload["requirement_terms"]),
        expansion_terms=tuple(payload["expansion_terms"]),
        node_kind=node_kind,
        value_type=value_type,
        cardinality=cardinality,
        proposed_parent_node_id=request.proposed_parent_node_id,
        query_hash=canonical_digest(payload),
    )


def build_node_search_documents(tree: CanonicalTree) -> tuple[NodeSearchDocument, ...]:
    if not isinstance(tree, CanonicalTree) or tree.source_map_type != "resource":
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_NOT_RESOURCE",
            "decoupled retrieval accepts resource snapshots only",
        )
    documents = []
    for node in sorted(tree.nodes, key=lambda item: item.node_id):
        if node.kind == "UNSUPPORTED":
            continue
        contract = node.value_contract
        documents.append(
            NodeSearchDocument(
                node_id=node.node_id,
                node_hash=node.node_hash,
                kind=node.kind,
                value_type=contract.value_type if contract is not None else None,
                cardinality=contract.cardinality if contract is not None else None,
                name_terms=tuple(sorted(text_terms(" ".join((node.name, node.label))))),
                path_terms=tuple(sorted(text_terms(" ".join(node.path_labels[:-1])))),
            )
        )
    return tuple(documents)


def build_decoupled_candidate_set(
    query: RetrievalQuery,
    tree: CanonicalTree,
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> DecoupledCandidateSet:
    if not isinstance(query, RetrievalQuery):
        raise CandidateRetrievalError(
            "CANDIDATE_QUERY_INVALID",
            "decoupled retrieval requires a RetrievalQuery",
        )
    if query.source_snapshot_hash != tree.snapshot_hash:
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_STALE",
            "retrieval query does not bind the current snapshot",
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
    documents = build_node_search_documents(tree)
    all_query_terms = set(query.requirement_terms) | set(query.expansion_terms)
    if not all_query_terms:
        return _candidate_set(query, tree, "INSUFFICIENT_SIGNAL", max_candidates, ())
    document_frequency = _document_frequency(documents)
    node_by_id = {node.node_id: node for node in tree.nodes}
    parent = (
        node_by_id.get(query.proposed_parent_node_id)
        if query.proposed_parent_node_id is not None
        else None
    )
    if query.proposed_parent_node_id is not None and (
        parent is None or parent.kind == "UNSUPPORTED"
    ):
        raise CandidateRetrievalError(
            "CANDIDATE_PARENT_UNKNOWN",
            "retrieval query parent is unavailable in the source tree",
        )
    scored: list[tuple[int, str, DecoupledCandidateScore]] = []
    for document in documents:
        score = _score_document(
            document,
            query,
            document_frequency,
            len(documents),
            node_by_id[document.node_id],
            parent,
        )
        lexical_total = (
            score.requirement_name
            + score.requirement_path
            + score.expansion_name
            + score.expansion_path
        )
        if lexical_total == 0:
            continue
        scored.append((-score.total, document.node_id, score))
    scored.sort(key=lambda item: (item[0], item[1]))
    candidates = tuple(
        DecoupledRetrievalCandidate(rank, node_id, score)
        for rank, (_, node_id, score) in enumerate(scored[:max_candidates], start=1)
    )
    status = "CANDIDATES_READY" if candidates else "NO_CANDIDATES"
    return _candidate_set(query, tree, status, max_candidates, candidates)


def _validate_sources(
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
) -> None:
    if not isinstance(request, IntentRequest) or not isinstance(
        confirmation, IntentConfirmation
    ):
        raise CandidateRetrievalError(
            "CANDIDATE_QUERY_SOURCE_INVALID",
            "retrieval query sources are invalid",
        )
    if not isinstance(tree, CanonicalTree) or tree.source_map_type != "resource":
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_NOT_RESOURCE",
            "decoupled retrieval accepts resource snapshots only",
        )
    if confirmation.source_request_hash != request.request_hash:
        raise CandidateRetrievalError(
            "CANDIDATE_QUERY_REQUEST_MISMATCH",
            "intent confirmation does not bind the request",
        )
    if confirmation.source_snapshot_hash != tree.snapshot_hash:
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_STALE",
            "intent confirmation does not bind the current snapshot",
        )
    if confirmation.status != "CONFIRMED_FOR_RETRIEVAL" or confirmation.intent is None:
        raise CandidateRetrievalError(
            "CANDIDATE_INTENT_NOT_CONFIRMED",
            "only retrieval-confirmed intent can produce a query",
        )
    if confirmation.proposed_parent_node_id != request.proposed_parent_node_id:
        raise CandidateRetrievalError(
            "CANDIDATE_QUERY_PARENT_MISMATCH",
            "intent confirmation does not bind the request parent",
        )


def _document_frequency(
    documents: tuple[NodeSearchDocument, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for document in documents:
        for term in set(document.name_terms) | set(document.path_terms):
            counts[term] = counts.get(term, 0) + 1
    return counts


def _term_weight(term: str, frequencies: dict[str, int], document_count: int) -> int:
    return 100 + (document_count * 100 // frequencies.get(term, document_count))


def _weighted_overlap(
    query_terms: set[str],
    document_terms: tuple[str, ...],
    frequencies: dict[str, int],
    document_count: int,
    multiplier: int,
) -> int:
    return sum(
        _term_weight(term, frequencies, document_count) * multiplier
        for term in query_terms & set(document_terms)
    )


def _score_document(
    document: NodeSearchDocument,
    query: RetrievalQuery,
    frequencies: dict[str, int],
    document_count: int,
    node: CanonicalNode,
    parent: CanonicalNode | None,
) -> DecoupledCandidateScore:
    requirement = set(query.requirement_terms)
    expansion = set(query.expansion_terms)
    requirement_name = _weighted_overlap(
        requirement, document.name_terms, frequencies, document_count, 12
    )
    requirement_path = _weighted_overlap(
        requirement, document.path_terms, frequencies, document_count, 4
    )
    expansion_name = _weighted_overlap(
        expansion, document.name_terms, frequencies, document_count, 3
    )
    expansion_path = _weighted_overlap(
        expansion, document.path_terms, frequencies, document_count, 1
    )
    kind_match = query.node_kind != "UNKNOWN" and document.kind == query.node_kind
    value_type_match = (
        query.value_type is not None and document.value_type == query.value_type
    )
    cardinality_match = (
        query.cardinality != "UNKNOWN" and document.cardinality == query.cardinality
    )
    parent_relation = _parent_relation(node, parent)
    total = (
        requirement_name
        + requirement_path
        + expansion_name
        + expansion_path
        + int(kind_match) * 40
        + int(value_type_match) * 30
        + int(cardinality_match) * 20
        + _PARENT_RELATION_WEIGHT[parent_relation]
    )
    return DecoupledCandidateScore(
        requirement_name=requirement_name,
        requirement_path=requirement_path,
        expansion_name=expansion_name,
        expansion_path=expansion_path,
        kind_match=kind_match,
        value_type_match=value_type_match,
        cardinality_match=cardinality_match,
        parent_relation=parent_relation,
        total=total,
    )


def _parent_relation(node: CanonicalNode, parent: CanonicalNode | None) -> str:
    if parent is None:
        return "NONE"
    if node.parent_node_id == parent.node_id:
        return "DIRECT_CHILD"
    if node.node_id == parent.node_id:
        return "PROPOSED_PARENT"
    if (
        len(node.path_labels) > len(parent.path_labels)
        and node.path_labels[: len(parent.path_labels)] == parent.path_labels
    ):
        return "SAME_BRANCH"
    return "NONE"


def _candidate_set(
    query: RetrievalQuery,
    tree: CanonicalTree,
    status: str,
    max_candidates: int,
    candidates: tuple[DecoupledRetrievalCandidate, ...],
) -> DecoupledCandidateSet:
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "source_query_hash": query.query_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "status": status,
        "embedding_used": False,
        "allows_addition": False,
        "requirement_term_count": len(query.requirement_terms),
        "expansion_term_count": len(query.expansion_terms),
        "max_candidates": max_candidates,
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    return DecoupledCandidateSet(
        source_query_hash=query.query_hash,
        source_snapshot_hash=tree.snapshot_hash,
        status=status,
        requirement_term_count=len(query.requirement_terms),
        expansion_term_count=len(query.expansion_terms),
        max_candidates=max_candidates,
        candidates=candidates,
        candidate_set_hash=canonical_digest(payload),
    )


__all__ = [
    "ALGORITHM_VERSION",
    "DecoupledCandidateScore",
    "DecoupledCandidateSet",
    "DecoupledRetrievalCandidate",
    "NodeSearchDocument",
    "QUERY_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "RetrievalQuery",
    "build_decoupled_candidate_set",
    "build_node_search_documents",
    "build_retrieval_query",
]
