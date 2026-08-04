"""Boundary-tolerant role retrieval for the pre-registered R2 calibration."""

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
    build_decoupled_candidate_set,
    build_retrieval_query,
)
from treeguard.retrieval_roles import (
    RetrievalRoleEvidence,
    verify_retrieval_role_evidence,
)


RESULT_SCHEMA_VERSION = "boundary-tolerant-role-candidate-set.v1"
ALGORITHM_VERSION = "treeguard.boundary-tolerant-role-lexical-retrieval.v1"
RETRIEVAL_SEMANTICS = "DECOUPLED_BOUNDARY_TOLERANT_ROLE_EVIDENCE"
DEFAULT_MAX_CANDIDATES = 20
SIMILARITY_SCALE = 1_000_000
_TARGET_NAME_WEIGHT = 30_000_000
_TARGET_PATH_WEIGHT = 15_000_000
_SCOPE_NAME_WEIGHT = 2_000_000
_SCOPE_PATH_WEIGHT = 5_000_000
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ASCII_WORD = re.compile(r"[a-z0-9]+")
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class BoundaryTolerantRoleScore:
    base_total: int
    target_name_similarity: int
    target_path_similarity: int
    scope_name_similarity: int
    scope_path_similarity: int
    total: int

    def __post_init__(self) -> None:
        components = (
            self.base_total,
            self.target_name_similarity,
            self.target_path_similarity,
            self.scope_name_similarity,
            self.scope_path_similarity,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in components
        ):
            raise ValueError("boundary-tolerant score components are invalid")
        if any(value > SIMILARITY_SCALE for value in components[1:]):
            raise ValueError("boundary-tolerant similarity exceeds its scale")
        expected = self.base_total + sum(
            (
                self.target_name_similarity * _TARGET_NAME_WEIGHT,
                self.target_path_similarity * _TARGET_PATH_WEIGHT,
                self.scope_name_similarity * _SCOPE_NAME_WEIGHT,
                self.scope_path_similarity * _SCOPE_PATH_WEIGHT,
            )
        ) // SIMILARITY_SCALE
        if (
            not isinstance(self.total, int)
            or isinstance(self.total, bool)
            or self.total != expected
        ):
            raise ValueError("boundary-tolerant score total is invalid")

    def to_dict(self) -> dict[str, int]:
        return {
            "base_total": self.base_total,
            "target_name_similarity": self.target_name_similarity,
            "target_path_similarity": self.target_path_similarity,
            "scope_name_similarity": self.scope_name_similarity,
            "scope_path_similarity": self.scope_path_similarity,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class BoundaryTolerantRoleCandidate:
    rank: int
    node_id: str
    score: BoundaryTolerantRoleScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.score, BoundaryTolerantRoleScore)
        ):
            raise ValueError("boundary-tolerant candidate is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class BoundaryTolerantRoleCandidateSet:
    source_evidence_hash: str
    source_query_hash: str
    source_snapshot_hash: str
    status: str
    max_candidates: int
    candidates: tuple[BoundaryTolerantRoleCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        for digest in (
            self.source_evidence_hash,
            self.source_query_hash,
            self.source_snapshot_hash,
            self.candidate_set_hash,
        ):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("boundary-tolerant candidate hashes must be SHA-256")
        if self.status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("boundary-tolerant candidate status is invalid")
        if (
            not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or not 1 <= self.max_candidates <= 100
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > self.max_candidates
            or any(
                not isinstance(item, BoundaryTolerantRoleCandidate)
                for item in self.candidates
            )
        ):
            raise ValueError("boundary-tolerant candidate collection is invalid")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("boundary-tolerant candidate ranks are not canonical")
        order = tuple((-item.score.total, item.node_id) for item in self.candidates)
        if order != tuple(sorted(order)):
            raise ValueError("boundary-tolerant candidates are not canonically ordered")
        if self.status == "CANDIDATES_READY" and not self.candidates:
            raise ValueError("ready boundary-tolerant result requires candidates")
        if self.status != "CANDIDATES_READY" and self.candidates:
            raise ValueError("non-ready boundary-tolerant result cannot have candidates")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("boundary-tolerant candidate hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "source_evidence_hash": self.source_evidence_hash,
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
            "report_version": "boundary-tolerant-role-retrieval-aggregate.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": False,
            "allows_addition": False,
            "candidate_count": len(self.candidates),
        }


def build_boundary_tolerant_role_candidate_set(
    evidence: RetrievalRoleEvidence,
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    include_model_expansion: bool = True,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> BoundaryTolerantRoleCandidateSet:
    verify_retrieval_role_evidence(evidence, request)
    if (
        not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or not 1 <= max_candidates <= 100
    ):
        raise CandidateRetrievalError(
            "CANDIDATE_LIMIT_INVALID",
            "max_candidates must be between one and one hundred",
        )
    query = build_retrieval_query(
        request,
        confirmation,
        tree,
        include_model_expansion=include_model_expansion,
    )
    base = build_decoupled_candidate_set(query, tree, max_candidates=100)
    if base.status != "CANDIDATES_READY":
        return _candidate_set(
            evidence, query.query_hash, tree, base.status, max_candidates, ()
        )

    role_terms = {
        role: tuple(
            _boundary_terms(span.text)
            for span in evidence.spans
            if span.role == role
        )
        for role in ("TARGET", "SCOPE")
    }
    exclusions = {
        _normalize_text(span.text)
        for span in evidence.spans
        if span.role == "EXCLUSION"
    }
    node_by_id = {node.node_id: node for node in tree.nodes}
    scored = []
    for candidate in base.candidates:
        node = node_by_id[candidate.node_id]
        name_texts = (_normalize_text(node.name), _normalize_text(node.label))
        path_texts = tuple(_normalize_text(value) for value in node.path_labels)
        exclusion_documents = name_texts + (
            _normalize_text(" ".join(node.path_labels)),
        )
        if _contains_any(exclusions, exclusion_documents):
            continue
        name_term_sets = tuple(_boundary_terms(value) for value in name_texts)
        path_term_sets = tuple(_boundary_terms(value) for value in path_texts)
        target_name = _best_similarity(role_terms["TARGET"], name_term_sets)
        target_path = _best_similarity(role_terms["TARGET"], path_term_sets)
        if target_name == 0 and target_path == 0:
            continue
        scope_name = _best_similarity(role_terms["SCOPE"], name_term_sets)
        scope_path = _best_similarity(role_terms["SCOPE"], path_term_sets)
        weighted = sum(
            (
                target_name * _TARGET_NAME_WEIGHT,
                target_path * _TARGET_PATH_WEIGHT,
                scope_name * _SCOPE_NAME_WEIGHT,
                scope_path * _SCOPE_PATH_WEIGHT,
            )
        ) // SIMILARITY_SCALE
        score = BoundaryTolerantRoleScore(
            base_total=candidate.score.total,
            target_name_similarity=target_name,
            target_path_similarity=target_path,
            scope_name_similarity=scope_name,
            scope_path_similarity=scope_path,
            total=candidate.score.total + weighted,
        )
        scored.append((-score.total, candidate.node_id, score))
    scored.sort(key=lambda item: (item[0], item[1]))
    candidates = tuple(
        BoundaryTolerantRoleCandidate(rank, node_id, score)
        for rank, (_, node_id, score) in enumerate(scored[:max_candidates], start=1)
    )
    return _candidate_set(
        evidence,
        query.query_hash,
        tree,
        "CANDIDATES_READY" if candidates else "NO_CANDIDATES",
        max_candidates,
        candidates,
    )


def _normalize_text(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _boundary_terms(value: str) -> frozenset[str]:
    normalized = _normalize_text(value)
    terms = set(_ASCII_WORD.findall(normalized))
    for run in _CJK_RUN.findall(normalized):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return frozenset(terms)


def _dice(left: frozenset[str], right: frozenset[str]) -> int:
    if not left or not right:
        return 0
    return 2 * len(left & right) * SIMILARITY_SCALE // (len(left) + len(right))


def _best_similarity(
    queries: tuple[frozenset[str], ...],
    documents: tuple[frozenset[str], ...],
) -> int:
    return max(
        (_dice(query, document) for query in queries for document in documents),
        default=0,
    )


def _contains_any(phrases: set[str], documents: tuple[str, ...]) -> bool:
    return any(phrase in document for phrase in phrases for document in documents)


def _candidate_set(
    evidence: RetrievalRoleEvidence,
    query_hash: str,
    tree: CanonicalTree,
    status: str,
    max_candidates: int,
    candidates: tuple[BoundaryTolerantRoleCandidate, ...],
) -> BoundaryTolerantRoleCandidateSet:
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "source_evidence_hash": evidence.evidence_hash,
        "source_query_hash": query_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "status": status,
        "embedding_used": False,
        "allows_addition": False,
        "max_candidates": max_candidates,
        "candidates": [item.to_dict() for item in candidates],
    }
    return BoundaryTolerantRoleCandidateSet(
        source_evidence_hash=evidence.evidence_hash,
        source_query_hash=query_hash,
        source_snapshot_hash=tree.snapshot_hash,
        status=status,
        max_candidates=max_candidates,
        candidates=candidates,
        candidate_set_hash=canonical_digest(payload),
    )


__all__ = [
    "ALGORITHM_VERSION",
    "BoundaryTolerantRoleCandidate",
    "BoundaryTolerantRoleCandidateSet",
    "BoundaryTolerantRoleScore",
    "RESULT_SCHEMA_VERSION",
    "SIMILARITY_SCALE",
    "build_boundary_tolerant_role_candidate_set",
]
