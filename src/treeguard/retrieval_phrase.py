"""Whole-phrase anchor reranking for the pre-registered Retrieval B3."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import IntentConfirmation, IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree
from treeguard.retrieval import CandidateRetrievalError
from treeguard.retrieval_query import (
    RetrievalQuery,
    build_decoupled_candidate_set,
    build_retrieval_query,
)


QUERY_SCHEMA_VERSION = "phrase-retrieval-query.v1"
RESULT_SCHEMA_VERSION = "phrase-candidate-set.v1"
ALGORITHM_VERSION = "treeguard.decoupled-whole-phrase-retrieval.v1"
RETRIEVAL_SEMANTICS = "DECOUPLED_REQUIREMENT_WHOLE_PHRASE"
DEFAULT_MAX_CANDIDATES = 20
_POSITIVE_NAME_WEIGHT = 30_000_000
_POSITIVE_PATH_WEIGHT = 15_000_000
_EXCLUDED_MATCH_WEIGHT = 60_000_000
_QUOTED = re.compile(r"[“\"]([^”\"]+)[”\"]")
_ASCII_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9._-]{3,}")
_WHITESPACE = re.compile(r"\s+")
_NEGATIVE_MARKERS = ("不要误用", "排除")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PhraseRetrievalQuery:
    base_query: RetrievalQuery
    positive_phrases: tuple[str, ...]
    excluded_phrases: tuple[str, ...]
    query_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.base_query, RetrievalQuery):
            raise ValueError("phrase query requires a RetrievalQuery")
        for phrases in (self.positive_phrases, self.excluded_phrases):
            if (
                not isinstance(phrases, tuple)
                or phrases != tuple(sorted(set(phrases)))
                or any(
                    not isinstance(phrase, str)
                    or not phrase
                    or phrase != _normalize_phrase(phrase)
                    for phrase in phrases
                )
            ):
                raise ValueError("query phrases must be sorted and unique")
        if set(self.positive_phrases) & set(self.excluded_phrases):
            raise ValueError("positive and excluded phrases must be disjoint")
        if not isinstance(self.query_hash, str) or _DIGEST.fullmatch(self.query_hash) is None:
            raise ValueError("phrase query hash must be a SHA-256 digest")
        if self.query_hash != canonical_digest(self._payload()):
            raise ValueError("phrase query hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_SCHEMA_VERSION,
            "base_query": self.base_query.to_dict(),
            "positive_phrases": list(self.positive_phrases),
            "excluded_phrases": list(self.excluded_phrases),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["query_hash"] = self.query_hash
        return payload


@dataclass(frozen=True, slots=True)
class PhraseCandidateScore:
    base_total: int
    positive_name_matches: int
    positive_path_matches: int
    excluded_name_matches: int
    excluded_path_matches: int
    total: int

    def __post_init__(self) -> None:
        components = (
            self.base_total,
            self.positive_name_matches,
            self.positive_path_matches,
            self.excluded_name_matches,
            self.excluded_path_matches,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in components
        ):
            raise ValueError("phrase score components must be non-negative integers")
        expected = (
            self.base_total
            + self.positive_name_matches * _POSITIVE_NAME_WEIGHT
            + self.positive_path_matches * _POSITIVE_PATH_WEIGHT
            - (self.excluded_name_matches + self.excluded_path_matches)
            * _EXCLUDED_MATCH_WEIGHT
        )
        if not isinstance(self.total, int) or isinstance(self.total, bool):
            raise ValueError("phrase score total must be an integer")
        if self.total != expected:
            raise ValueError("phrase score total does not match its components")

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_total": self.base_total,
            "positive_name_matches": self.positive_name_matches,
            "positive_path_matches": self.positive_path_matches,
            "excluded_name_matches": self.excluded_name_matches,
            "excluded_path_matches": self.excluded_path_matches,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class PhraseCandidate:
    rank: int
    node_id: str
    score: PhraseCandidateScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.score, PhraseCandidateScore)
        ):
            raise ValueError("phrase candidate is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PhraseCandidateSet:
    source_query_hash: str
    source_snapshot_hash: str
    status: str
    max_candidates: int
    candidates: tuple[PhraseCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.source_query_hash,
            self.source_snapshot_hash,
            self.candidate_set_hash,
        ):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise ValueError("phrase candidate hashes must be SHA-256 digests")
        if self.status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("phrase candidate status is invalid")
        if (
            not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or self.max_candidates < 1
            or self.max_candidates > 100
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > self.max_candidates
            or any(not isinstance(item, PhraseCandidate) for item in self.candidates)
        ):
            raise ValueError("phrase candidate collection is invalid")
        ranks = tuple(item.rank for item in self.candidates)
        if ranks != tuple(range(1, len(self.candidates) + 1)):
            raise ValueError("phrase candidate ranks are not canonical")
        order = tuple((-item.score.total, item.node_id) for item in self.candidates)
        if order != tuple(sorted(order)):
            raise ValueError("phrase candidates are not canonically ordered")
        if self.status == "CANDIDATES_READY" and not self.candidates:
            raise ValueError("ready phrase result requires candidates")
        if self.status != "CANDIDATES_READY" and self.candidates:
            raise ValueError("non-ready phrase result cannot contain candidates")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("phrase candidate hash does not match its payload")

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
            "report_version": "phrase-retrieval-aggregate.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": False,
            "allows_addition": False,
            "candidate_count": len(self.candidates),
        }


def build_phrase_retrieval_query(
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    include_model_expansion: bool = True,
) -> PhraseRetrievalQuery:
    base_query = build_retrieval_query(
        request,
        confirmation,
        tree,
        include_model_expansion=include_model_expansion,
    )
    positive, excluded = _explicit_phrases(request.requirement_text)
    payload = {
        "schema_version": QUERY_SCHEMA_VERSION,
        "base_query": base_query.to_dict(),
        "positive_phrases": list(positive),
        "excluded_phrases": list(excluded),
    }
    return PhraseRetrievalQuery(
        base_query=base_query,
        positive_phrases=positive,
        excluded_phrases=excluded,
        query_hash=canonical_digest(payload),
    )


def build_phrase_candidate_set(
    query: PhraseRetrievalQuery,
    tree: CanonicalTree,
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> PhraseCandidateSet:
    if not isinstance(query, PhraseRetrievalQuery):
        raise CandidateRetrievalError(
            "CANDIDATE_PHRASE_QUERY_INVALID",
            "phrase retrieval requires a PhraseRetrievalQuery",
        )
    if query.base_query.source_snapshot_hash != tree.snapshot_hash:
        raise CandidateRetrievalError(
            "CANDIDATE_SOURCE_STALE",
            "phrase retrieval query does not bind the current snapshot",
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
    node_by_id = {node.node_id: node for node in tree.nodes}
    positive = set(query.positive_phrases)
    excluded = set(query.excluded_phrases)
    scored = []
    for candidate in base.candidates:
        node = node_by_id[candidate.node_id]
        name_text = _normalize_phrase(" ".join((node.name, node.label)))
        path_text = _normalize_phrase(" ".join(node.path_labels))
        positive_name = _match_count(positive, name_text)
        positive_path = _match_count(positive, path_text)
        if positive and positive_name + positive_path == 0:
            continue
        excluded_name = _match_count(excluded, name_text)
        excluded_path = _match_count(excluded, path_text)
        total = (
            candidate.score.total
            + positive_name * _POSITIVE_NAME_WEIGHT
            + positive_path * _POSITIVE_PATH_WEIGHT
            - (excluded_name + excluded_path) * _EXCLUDED_MATCH_WEIGHT
        )
        score = PhraseCandidateScore(
            base_total=candidate.score.total,
            positive_name_matches=positive_name,
            positive_path_matches=positive_path,
            excluded_name_matches=excluded_name,
            excluded_path_matches=excluded_path,
            total=total,
        )
        scored.append((-score.total, candidate.node_id, score))
    scored.sort(key=lambda item: (item[0], item[1]))
    candidates = tuple(
        PhraseCandidate(rank, node_id, score)
        for rank, (_, node_id, score) in enumerate(scored[:max_candidates], start=1)
    )
    return _candidate_set(
        query,
        tree,
        "CANDIDATES_READY" if candidates else "NO_CANDIDATES",
        max_candidates,
        candidates,
    )


def _explicit_phrases(requirement_text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
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
    quoted_matches = tuple(_QUOTED.finditer(requirement_text))
    quoted_spans = tuple(match.span() for match in quoted_matches)
    for match in quoted_matches:
        phrase = _normalize_phrase(match.group(1))
        if phrase:
            target = excluded if match.start() >= negative_position else positive
            target.add(phrase)
    for match in _ASCII_IDENTIFIER.finditer(requirement_text):
        if any(start <= match.start() < end for start, end in quoted_spans):
            continue
        phrase = _normalize_phrase(match.group(0))
        if phrase:
            target = excluded if match.start() >= negative_position else positive
            target.add(phrase)
    positive -= excluded
    return tuple(sorted(positive)), tuple(sorted(excluded))


def _normalize_phrase(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _match_count(phrases: set[str], document_text: str) -> int:
    return sum(phrase in document_text for phrase in phrases)


def _candidate_set(
    query: PhraseRetrievalQuery,
    tree: CanonicalTree,
    status: str,
    max_candidates: int,
    candidates: tuple[PhraseCandidate, ...],
) -> PhraseCandidateSet:
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
    return PhraseCandidateSet(
        source_query_hash=query.query_hash,
        source_snapshot_hash=tree.snapshot_hash,
        status=status,
        max_candidates=max_candidates,
        candidates=candidates,
        candidate_set_hash=canonical_digest(payload),
    )


__all__ = [
    "ALGORITHM_VERSION",
    "PhraseCandidate",
    "PhraseCandidateScore",
    "PhraseCandidateSet",
    "PhraseRetrievalQuery",
    "build_phrase_candidate_set",
    "build_phrase_retrieval_query",
]
