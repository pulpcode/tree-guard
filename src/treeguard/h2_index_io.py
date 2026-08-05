"""Private persistence boundary for immutable H2 local embedding indexes."""

from __future__ import annotations

from pathlib import Path

from treeguard.models import CanonicalTree
from treeguard.private_io import read_private_json, write_private_json
from treeguard.retrieval_hybrid import HybridRetrievalError
from treeguard.retrieval_hybrid_h2 import (
    H2EmbeddingIndex,
    H2EmbeddingProfile,
    verify_h2_embedding_index,
)


MAX_PRIVATE_H2_INDEX_BYTES = 64_000_000


def read_private_h2_embedding_index(
    path: Path,
    tree: CanonicalTree,
    profile: H2EmbeddingProfile,
) -> H2EmbeddingIndex:
    try:
        payload = read_private_json(path, max_bytes=MAX_PRIVATE_H2_INDEX_BYTES)
    except OSError:
        raise
    except (UnicodeError, ValueError):
        raise HybridRetrievalError("H2_INDEX_ARTIFACT_INVALID") from None
    index = H2EmbeddingIndex.from_dict(payload)
    verify_h2_embedding_index(index, tree, profile)
    return index


def write_private_h2_embedding_index(
    path: Path,
    index: H2EmbeddingIndex,
) -> bool:
    if not isinstance(path, Path) or not isinstance(index, H2EmbeddingIndex):
        raise HybridRetrievalError("H2_INDEX_ARTIFACT_INVALID")
    return write_private_json(path, index.to_dict())


__all__ = [
    "MAX_PRIVATE_H2_INDEX_BYTES",
    "read_private_h2_embedding_index",
    "write_private_h2_embedding_index",
]
