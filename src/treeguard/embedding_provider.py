"""Controlled embedding side-effect boundary for the frozen H1 experiment."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Protocol

from treeguard.ai_review import BailianConfig
from treeguard.http_utils import build_isolated_opener
from treeguard.json_utils import StrictJSONError, strict_json_loads
from treeguard.retrieval_hybrid import (
    EMBEDDING_DIMENSIONS,
    MAX_DOCUMENT_CHARACTERS,
    MODEL_ID,
    HybridNodeDocument,
    HybridEmbeddingIndex,
    HybridQueryDocument,
    HybridQueryEmbedding,
    HybridRetrievalError,
    build_hybrid_embedding_index,
    build_hybrid_node_documents,
    build_hybrid_query_embedding,
    validate_hybrid_embedding_vector,
)
from treeguard.models import CanonicalTree


MAX_BATCH_SIZE = 10
MAX_RESPONSE_BYTES = 2_000_000
_RESPONSE_KEYS = {"data", "id", "model", "object", "usage"}
_DATA_KEYS = {"embedding", "index", "object"}
_USAGE_KEYS = {"prompt_tokens", "total_tokens"}


class EmbeddingProviderError(RuntimeError):
    """An embedding request failed without exposing request or response text."""

    def __init__(self, code: str, message: str = "embedding provider rejected") -> None:
        self.code = code
        super().__init__(message)


class HybridEmbeddingProvider(Protocol):
    """Replaceable transport contract used outside the deterministic core."""

    model_id: str
    dimensions: int

    def embed_batch(
        self,
        texts: tuple[str, ...],
        *,
        external_data_approved: bool = False,
    ) -> tuple[tuple[float, ...], ...]: ...


class BailianHybridEmbeddingProvider:
    """Call the frozen text-embedding-v4 H1 profile through Bailian."""

    model_id = MODEL_ID
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self, config: BailianConfig) -> None:
        if not isinstance(config, BailianConfig) or config.model != MODEL_ID:
            raise EmbeddingProviderError("BAILIAN_EMBEDDING_CONFIG_INVALID")
        self.config = config
        self._opener = build_isolated_opener()
        self.wire_attempt_count = 0

    @classmethod
    def from_env(cls) -> "BailianHybridEmbeddingProvider":
        """Reuse the hardened Bailian environment loader with the frozen H1 model."""

        return cls(replace(BailianConfig.from_env(), model=MODEL_ID))

    def embed_batch(
        self,
        texts: tuple[str, ...],
        *,
        external_data_approved: bool = False,
    ) -> tuple[tuple[float, ...], ...]:
        if external_data_approved is not True:
            raise EmbeddingProviderError("EXTERNAL_DATA_APPROVAL_REQUIRED")
        if (
            not isinstance(texts, tuple)
            or not 1 <= len(texts) <= MAX_BATCH_SIZE
            or any(not _valid_text(text) for text in texts)
        ):
            raise EmbeddingProviderError("BAILIAN_EMBEDDING_INPUT_INVALID")
        body = {
            "model": MODEL_ID,
            "input": list(texts),
            "dimensions": EMBEDDING_DIMENSIONS,
            "encoding_format": "float",
        }
        return _parse_embedding_response(self._post_json(body), len(texts))

    def _post_json(self, body: dict[str, Any]) -> Any:
        endpoint = self.config.base_url.rstrip("/") + "/embeddings"
        try:
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
        except (TypeError, ValueError, UnicodeError):
            raise EmbeddingProviderError("BAILIAN_EMBEDDING_REQUEST_INVALID") from None
        try:
            self.wire_attempt_count += 1
            with self._opener.open(
                request,
                timeout=float(self.config.timeout_seconds),
            ) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise EmbeddingProviderError(f"BAILIAN_EMBEDDING_HTTP_{exc.code}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise EmbeddingProviderError("BAILIAN_EMBEDDING_CONNECTION_FAILED") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise EmbeddingProviderError("BAILIAN_EMBEDDING_RESPONSE_TOO_LARGE")
        try:
            return strict_json_loads(raw)
        except (
            StrictJSONError,
            RecursionError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            raise EmbeddingProviderError("BAILIAN_EMBEDDING_RESPONSE_NOT_JSON") from exc


def embed_hybrid_documents(
    provider: HybridEmbeddingProvider,
    documents: tuple[HybridNodeDocument, ...],
    *,
    external_data_approved: bool = False,
) -> tuple[tuple[float, ...], ...]:
    """Embed canonical documents in stable, bounded batches without reordering."""

    _verify_h1_provider(provider)
    if (
        not isinstance(documents, tuple)
        or not documents
        or any(not isinstance(document, HybridNodeDocument) for document in documents)
    ):
        raise EmbeddingProviderError("HYBRID_EMBEDDING_PROVIDER_INVALID")
    vectors = []
    for offset in range(0, len(documents), MAX_BATCH_SIZE):
        batch = documents[offset : offset + MAX_BATCH_SIZE]
        result = provider.embed_batch(
            tuple(document.to_model_text() for document in batch),
            external_data_approved=external_data_approved,
        )
        if not isinstance(result, tuple) or len(result) != len(batch):
            raise EmbeddingProviderError("HYBRID_EMBEDDING_PROVIDER_RESPONSE_INVALID")
        try:
            vectors.extend(validate_hybrid_embedding_vector(vector) for vector in result)
        except HybridRetrievalError:
            raise EmbeddingProviderError("HYBRID_EMBEDDING_PROVIDER_RESPONSE_INVALID") from None
    return tuple(vectors)


def build_hybrid_index_with_provider(
    provider: HybridEmbeddingProvider,
    tree: CanonicalTree,
    *,
    external_data_approved: bool = False,
) -> HybridEmbeddingIndex:
    """Build a tree-bound H1 index while keeping transport outside the core."""

    documents = build_hybrid_node_documents(tree)
    vectors = embed_hybrid_documents(
        provider,
        documents,
        external_data_approved=external_data_approved,
    )
    return build_hybrid_embedding_index(
        tree,
        documents,
        {
            document.node_id: vector
            for document, vector in zip(documents, vectors, strict=True)
        },
    )


def build_hybrid_query_embedding_with_provider(
    provider: HybridEmbeddingProvider,
    document: HybridQueryDocument,
    *,
    external_data_approved: bool = False,
) -> HybridQueryEmbedding:
    """Embed one trusted query document and bind the result to its hash."""

    _verify_h1_provider(provider)
    if not isinstance(document, HybridQueryDocument):
        raise EmbeddingProviderError("HYBRID_QUERY_DOCUMENT_INVALID")
    result = provider.embed_batch(
        (document.to_model_text(),),
        external_data_approved=external_data_approved,
    )
    if not isinstance(result, tuple) or len(result) != 1:
        raise EmbeddingProviderError("HYBRID_EMBEDDING_PROVIDER_RESPONSE_INVALID")
    try:
        return build_hybrid_query_embedding(document, result[0])
    except HybridRetrievalError:
        raise EmbeddingProviderError("HYBRID_EMBEDDING_PROVIDER_RESPONSE_INVALID") from None


def _verify_h1_provider(provider: HybridEmbeddingProvider) -> None:
    if (
        getattr(provider, "model_id", None) != MODEL_ID
        or getattr(provider, "dimensions", None) != EMBEDDING_DIMENSIONS
        or not callable(getattr(provider, "embed_batch", None))
    ):
        raise EmbeddingProviderError("HYBRID_EMBEDDING_PROVIDER_INVALID")


def _valid_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= MAX_DOCUMENT_CHARACTERS
        and not any(
            ord(character) < 9
            or 10 < ord(character) < 32
            or ord(character) == 127
            for character in value
        )
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    )


def _parse_embedding_response(
    payload: Any,
    expected_count: int,
) -> tuple[tuple[float, ...], ...]:
    try:
        if not isinstance(payload, dict) or set(payload) != _RESPONSE_KEYS:
            raise ValueError
        if payload["model"] != MODEL_ID or payload["object"] != "list":
            raise ValueError
        if not isinstance(payload["id"], str) or not payload["id"]:
            raise ValueError
        usage = payload["usage"]
        if not isinstance(usage, dict) or set(usage) != _USAGE_KEYS:
            raise ValueError
        prompt_tokens = usage["prompt_tokens"]
        total_tokens = usage["total_tokens"]
        if (
            not isinstance(prompt_tokens, int)
            or isinstance(prompt_tokens, bool)
            or prompt_tokens < 0
            or not isinstance(total_tokens, int)
            or isinstance(total_tokens, bool)
            or total_tokens < prompt_tokens
        ):
            raise ValueError
        data = payload["data"]
        if not isinstance(data, list) or len(data) != expected_count:
            raise ValueError
        vectors = []
        for expected_index, item in enumerate(data):
            if (
                not isinstance(item, dict)
                or set(item) != _DATA_KEYS
                or item["object"] != "embedding"
                or not isinstance(item["index"], int)
                or isinstance(item["index"], bool)
                or item["index"] != expected_index
            ):
                raise ValueError
            vectors.append(validate_hybrid_embedding_vector(item["embedding"]))
        return tuple(vectors)
    except (HybridRetrievalError, KeyError, TypeError, ValueError):
        raise EmbeddingProviderError("BAILIAN_EMBEDDING_RESPONSE_INVALID") from None


__all__ = [
    "BailianHybridEmbeddingProvider",
    "EmbeddingProviderError",
    "HybridEmbeddingProvider",
    "build_hybrid_index_with_provider",
    "build_hybrid_query_embedding_with_provider",
    "embed_hybrid_documents",
]
