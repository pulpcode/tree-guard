"""Private persistence boundary for immutable H1 embedding indexes."""

from __future__ import annotations

from pathlib import Path

from treeguard.models import CanonicalTree
from treeguard.private_io import read_private_json, write_private_json
from treeguard.retrieval_hybrid import (
    HybridEmbeddingIndex,
    HybridRetrievalError,
    verify_hybrid_embedding_index,
)


MAX_PRIVATE_INDEX_BYTES = 64_000_000


def read_private_hybrid_embedding_index(
    path: Path,
    tree: CanonicalTree,
) -> HybridEmbeddingIndex:
    """Read, reconstruct, and bind one private index to a trusted tree."""

    try:
        payload = read_private_json(path, max_bytes=MAX_PRIVATE_INDEX_BYTES)
    except OSError:
        raise
    except (UnicodeError, ValueError):
        raise HybridRetrievalError("HYBRID_INDEX_ARTIFACT_INVALID") from None
    index = HybridEmbeddingIndex.from_dict(payload)
    verify_hybrid_embedding_index(index, tree)
    return index


def write_private_hybrid_embedding_index(
    path: Path,
    index: HybridEmbeddingIndex,
) -> bool:
    """Publish an immutable 0600 index without overwriting an existing path."""

    if not isinstance(path, Path) or not isinstance(index, HybridEmbeddingIndex):
        raise HybridRetrievalError("HYBRID_INDEX_ARTIFACT_INVALID")
    return write_private_json(path, index.to_dict())


__all__ = [
    "MAX_PRIVATE_INDEX_BYTES",
    "read_private_hybrid_embedding_index",
    "write_private_hybrid_embedding_index",
]
