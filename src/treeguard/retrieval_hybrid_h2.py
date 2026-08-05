"""Frozen H2 local-BGE profile, index, and query embedding contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from treeguard.change_intent import IntentConfirmation, IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree
from treeguard.retrieval_hybrid import (
    DEFAULT_MAX_CANDIDATES,
    EMBEDDING_DIMENSIONS,
    MAX_INDEX_ENTRIES,
    HybridCandidate,
    HybridNodeDocument,
    HybridQueryDocument,
    HybridRetrievalError,
    build_hybrid_node_documents,
    build_hybrid_query_document,
    rank_hybrid_candidates,
    validate_hybrid_embedding_vector,
    vector_leg_enabled,
)
from treeguard.retrieval_role_tolerant import (
    build_boundary_tolerant_role_candidate_set,
)
from treeguard.retrieval_roles import RetrievalRoleEvidence


MODEL_ID = "BAAI/bge-small-zh-v1.5"
MODEL_REVISION = "7999e1d3359715c523056ef9478215996d62a620"
WEIGHTS_SHA256 = (
    "354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026"
)
PROFILE_VERSION = "treeguard.local-bge-small-zh-v1.5.h2.v1"
INDEX_SCHEMA_VERSION = "treeguard.hybrid-embedding-index.h2.v1"
QUERY_EMBEDDING_SCHEMA_VERSION = "treeguard.hybrid-query-embedding.h2.v1"
RESULT_SCHEMA_VERSION = "treeguard.hybrid-candidate-set.h2.v1"
ALGORITHM_VERSION = "treeguard.r2-vector-rrf-h2.v1"
RETRIEVAL_SEMANTICS = "R2_LEXICAL_PLUS_LOCAL_BGE_FIXED_RRF"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
MAX_TOKENS = 512
POOLING = "CLS"
NORMALIZATION = "L2"
DTYPE = "float32"
DEVICE = "cpu"
FROZEN_BATCH_SIZE = 16
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_KEYS = {
    "profile_version",
    "model_id",
    "model_revision",
    "weights_sha256",
    "artifact_manifest_hash",
    "dimensions",
    "max_tokens",
    "pooling",
    "normalization",
    "dtype",
    "device",
    "query_instruction",
    "batch_size",
    "profile_hash",
}
_INDEX_KEYS = {
    "schema_version",
    "source_snapshot_hash",
    "source_profile_hash",
    "document_version",
    "entries",
    "index_hash",
}
_ENTRY_KEYS = {"node_id", "source_document_hash", "values"}


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class H2EmbeddingProfile:
    artifact_manifest_hash: str
    batch_size: int
    profile_hash: str

    def __post_init__(self) -> None:
        if (
            not _is_digest(self.artifact_manifest_hash)
            or not isinstance(self.batch_size, int)
            or isinstance(self.batch_size, bool)
            or self.batch_size != FROZEN_BATCH_SIZE
            or not _is_digest(self.profile_hash)
        ):
            raise ValueError("H2 embedding profile is invalid")
        if self.profile_hash != canonical_digest(self._payload()):
            raise ValueError("H2 embedding profile hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "profile_version": PROFILE_VERSION,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "weights_sha256": WEIGHTS_SHA256,
            "artifact_manifest_hash": self.artifact_manifest_hash,
            "dimensions": EMBEDDING_DIMENSIONS,
            "max_tokens": MAX_TOKENS,
            "pooling": POOLING,
            "normalization": NORMALIZATION,
            "dtype": DTYPE,
            "device": DEVICE,
            "query_instruction": QUERY_INSTRUCTION,
            "batch_size": self.batch_size,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "profile_hash": self.profile_hash}

    @classmethod
    def build(
        cls,
        *,
        artifact_manifest_hash: str,
        batch_size: int,
    ) -> "H2EmbeddingProfile":
        payload = {
            "profile_version": PROFILE_VERSION,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "weights_sha256": WEIGHTS_SHA256,
            "artifact_manifest_hash": artifact_manifest_hash,
            "dimensions": EMBEDDING_DIMENSIONS,
            "max_tokens": MAX_TOKENS,
            "pooling": POOLING,
            "normalization": NORMALIZATION,
            "dtype": DTYPE,
            "device": DEVICE,
            "query_instruction": QUERY_INSTRUCTION,
            "batch_size": batch_size,
        }
        return cls(artifact_manifest_hash, batch_size, canonical_digest(payload))

    @classmethod
    def from_dict(cls, payload: Any) -> "H2EmbeddingProfile":
        if not isinstance(payload, dict) or set(payload) != _PROFILE_KEYS:
            raise HybridRetrievalError("H2_PROFILE_ARTIFACT_INVALID")
        fixed = {
            "profile_version": PROFILE_VERSION,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "weights_sha256": WEIGHTS_SHA256,
            "dimensions": EMBEDDING_DIMENSIONS,
            "max_tokens": MAX_TOKENS,
            "pooling": POOLING,
            "normalization": NORMALIZATION,
            "dtype": DTYPE,
            "device": DEVICE,
            "query_instruction": QUERY_INSTRUCTION,
        }
        if any(payload[key] != value for key, value in fixed.items()):
            raise HybridRetrievalError("H2_PROFILE_ARTIFACT_INVALID")
        try:
            profile = cls(
                payload["artifact_manifest_hash"],
                payload["batch_size"],
                payload["profile_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise HybridRetrievalError("H2_PROFILE_ARTIFACT_INVALID") from None
        if profile.to_dict() != payload:
            raise HybridRetrievalError("H2_PROFILE_ARTIFACT_INVALID")
        return profile


@dataclass(frozen=True, slots=True)
class H2EmbeddingEntry:
    node_id: str
    source_document_hash: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.node_id, str)
            or not self.node_id
            or not _is_digest(self.source_document_hash)
        ):
            raise ValueError("H2 embedding entry source is invalid")
        object.__setattr__(
            self,
            "values",
            validate_hybrid_embedding_vector(self.values),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "source_document_hash": self.source_document_hash,
            "values": list(self.values),
        }


@dataclass(frozen=True, slots=True)
class H2EmbeddingIndex:
    source_snapshot_hash: str
    source_profile_hash: str
    document_version: str
    entries: tuple[H2EmbeddingEntry, ...]
    index_hash: str

    def __post_init__(self) -> None:
        if (
            not _is_digest(self.source_snapshot_hash)
            or not _is_digest(self.source_profile_hash)
            or self.document_version
            != "treeguard.hybrid-node-document.h1.v1"
            or not isinstance(self.entries, tuple)
            or not self.entries
            or len(self.entries) > MAX_INDEX_ENTRIES
            or tuple(item.node_id for item in self.entries)
            != tuple(sorted(item.node_id for item in self.entries))
            or len({item.node_id for item in self.entries}) != len(self.entries)
            or not _is_digest(self.index_hash)
        ):
            raise ValueError("H2 embedding index contract is invalid")
        if self.index_hash != canonical_digest(self._payload()):
            raise ValueError("H2 embedding index hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": INDEX_SCHEMA_VERSION,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_profile_hash": self.source_profile_hash,
            "document_version": self.document_version,
            "entries": [item.to_dict() for item in self.entries],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "index_hash": self.index_hash}

    @classmethod
    def from_dict(cls, payload: Any) -> "H2EmbeddingIndex":
        if not isinstance(payload, dict) or set(payload) != _INDEX_KEYS:
            raise HybridRetrievalError("H2_INDEX_ARTIFACT_INVALID")
        raw_entries = payload["entries"]
        if not isinstance(raw_entries, list) or not raw_entries:
            raise HybridRetrievalError("H2_INDEX_ARTIFACT_INVALID")
        try:
            entries = tuple(
                H2EmbeddingEntry(
                    item["node_id"],
                    item["source_document_hash"],
                    item["values"],
                )
                for item in raw_entries
                if isinstance(item, dict) and set(item) == _ENTRY_KEYS
            )
            if len(entries) != len(raw_entries):
                raise ValueError
            index = cls(
                payload["source_snapshot_hash"],
                payload["source_profile_hash"],
                payload["document_version"],
                entries,
                payload["index_hash"],
            )
        except (HybridRetrievalError, KeyError, TypeError, ValueError):
            raise HybridRetrievalError("H2_INDEX_ARTIFACT_INVALID") from None
        if index.to_dict() != payload:
            raise HybridRetrievalError("H2_INDEX_ARTIFACT_INVALID")
        return index


@dataclass(frozen=True, slots=True)
class H2QueryEmbedding:
    source_document_hash: str
    source_profile_hash: str
    values: tuple[float, ...]
    embedding_hash: str

    def __post_init__(self) -> None:
        if (
            not _is_digest(self.source_document_hash)
            or not _is_digest(self.source_profile_hash)
            or not _is_digest(self.embedding_hash)
        ):
            raise ValueError("H2 query embedding contract is invalid")
        object.__setattr__(
            self,
            "values",
            validate_hybrid_embedding_vector(self.values),
        )
        if self.embedding_hash != canonical_digest(self._payload()):
            raise ValueError("H2 query embedding hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_EMBEDDING_SCHEMA_VERSION,
            "source_document_hash": self.source_document_hash,
            "source_profile_hash": self.source_profile_hash,
            "values": list(self.values),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "embedding_hash": self.embedding_hash}


@dataclass(frozen=True, slots=True)
class H2CandidateSet:
    source_evidence_hash: str
    source_query_hash: str
    source_snapshot_hash: str
    source_lexical_candidate_set_hash: str
    source_query_document_hash: str
    source_profile_hash: str
    source_index_hash: str | None
    source_query_embedding_hash: str | None
    status: str
    vector_enabled: bool
    max_candidates: int
    candidates: tuple[HybridCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        required_hashes = (
            self.source_evidence_hash,
            self.source_query_hash,
            self.source_snapshot_hash,
            self.source_lexical_candidate_set_hash,
            self.source_query_document_hash,
            self.source_profile_hash,
            self.candidate_set_hash,
        )
        if (
            not all(_is_digest(value) for value in required_hashes)
            or self.status
            not in {"CANDIDATES_READY", "NO_CANDIDATES", "INSUFFICIENT_SIGNAL"}
            or not isinstance(self.vector_enabled, bool)
            or self.vector_enabled
            != (
                self.source_index_hash is not None
                and self.source_query_embedding_hash is not None
            )
            or not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or not 1 <= self.max_candidates <= 40
            or not isinstance(self.candidates, tuple)
            or any(not isinstance(item, HybridCandidate) for item in self.candidates)
            or len(self.candidates) > self.max_candidates
            or tuple(item.rank for item in self.candidates)
            != tuple(range(1, len(self.candidates) + 1))
            or len({item.node_id for item in self.candidates})
            != len(self.candidates)
            or (self.status == "CANDIDATES_READY") != bool(self.candidates)
        ):
            raise ValueError("H2 candidate set contract is invalid")
        if self.vector_enabled and (
            not _is_digest(self.source_index_hash)
            or not _is_digest(self.source_query_embedding_hash)
        ):
            raise ValueError("H2 candidate vector sources are invalid")
        if tuple(
            (-item.score.total, item.node_id) for item in self.candidates
        ) != tuple(
            sorted((-item.score.total, item.node_id) for item in self.candidates)
        ):
            raise ValueError("H2 candidate order is invalid")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("H2 candidate set hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "source_evidence_hash": self.source_evidence_hash,
            "source_query_hash": self.source_query_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_lexical_candidate_set_hash": (
                self.source_lexical_candidate_set_hash
            ),
            "source_query_document_hash": self.source_query_document_hash,
            "source_profile_hash": self.source_profile_hash,
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
            "report_version": "treeguard.hybrid-retrieval-aggregate.h2.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": self.vector_enabled,
            "allows_addition": False,
            "candidate_count": len(self.candidates),
        }


def build_h2_embedding_index(
    tree: CanonicalTree,
    documents: tuple[HybridNodeDocument, ...],
    vectors: Mapping[str, Sequence[float]],
    profile: H2EmbeddingProfile,
) -> H2EmbeddingIndex:
    canonical_documents = build_hybrid_node_documents(tree)
    if documents != canonical_documents or not isinstance(profile, H2EmbeddingProfile):
        raise HybridRetrievalError("H2_DOCUMENT_SET_INVALID")
    expected = {document.node_id: document for document in documents}
    if set(vectors) != set(expected):
        raise HybridRetrievalError("H2_EMBEDDING_RESPONSE_INVALID")
    try:
        entries = tuple(
            H2EmbeddingEntry(
                node_id,
                expected[node_id].document_hash,
                tuple(vectors[node_id]),
            )
            for node_id in sorted(expected)
        )
    except (HybridRetrievalError, TypeError, ValueError):
        raise HybridRetrievalError("H2_EMBEDDING_RESPONSE_INVALID") from None
    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_profile_hash": profile.profile_hash,
        "document_version": "treeguard.hybrid-node-document.h1.v1",
        "entries": [entry.to_dict() for entry in entries],
    }
    return H2EmbeddingIndex(
        tree.snapshot_hash,
        profile.profile_hash,
        "treeguard.hybrid-node-document.h1.v1",
        entries,
        canonical_digest(payload),
    )


def build_h2_query_embedding(
    document: HybridQueryDocument,
    values: Sequence[float],
    profile: H2EmbeddingProfile,
) -> H2QueryEmbedding:
    if not isinstance(document, HybridQueryDocument) or not isinstance(
        profile, H2EmbeddingProfile
    ):
        raise HybridRetrievalError("H2_QUERY_DOCUMENT_INVALID")
    vector = validate_hybrid_embedding_vector(values)
    payload = {
        "schema_version": QUERY_EMBEDDING_SCHEMA_VERSION,
        "source_document_hash": document.document_hash,
        "source_profile_hash": profile.profile_hash,
        "values": list(vector),
    }
    return H2QueryEmbedding(
        document.document_hash,
        profile.profile_hash,
        vector,
        canonical_digest(payload),
    )


def verify_h2_embedding_index(
    index: H2EmbeddingIndex,
    tree: CanonicalTree,
    profile: H2EmbeddingProfile,
) -> None:
    if (
        not isinstance(index, H2EmbeddingIndex)
        or not isinstance(tree, CanonicalTree)
        or not isinstance(profile, H2EmbeddingProfile)
    ):
        raise HybridRetrievalError("H2_INDEX_ARTIFACT_INVALID")
    expected = {
        document.node_id: document.document_hash
        for document in build_hybrid_node_documents(tree)
    }
    actual = {entry.node_id: entry.source_document_hash for entry in index.entries}
    if (
        index.source_snapshot_hash != tree.snapshot_hash
        or index.source_profile_hash != profile.profile_hash
        or actual != expected
    ):
        raise HybridRetrievalError("H2_INDEX_STALE")


def build_h2_candidate_set(
    evidence: RetrievalRoleEvidence,
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    profile: H2EmbeddingProfile,
    index: H2EmbeddingIndex | None = None,
    query_embedding: H2QueryEmbedding | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> H2CandidateSet:
    if not isinstance(profile, H2EmbeddingProfile):
        raise HybridRetrievalError("H2_PROFILE_ARTIFACT_INVALID")
    if (
        not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or not 1 <= max_candidates <= 40
    ):
        raise HybridRetrievalError("H2_CANDIDATE_LIMIT_INVALID")
    documents = build_hybrid_node_documents(tree)
    query_document = build_hybrid_query_document(
        evidence, request, confirmation, tree
    )
    lexical = build_boundary_tolerant_role_candidate_set(
        evidence,
        request,
        confirmation,
        tree,
        include_model_expansion=False,
        max_candidates=40,
    )
    if not vector_leg_enabled(query_document, documents):
        if index is not None or query_embedding is not None:
            raise HybridRetrievalError("H2_UNEXPECTED_VECTOR_INPUT")
        candidates, status = rank_hybrid_candidates(
            evidence, lexical, tree, None, None, max_candidates
        )
        return _build_h2_candidate_set(
            evidence,
            query_document,
            lexical.candidate_set_hash,
            tree,
            profile,
            None,
            None,
            status,
            max_candidates,
            candidates,
        )
    if not isinstance(index, H2EmbeddingIndex) or not isinstance(
        query_embedding, H2QueryEmbedding
    ):
        raise HybridRetrievalError("H2_EMBEDDING_REQUIRED")
    verify_h2_embedding_index(index, tree, profile)
    if (
        query_embedding.source_document_hash != query_document.document_hash
        or query_embedding.source_profile_hash != profile.profile_hash
    ):
        raise HybridRetrievalError("H2_INDEX_STALE")
    candidates, status = rank_hybrid_candidates(
        evidence,
        lexical,
        tree,
        index,
        query_embedding,
        max_candidates,
    )
    return _build_h2_candidate_set(
        evidence,
        query_document,
        lexical.candidate_set_hash,
        tree,
        profile,
        index,
        query_embedding,
        status,
        max_candidates,
        candidates,
    )


def _build_h2_candidate_set(
    evidence: RetrievalRoleEvidence,
    query_document: HybridQueryDocument,
    lexical_candidate_set_hash: str,
    tree: CanonicalTree,
    profile: H2EmbeddingProfile,
    index: H2EmbeddingIndex | None,
    query_embedding: H2QueryEmbedding | None,
    status: str,
    max_candidates: int,
    candidates: tuple[HybridCandidate, ...],
) -> H2CandidateSet:
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "source_evidence_hash": evidence.evidence_hash,
        "source_query_hash": query_document.source_query_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_lexical_candidate_set_hash": lexical_candidate_set_hash,
        "source_query_document_hash": query_document.document_hash,
        "source_profile_hash": profile.profile_hash,
        "source_index_hash": index.index_hash if index is not None else None,
        "source_query_embedding_hash": (
            query_embedding.embedding_hash if query_embedding is not None else None
        ),
        "status": status,
        "vector_enabled": index is not None,
        "embedding_used": index is not None,
        "allows_addition": False,
        "max_candidates": max_candidates,
        "candidates": [item.to_dict() for item in candidates],
    }
    return H2CandidateSet(
        evidence.evidence_hash,
        query_document.source_query_hash,
        tree.snapshot_hash,
        lexical_candidate_set_hash,
        query_document.document_hash,
        profile.profile_hash,
        index.index_hash if index is not None else None,
        query_embedding.embedding_hash if query_embedding is not None else None,
        status,
        index is not None,
        max_candidates,
        candidates,
        canonical_digest(payload),
    )


__all__ = [
    "H2EmbeddingEntry",
    "H2EmbeddingIndex",
    "H2EmbeddingProfile",
    "H2CandidateSet",
    "H2QueryEmbedding",
    "MODEL_ID",
    "MODEL_REVISION",
    "PROFILE_VERSION",
    "QUERY_INSTRUCTION",
    "WEIGHTS_SHA256",
    "build_h2_candidate_set",
    "build_h2_embedding_index",
    "build_h2_query_embedding",
    "verify_h2_embedding_index",
]
