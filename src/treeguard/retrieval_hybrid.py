"""Deterministic H1 dense-vector validation, ranking, and RRF fusion."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from treeguard.change_intent import IntentConfirmation, IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.lexical import text_terms
from treeguard.models import CanonicalTree
from treeguard.retrieval_query import build_retrieval_query
from treeguard.retrieval_role_tolerant import (
    BoundaryTolerantRoleCandidateSet,
    build_boundary_tolerant_role_candidate_set,
)
from treeguard.retrieval_roles import RetrievalRoleEvidence, verify_retrieval_role_evidence


MODEL_ID = "text-embedding-v4"
EMBEDDING_DIMENSIONS = 512
NODE_DOCUMENT_VERSION = "treeguard.hybrid-node-document.h1.v1"
QUERY_DOCUMENT_VERSION = "treeguard.hybrid-query-document.h1.v1"
INDEX_SCHEMA_VERSION = "treeguard.hybrid-embedding-index.h1.v1"
QUERY_EMBEDDING_SCHEMA_VERSION = "treeguard.hybrid-query-embedding.h1.v1"
RESULT_SCHEMA_VERSION = "treeguard.hybrid-candidate-set.h1.v1"
ALGORITHM_VERSION = "treeguard.r2-vector-rrf-h1.v1"
RETRIEVAL_SEMANTICS = "R2_LEXICAL_PLUS_DENSE_VECTOR_FIXED_RRF"
MAX_DOCUMENT_CHARACTERS = 2_000
MAX_INDEX_ENTRIES = 10_000
LEG_LIMIT = 40
DEFAULT_MAX_CANDIDATES = 20
RRF_K = 60
RRF_SCALE = 1_000_000
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_WHITESPACE = re.compile(r"\s+")
_INDEX_KEYS = {
    "schema_version",
    "source_snapshot_hash",
    "model_id",
    "dimensions",
    "document_version",
    "entries",
    "index_hash",
}
_INDEX_ENTRY_KEYS = {"node_id", "source_document_hash", "values"}


class HybridRetrievalError(ValueError):
    def __init__(self, code: str, message: str = "hybrid retrieval rejected") -> None:
        super().__init__(message)
        self.code = code


class DenseVectorEntry(Protocol):
    node_id: str
    values: tuple[float, ...]


class DenseVectorSource(Protocol):
    entries: tuple[DenseVectorEntry, ...]
    index_hash: str


class DenseQuerySource(Protocol):
    values: tuple[float, ...]
    embedding_hash: str


def _digest(value: str) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _finite_vector(values: Sequence[float], dimensions: int) -> tuple[float, ...]:
    try:
        valid_length = not isinstance(values, (str, bytes)) and len(values) == dimensions
    except TypeError:
        valid_length = False
    if not valid_length:
        raise HybridRetrievalError("HYBRID_EMBEDDING_RESPONSE_INVALID")
    vector = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise HybridRetrievalError("HYBRID_EMBEDDING_RESPONSE_INVALID")
        vector.append(float(value))
    if math.fsum(value * value for value in vector) <= 0:
        raise HybridRetrievalError("HYBRID_EMBEDDING_RESPONSE_INVALID")
    return tuple(vector)


def validate_hybrid_embedding_vector(values: Sequence[float]) -> tuple[float, ...]:
    """Validate one untrusted H1 embedding without retaining caller containers."""

    return _finite_vector(values, EMBEDDING_DIMENSIONS)


def _normalized(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _anchor_terms(value: str) -> tuple[str, ...]:
    return tuple(sorted(term for term in text_terms(_normalized(value)) if len(term) >= 2))


def _requirement_without_exclusions(
    evidence: RetrievalRoleEvidence,
    requirement_text: str,
) -> str:
    exclusions = sorted(
        ((span.start, span.end) for span in evidence.spans if span.role == "EXCLUSION"),
        reverse=True,
    )
    result = requirement_text
    for start, end in exclusions:
        result = result[:start] + " " + result[end:]
    return _WHITESPACE.sub(" ", result).strip()


@dataclass(frozen=True, slots=True)
class HybridNodeDocument:
    node_id: str
    text: str
    anchor_terms: tuple[str, ...]
    document_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id:
            raise ValueError("hybrid node document id is invalid")
        if not isinstance(self.text, str) or not self.text or len(self.text) > MAX_DOCUMENT_CHARACTERS:
            raise ValueError("hybrid node document text is invalid")
        if self.anchor_terms != tuple(sorted(set(self.anchor_terms))) or not all(
            isinstance(term, str) and term and len(term) >= 2 for term in self.anchor_terms
        ):
            raise ValueError("hybrid node document anchors are invalid")
        if self.document_hash != canonical_digest(self._payload()):
            raise ValueError("hybrid node document hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": NODE_DOCUMENT_VERSION,
            "node_id": self.node_id,
            "text": self.text,
            "anchor_terms": list(self.anchor_terms),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "document_hash": self.document_hash}

    def to_model_text(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class HybridQueryDocument:
    source_evidence_hash: str
    source_query_hash: str
    text: str
    anchor_terms: tuple[str, ...]
    document_hash: str

    def __post_init__(self) -> None:
        if not _digest(self.source_evidence_hash) or not _digest(self.source_query_hash):
            raise ValueError("hybrid query source hashes are invalid")
        if not isinstance(self.text, str) or not self.text or len(self.text) > MAX_DOCUMENT_CHARACTERS:
            raise ValueError("hybrid query text is invalid")
        if self.anchor_terms != tuple(sorted(set(self.anchor_terms))) or not all(
            isinstance(term, str) and term and len(term) >= 2 for term in self.anchor_terms
        ):
            raise ValueError("hybrid query anchors are invalid")
        if self.document_hash != canonical_digest(self._payload()):
            raise ValueError("hybrid query document hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_DOCUMENT_VERSION,
            "source_evidence_hash": self.source_evidence_hash,
            "source_query_hash": self.source_query_hash,
            "text": self.text,
            "anchor_terms": list(self.anchor_terms),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "document_hash": self.document_hash}

    def to_model_text(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class HybridEmbeddingEntry:
    node_id: str
    source_document_hash: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id or not _digest(self.source_document_hash):
            raise ValueError("hybrid embedding entry source is invalid")
        object.__setattr__(self, "values", _finite_vector(self.values, EMBEDDING_DIMENSIONS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "source_document_hash": self.source_document_hash,
            "values": list(self.values),
        }


@dataclass(frozen=True, slots=True)
class HybridEmbeddingIndex:
    source_snapshot_hash: str
    model_id: str
    dimensions: int
    document_version: str
    entries: tuple[HybridEmbeddingEntry, ...]
    index_hash: str

    def __post_init__(self) -> None:
        if (
            not _digest(self.source_snapshot_hash)
            or self.model_id != MODEL_ID
            or self.dimensions != EMBEDDING_DIMENSIONS
            or self.document_version != NODE_DOCUMENT_VERSION
            or not isinstance(self.entries, tuple)
            or not self.entries
            or len(self.entries) > MAX_INDEX_ENTRIES
            or tuple(item.node_id for item in self.entries) != tuple(sorted(item.node_id for item in self.entries))
            or len({item.node_id for item in self.entries}) != len(self.entries)
        ):
            raise ValueError("hybrid embedding index contract is invalid")
        if self.index_hash != canonical_digest(self._payload()):
            raise ValueError("hybrid embedding index hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": INDEX_SCHEMA_VERSION,
            "source_snapshot_hash": self.source_snapshot_hash,
            "model_id": self.model_id,
            "dimensions": self.dimensions,
            "document_version": self.document_version,
            "entries": [item.to_dict() for item in self.entries],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "index_hash": self.index_hash}

    @classmethod
    def from_dict(cls, payload: Any) -> "HybridEmbeddingIndex":
        if not isinstance(payload, dict) or set(payload) != _INDEX_KEYS:
            raise HybridRetrievalError("HYBRID_INDEX_ARTIFACT_INVALID")
        raw_entries = payload["entries"]
        if not isinstance(raw_entries, list) or not raw_entries:
            raise HybridRetrievalError("HYBRID_INDEX_ARTIFACT_INVALID")
        entries = []
        try:
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict) or set(raw_entry) != _INDEX_ENTRY_KEYS:
                    raise HybridRetrievalError("HYBRID_INDEX_ARTIFACT_INVALID")
                entries.append(
                    HybridEmbeddingEntry(
                        node_id=raw_entry["node_id"],
                        source_document_hash=raw_entry["source_document_hash"],
                        values=raw_entry["values"],
                    )
                )
            return cls(
                source_snapshot_hash=payload["source_snapshot_hash"],
                model_id=payload["model_id"],
                dimensions=payload["dimensions"],
                document_version=payload["document_version"],
                entries=tuple(entries),
                index_hash=payload["index_hash"],
            )
        except (HybridRetrievalError, KeyError, TypeError, ValueError):
            raise HybridRetrievalError("HYBRID_INDEX_ARTIFACT_INVALID") from None


@dataclass(frozen=True, slots=True)
class HybridQueryEmbedding:
    source_document_hash: str
    model_id: str
    dimensions: int
    values: tuple[float, ...]
    embedding_hash: str

    def __post_init__(self) -> None:
        if not _digest(self.source_document_hash) or self.model_id != MODEL_ID or self.dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError("hybrid query embedding contract is invalid")
        object.__setattr__(self, "values", _finite_vector(self.values, EMBEDDING_DIMENSIONS))
        if self.embedding_hash != canonical_digest(self._payload()):
            raise ValueError("hybrid query embedding hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_EMBEDDING_SCHEMA_VERSION,
            "source_document_hash": self.source_document_hash,
            "model_id": self.model_id,
            "dimensions": self.dimensions,
            "values": list(self.values),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "embedding_hash": self.embedding_hash}


@dataclass(frozen=True, slots=True)
class HybridCandidateScore:
    lexical_rank: int | None
    vector_rank: int | None
    vector_similarity_scaled: int | None
    total: int

    def __post_init__(self) -> None:
        for rank in (self.lexical_rank, self.vector_rank):
            if rank is not None and (not isinstance(rank, int) or isinstance(rank, bool) or not 1 <= rank <= LEG_LIMIT):
                raise ValueError("hybrid candidate rank is invalid")
        if self.lexical_rank is None and self.vector_rank is None:
            raise ValueError("hybrid candidate requires a source leg")
        if self.vector_rank is None and self.vector_similarity_scaled is not None:
            raise ValueError("hybrid candidate vector diagnostic is inconsistent")
        if self.vector_rank is not None and (
            not isinstance(self.vector_similarity_scaled, int)
            or isinstance(self.vector_similarity_scaled, bool)
            or not -RRF_SCALE <= self.vector_similarity_scaled <= RRF_SCALE
        ):
            raise ValueError("hybrid vector similarity is invalid")
        expected = sum(
            RRF_SCALE // (RRF_K + rank)
            for rank in (self.lexical_rank, self.vector_rank)
            if rank is not None
        )
        if not isinstance(self.total, int) or isinstance(self.total, bool) or self.total != expected:
            raise ValueError("hybrid RRF total is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "lexical_rank": self.lexical_rank,
            "vector_rank": self.vector_rank,
            "vector_similarity_scaled": self.vector_similarity_scaled,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    rank: int
    node_id: str
    score: HybridCandidateScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.score, HybridCandidateScore)
        ):
            raise ValueError("hybrid candidate is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"rank": self.rank, "node_id": self.node_id, "score": self.score.to_dict()}


@dataclass(frozen=True, slots=True)
class HybridCandidateSet:
    source_evidence_hash: str
    source_query_hash: str
    source_snapshot_hash: str
    source_lexical_candidate_set_hash: str
    source_query_document_hash: str
    source_index_hash: str | None
    source_query_embedding_hash: str | None
    status: str
    vector_enabled: bool
    max_candidates: int
    candidates: tuple[HybridCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        digests = (
            self.source_evidence_hash,
            self.source_query_hash,
            self.source_snapshot_hash,
            self.source_lexical_candidate_set_hash,
            self.source_query_document_hash,
            self.candidate_set_hash,
        )
        if not all(_digest(item) for item in digests):
            raise ValueError("hybrid candidate source hashes are invalid")
        if not isinstance(self.vector_enabled, bool) or self.status not in {"CANDIDATES_READY", "NO_CANDIDATES", "INSUFFICIENT_SIGNAL"}:
            raise ValueError("hybrid candidate status is invalid")
        if self.vector_enabled != (self.source_index_hash is not None and self.source_query_embedding_hash is not None):
            raise ValueError("hybrid vector sources are inconsistent")
        if self.vector_enabled and (not _digest(self.source_index_hash) or not _digest(self.source_query_embedding_hash)):
            raise ValueError("hybrid vector source hashes are invalid")
        if not isinstance(self.max_candidates, int) or isinstance(self.max_candidates, bool) or not 1 <= self.max_candidates <= LEG_LIMIT:
            raise ValueError("hybrid candidate limit is invalid")
        if not isinstance(self.candidates, tuple) or not all(
            isinstance(item, HybridCandidate) for item in self.candidates
        ):
            raise ValueError("hybrid candidate collection is invalid")
        if tuple(item.rank for item in self.candidates) != tuple(range(1, len(self.candidates) + 1)) or len(self.candidates) > self.max_candidates:
            raise ValueError("hybrid candidate ranks are invalid")
        if len({item.node_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("hybrid candidate nodes are not unique")
        if tuple((-item.score.total, item.node_id) for item in self.candidates) != tuple(sorted((-item.score.total, item.node_id) for item in self.candidates)):
            raise ValueError("hybrid candidate order is invalid")
        if (self.status == "CANDIDATES_READY") != bool(self.candidates):
            raise ValueError("hybrid candidate status and items disagree")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("hybrid candidate hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "source_evidence_hash": self.source_evidence_hash,
            "source_query_hash": self.source_query_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_lexical_candidate_set_hash": self.source_lexical_candidate_set_hash,
            "source_query_document_hash": self.source_query_document_hash,
            "source_index_hash": self.source_index_hash,
            "source_query_embedding_hash": self.source_query_embedding_hash,
            "status": self.status,
            "vector_enabled": self.vector_enabled,
            "embedding_used": self.vector_enabled,
            "allows_addition": False,
            "max_candidates": self.max_candidates,
            "candidates": [item.to_dict() for item in self.candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "candidate_set_hash": self.candidate_set_hash}

    def aggregate_report(self) -> dict[str, Any]:
        return {
            "report_version": "treeguard.hybrid-retrieval-aggregate.h1.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": self.vector_enabled,
            "allows_addition": False,
            "candidate_count": len(self.candidates),
        }


def build_hybrid_node_documents(tree: CanonicalTree) -> tuple[HybridNodeDocument, ...]:
    if not isinstance(tree, CanonicalTree) or not tree.is_resource_map:
        raise HybridRetrievalError("CANDIDATE_SOURCE_NOT_RESOURCE")
    documents = []
    nodes_by_id = {node.node_id: node for node in tree.nodes}
    for node in sorted(tree.nodes, key=lambda item: item.node_id):
        if node.kind == "UNSUPPORTED":
            continue
        contract = node.value_contract
        ancestor_parts = []
        parent_id = node.parent_node_id
        while parent_id is not None:
            parent = nodes_by_id.get(parent_id)
            if parent is None:
                raise HybridRetrievalError("HYBRID_DOCUMENT_SET_INVALID")
            ancestor_parts.append(f"{parent.name} [{parent.label}]")
            parent_id = parent.parent_node_id
        ancestors = " / ".join(reversed(ancestor_parts))
        text = "\n".join(
            (
                f"name: {node.name}",
                f"label: {node.label}",
                f"ancestors: {ancestors}",
                f"kind: {node.kind}",
                f"value_type: {contract.value_type if contract is not None else ''}",
                f"cardinality: {contract.cardinality if contract is not None else ''}",
            )
        )
        if len(text) > MAX_DOCUMENT_CHARACTERS:
            raise HybridRetrievalError("HYBRID_DOCUMENT_TOO_LARGE")
        anchors = _anchor_terms(" ".join((node.name, node.label, ancestors)))
        payload = {"schema_version": NODE_DOCUMENT_VERSION, "node_id": node.node_id, "text": text, "anchor_terms": list(anchors)}
        documents.append(HybridNodeDocument(node.node_id, text, anchors, canonical_digest(payload)))
    return tuple(documents)


def build_hybrid_query_document(
    evidence: RetrievalRoleEvidence,
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
) -> HybridQueryDocument:
    verify_retrieval_role_evidence(evidence, request)
    query = build_retrieval_query(request, confirmation, tree, include_model_expansion=False)
    role_values = {role: [span.text for span in evidence.spans if span.role == role] for role in ("TARGET", "SCOPE")}
    requirement = _requirement_without_exclusions(evidence, request.requirement_text)
    text = "\n".join(
        (
            f"requirement: {requirement}",
            f"target: {' | '.join(role_values['TARGET'])}",
            f"scope: {' | '.join(role_values['SCOPE'])}",
            f"kind: {query.node_kind}",
            f"value_type: {query.value_type or ''}",
            f"cardinality: {query.cardinality}",
        )
    )
    if len(text) > MAX_DOCUMENT_CHARACTERS:
        raise HybridRetrievalError("HYBRID_DOCUMENT_TOO_LARGE")
    anchors = tuple(sorted(set().union(*(_anchor_terms(value) for values in role_values.values() for value in values))))
    payload = {
        "schema_version": QUERY_DOCUMENT_VERSION,
        "source_evidence_hash": evidence.evidence_hash,
        "source_query_hash": query.query_hash,
        "text": text,
        "anchor_terms": list(anchors),
    }
    return HybridQueryDocument(evidence.evidence_hash, query.query_hash, text, anchors, canonical_digest(payload))


def vector_leg_enabled(query: HybridQueryDocument, documents: tuple[HybridNodeDocument, ...]) -> bool:
    if not isinstance(query, HybridQueryDocument) or not isinstance(documents, tuple):
        raise HybridRetrievalError("HYBRID_DOCUMENT_SET_INVALID")
    available = set().union(*(document.anchor_terms for document in documents))
    return bool(set(query.anchor_terms) & available)


def build_hybrid_embedding_index(
    tree: CanonicalTree,
    documents: tuple[HybridNodeDocument, ...],
    vectors: Mapping[str, Sequence[float]],
) -> HybridEmbeddingIndex:
    canonical_documents = build_hybrid_node_documents(tree)
    if documents != canonical_documents:
        raise HybridRetrievalError("HYBRID_DOCUMENT_SET_INVALID")
    expected = {item.node_id: item for item in documents}
    if set(vectors) != set(expected):
        raise HybridRetrievalError("HYBRID_EMBEDDING_RESPONSE_INVALID")
    entries = tuple(
        HybridEmbeddingEntry(node_id, expected[node_id].document_hash, _finite_vector(vectors[node_id], EMBEDDING_DIMENSIONS))
        for node_id in sorted(expected)
    )
    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source_snapshot_hash": tree.snapshot_hash,
        "model_id": MODEL_ID,
        "dimensions": EMBEDDING_DIMENSIONS,
        "document_version": NODE_DOCUMENT_VERSION,
        "entries": [item.to_dict() for item in entries],
    }
    return HybridEmbeddingIndex(tree.snapshot_hash, MODEL_ID, EMBEDDING_DIMENSIONS, NODE_DOCUMENT_VERSION, entries, canonical_digest(payload))


def build_hybrid_query_embedding(document: HybridQueryDocument, values: Sequence[float]) -> HybridQueryEmbedding:
    vector = _finite_vector(values, EMBEDDING_DIMENSIONS)
    payload = {
        "schema_version": QUERY_EMBEDDING_SCHEMA_VERSION,
        "source_document_hash": document.document_hash,
        "model_id": MODEL_ID,
        "dimensions": EMBEDDING_DIMENSIONS,
        "values": list(vector),
    }
    return HybridQueryEmbedding(document.document_hash, MODEL_ID, EMBEDDING_DIMENSIONS, vector, canonical_digest(payload))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    denominator = math.sqrt(math.fsum(value * value for value in left)) * math.sqrt(math.fsum(value * value for value in right))
    return math.fsum(a * b for a, b in zip(left, right, strict=True)) / denominator


def _excluded_node_ids(evidence: RetrievalRoleEvidence, tree: CanonicalTree) -> set[str]:
    exclusions = {_normalized(span.text) for span in evidence.spans if span.role == "EXCLUSION"}
    return {
        node.node_id
        for node in tree.nodes
        if any(
            phrase and phrase in document
            for phrase in exclusions
            for document in (_normalized(node.name), _normalized(node.label), _normalized(" ".join(node.path_labels)))
        )
    }


def _validate_vector_sources(
    tree: CanonicalTree,
    documents: tuple[HybridNodeDocument, ...],
    query_document: HybridQueryDocument,
    index: HybridEmbeddingIndex,
    query_embedding: HybridQueryEmbedding,
) -> None:
    verify_hybrid_embedding_index(index, tree, documents)
    if (
        query_embedding.source_document_hash != query_document.document_hash
        or index.model_id != query_embedding.model_id
        or index.dimensions != query_embedding.dimensions
    ):
        raise HybridRetrievalError("HYBRID_INDEX_STALE")


def verify_hybrid_embedding_index(
    index: HybridEmbeddingIndex,
    tree: CanonicalTree,
    documents: tuple[HybridNodeDocument, ...] | None = None,
) -> None:
    """Bind a persisted index back to the trusted tree and canonical documents."""

    if not isinstance(index, HybridEmbeddingIndex) or not isinstance(tree, CanonicalTree):
        raise HybridRetrievalError("HYBRID_INDEX_ARTIFACT_INVALID")
    canonical_documents = build_hybrid_node_documents(tree)
    if documents is not None and documents != canonical_documents:
        raise HybridRetrievalError("HYBRID_DOCUMENT_SET_INVALID")
    expected = {item.node_id: item.document_hash for item in canonical_documents}
    actual = {item.node_id: item.source_document_hash for item in index.entries}
    if index.source_snapshot_hash != tree.snapshot_hash or actual != expected:
        raise HybridRetrievalError("HYBRID_INDEX_STALE")


def build_hybrid_candidate_set(
    evidence: RetrievalRoleEvidence,
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    index: HybridEmbeddingIndex | None = None,
    query_embedding: HybridQueryEmbedding | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> HybridCandidateSet:
    if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or not 1 <= max_candidates <= LEG_LIMIT:
        raise HybridRetrievalError("CANDIDATE_LIMIT_INVALID")
    documents = build_hybrid_node_documents(tree)
    query_document = build_hybrid_query_document(evidence, request, confirmation, tree)
    lexical = build_boundary_tolerant_role_candidate_set(
        evidence, request, confirmation, tree, include_model_expansion=False, max_candidates=LEG_LIMIT
    )
    enabled = vector_leg_enabled(query_document, documents)
    if not enabled:
        if index is not None or query_embedding is not None:
            raise HybridRetrievalError("HYBRID_UNEXPECTED_VECTOR_INPUT")
        return fuse_hybrid_candidate_set(
            evidence, query_document, lexical, tree, None, None, max_candidates
        )
    if not isinstance(index, HybridEmbeddingIndex) or not isinstance(query_embedding, HybridQueryEmbedding):
        raise HybridRetrievalError("HYBRID_EMBEDDING_REQUIRED")
    _validate_vector_sources(tree, documents, query_document, index, query_embedding)
    return fuse_hybrid_candidate_set(
        evidence,
        query_document,
        lexical,
        tree,
        index,
        query_embedding,
        max_candidates,
    )


def fuse_hybrid_candidate_set(
    evidence: RetrievalRoleEvidence,
    query_document: HybridQueryDocument,
    lexical: BoundaryTolerantRoleCandidateSet,
    tree: CanonicalTree,
    index: DenseVectorSource | None,
    query_embedding: DenseQuerySource | None,
    max_candidates: int,
) -> HybridCandidateSet:
    if (
        not isinstance(evidence, RetrievalRoleEvidence)
        or not isinstance(query_document, HybridQueryDocument)
        or not isinstance(lexical, BoundaryTolerantRoleCandidateSet)
        or not isinstance(tree, CanonicalTree)
        or not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or not 1 <= max_candidates <= LEG_LIMIT
        or (index is None) != (query_embedding is None)
    ):
        raise HybridRetrievalError("HYBRID_VECTOR_SOURCE_INVALID")
    if index is not None and query_embedding is not None:
        if (
            not _digest(getattr(index, "index_hash", ""))
            or not _digest(getattr(query_embedding, "embedding_hash", ""))
            or not isinstance(getattr(index, "entries", None), tuple)
        ):
            raise HybridRetrievalError("HYBRID_VECTOR_SOURCE_INVALID")
        expected_node_ids = {
            document.node_id for document in build_hybrid_node_documents(tree)
        }
        actual_node_ids = {entry.node_id for entry in index.entries}
        if actual_node_ids != expected_node_ids:
            raise HybridRetrievalError("HYBRID_VECTOR_SOURCE_INVALID")
        _finite_vector(query_embedding.values, EMBEDDING_DIMENSIONS)
        for entry in index.entries:
            _finite_vector(entry.values, EMBEDDING_DIMENSIONS)
    candidates, status = rank_hybrid_candidates(
        evidence,
        lexical,
        tree,
        index,
        query_embedding,
        max_candidates,
    )
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "source_evidence_hash": evidence.evidence_hash,
        "source_query_hash": query_document.source_query_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_lexical_candidate_set_hash": lexical.candidate_set_hash,
        "source_query_document_hash": query_document.document_hash,
        "source_index_hash": index.index_hash if index is not None else None,
        "source_query_embedding_hash": query_embedding.embedding_hash if query_embedding is not None else None,
        "status": status,
        "vector_enabled": index is not None,
        "embedding_used": index is not None,
        "allows_addition": False,
        "max_candidates": max_candidates,
        "candidates": [item.to_dict() for item in candidates],
    }
    return HybridCandidateSet(
        evidence.evidence_hash,
        query_document.source_query_hash,
        tree.snapshot_hash,
        lexical.candidate_set_hash,
        query_document.document_hash,
        index.index_hash if index is not None else None,
        query_embedding.embedding_hash if query_embedding is not None else None,
        status,
        index is not None,
        max_candidates,
        candidates,
        canonical_digest(payload),
    )


def rank_hybrid_candidates(
    evidence: RetrievalRoleEvidence,
    lexical: BoundaryTolerantRoleCandidateSet,
    tree: CanonicalTree,
    index: DenseVectorSource | None,
    query_embedding: DenseQuerySource | None,
    max_candidates: int,
) -> tuple[tuple[HybridCandidate, ...], str]:
    """Return fixed RRF candidates without choosing an artifact version."""

    lexical_ranks = {
        item.node_id: item.rank for item in lexical.candidates[:LEG_LIMIT]
    }
    vector_ranks: dict[str, int] = {}
    similarities: dict[str, int] = {}
    if index is not None and query_embedding is not None:
        excluded = _excluded_node_ids(evidence, tree)
        scored = []
        for entry in index.entries:
            if entry.node_id in excluded:
                continue
            similarity = _cosine(query_embedding.values, entry.values)
            scored.append((-similarity, entry.node_id, similarity))
        scored.sort(key=lambda item: (item[0], item[1]))
        for rank, (_, node_id, similarity) in enumerate(scored[:LEG_LIMIT], start=1):
            vector_ranks[node_id] = rank
            similarities[node_id] = max(-RRF_SCALE, min(RRF_SCALE, int(similarity * RRF_SCALE)))
    scored_candidates = []
    for node_id in set(lexical_ranks) | set(vector_ranks):
        lexical_rank = lexical_ranks.get(node_id)
        vector_rank = vector_ranks.get(node_id)
        total = sum(RRF_SCALE // (RRF_K + rank) for rank in (lexical_rank, vector_rank) if rank is not None)
        score = HybridCandidateScore(lexical_rank, vector_rank, similarities.get(node_id), total)
        scored_candidates.append((-total, node_id, score))
    scored_candidates.sort(key=lambda item: (item[0], item[1]))
    candidates = tuple(
        HybridCandidate(rank, node_id, score)
        for rank, (_, node_id, score) in enumerate(scored_candidates[:max_candidates], start=1)
    )
    status = "CANDIDATES_READY" if candidates else lexical.status
    return candidates, status


__all__ = [
    "ALGORITHM_VERSION",
    "EMBEDDING_DIMENSIONS",
    "MAX_INDEX_ENTRIES",
    "HybridCandidateSet",
    "HybridEmbeddingIndex",
    "HybridNodeDocument",
    "HybridQueryDocument",
    "HybridQueryEmbedding",
    "HybridRetrievalError",
    "MODEL_ID",
    "build_hybrid_candidate_set",
    "build_hybrid_embedding_index",
    "build_hybrid_node_documents",
    "build_hybrid_query_document",
    "build_hybrid_query_embedding",
    "fuse_hybrid_candidate_set",
    "rank_hybrid_candidates",
    "validate_hybrid_embedding_vector",
    "vector_leg_enabled",
    "verify_hybrid_embedding_index",
]
