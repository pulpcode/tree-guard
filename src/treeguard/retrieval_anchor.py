"""Explicit-anchor reranking for the pre-registered decoupled Retrieval B2."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import IntentConfirmation, IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.lexical import text_terms
from treeguard.models import CanonicalTree
from treeguard.retrieval import CandidateRetrievalError
from treeguard.retrieval_query import (
    DecoupledCandidateSet,
    RetrievalQuery,
    build_decoupled_candidate_set,
    build_node_search_documents,
    build_retrieval_query,
)


QUERY_SCHEMA_VERSION = "anchored-retrieval-query.v1"
RESULT_SCHEMA_VERSION = "anchored-candidate-set.v1"
ALGORITHM_VERSION = "treeguard.decoupled-explicit-anchor-retrieval.v1"
RETRIEVAL_SEMANTICS = "DECOUPLED_REQUIREMENT_EXPLICIT_ANCHOR"
DEFAULT_MAX_CANDIDATES = 20
_POSITIVE_ANCHOR_WEIGHT = 10_000_000
_EXCLUDED_ANCHOR_WEIGHT = 20_000_000
_QUOTED = re.compile(r"[“\"]([^”\"]+)[”\"]")
_ASCII_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9._-]{3,}")
_NEGATIVE_MARKERS = ("不要误用", "排除")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class AnchoredRetrievalQuery:
    base_query: RetrievalQuery
    positive_anchor_terms: tuple[str, ...]
    excluded_anchor_terms: tuple[str, ...]
    query_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.base_query, RetrievalQuery):
            raise ValueError("anchored query requires a RetrievalQuery")
        for terms in (self.positive_anchor_terms, self.excluded_anchor_terms):
            if (
                not isinstance(terms, tuple)
                or terms != tuple(sorted(set(terms)))
                or any(not isinstance(term, str) or not term for term in terms)
            ):
                raise ValueError("anchored query terms must be sorted and unique")
        if set(self.positive_anchor_terms) & set(self.excluded_anchor_terms):
            raise ValueError("positive and excluded anchors must be disjoint")
        if not isinstance(self.query_hash, str) or _DIGEST.fullmatch(self.query_hash) is None:
            raise ValueError("anchored query hash must be a SHA-256 digest")
        if self.query_hash != canonical_digest(self._payload()):
            raise ValueError("anchored query hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_SCHEMA_VERSION,
            "base_query": self.base_query.to_dict(),
            "positive_anchor_terms": list(self.positive_anchor_terms),
            "excluded_anchor_terms": list(self.excluded_anchor_terms),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["query_hash"] = self.query_hash
        return payload


@dataclass(frozen=True, slots=True)
class AnchoredCandidateScore:
    base_total: int
    positive_anchor_overlap: int
    excluded_anchor_overlap: int
    total: int

    def __post_init__(self) -> None:
        for value in (
            self.base_total,
            self.positive_anchor_overlap,
            self.excluded_anchor_overlap,
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("anchored score components must be non-negative integers")
        if not isinstance(self.total, int) or isinstance(self.total, bool):
            raise ValueError("anchored total must be an integer")
        expected = (
            self.base_total
            + self.positive_anchor_overlap * _POSITIVE_ANCHOR_WEIGHT
            - self.excluded_anchor_overlap * _EXCLUDED_ANCHOR_WEIGHT
        )
        if self.total != expected:
            raise ValueError("anchored total does not match its components")

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_total": self.base_total,
            "positive_anchor_overlap": self.positive_anchor_overlap,
            "excluded_anchor_overlap": self.excluded_anchor_overlap,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class AnchoredCandidate:
    rank: int
    node_id: str
    score: AnchoredCandidateScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.score, AnchoredCandidateScore)
        ):
            raise ValueError("anchored candidate is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class AnchoredCandidateSet:
    source_query_hash: str
    source_snapshot_hash: str
    status: str
    max_candidates: int
    candidates: tuple[AnchoredCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_query_hash,
            self.source_snapshot_hash,
            self.candidate_set_hash,
        ):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise ValueError("anchored candidate hashes must be SHA-256 digests")
        if self.status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("anchored candidate status is invalid")
        if (
            not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or self.max_candidates < 1
            or self.max_candidates > 100
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > self.max_candidates
            or any(not isinstance(item, AnchoredCandidate) for item in self.candidates)
        ):
            raise ValueError("anchored candidate collection is invalid")
        ranks = tuple(item.rank for item in self.candidates)
        if ranks != tuple(range(1, len(self.candidates) + 1)):
            raise ValueError("anchored candidate ranks are not canonical")
        order = tuple((-item.score.total, item.node_id) for item in self.candidates)
        if order != tuple(sorted(order)):
            raise ValueError("anchored candidates are not canonically ordered")
        if self.status == "CANDIDATES_READY" and not self.candidates:
            raise ValueError("ready anchored result requires candidates")
        if self.status != "CANDIDATES_READY" and self.candidates:
            raise ValueError("non-ready anchored result cannot contain candidates")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("anchored candidate hash does not match its payload")

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
            "max_candidates": self.max_candidates,
            "candidates": [item.to_dict() for item in self.candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["candidate_set_hash"] = self.candidate_set_hash
        return payload

    def aggregate_report(self) -> dict[str, Any]:
        return {
            "report_version": "anchored-retrieval-aggregate.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": False,
            "allows_addition": False,
            "candidate_count": len(self.candidates),
        }


def build_anchored_retrieval_query(
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    include_model_expansion: bool = True,
) -> AnchoredRetrievalQuery:
    base_query = build_retrieval_query(
        request,
        confirmation,
        tree,
        include_model_expansion=include_model_expansion,
    )
    positive, excluded = _explicit_anchor_terms(request.requirement_text)
    payload = {
        "schema_version": QUERY_SCHEMA_VERSION,
        "base_query": base_query.to_dict(),
        "positive_anchor_terms": list(positive),
        "excluded_anchor_terms": list(excluded),
    }
    return AnchoredRetrievalQuery(
        base_query=base_query,
        positive_anchor_terms=positive,
        excluded_anchor_terms=excluded,
        query_hash=canonical_digest(payload),
    )


def build_anchored_candidate_set(
    query: AnchoredRetrievalQuery,
    tree: CanonicalTree,
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> AnchoredCandidateSet:
    if not isinstance(query, AnchoredRetrievalQuery):
        raise CandidateRetrievalError(
            "CANDIDATE_ANCHOR_QUERY_INVALID",
            "anchored retrieval requires an AnchoredRetrievalQuery",
        )
    if query.base_query.source_snapshot_hash != tree.snapshot_hash:
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_STALE",
            "anchored retrieval query does not bind the current snapshot",
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
    base = build_decoupled_candidate_set(query.base_query, tree, max_candidates=100)
    if base.status != "CANDIDATES_READY":
        return _candidate_set(query, tree, base.status, max_candidates, ())
    documents = {
        document.node_id: document for document in build_node_search_documents(tree)
    }
    positive_terms = set(query.positive_anchor_terms)
    excluded_terms = set(query.excluded_anchor_terms)
    scored = []
    for candidate in base.candidates:
        document = documents[candidate.node_id]
        document_terms = set(document.name_terms) | set(document.path_terms)
        positive_overlap = len(positive_terms & document_terms)
        if positive_terms and positive_overlap == 0:
            continue
        excluded_overlap = len(excluded_terms & document_terms)
        score = AnchoredCandidateScore(
            base_total=candidate.score.total,
            positive_anchor_overlap=positive_overlap,
            excluded_anchor_overlap=excluded_overlap,
            total=(
                candidate.score.total
                + positive_overlap * _POSITIVE_ANCHOR_WEIGHT
                - excluded_overlap * _EXCLUDED_ANCHOR_WEIGHT
            ),
        )
        scored.append((-score.total, candidate.node_id, score))
    scored.sort(key=lambda item: (item[0], item[1]))
    candidates = tuple(
        AnchoredCandidate(rank, node_id, score)
        for rank, (_, node_id, score) in enumerate(scored[:max_candidates], start=1)
    )
    return _candidate_set(
        query,
        tree,
        "CANDIDATES_READY" if candidates else "NO_CANDIDATES",
        max_candidates,
        candidates,
    )


def _explicit_anchor_terms(requirement_text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    negative_position = min(
        (
            position
            for marker in _NEGATIVE_MARKERS
            if (position := requirement_text.find(marker)) >= 0
        ),
        default=len(requirement_text) + 1,
    )
    positive: set[str] = set()
    excluded: set[str] = set()
    for match in _QUOTED.finditer(requirement_text):
        target = excluded if match.start() >= negative_position else positive
        target.update(text_terms(match.group(1)))
    for match in _ASCII_IDENTIFIER.finditer(requirement_text):
        target = excluded if match.start() >= negative_position else positive
        target.update(text_terms(match.group(0)))
    positive -= excluded
    return tuple(sorted(positive)), tuple(sorted(excluded))


def _candidate_set(
    query: AnchoredRetrievalQuery,
    tree: CanonicalTree,
    status: str,
    max_candidates: int,
    candidates: tuple[AnchoredCandidate, ...],
) -> AnchoredCandidateSet:
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "source_query_hash": query.query_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "status": status,
        "embedding_used": False,
        "allows_addition": False,
        "max_candidates": max_candidates,
        "candidates": [item.to_dict() for item in candidates],
    }
    return AnchoredCandidateSet(
        source_query_hash=query.query_hash,
        source_snapshot_hash=tree.snapshot_hash,
        status=status,
        max_candidates=max_candidates,
        candidates=candidates,
        candidate_set_hash=canonical_digest(payload),
    )


__all__ = [
    "ALGORITHM_VERSION",
    "AnchoredCandidate",
    "AnchoredCandidateScore",
    "AnchoredCandidateSet",
    "AnchoredRetrievalQuery",
    "build_anchored_candidate_set",
    "build_anchored_retrieval_query",
]
